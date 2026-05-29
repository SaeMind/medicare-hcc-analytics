"""
CMS-HCC V28 Grouper
===================
Maps ICD-10-CM diagnosis codes to HCC condition categories, applies
V28 hierarchy rules, and resolves interaction terms.

Usage:
    from src.hcc_v28_grouper import HCCGrouper
    grouper = HCCGrouper()
    hccs = grouper.map_diagnoses(["E1140", "N185", "I5020"])
    # Returns: {35, 311, 224}  (after hierarchy)
"""

import logging
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from hcc_v28_coefficients import (
    HCC_COEFFICIENTS,
    HCC_HIERARCHY,
    ICD10_TO_HCC,
    INTERACTION_COEFFICIENTS,
)

logger = logging.getLogger(__name__)


class HCCGrouper:
    """
    CMS-HCC V28 diagnosis-to-HCC grouper.

    Implements:
      1. ICD-10-CM → raw HCC mapping
      2. V28 hierarchy pruning (drop superseded HCCs)
      3. Interaction term detection
      4. Frailty flag detection
    """

    def __init__(self):
        self._icd_map = ICD10_TO_HCC
        self._hierarchy = HCC_HIERARCHY
        self._interactions = INTERACTION_COEFFICIENTS
        self._valid_hccs = set(HCC_COEFFICIENTS.keys())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def map_diagnoses(
        self,
        icd_codes: List[str],
        strip_dots: bool = True,
    ) -> Set[int]:
        """
        Map a list of ICD-10-CM codes to a set of HCCs after hierarchy.

        Args:
            icd_codes:  Raw ICD-10-CM codes (e.g. ["E11.40", "N18.5"])
            strip_dots: If True, remove dots before lookup (standard format)

        Returns:
            Set of integer HCC codes after hierarchy pruning.
        """
        cleaned = [self._clean_icd(c, strip_dots) for c in icd_codes]
        raw_hccs = self._icd_to_raw_hccs(cleaned)
        pruned = self._apply_hierarchy(raw_hccs)
        return pruned

    def get_interactions(
        self,
        hccs: Set[int],
        is_disabled: bool = False,
    ) -> Dict[str, float]:
        """
        Return applicable interaction terms and their coefficients.

        Args:
            hccs:        Set of HCCs after hierarchy pruning.
            is_disabled: Whether the member is in a disabled segment.

        Returns:
            Dict mapping interaction key → coefficient.
        """
        applicable: Dict[str, float] = {}
        hcc_set = set(hccs)

        for key, coeff in self._interactions.items():
            if key.startswith("DISABLED_"):
                if not is_disabled:
                    continue
                hcc_part = int(key.split("HCC")[1])
                if hcc_part in hcc_set:
                    applicable[key] = coeff
            else:
                parts = key.split("_")
                hcc_ids = [int(p.replace("HCC", "")) for p in parts]
                if all(h in hcc_set for h in hcc_ids):
                    applicable[key] = coeff

        return applicable

    def get_frailty_flag(self, hccs: Set[int]) -> bool:
        """Return True if any frailty-indicating HCC is present (V28 new)."""
        from hcc_v28_coefficients import FRAILTY_HCC_INDICATORS
        return bool(hccs & set(FRAILTY_HCC_INDICATORS))

    def describe_hccs(self, hccs: Set[int]) -> Dict[int, float]:
        """Return HCC → coefficient mapping for a given HCC set."""
        return {h: HCC_COEFFICIENTS[h] for h in hccs if h in HCC_COEFFICIENTS}

    def get_unmapped_codes(self, icd_codes: List[str]) -> List[str]:
        """Return ICD codes that had no V28 HCC mapping."""
        cleaned = [self._clean_icd(c) for c in icd_codes]
        return [c for c in cleaned if c not in self._icd_map]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_icd(code: str, strip_dots: bool = True) -> str:
        code = code.strip().upper()
        if strip_dots:
            code = code.replace(".", "")
        return code

    def _icd_to_raw_hccs(self, cleaned_codes: List[str]) -> Set[int]:
        """Map cleaned ICD codes to raw HCC set (pre-hierarchy)."""
        raw: Set[int] = set()
        for code in cleaned_codes:
            hcc = self._icd_map.get(code)
            if hcc is not None and hcc in self._valid_hccs:
                raw.add(hcc)
            else:
                # Attempt 3-char prefix lookup for catch-all mappings
                prefix = code[:3]
                hcc = self._icd_map.get(prefix)
                if hcc is not None and hcc in self._valid_hccs:
                    raw.add(hcc)
        return raw

    def _apply_hierarchy(self, raw_hccs: Set[int]) -> Set[int]:
        """
        Apply V28 hierarchy rules.

        For each disease group, if a higher-severity HCC is present,
        remove all HCCs it supersedes.
        """
        to_remove: Set[int] = set()
        for higher_hcc, superseded in self._hierarchy.items():
            if higher_hcc in raw_hccs:
                for lower in superseded:
                    if lower in raw_hccs:
                        to_remove.add(lower)
                        logger.debug(
                            "Hierarchy: HCC %d supersedes HCC %d",
                            higher_hcc, lower
                        )
        return raw_hccs - to_remove


