"""
Unit Tests — CMS-HCC V28 Pipeline
===================================
Tests cover:
  - HCC grouper: ICD mapping, hierarchy, interactions
  - RAF calculator: demographic scoring, HCC scoring, normalization
  - Concordance validator: metric computation, threshold checks
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hcc_v28_grouper import HCCGrouper, DiagnosisRecord
from raf_calculator import RAFCalculator, MemberProfile, compute_raf_distribution
from concordance_validator import ConcordanceValidator


class TestHCCGrouper(unittest.TestCase):

    def setUp(self):
        self.grouper = HCCGrouper()

    def test_basic_icd_mapping(self):
        """Known ICD codes map to expected HCCs."""
        hccs = self.grouper.map_diagnoses(["E1140"])
        self.assertIn(35, hccs)  # Diabetes with chronic complications

    def test_dot_stripping(self):
        """ICD codes with dots are normalized correctly."""
        hccs_with = self.grouper.map_diagnoses(["E11.40"])
        hccs_without = self.grouper.map_diagnoses(["E1140"])
        self.assertEqual(hccs_with, hccs_without)

    def test_hierarchy_pruning(self):
        """HCC 311 (CKD5) supersedes HCC 312 (CKD4) and HCC 313 (CKD3)."""
        hccs = self.grouper.map_diagnoses(["N185", "N184", "N183"])
        self.assertIn(311, hccs)
        self.assertNotIn(312, hccs)
        self.assertNotIn(313, hccs)

    def test_cancer_hierarchy(self):
        """Metastatic cancer (HCC 22) supersedes lower cancers."""
        hccs = self.grouper.map_diagnoses(["C780", "C340", "C180"])
        self.assertIn(22, hccs)
        self.assertNotIn(23, hccs)
        self.assertNotIn(24, hccs)

    def test_no_hierarchy_when_single(self):
        """Single HCC assignment — no hierarchy pruning needed."""
        hccs = self.grouper.map_diagnoses(["N183"])
        self.assertEqual(hccs, {313})

    def test_interaction_detection_diabetes_ckd(self):
        """Diabetes + CKD5 interaction is detected correctly."""
        hccs = {35, 311}
        interactions = self.grouper.get_interactions(hccs, is_disabled=False)
        self.assertIn("HCC35_HCC311", interactions)
        self.assertAlmostEqual(interactions["HCC35_HCC311"], 0.249)

    def test_interaction_not_present_without_both(self):
        """Interaction not returned if only one condition present."""
        hccs = {35}  # Diabetes only, no CKD
        interactions = self.grouper.get_interactions(hccs)
        self.assertNotIn("HCC35_HCC311", interactions)

    def test_disabled_interaction(self):
        """Disabled + CHF interaction only fires for disabled members."""
        hccs = {85}
        interactions_disabled = self.grouper.get_interactions(hccs, is_disabled=True)
        interactions_able = self.grouper.get_interactions(hccs, is_disabled=False)
        self.assertIn("DISABLED_HCC85", interactions_disabled)
        self.assertNotIn("DISABLED_HCC85", interactions_able)

    def test_frailty_flag(self):
        """Frailty HCCs trigger frailty flag."""
        self.assertTrue(self.grouper.get_frailty_flag({72}))    # Quadriplegia
        self.assertTrue(self.grouper.get_frailty_flag({379}))   # Pressure ulcer
        self.assertFalse(self.grouper.get_frailty_flag({37}))   # Diabetes only

    def test_empty_codes(self):
        """Empty code list returns empty HCC set."""
        self.assertEqual(self.grouper.map_diagnoses([]), set())

    def test_unmapped_code(self):
        """Codes not in mapping return empty set and are flagged."""
        hccs = self.grouper.map_diagnoses(["Z99999"])
        self.assertEqual(hccs, set())
        unmapped = self.grouper.get_unmapped_codes(["Z99999"])
        self.assertIn("Z99999", unmapped)

    def test_case_insensitive(self):
        """ICD codes are normalized to uppercase."""
        hccs_lower = self.grouper.map_diagnoses(["e1140"])
        hccs_upper = self.grouper.map_diagnoses(["E1140"])
        self.assertEqual(hccs_lower, hccs_upper)


class TestDiagnosisRecord(unittest.TestCase):

    def test_deduplication(self):
        """Same ICD code added multiple times is stored once."""
        rec = DiagnosisRecord("M001")
        rec.add_diagnosis("E1140")
        rec.add_diagnosis("E1140")
        rec.add_diagnosis("E1140", service_date="2023-03-15")
        self.assertEqual(len(rec.get_codes()), 1)

    def test_invalid_code_rejected(self):
        """Codes not matching ICD-10 structure are silently dropped."""
        rec = DiagnosisRecord("M002")
        rec.add_diagnosis("INVALID_CODE")
        rec.add_diagnosis("12345")
        self.assertEqual(len(rec.get_codes()), 0)

    def test_valid_code_accepted(self):
        rec = DiagnosisRecord("M003")
        rec.add_diagnosis("N185")
        self.assertIn("N185", rec.get_codes())


class TestRAFCalculator(unittest.TestCase):

    def setUp(self):
        self.calc = RAFCalculator()

    def test_demographic_only_no_hccs(self):
        """Member with no HCCs has RAF equal to demographic score."""
        profile = MemberProfile(
            member_id="M001", age=72, sex="M", segment="CNA", hccs=set()
        )
        result = self.calc.calculate(profile)
        self.assertAlmostEqual(result.raw_raf, result.demographic_score, places=4)
        self.assertGreater(result.payment_raf, 0)

    def test_raf_increases_with_hccs(self):
        """Adding HCCs increases RAF score."""
        base = MemberProfile("M001", 72, "M", "CNA", hccs=set())
        with_hcc = MemberProfile("M001", 72, "M", "CNA", hccs={83})

        base_result = self.calc.calculate(base)
        hcc_result = self.calc.calculate(with_hcc)
        self.assertGreater(hcc_result.payment_raf, base_result.payment_raf)

    def test_interaction_adds_to_raf(self):
        """HCC interactions add incremental RAF beyond individual HCCs."""
        without_interaction = MemberProfile("M001", 72, "M", "CNA", hccs={35})
        with_interaction = MemberProfile("M001", 72, "M", "CNA", hccs={35, 311})

        r1 = self.calc.calculate(without_interaction)
        r2 = self.calc.calculate(with_interaction)
        self.assertGreater(r2.payment_raf, r1.payment_raf)
        self.assertIn("HCC35_HCC311", r2.interaction_scores)

    def test_frailty_only_institutional(self):
        """Frailty coefficient applies only to institutional members."""
        frailty_hcc = {379}
        community = MemberProfile("M001", 80, "F", "CNA",
                                  hccs=frailty_hcc, is_institutional=False)
        institutional = MemberProfile("M002", 80, "F", "INS",
                                      hccs=frailty_hcc, is_institutional=True)
        r_comm = self.calc.calculate(community)
        r_inst = self.calc.calculate(institutional)
        self.assertEqual(r_comm.frailty_score, 0.0)
        self.assertGreater(r_inst.frailty_score, 0.0)

    def test_age_band_boundaries(self):
        """Age band transitions produce correct demographic keys."""
        test_cases = [
            (34, "M", "M_LT35"),
            (35, "M", "M_35_44"),
            (65, "F", "F_65_69"),
            (95, "F", "F_GE95"),
        ]
        for age, sex, expected_key in test_cases:
            profile = MemberProfile("M_test", age, sex, "CNA", hccs=set())
            result = self.calc.calculate(profile)
            self.assertEqual(result.demographic_key, expected_key,
                             f"Age {age} sex {sex}: expected {expected_key}")

    def test_normalization_applied(self):
        """Payment RAF = raw RAF / normalization factor."""
        from hcc_v28_coefficients import CMS_NORMALIZATION_FACTOR
        profile = MemberProfile("M001", 72, "M", "CNA", hccs={83, 312})
        result = self.calc.calculate(profile)
        expected = result.raw_raf / CMS_NORMALIZATION_FACTOR
        self.assertAlmostEqual(result.payment_raf, expected, places=6)

    def test_icd_auto_grouping(self):
        """When icd_codes provided and hccs empty, grouper runs automatically."""
        profile = MemberProfile(
            member_id="M001", age=72, sex="M", segment="CNA",
            hccs=set(), icd_codes=["E1140", "N185"]
        )
        result = self.calc.calculate(profile)
        self.assertGreater(result.hcc_count, 0)

    def test_raf_distribution_stats(self):
        """RAF distribution returns expected keys."""
        profiles = [
            MemberProfile(f"M{i}", 70 + i % 20, "F", "CNA", hccs=set())
            for i in range(100)
        ]
        results = self.calc.calculate_batch(profiles)
        dist = compute_raf_distribution(results)
        for key in ["count", "mean", "median", "stdev", "min", "max", "p10", "p90"]:
            self.assertIn(key, dist)
        self.assertEqual(dist["count"], 100)


class TestConcordanceValidator(unittest.TestCase):

    def setUp(self):
        self.validator = ConcordanceValidator(raf_tolerance=0.05)
        self._build_test_data()

    def _build_test_data(self):
        import pandas as pd
        n = 1000
        # Perfect concordance baseline
        self.perfect_pipeline = pd.DataFrame({
            "member_id": [f"M{i}" for i in range(n)],
            "hcc_list": [[35, 312]] * 500 + [[]] * 500,
            "payment_raf": [1.45] * 500 + [0.40] * 500,
        })
        self.perfect_reference = self.perfect_pipeline.copy()

        # 6% error pipeline
        self.imperfect_pipeline = self.perfect_pipeline.copy()
        imperfect_hccs = self.imperfect_pipeline["hcc_list"].copy()
        for i in range(60):  # 6% error
            imperfect_hccs.iloc[i] = [35]  # Missing HCC 312
        self.imperfect_pipeline["hcc_list"] = imperfect_hccs
        self.imperfect_pipeline.loc[:59, "payment_raf"] = 1.20

    def test_perfect_concordance(self):
        """Identical pipeline and reference → 100% concordance."""
        import pandas as pd
        report = self.validator.validate(
            self.perfect_pipeline,
            self.perfect_reference
        )
        self.assertAlmostEqual(report.hcc_concordance_rate, 1.0, places=4)

    def test_imperfect_concordance_near_94pct(self):
        """6% error rate → concordance near 94%."""
        report = self.validator.validate(
            self.imperfect_pipeline,
            self.perfect_reference
        )
        self.assertGreater(report.hcc_concordance_rate, 0.90)
        self.assertLess(report.hcc_concordance_rate, 1.0)

    def test_passes_cms_threshold(self):
        """94% concordance threshold check works correctly."""
        report = self.validator.validate(
            self.perfect_pipeline,
            self.perfect_reference
        )
        self.assertTrue(report.passes_cms_threshold(0.94))

    def test_report_has_all_keys(self):
        """Concordance report to_dict contains expected keys."""
        report = self.validator.validate(
            self.perfect_pipeline,
            self.perfect_reference
        )
        d = report.to_dict()
        expected_keys = [
            "hcc_concordance_rate", "hcc_precision", "hcc_recall", "hcc_f1",
            "raf_within_5pct", "mean_absolute_raf_error",
            "overcoding_rate", "undercoding_rate", "total_members",
        ]
        for key in expected_keys:
            self.assertIn(key, d, f"Missing key: {key}")

    def test_empty_hcc_members(self):
        """Members with no HCCs are handled without errors."""
        import pandas as pd
        empty_df = pd.DataFrame({
            "member_id": ["M0", "M1", "M2"],
            "hcc_list": [[], [], []],
            "payment_raf": [0.40, 0.45, 0.38],
        })
        report = self.validator.validate(empty_df, empty_df.copy())
        self.assertEqual(report.hcc_concordance_rate, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
