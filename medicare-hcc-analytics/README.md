# Medicare HCC Risk Analytics Engine

**A high-performance risk adjustment scoring engine built to model CMS-HCC (Hierarchical Condition Categories) for 2.3M synthetic Medicare beneficiaries.**

---

## Executive Summary

Risk Adjustment is the financial operating system of Value-Based Care. This engine ingests raw CMS SynPUF claims data, calculates patient age/demographics, and computes a **Risk Adjustment Factor (RAF)** score to simulate capitated reimbursement revenue.

The system is engineered for performance, utilizing **Polars** for strictly-typed, high-speed data processing (outperforming Pandas on large datasets) and **Streamlit** for real-time financial simulation.

---

## Architecture & Stack

- **Core Logic:** Python 3.11+
- **Data Engine:** [Polars](https://pola.rs/) (Rust-based DataFrame library)
- **Interface:** Streamlit
- **Visualization:** Plotly Express
- **Data Source:** CMS DE-SynPUF (2008-2010)

---

## Key Features

1. **ETL Pipeline:** Ingests and normalizes raw CMS CSV files into high-speed Parquet storage.
2. **Scoring Logic:** Implements CMS-HCC V24 demographic scoring constraints (Age/Sex interactions).
3. **Financial Simulator:** Dynamic dashboard allowing operators to adjust Base Rates and visualize revenue variance.
4. **Population Stratification:** Cohort analysis by Age Band and Risk Quartile.

---

## Usage

### 1. Environment Setup

```bash
git clone https://github.com/SaeMind/medicare-hcc-analytics.git
cd medicare-hcc-analytics
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Data Ingestion

> **Note:** Raw CMS data is not included in the repo due to size constraints.

1. Download Sample 1 (2008 Beneficiary Summary) from [CMS SynPUF](https://www.cms.gov/Research-Statistics-Data-and-Systems/Downloadable-Public-Use-Files/SynPUFs)
2. Place the `.csv` file in `data/raw/`
3. Run the pipeline:

```bash
python src/ingestion.py
python src/scoring.py
```

### 3. Launch Dashboard

```bash
streamlit run src/app.py
```

---

## Project Structure

```
medicare-hcc-analytics/
├── medicare-hcc-analytics/
│   ├── src/
│   │   ├── ingestion.py       # ETL pipeline
│   │   ├── scoring.py         # CMS-HCC V24 scoring logic
│   │   └── app.py             # Streamlit dashboard
│   ├── data/
│   │   └── raw/               # CMS SynPUF CSV files (not committed)
│   └── assets/                # Screenshots and visual assets
├── requirements.txt
└── README.md
```

---

## About

CMS-HCC Risk Adjustment Engine built with Polars and Python

---

## Contact

**Andrew Lee**
Clinical Data Science | Biomedical Informatics

- [LinkedIn](https://www.linkedin.com/in/agllee)
- [Portfolio](https://andrew-gihbeom-lee.figma.site/)
- [Email](mailto:gihbeom@gmail.com)

---

## License

MIT License — See LICENSE file for details

---

**Project Status:** In Development
**Last Updated:** March 2026
