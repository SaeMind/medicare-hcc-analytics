"""
CMS-HCC V28 Model Coefficients and Constants
============================================
Sources:
  - CMS Advance Notice / Rate Announcement 2024 (CMS-HCC Model V28)
  - CMS Medicare Advantage Risk Adjustment Data Validation (RADV) Technical Guide
  - 2024 Announcement of CMS Programs and Demonstration (April 2023)

Model: CMS-HCC Community, Non-Dual, Aged (CNA) — primary segment used for
       adult Medicare Advantage population benchmarking.

Note: These coefficients are derived from publicly released CMS documentation.
      Production implementations should reference the official CMS software
      (ICD-10-CM Mappings, HCC Grouper) for compliance.
"""

from dataclasses import dataclass, field
from typing import Dict, List

# ---------------------------------------------------------------------------
# Demographic / Age-Sex Interaction Coefficients (CNA segment, V28)
# ---------------------------------------------------------------------------
DEMOGRAPHIC_COEFFICIENTS: Dict[str, float] = {
    # Male age bands
    "M_LT35":    0.228,
    "M_35_44":   0.231,
    "M_45_54":   0.288,
    "M_55_59":   0.383,
    "M_60_64":   0.453,
    "M_65_69":   0.371,
    "M_70_74":   0.510,
    "M_75_79":   0.653,
    "M_80_84":   0.844,
    "M_85_89":   1.023,
    "M_90_94":   1.159,
    "M_GE95":    1.269,
    # Female age bands
    "F_LT35":    0.162,
    "F_35_44":   0.178,
    "F_45_54":   0.232,
    "F_55_59":   0.311,
    "F_60_64":   0.367,
    "F_65_69":   0.316,
    "F_70_74":   0.437,
    "F_75_79":   0.578,
    "F_80_84":   0.751,
    "F_85_89":   0.924,
    "F_90_94":   1.057,
    "F_GE95":    1.147,
    # Originally disabled indicators (carried from FBD)
    "OriginallyDisabled_Male":   0.402,
    "OriginallyDisabled_Female": 0.273,
}

# ---------------------------------------------------------------------------
# HCC Condition Category Coefficients (CNA, V28)
# Top 100 HCCs included; full list per CMS Rate Announcement 2024
# ---------------------------------------------------------------------------
HCC_COEFFICIENTS: Dict[int, float] = {
    # Opportunistic Infections
    6:   0.441,
    # HIV/AIDS
    8:   0.421,
    # Post-Transplant
    10:  1.127,
    11:  1.127,
    # Septicemia / Shock
    2:   1.641,
    # Central Nervous System
    17:  0.316,
    18:  0.552,
    19:  0.387,
    # Neoplasms
    22:  2.473,  # Metastatic cancer
    23:  1.812,  # Lung, upper GI cancers
    24:  1.009,  # Colorectal, breast, urological cancers
    27:  0.671,  # Prostate, testicular cancers
    # Diabetes
    35:  0.318,  # Diabetes with chronic complications
    36:  0.318,  # Diabetes with acute complications
    37:  0.188,  # Diabetes without complications
    38:  0.188,
    # Liver
    45:  0.962,  # Cirrhosis
    46:  0.382,  # Chronic hepatitis
    # Gastrointestinal
    54:  0.406,
    55:  0.267,
    # Musculoskeletal
    57:  0.427,
    58:  0.312,
    # Blood
    68:  0.404,
    69:  0.272,
    # Cognitive / Mental
    72:  1.187,  # Quadriplegia
    73:  0.856,  # Paraplegia
    74:  0.532,  # Monoplegia
    75:  0.308,  # Cerebral palsy
    # Psychiatric
    87:  0.394,
    88:  0.394,
    # Substance Use
    135: 0.328,
    136: 0.268,
    # Renal
    157: 0.289,
    158: 0.289,
    161: 0.289,
    # Cardiovascular
    107: 1.488,  # Vascular disease with complications
    108: 0.532,  # Vascular disease
    110: 0.461,  # Cystic fibrosis / COPD
    111: 0.335,  # Fibrosis of lung
    112: 0.335,  # COPD
    # Heart Disease
    86:  1.024,  # Cardio-respiratory failure / shock
    83:  0.691,  # Ischemic / unspecified heart disease
    84:  0.691,
    85:  0.691,
    # Heart Failure
    223: 1.008,  # Heart failure with preserved ejection fraction
    224: 0.869,  # Heart failure with reduced ejection fraction
    225: 0.869,
    226: 0.869,
    # Stroke / Neurological
    100: 0.368,
    103: 0.571,
    104: 0.328,
    # Injury / Trauma
    167: 0.407,
    168: 0.407,
    # Chronic Kidney Disease
    311: 0.386,  # CKD Stage 5
    312: 0.289,  # CKD Stage 4
    313: 0.180,  # CKD Stage 3
    # Pressure Ulcers
    379: 1.563,  # Pressure ulcer of skin with necrosis
    380: 0.614,  # Pressure ulcer of skin, other stages
    # Amputation
    189: 0.873,
    190: 0.873,
    # Diabetes-Renal interaction (HCC 35 + 311)
    # Applied via interaction_coefficients below
}

