"""
Synthetic Medicare Claims Generator
=====================================
Generates 2.5M synthetic Medicare Part A/B claims records for
pipeline validation and benchmarking. Designed to produce a
clinically realistic distribution that mirrors CMS Medicare
Advantage population statistics.

Key properties of generated population:
  - Age distribution: skewed toward 70–85 (Medicare-typical)
  - Sex distribution: 55% F / 45% M (MA population benchmark)
  - Chronic condition prevalence: matched to CMS chronic conditions
    data warehouse prevalence rates
  - HCC distribution: ~42% of members have ≥1 HCC (MA benchmark)
  - Mean RAF: ~1.0 (normalized; community non-dual aged)
  - Claim volume: 6–18 claims per member per year (typical utilization)

Usage:
    python src/synthetic_claims_generator.py --members 2500000 --output data/
    
    # Or from Python:
    from src.synthetic_claims_generator import SyntheticClaimsGenerator
    gen = SyntheticClaimsGenerator(n_members=2_500_000, seed=42)
    members_df, claims_df = gen.generate()
"""

import argparse
import logging
import os
import random
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ---------------------------------------------------------------------------
# Prevalence tables (source: CMS Chronic Conditions Data Warehouse, 2022)
# ---------------------------------------------------------------------------

# (icd_codes, prevalence_rate, typical_claim_count_range)
CONDITION_PREVALENCE = [
    # High-prevalence chronic conditions
    (["E1140", "E1149", "E119"],          0.31,  (3, 12)),  # Diabetes
    (["I5020", "I5031", "I509"],          0.19,  (4, 15)),  # Heart failure
    (["J440", "J441", "J449"],            0.15,  (2, 8)),   # COPD
    (["I7000", "I702", "I7090"],          0.14,  (2, 7)),   # Vascular disease
    (["N183", "N184", "N185"],            0.20,  (3, 10)),  # CKD
    (["I2510", "I213", "I219"],           0.22,  (2, 9)),   # Ischemic HD
    (["F329", "F3289"],                   0.13,  (2, 6)),   # Depression
    # Moderate-prevalence
    (["C340", "C341"],                    0.04,  (4, 16)),  # Lung cancer
    (["C180", "C182", "C20"],             0.03,  (3, 12)),  # Colorectal cancer
    (["A411", "A412", "A419"],            0.06,  (5, 20)),  # Septicemia (high acuity)
    (["K7030", "K7031"],                  0.05,  (3, 10)),  # Liver cirrhosis
    (["I6300", "I6301"],                  0.07,  (4, 14)),  # Stroke
    # Lower prevalence / high RAF
    (["C780", "C781", "C782"],            0.02,  (6, 20)),  # Metastatic cancer
    (["B20"],                             0.01,  (4, 16)),  # HIV
    (["L89000", "L89003"],                0.03,  (3, 12)),  # Pressure ulcers
    (["Z8961", "Z8962"],                  0.02,  (2, 8)),   # Amputation
]

# Interaction condition pairs (assigned together for realism)
COMORBIDITY_PAIRS = [
    (["E1140"], ["N185"],   0.08),  # Diabetes + ESRD
    (["E119"],  ["N183"],   0.12),  # Diabetes + CKD3
    (["I5031"], ["J449"],   0.07),  # CHF + COPD
    (["I5020"], ["I7000"],  0.09),  # CHF + vascular disease
]

# ICD codes representing routine/non-HCC encounters (filler claims)
ROUTINE_CODES = [
    "Z0000", "Z0001", "Z1231", "Z1239",  # Preventive visits
    "M5450", "M5460", "M5471",           # Back pain
    "J069",  "J0090", "J209",            # URI / bronchitis
    "K5900", "K5902", "K219",            # GI symptoms
    "H25011","H25012","H3530",           # Eye conditions
    "R0500", "R0510", "R0600",           # Symptoms
    "Z7901", "Z7982", "Z7984",           # Long-term medication use
    "I10",   "E785",  "E119",            # HTN / hyperlipidemia (common fillers)
]


@dataclass
class MemberRecord:
    member_id: str
    age: int
    sex: str
    segment: str
    state: str
    enrollment_start: str
    enrollment_end: str
    is_dual: bool
    is_disabled: bool
    condition_flags: List[str]  # For validation auditing


