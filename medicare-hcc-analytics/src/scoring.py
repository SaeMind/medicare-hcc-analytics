import polars as pl
import os
from datetime import date

# --- CONFIGURATION ---
INPUT_PATH = "data/processed/beneficiaries_2008.parquet"
OUTPUT_PATH = "data/processed/beneficiaries_scored.parquet"
REFERENCE_DATE = date(2008, 12, 31) # The end of the coverage year

def calculate_demographic_score():
    print(f"\n🚀 Starting Demographic Scoring...")
    
    # 1. Load Data
    if not os.path.exists(INPUT_PATH):
        print("❌ Error: Processed data not found. Run ingestion.py first.")
        return

    df = pl.read_parquet(INPUT_PATH)
    
    # 2. Transformation: Calculate Age
    # SynPUF Format is usually YYYYMMDD (e.g., "19400212")
    # Sex Code: 1 = Male, 2 = Female
    
    df_scored = df.with_columns([
        # Parse Date string to Date Object
        pl.col("dob").str.to_date("%Y%m%d").alias("dob_date")
    ]).with_columns([
        # Calculate Age in Years
        ((pl.lit(REFERENCE_DATE) - pl.col("dob_date")).dt.total_days() / 365.25).floor().cast(pl.Int16).alias("age")
    ])

    # 3. Apply CMS Risk Factors (Simplified V24 Community Model)
    # In a real app, we would load this from a CSV. For this MVP, we use a mapping function.
    # Logic: Older = Higher Score. Males usually higher than Females at older ages.
    
    df_final = df_scored.with_columns(
        pl.when(pl.col("sex") == 1) # MALE
        .then(
            pl.when(pl.col("age") < 65).then(0.15)
            .when(pl.col("age").is_between(65, 69)).then(0.25)
            .when(pl.col("age").is_between(70, 74)).then(0.39)
            .when(pl.col("age").is_between(75, 79)).then(0.53)
            .when(pl.col("age").is_between(80, 84)).then(0.70)
            .otherwise(0.85) # 85+
        )
        .otherwise( # FEMALE (Sex = 2)
            pl.when(pl.col("age") < 65).then(0.12)
            .when(pl.col("age").is_between(65, 69)).then(0.20)
            .when(pl.col("age").is_between(70, 74)).then(0.32)
            .when(pl.col("age").is_between(75, 79)).then(0.45)
            .when(pl.col("age").is_between(80, 84)).then(0.60)
            .otherwise(0.78) # 85+
        ).alias("demographic_risk_score")
    )

    # 4. Metrics & Save
    mean_score = df_final["demographic_risk_score"].mean()
    
    print(f"✅ Demographic Scoring Complete.")
    print(f"   - Average Risk Score: {mean_score:.4f}")
    print(f"   - Sample Patient:")
    print(df_final.select(["member_id", "sex", "age", "demographic_risk_score"]).head(3))
    
    df_final.write_parquet(OUTPUT_PATH)
    print(f"💾 Saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    calculate_demographic_score()