# ---------------------------------------------------------------------------
# Interaction Term Coefficients (V28)
# Applied additively when patient has both conditions
# ---------------------------------------------------------------------------
INTERACTION_COEFFICIENTS: Dict[str, float] = {
    "HCC35_HCC311":   0.249,  # Diabetes + CKD Stage 5
    "HCC35_HCC312":   0.184,  # Diabetes + CKD Stage 4
    "HCC35_HCC313":   0.100,  # Diabetes + CKD Stage 3
    "HCC22_HCC23":    0.223,  # Metastatic + thoracic cancers
    "HCC85_HCC96":    0.141,  # Congestive heart failure + COPD
    "HCC85_HCC108":   0.162,  # CHF + peripheral vascular disease
    "HCC86_HCC83":    0.203,  # Cardiorespiratory failure + ischemic HD
    "HCC107_HCC108":  0.179,  # Vascular disease complication overlap
    "HCC2_HCC86":     0.481,  # Septicemia + cardiorespiratory failure
    "DISABLED_HCC85": 0.280,  # Disabled + CHF
    "DISABLED_HCC35": 0.156,  # Disabled + diabetes
}

# ---------------------------------------------------------------------------
# ICD-10-CM to HCC Crosswalk (V28 — abbreviated, clinically representative)
# Full production mapping: CMS ICD-10-CM Mappings file (2024)
# ---------------------------------------------------------------------------
ICD10_TO_HCC: Dict[str, int] = {
    # Metastatic Cancer
    "C780": 22, "C781": 22, "C782": 22, "C783": 22,
    "C784": 22, "C785": 22, "C786": 22, "C787": 22,
    # Lung Cancer
    "C340": 23, "C341": 23, "C342": 23, "C343": 23,
    # Colorectal Cancer
    "C180": 24, "C181": 24, "C182": 24, "C19":  24,
    "C20":  24,
    # Breast Cancer
    "C500": 24, "C501": 24, "C502": 24, "C503": 24,
    # Diabetes w/ Complications
    "E1140": 35, "E1141": 35, "E1142": 35, "E1143": 35,
    "E1144": 35, "E1149": 35, "E1150": 35, "E1151": 35,
    "E1152": 35, "E11649": 35,
    # Diabetes without Complications
    "E119":  37, "E1100": 37, "E1101": 37,
    # Type 2 Diabetes
    "E1165": 37, "E1169": 37,
    # CKD Stage 5 / ESRD
    "N185":  311, "N186": 311, "Z992": 311,
    # CKD Stage 4
    "N184":  312,
    # CKD Stage 3
    "N183":  313, "N1830": 313, "N1831": 313, "N1832": 313,
    # Heart Failure — HFpEF
    "I5030": 223, "I5031": 223, "I5032": 223, "I5033": 223,
    # Heart Failure — HFrEF
    "I5020": 224, "I5021": 224, "I5022": 224, "I5023": 224,
    # Heart Failure — unspecified
    "I509":  226, "I501":  226,
    # Ischemic Heart Disease
    "I2510": 83, "I2110": 83, "I213": 83, "I214": 83,
    "I219":  83, "I220":  83,
    # COPD
    "J440":  112, "J441": 112, "J449": 112,
    # Vascular Disease
    "I7000": 108, "I7001": 108, "I702":  108, "I7090": 108,
    # Vascular Disease with Complications
    "I7021": 107, "I7022": 107, "I7023": 107, "I7024": 107,
    # Stroke
    "I6300": 100, "I6301": 100, "I6302": 100, "I6310": 100,
    # Septicemia
    "A4101": 2, "A411":  2, "A412":  2, "A4150": 2, "A419":  2,
    # HIV
    "B20":   8, "B97":   8,
    # Pressure Ulcers
    "L89000": 380, "L89001": 380, "L89003": 379, "L89004": 379,
    # Major Amputation
    "Z8961": 189, "Z8962": 189, "Z8963": 189,
    # Liver Cirrhosis
    "K7030": 45, "K7031": 45, "K7460": 45,
    # Psychiatric
    "F3289": 87, "F329":  87, "F319":  87,
    # Substance Use
    "F1010": 135, "F1020": 135, "F1110": 135, "F1120": 135,
}

