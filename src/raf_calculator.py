"""
CMS-HCC V28 Risk Adjustment Factor (RAF) Calculator
====================================================
Computes member-level RAF scores from demographic factors,
HCC condition categories, and interaction terms.

RAF Score = demographic_score + sum(HCC_scores) + sum(interaction_scores)
            + frailty_adjustment (if applicable)

Then normalized: payment_RAF = raw_RAF / CMS_NORMALIZATION_FACTOR

Usage:
    from src.raf_calculator import RAFCalculator, MemberProfile
    calc = RAFCalculator()
    profile = MemberProfile(
        member_id="M001",
        age=72,
        sex="M",
        segment="CNA",
        hccs={83, 312},
        is_disabled=False,
    )
    result = calc.calculate(profile)
    print(result.payment_raf)  # e.g. 1.423
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Set

from hcc_v28_coefficients import (
    CMS_NORMALIZATION_FACTOR,
    DEMOGRAPHIC_COEFFICIENTS,
    FRAILTY_COEFFICIENT,
    HCC_COEFFICIENTS,
    INTERACTION_COEFFICIENTS,
)
from hcc_v28_grouper import HCCGrouper

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class MemberProfile:
    """Input profile for a single Medicare beneficiary."""
    member_id: str
    age: int
    sex: str                     # "M" or "F"
    segment: str = "CNA"         # CNA, CND, CFA, INS
    hccs: Set[int] = field(default_factory=set)
    is_disabled: bool = False
    is_originally_disabled: bool = False
    is_institutional: bool = False
    icd_codes: Optional[List[str]] = None  # If provided, grouper runs automatically


@dataclass
class RAFResult:
    """Output of RAF calculation for a single member."""
    member_id: str
    demographic_score: float
    hcc_scores: Dict[int, float]          # HCC → coefficient
    interaction_scores: Dict[str, float]  # interaction key → coefficient
    frailty_score: float
    raw_raf: float
    payment_raf: float                    # raw_raf / normalization_factor
    hcc_list: List[int]
    hcc_count: int
    demographic_key: str
    has_frailty: bool

    @property
    def condition_score(self) -> float:
        return sum(self.hcc_scores.values())

    @property
    def interaction_total(self) -> float:
        return sum(self.interaction_scores.values())

    def to_dict(self) -> dict:
        return {
            "member_id": self.member_id,
            "demographic_key": self.demographic_key,
            "demographic_score": round(self.demographic_score, 4),
            "condition_score": round(self.condition_score, 4),
            "interaction_score": round(self.interaction_total, 4),
            "frailty_score": round(self.frailty_score, 4),
            "raw_raf": round(self.raw_raf, 4),
            "payment_raf": round(self.payment_raf, 4),
            "hcc_list": self.hcc_list,
            "hcc_count": self.hcc_count,
            "has_frailty": self.has_frailty,
        }


# ---------------------------------------------------------------------------
# RAF Calculator
# ---------------------------------------------------------------------------

class RAFCalculator:
    """
    Computes CMS-HCC V28 Risk Adjustment Factor scores.

    Implements:
      - Demographic score (age/sex interaction bands)
      - HCC condition scores (V28 coefficients)
      - Interaction term scores
      - V28 frailty adjustment
      - CMS normalization
    """

    def __init__(self):
        self._grouper = HCCGrouper()
        self._demo_coeffs = DEMOGRAPHIC_COEFFICIENTS
        self._hcc_coeffs = HCC_COEFFICIENTS
        self._norm_factor = CMS_NORMALIZATION_FACTOR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate(self, profile: MemberProfile) -> RAFResult:
        """
        Calculate RAF for a single member.

        If profile.icd_codes is provided and profile.hccs is empty,
        the grouper runs automatically.
        """
        # Auto-group ICD codes if HCCs not pre-computed
        hccs = set(profile.hccs)
        if not hccs and profile.icd_codes:
            hccs = self._grouper.map_diagnoses(profile.icd_codes)

        demo_key = self._get_demographic_key(profile)
        demo_score = self._demo_coeffs.get(demo_key, 0.0)

        # Originally disabled add-on
        if profile.is_originally_disabled:
            orig_dis_key = (
                "OriginallyDisabled_Male"
                if profile.sex.upper() == "M"
                else "OriginallyDisabled_Female"
            )
            demo_score += self._demo_coeffs.get(orig_dis_key, 0.0)

        # HCC scores
        hcc_scores = {h: self._hcc_coeffs[h] for h in hccs if h in self._hcc_coeffs}

        # Interaction scores
        interaction_scores = self._grouper.get_interactions(
            hccs, is_disabled=profile.is_disabled
        )

        # Frailty (V28 new)
        has_frailty = self._grouper.get_frailty_flag(hccs)
        frailty_score = FRAILTY_COEFFICIENT if has_frailty and profile.is_institutional else 0.0

        # Sum components
        raw_raf = (
            demo_score
            + sum(hcc_scores.values())
            + sum(interaction_scores.values())
            + frailty_score
        )

        # Apply CMS normalization
        payment_raf = raw_raf / self._norm_factor

        return RAFResult(
            member_id=profile.member_id,
            demographic_score=demo_score,
            hcc_scores=hcc_scores,
            interaction_scores=interaction_scores,
            frailty_score=frailty_score,
            raw_raf=raw_raf,
            payment_raf=payment_raf,
            hcc_list=sorted(hccs),
            hcc_count=len(hccs),
            demographic_key=demo_key,
            has_frailty=has_frailty,
        )

    def calculate_batch(
        self,
        profiles: List[MemberProfile],
        progress_interval: int = 10_000,
    ) -> List[RAFResult]:
        """Calculate RAF for a list of member profiles."""
        results = []
        for i, profile in enumerate(profiles):
            if i > 0 and i % progress_interval == 0:
                logger.info("Processed %d / %d members", i, len(profiles))
            results.append(self.calculate(profile))
        return results

    def calculate_batch_df(self, profiles: List[MemberProfile]) -> "pd.DataFrame":
        """Calculate RAF for all members and return as a DataFrame."""
        import pandas as pd
        results = self.calculate_batch(profiles)
        return pd.DataFrame([r.to_dict() for r in results])

    # ------------------------------------------------------------------
    # Demographic Key Construction
    # ------------------------------------------------------------------

    def _get_demographic_key(self, profile: MemberProfile) -> str:
        """Map age + sex to V28 demographic coefficient key."""
        sex = profile.sex.upper()
        if sex not in ("M", "F"):
            logger.warning("Unknown sex '%s' for member %s — defaulting to F",
                           profile.sex, profile.member_id)
            sex = "F"

        age_band = self._age_to_band(profile.age)
        return f"{sex}_{age_band}"

    @staticmethod
    def _age_to_band(age: int) -> str:
        if age < 35:    return "LT35"
        if age < 45:    return "35_44"
        if age < 55:    return "45_54"
        if age < 60:    return "55_59"
        if age < 65:    return "60_64"
        if age < 70:    return "65_69"
        if age < 75:    return "70_74"
        if age < 80:    return "75_79"
        if age < 85:    return "80_84"
        if age < 90:    return "85_89"
        if age < 95:    return "90_94"
        return "GE95"


# ---------------------------------------------------------------------------
# Composite RAF Utilities
# ---------------------------------------------------------------------------

def compute_plan_average_raf(results: List[RAFResult]) -> float:
    """Return the population-weighted average payment RAF."""
    if not results:
        return 0.0
    return sum(r.payment_raf for r in results) / len(results)


def compute_raf_distribution(results: List[RAFResult]) -> dict:
    """Return descriptive statistics of RAF distribution."""
    import statistics
    rafs = [r.payment_raf for r in results]
    return {
        "count": len(rafs),
        "mean": round(statistics.mean(rafs), 4),
        "median": round(statistics.median(rafs), 4),
        "stdev": round(statistics.stdev(rafs), 4) if len(rafs) > 1 else 0.0,
        "min": round(min(rafs), 4),
        "max": round(max(rafs), 4),
        "p10": round(sorted(rafs)[int(len(rafs) * 0.10)], 4),
        "p25": round(sorted(rafs)[int(len(rafs) * 0.25)], 4),
        "p75": round(sorted(rafs)[int(len(rafs) * 0.75)], 4),
        "p90": round(sorted(rafs)[int(len(rafs) * 0.90)], 4),
    }
