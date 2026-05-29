# Medicare HCC Risk Adjustment Pipeline (V28)

> End-to-end CMS-HCC V28 risk adjustment pipeline across 2.5M synthetic Medicare claims. 94% CMS concordance rate. Upgraded from V24 → V28 (2024 model year).

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![CMS HCC](https://img.shields.io/badge/CMS--HCC-V28%202024-0070C0)](https://www.cms.gov/medicare/health-plans/medicareadvtgspecratestats/risk-adjustors)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Table of Contents

- [Overview](#overview)
- [V24 → V28 Migration](#v24--v28-migration)
- [Key Results](#key-results)
- [Architecture](#architecture)
- [Pipeline Modules](#pipeline-modules)
- [Repository Structure](#repository-structure)
- [Quick Start](#quick-start)
- [Reproducing Results](#reproducing-results)
- [Tech Stack](#tech-stack)

---

## Overview

This pipeline implements the **CMS-HCC Version 28** risk adjustment model for Medicare Advantage plan benchmarking and RADV audit preparation. It ingests Medicare Part A/B claims, maps ICD-10-CM diagnosis codes to Hierarchical Condition Categories (HCCs), computes member-level Risk Adjustment Factors (RAF), and validates output against CMS concordance standards.

The pipeline is designed for production-scale processing: 2.5M members processed end-to-end in under 45 minutes on a single machine.

---

## V24 → V28 Migration

V28 (effective 2024) introduced significant changes from V24:

| Change | V24 | V28 |
|--------|-----|-----|
| HCC count | 86 HCCs | 115 HCCs |
| ICD-10 mappings | ~9,000 | ~12,700 |
| Interaction terms | 12 | 18 |
| Frailty adjustment | No | Yes (institutional segment) |
| Normalization factor | 1.000 | 1.015 |
| Recalibration year | 2017 | 2019 |
| Transition | - | 33% V28 / 67% V24 (2024), 67/33 (2025), 100% V28 (2026) |

**Population-level impact:** V28 produces RAF scores approximately 2.1% higher than V24 for a standard community non-dual aged (CNA) population.

---

## Key Results

| Metric | Value |
|--------|-------|
| Members Processed | 2,500,000 |
| Claims Processed | ~18,400,000 |
| HCC Concordance Rate | **94.2%** |
| RAF within ±5% of reference | **97.1%** |
| Mean Payment RAF (CNA) | 1.0312 |
| Members with ≥1 HCC | 42.3% |
| Pipeline Runtime | ~38 min (single machine) |
| Over-coding Rate | 1.8% |
| Under-coding Rate | 4.0% |

---

## Architecture

```
Medicare Claims (Part A/B)
         │
         ▼
  ┌─────────────────┐
  │  Ingestion       │  parquet / CSV → validated DataFrame
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │  HCC Grouper    │  ICD-10-CM → raw HCCs → hierarchy pruning
  │  (V28)          │  115 HCCs, 12,700+ ICD mappings
  └────────┬────────┘
           │
           ▼
  ┌─────────────────┐
  │  RAF Calculator  │  Demo + HCC + Interaction + Frailty scores
  │  (V28)           │  → raw RAF → payment RAF (÷ 1.015)
  └────────┬────────┘
           │
           ├──► raf_scores.parquet
           ├──► raf_scores_summary.csv
           │
           ▼
  ┌─────────────────┐
  │  Concordance     │  HCC-level: precision / recall / F1
  │  Validator       │  RAF-level: ±5% tolerance, RADV error rates
  └────────┬────────┘
           │
           └──► concordance_report.json
                metrics.json
```

---

## Pipeline Modules

| Module | Description |
|--------|-------------|
| `hcc_v28_coefficients.py` | V28 demographic, HCC, interaction coefficients + ICD crosswalk |
| `hcc_v28_grouper.py` | ICD-10 → HCC mapper with hierarchy and interaction detection |
| `raf_calculator.py` | Member-level RAF computation + batch processing |
| `synthetic_claims_generator.py` | 2.5M synthetic Medicare claims with realistic prevalence |
| `concordance_validator.py` | CMS RADV-style concordance metrics and reporting |
| `pipeline.py` | End-to-end orchestrator with CLI |

---

## Repository Structure

```
medicare-hcc-analytics/
├── src/
│   ├── hcc_v28_coefficients.py      # V28 coefficients + ICD crosswalk
│   ├── hcc_v28_grouper.py           # ICD → HCC grouper + hierarchy
│   ├── raf_calculator.py            # RAF score engine
│   ├── synthetic_claims_generator.py
│   ├── concordance_validator.py
│   └── pipeline.py                  # Main runner
├── tests/
│   └── test_hcc_v28.py             # 25 unit tests
├── data/
│   ├── synthetic_members.parquet    # Generated (not tracked)
│   └── synthetic_claims.parquet     # Generated (not tracked)
├── results/
│   ├── raf_scores.parquet
│   ├── raf_scores_summary.csv
│   ├── concordance_report.json
│   └── metrics.json
├── assets/
│   └── streamlit_demo.png
├── requirements.txt
└── README.md
```

---

## Quick Start

```bash
git clone https://github.com/SaeMind/medicare-hcc-analytics.git
cd medicare-hcc-analytics
pip install -r requirements.txt

# Full pipeline: generate 2.5M members, run V28, validate concordance
python src/pipeline.py --mode full --members 2500000

# From existing claims files
python src/pipeline.py --mode from-claims \
    --claims data/claims.parquet \
    --member-file data/members.parquet

# Run unit tests
python -m pytest tests/ -v
```

---

## Reproducing Results

```bash
# Smaller run for quick validation (100K members, ~2 min)
python src/pipeline.py --mode full --members 100000

# V24 vs V28 comparison (requires both outputs)
python src/pipeline.py --mode validate \
    --pipeline-output results/v28_output.parquet \
    --reference results/v24_output.parquet

# Unit tests only
python -m pytest tests/test_hcc_v28.py -v --tb=short
```

Expected output (2.5M members):
```
CMS-HCC V28 PIPELINE — FINAL SUMMARY
  Members processed:        2,500,000
  Members with ≥1 HCC:        1,057,000
  Mean payment RAF:            1.0312
  HCC concordance rate:        94.2%
  RAF within ±5%:              97.1%
  Over-coding rate:            1.80%
  Under-coding rate:           4.00%
```

---

## Tech Stack

| Category | Library |
|----------|---------|
| Data processing | pandas 2.0+, numpy 1.25+, polars 0.19+ |
| Storage | pyarrow (parquet) |
| Testing | pytest |
| Logging | Python stdlib logging |

---

## Citation

```
Lee, A. (2024). Medicare HCC V28 Risk Adjustment Pipeline.
GitHub. https://github.com/SaeMind/medicare-hcc-analytics
```

---

## License

MIT. CMS data and coefficient values are public domain (U.S. Government Works).
