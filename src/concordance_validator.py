"""
CMS Concordance Validator
==========================
Measures how closely the V28 pipeline's RAF scores align with
CMS-published benchmark distributions and RADV audit standards.

CMS defines concordance as: for each member, the pipeline-assigned
HCC set matches the expected HCC set within acceptable tolerance.

Metrics computed:
  1. HCC-level concordance: % of HCC assignments matching expected
  2. RAF-level concordance: % of members within ±5% of expected RAF
  3. Population-level concordance: mean RAF within ±2% of CMS benchmark
  4. RADV-style error rate: over-coding and under-coding rates

Target: ≥94% concordance on HCC assignment (matches project specification)

Usage:
    from src.concordance_validator import ConcordanceValidator
    validator = ConcordanceValidator()
    report = validator.validate(pipeline_results, reference_results)
    print(report.summary())
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class ConcordanceReport:
    """Full concordance validation report."""

    # HCC-level metrics
    hcc_concordance_rate: float       # % members with identical HCC sets
    hcc_precision: float              # TP / (TP + FP)
    hcc_recall: float                 # TP / (TP + FN)
    hcc_f1: float                     # Harmonic mean of precision and recall

    # RAF-level metrics
    raf_within_5pct: float            # % members with RAF within ±5% of reference
    raf_within_2pct: float            # % members with RAF within ±2% of reference
    mean_absolute_raf_error: float    # Mean |pipeline_RAF - reference_RAF|
    mean_raf_error: float             # Signed: positive = over-coding

    # Population-level metrics
    pipeline_mean_raf: float
    reference_mean_raf: float
    population_raf_delta: float       # pipeline - reference (%)

    # RADV-style error rates
    overcoding_rate: float            # % members with pipeline RAF > reference + 5%
    undercoding_rate: float           # % members with pipeline RAF < reference - 5%
    error_hcc_count: int              # Total HCC assignment errors

    # Counts
    total_members: int
    members_with_hccs: int
    total_hccs_pipeline: int
    total_hccs_reference: int

    # Per-HCC concordance
    hcc_concordance_detail: Dict[int, dict] = field(default_factory=dict)

    # V28 vs V24 comparison (if reference is V24)
    v24_v28_raf_delta_mean: Optional[float] = None

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "CMS-HCC V28 CONCORDANCE VALIDATION REPORT",
            "=" * 60,
            "",
            "HCC ASSIGNMENT CONCORDANCE",
            f"  Overall HCC Concordance Rate:  {self.hcc_concordance_rate:.1%}",
            f"  HCC Precision:                 {self.hcc_precision:.4f}",
            f"  HCC Recall:                    {self.hcc_recall:.4f}",
            f"  HCC F1-Score:                  {self.hcc_f1:.4f}",
            "",
            "RAF ACCURACY",
            f"  Members within ±5% RAF:        {self.raf_within_5pct:.1%}",
            f"  Members within ±2% RAF:        {self.raf_within_2pct:.1%}",
            f"  Mean Absolute RAF Error:       {self.mean_absolute_raf_error:.4f}",
            f"  Mean Signed RAF Error:         {self.mean_raf_error:+.4f}",
            "",
            "POPULATION BENCHMARKS",
            f"  Pipeline Mean RAF:             {self.pipeline_mean_raf:.4f}",
            f"  Reference Mean RAF:            {self.reference_mean_raf:.4f}",
            f"  Population RAF Delta:          {self.population_raf_delta:+.2f}%",
            "",
            "RADV-STYLE ERROR RATES",
            f"  Over-coding Rate:              {self.overcoding_rate:.2%}",
            f"  Under-coding Rate:             {self.undercoding_rate:.2%}",
            f"  Total HCC Assignment Errors:   {self.error_hcc_count:,}",
            "",
            "COUNTS",
            f"  Total Members:                 {self.total_members:,}",
            f"  Members with ≥1 HCC:           {self.members_with_hccs:,}",
            f"  Total Pipeline HCCs:           {self.total_hccs_pipeline:,}",
            f"  Total Reference HCCs:          {self.total_hccs_reference:,}",
            "=" * 60,
        ]
        if self.v24_v28_raf_delta_mean is not None:
            lines.insert(-1, f"  V24→V28 Mean RAF Delta:        {self.v24_v28_raf_delta_mean:+.4f}")
        return "\n".join(lines)

    def passes_cms_threshold(self, threshold: float = 0.94) -> bool:
        """Return True if HCC concordance meets or exceeds CMS threshold."""
        return self.hcc_concordance_rate >= threshold

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()
                if k != "hcc_concordance_detail"}


class ConcordanceValidator:
    """
    Validates CMS-HCC V28 pipeline outputs against a reference standard.

    Reference standard options:
      1. CMS-published RADV audit results (gold standard)
      2. V24 pipeline outputs (for V24→V28 migration comparison)
      3. Synthetic reference with known ground truth (for unit testing)
    """

    def __init__(self, raf_tolerance: float = 0.05):
        """
        Args:
            raf_tolerance: Maximum acceptable RAF deviation (default 5% = 0.05)
        """
        self.raf_tolerance = raf_tolerance

    # ------------------------------------------------------------------
    # Primary Validation
    # ------------------------------------------------------------------

    def validate(
        self,
        pipeline_df: pd.DataFrame,
        reference_df: pd.DataFrame,
        member_id_col: str = "member_id",
    ) -> ConcordanceReport:
        """
        Run full concordance validation.

        Args:
            pipeline_df:   Output from RAF pipeline. Must have columns:
                           member_id, payment_raf, hcc_list
            reference_df:  Reference standard. Same columns required.
            member_id_col: Column name for member ID join key.

        Returns:
            ConcordanceReport with all metrics.
        """
        # Join on member_id
        merged = pipeline_df.merge(
            reference_df,
            on=member_id_col,
            suffixes=("_pipeline", "_ref"),
        )

        if len(merged) == 0:
            raise ValueError("No matching members between pipeline and reference sets.")

        logger.info("Validating %d matched members", len(merged))

        # Parse HCC lists
        pipeline_hccs = merged["hcc_list_pipeline"].apply(self._parse_hcc_list)
        reference_hccs = merged["hcc_list_ref"].apply(self._parse_hcc_list)

        # Compute metrics
        hcc_metrics = self._compute_hcc_metrics(pipeline_hccs, reference_hccs)
        raf_metrics = self._compute_raf_metrics(
            merged["payment_raf_pipeline"].values,
            merged["payment_raf_ref"].values,
        )
        population_metrics = self._compute_population_metrics(
            merged["payment_raf_pipeline"].values,
            merged["payment_raf_ref"].values,
        )
        per_hcc_detail = self._compute_per_hcc_concordance(pipeline_hccs, reference_hccs)

        return ConcordanceReport(
            # HCC
            hcc_concordance_rate=hcc_metrics["concordance_rate"],
            hcc_precision=hcc_metrics["precision"],
            hcc_recall=hcc_metrics["recall"],
            hcc_f1=hcc_metrics["f1"],
            # RAF
            raf_within_5pct=raf_metrics["within_5pct"],
            raf_within_2pct=raf_metrics["within_2pct"],
            mean_absolute_raf_error=raf_metrics["mae"],
            mean_raf_error=raf_metrics["me"],
            # Population
            pipeline_mean_raf=population_metrics["pipeline_mean"],
            reference_mean_raf=population_metrics["reference_mean"],
            population_raf_delta=population_metrics["delta_pct"],
            # RADV
            overcoding_rate=raf_metrics["overcoding_rate"],
            undercoding_rate=raf_metrics["undercoding_rate"],
            error_hcc_count=hcc_metrics["total_errors"],
            # Counts
            total_members=len(merged),
            members_with_hccs=int((pipeline_hccs.apply(len) > 0).sum()),
            total_hccs_pipeline=int(pipeline_hccs.apply(len).sum()),
            total_hccs_reference=int(reference_hccs.apply(len).sum()),
            # Detail
            hcc_concordance_detail=per_hcc_detail,
        )

    # ------------------------------------------------------------------
    # Metric Computation
    # ------------------------------------------------------------------

    def _compute_hcc_metrics(
        self,
        pipeline_series: pd.Series,
        reference_series: pd.Series,
    ) -> dict:
        concordant = 0
        total_tp = total_fp = total_fn = total_errors = 0

        for p_hccs, r_hccs in zip(pipeline_series, reference_series):
            if p_hccs == r_hccs:
                concordant += 1
            tp = len(p_hccs & r_hccs)
            fp = len(p_hccs - r_hccs)
            fn = len(r_hccs - p_hccs)
            total_tp += tp
            total_fp += fp
            total_fn += fn
            total_errors += fp + fn

        n = len(pipeline_series)
        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) > 0 else 0.0)

        return {
            "concordance_rate": concordant / n,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "total_errors": total_errors,
        }

    def _compute_raf_metrics(
        self,
        pipeline_rafs: np.ndarray,
        reference_rafs: np.ndarray,
    ) -> dict:
        errors = pipeline_rafs - reference_rafs
        rel_errors = errors / np.where(reference_rafs > 0, reference_rafs, 1.0)

        within_5pct = float(np.mean(np.abs(rel_errors) <= 0.05))
        within_2pct = float(np.mean(np.abs(rel_errors) <= 0.02))
        mae = float(np.mean(np.abs(errors)))
        me = float(np.mean(errors))
        overcoding_rate = float(np.mean(rel_errors > self.raf_tolerance))
        undercoding_rate = float(np.mean(rel_errors < -self.raf_tolerance))

        return {
            "within_5pct": within_5pct,
            "within_2pct": within_2pct,
            "mae": mae,
            "me": me,
            "overcoding_rate": overcoding_rate,
            "undercoding_rate": undercoding_rate,
        }

    def _compute_population_metrics(
        self,
        pipeline_rafs: np.ndarray,
        reference_rafs: np.ndarray,
    ) -> dict:
        p_mean = float(np.mean(pipeline_rafs))
        r_mean = float(np.mean(reference_rafs))
        delta_pct = (p_mean - r_mean) / r_mean * 100 if r_mean > 0 else 0.0
        return {
            "pipeline_mean": p_mean,
            "reference_mean": r_mean,
            "delta_pct": delta_pct,
        }

    def _compute_per_hcc_concordance(
        self,
        pipeline_series: pd.Series,
        reference_series: pd.Series,
    ) -> Dict[int, dict]:
        """Compute concordance statistics for each individual HCC."""
        from collections import defaultdict
        stats: Dict[int, dict] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

        for p_hccs, r_hccs in zip(pipeline_series, reference_series):
            for h in p_hccs & r_hccs:
                stats[h]["tp"] += 1
            for h in p_hccs - r_hccs:
                stats[h]["fp"] += 1
            for h in r_hccs - p_hccs:
                stats[h]["fn"] += 1

        result = {}
        for hcc, s in stats.items():
            tp, fp, fn = s["tp"], s["fp"], s["fn"]
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            result[hcc] = {
                "tp": tp, "fp": fp, "fn": fn,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
            }
        return result

    @staticmethod
    def _parse_hcc_list(val) -> Set[int]:
        """Parse HCC list from various storage formats."""
        if isinstance(val, (list, set)):
            return set(int(h) for h in val)
        if isinstance(val, str):
            val = val.strip("[]").replace(" ", "")
            if not val:
                return set()
            return set(int(h) for h in val.split(","))
        return set()


class V24ToV28MigrationAnalyzer:
    """
    Compares V24 vs V28 RAF scores to quantify the impact of the model upgrade.
    V28 introduced:
      - Revised HCC list (removed some HCCs, added new ones)
      - New interaction terms
      - Frailty adjustment
      - Recalibrated coefficients
    Expected population-level impact: V28 RAF typically 2–4% higher than V24
    for a standard MA population.
    """

    def analyze(
        self,
        v24_results: pd.DataFrame,
        v28_results: pd.DataFrame,
    ) -> dict:
        """
        Compare V24 vs V28 RAF distributions.

        Both DataFrames must have columns: member_id, payment_raf, hcc_list
        """
        merged = v24_results.merge(
            v28_results, on="member_id", suffixes=("_v24", "_v28")
        )
        delta = merged["payment_raf_v28"] - merged["payment_raf_v24"]
        pct_change = delta / merged["payment_raf_v24"].replace(0, np.nan) * 100

        return {
            "n_members": len(merged),
            "v24_mean_raf": round(float(merged["payment_raf_v24"].mean()), 4),
            "v28_mean_raf": round(float(merged["payment_raf_v28"].mean()), 4),
            "mean_delta": round(float(delta.mean()), 4),
            "mean_pct_change": round(float(pct_change.mean()), 2),
            "pct_members_higher_v28": round(float((delta > 0).mean() * 100), 1),
            "pct_members_lower_v28": round(float((delta < 0).mean() * 100), 1),
            "pct_members_unchanged": round(float((delta == 0).mean() * 100), 1),
        }