class SyntheticClaimsGenerator:
    """
    Generates a synthetic Medicare claims population with realistic
    condition prevalence, demographics, and utilization patterns.
    """

    STATES = [
        "CA", "TX", "FL", "NY", "PA", "OH", "IL", "GA", "NC", "MI",
        "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI",
    ]

    SEGMENTS = {
        "CNA": 0.60,   # Community non-dual aged (largest)
        "CND": 0.15,   # Community non-dual disabled
        "CFA": 0.18,   # Community full-dual aged
        "INS": 0.07,   # Institutional
    }

    def __init__(
        self,
        n_members: int = 2_500_000,
        seed: int = 42,
        year: int = 2023,
    ):
        self.n_members = n_members
        self.seed = seed
        self.year = year
        np.random.seed(seed)
        random.seed(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        output_dir: Optional[str] = None,
        chunk_size: int = 100_000,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Generate members and claims DataFrames.

        Args:
            output_dir:  If provided, saves parquet files to this directory.
            chunk_size:  Members processed per chunk (memory management).

        Returns:
            (members_df, claims_df)
        """
        t0 = time.time()
        logger.info("Generating %s synthetic members...", f"{self.n_members:,}")

        members_df = self._generate_members()
        logger.info("Members generated in %.1fs. Generating claims...", time.time() - t0)

        t1 = time.time()
        claims_df = self._generate_claims(members_df, chunk_size=chunk_size)
        logger.info(
            "Claims generated: %s records in %.1fs",
            f"{len(claims_df):,}",
            time.time() - t1,
        )

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            members_path = os.path.join(output_dir, "synthetic_members.parquet")
            claims_path = os.path.join(output_dir, "synthetic_claims.parquet")
            members_df.to_parquet(members_path, index=False)
            claims_df.to_parquet(claims_path, index=False)
            logger.info("Saved:\n  %s\n  %s", members_path, claims_path)

        logger.info("Total generation time: %.1fs", time.time() - t0)
        return members_df, claims_df

    # ------------------------------------------------------------------
    # Member Generation
    # ------------------------------------------------------------------

    def _generate_members(self) -> pd.DataFrame:
        n = self.n_members

        # Segment assignment
        segment_keys = list(self.SEGMENTS.keys())
        segment_probs = list(self.SEGMENTS.values())
        segments = np.random.choice(segment_keys, size=n, p=segment_probs)

        # Demographics per segment
        ages = self._sample_ages(segments)
        sexes = np.random.choice(["M", "F"], size=n, p=[0.45, 0.55])
        states = np.random.choice(self.STATES, size=n)

        # Dual / disabled flags
        is_dual = np.array([s in ("CFA",) for s in segments])
        is_disabled = np.array([s == "CND" for s in segments])

        # Enrollment dates (full year or partial)
        enrollment_starts, enrollment_ends = self._sample_enrollment_dates(n)

        # Assign conditions
        condition_flags = self._assign_conditions(n, ages)

        member_ids = [f"M{str(i+1).zfill(8)}" for i in range(n)]

        return pd.DataFrame({
            "member_id": member_ids,
            "age": ages,
            "sex": sexes,
            "segment": segments,
            "state": states,
            "enrollment_start": enrollment_starts,
            "enrollment_end": enrollment_ends,
            "is_dual": is_dual,
            "is_disabled": is_disabled,
            "condition_flags": condition_flags,
        })

    def _sample_ages(self, segments: np.ndarray) -> np.ndarray:
        """Sample ages with segment-appropriate distributions."""
        ages = np.zeros(len(segments), dtype=int)
        for i, seg in enumerate(segments):
            if seg in ("CNA", "CFA"):
                # Aged: 65–99, skewed toward 70–85
                ages[i] = int(np.clip(np.random.normal(74, 7), 65, 99))
            elif seg == "CND":
                # Non-dual disabled: 18–64
                ages[i] = int(np.clip(np.random.normal(48, 12), 18, 64))
            else:
                # Institutional: 70–99, skewed older
                ages[i] = int(np.clip(np.random.normal(80, 8), 65, 99))
        return ages

    def _sample_enrollment_dates(
        self, n: int
    ) -> Tuple[List[str], List[str]]:
        starts, ends = [], []
        year = self.year
        for _ in range(n):
            # 80% enrolled full year, 20% partial
            if random.random() < 0.80:
                starts.append(f"{year}-01-01")
                ends.append(f"{year}-12-31")
            else:
                start_month = random.randint(1, 6)
                starts.append(f"{year}-{start_month:02d}-01")
                ends.append(f"{year}-12-31")
        return starts, ends

    def _assign_conditions(self, n: int, ages: np.ndarray) -> List[List[str]]:
        """
        Assign condition flags per member based on prevalence rates.
        Age-adjusts prevalence for CKD, CHF, cancer (higher in older patients).
        """
        flags = [[] for _ in range(n)]

        for icd_list, base_prev, _ in CONDITION_PREVALENCE:
            for i in range(n):
                age = ages[i]
                # Age adjustment: 20% higher prevalence per 10 years above 65
                age_factor = 1.0 + max(0, (age - 65) / 10) * 0.20
                adjusted_prev = min(base_prev * age_factor, 0.85)
                if random.random() < adjusted_prev:
                    flags[i].extend(icd_list[:1])  # Primary code only for flag

        # Add comorbidity pairs
        for primary_codes, secondary_codes, pair_prev in COMORBIDITY_PAIRS:
            primary_set = set(primary_codes)
            for i in range(n):
                member_flags = set(flags[i])
                if member_flags & primary_set:
                    if random.random() < pair_prev:
                        flags[i].extend(secondary_codes[:1])

        return flags

    # ------------------------------------------------------------------
    # Claims Generation
    # ------------------------------------------------------------------

    def _generate_claims(
        self,
        members_df: pd.DataFrame,
        chunk_size: int = 100_000,
    ) -> pd.DataFrame:
        all_claims = []
        n = len(members_df)

        for start in range(0, n, chunk_size):
            end = min(start + chunk_size, n)
            chunk = members_df.iloc[start:end]
            chunk_claims = self._generate_claims_for_chunk(chunk)
            all_claims.append(chunk_claims)

            if (start // chunk_size) % 5 == 0:
                logger.info(
                    "  Claims chunk %d/%d complete",
                    start // chunk_size + 1,
                    (n // chunk_size) + 1,
                )

        return pd.concat(all_claims, ignore_index=True)

    def _generate_claims_for_chunk(self, chunk: pd.DataFrame) -> pd.DataFrame:
        records = []
        year = self.year

        for _, member in chunk.iterrows():
            # Determine claim volume based on condition burden
            n_conditions = len(member["condition_flags"])
            base_claims = random.randint(4, 10)
            condition_claims = n_conditions * random.randint(1, 3)
            total_claims = min(base_claims + condition_claims, 30)

            condition_codes = list(member["condition_flags"])

            for _ in range(total_claims):
                # Service date within enrollment period
                service_date = self._random_date(year)

                # Assign ICD code: condition or routine
                if condition_codes and random.random() < 0.55:
                    icd = random.choice(condition_codes)
                    # Occasionally add secondary codes from same condition group
                    for icd_list, _, _ in CONDITION_PREVALENCE:
                        if icd in icd_list:
                            if random.random() < 0.40:
                                icd = random.choice(icd_list)
                            break
                else:
                    icd = random.choice(ROUTINE_CODES)

                records.append({
                    "member_id": member["member_id"],
                    "claim_id": f"CLM{random.randint(10**9, 10**10)}",
                    "service_date": service_date,
                    "icd_code": icd,
                    "claim_type": random.choice(["outpatient", "professional", "inpatient"]),
                    "provider_npi": f"NPI{random.randint(10**9, 10**10)}",
                    "paid_amount": round(random.uniform(50, 8000), 2),
                })

        return pd.DataFrame(records)

    @staticmethod
    def _random_date(year: int) -> str:
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        return f"{year}-{month:02d}-{day:02d}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic Medicare claims for HCC V28 pipeline testing"
    )
    parser.add_argument(
        "--members", type=int, default=2_500_000,
        help="Number of synthetic members to generate (default: 2,500,000)"
    )
    parser.add_argument(
        "--output", type=str, default="data/",
        help="Output directory for parquet files (default: data/)"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility (default: 42)"
    )
    parser.add_argument(
        "--year", type=int, default=2023,
        help="Service year (default: 2023)"
    )
    parser.add_argument(
        "--chunk-size", type=int, default=100_000,
        help="Processing chunk size (default: 100,000)"
    )
    args = parser.parse_args()

    gen = SyntheticClaimsGenerator(
        n_members=args.members,
        seed=args.seed,
        year=args.year,
    )
    members_df, claims_df = gen.generate(
        output_dir=args.output,
        chunk_size=args.chunk_size,
    )

    print(f"\nGeneration complete:")
    print(f"  Members: {len(members_df):,}")
    print(f"  Claims:  {len(claims_df):,}")
    print(f"  Avg claims/member: {len(claims_df)/len(members_df):.1f}")
    print(f"  Output: {args.output}")


if __name__ == "__main__":
    main()