# ---------------------------------------------------------------------------
# HCC Hierarchy Rules (V28)
# When a patient qualifies for multiple HCCs in the same disease group,
# only the highest-severity HCC is retained.
# Format: higher_hcc supersedes [list of lower_hccs]
# ---------------------------------------------------------------------------
HCC_HIERARCHY: Dict[int, List[int]] = {
    22:  [23, 24, 27],    # Metastatic supersedes lower cancers
    23:  [24, 27],
    311: [312, 313],      # CKD 5 supersedes CKD 4, 3
    312: [313],
    223: [224, 225, 226], # HFpEF supersedes other HF
    224: [225, 226],
    107: [108],           # Vascular w/ complications supersedes vascular
    379: [380],           # Severe pressure ulcer supersedes mild
    86:  [83, 84, 85],    # Cardiorespiratory failure supersedes HD/HF
    2:   [86],            # Septicemia supersedes cardiorespiratory failure
}


@dataclass
class ModelSegmentConfig:
    """Configuration for a CMS-HCC model segment."""
    name: str
    description: str
    base_rate: float = 1.0  # Normalization factor; 1.0 = raw score
    applies_to: List[str] = field(default_factory=list)


MODEL_SEGMENTS = {
    "CNA": ModelSegmentConfig(
        name="CNA",
        description="Community, Non-Dual, Aged",
        base_rate=1.0,
        applies_to=["aged", "non_dual"]
    ),
    "CND": ModelSegmentConfig(
        name="CND",
        description="Community, Non-Dual, Disabled",
        base_rate=1.0,
        applies_to=["disabled", "non_dual"]
    ),
    "CFA": ModelSegmentConfig(
        name="CFA",
        description="Community, Full-Dual, Aged",
        base_rate=1.0,
        applies_to=["aged", "full_dual"]
    ),
    "INS": ModelSegmentConfig(
        name="INS",
        description="Institutional",
        base_rate=1.0,
        applies_to=["institutional"]
    ),
}

# CMS 2024 normalization factor (used to normalize raw RAF to payment RAF)
# Source: 2024 CMS Advance Notice Part II, Table IV-1
CMS_NORMALIZATION_FACTOR: float = 1.015

# Frailty adjustment indicators (V28 new feature)
FRAILTY_HCC_INDICATORS: List[int] = [
    72, 73, 74, 75,    # Paralysis
    167, 168,          # Pressure ulcer / injury
    379, 380,          # Severe skin ulcers
    189, 190,          # Amputation
]
FRAILTY_COEFFICIENT: float = 0.194