class DiagnosisRecord:
    """
    Lightweight container for a single member's diagnosis history.
    Validates ICD format and deduplicates across service dates.
    """

    def __init__(self, member_id: str):
        self.member_id = member_id
        self._codes: Set[str] = set()
        self._raw_entries: List[Tuple[str, Optional[str]]] = []  # (code, date)

    def add_diagnosis(self, icd_code: str, service_date: Optional[str] = None):
        """Add a diagnosis code. Deduplicates by code (date preserved for audit)."""
        cleaned = icd_code.strip().upper().replace(".", "")
        if self._is_valid_icd10(cleaned):
            self._codes.add(cleaned)
            self._raw_entries.append((cleaned, service_date))
        else:
            logger.warning("Invalid ICD-10 format skipped: %s", icd_code)

    def get_codes(self) -> List[str]:
        return list(self._codes)

    @staticmethod
    def _is_valid_icd10(code: str) -> bool:
        """Basic structural validation: 3–7 alphanumeric chars."""
        if not code:
            return False
        if not (3 <= len(code) <= 7):
            return False
        if not code[0].isalpha():
            return False
        if not code[1:3].isdigit():
            return False
        return True


class BatchGrouper:
    """
    Vectorized grouper for processing large claims populations.
    Processes members in configurable batches for memory efficiency.
    """

    def __init__(self, batch_size: int = 10_000):
        self.grouper = HCCGrouper()
        self.batch_size = batch_size
        self._stats: Dict[str, int] = {
            "total_members": 0,
            "total_diagnoses": 0,
            "unmapped_codes": 0,
            "members_with_hccs": 0,
        }

    def process_claims_df(self, claims_df) -> "pd.DataFrame":
        """
        Process a claims DataFrame and return per-member HCC summary.

        Expected input columns:
            member_id, icd_code, service_date (optional)

        Returns DataFrame with columns:
            member_id, hcc_list, hcc_count, has_hccs
        """
        import pandas as pd

        results = []
        grouped = claims_df.groupby("member_id")

        for i, (member_id, member_claims) in enumerate(grouped):
            if i % self.batch_size == 0 and i > 0:
                logger.info("Processed %d members...", i)

            icd_codes = member_claims["icd_code"].dropna().tolist()
            hccs = self.grouper.map_diagnoses(icd_codes)

            results.append({
                "member_id": member_id,
                "hcc_list": sorted(hccs),
                "hcc_count": len(hccs),
                "has_hccs": len(hccs) > 0,
            })

            self._stats["total_members"] += 1
            self._stats["total_diagnoses"] += len(icd_codes)
            if hccs:
                self._stats["members_with_hccs"] += 1

        return pd.DataFrame(results)

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)
