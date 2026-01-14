import polars as pl
import os
import time

# --- CONFIGURATION ---
# We use relative paths. Ensure you run this from the project root folder.
RAW_PATH = "data/raw/DE1_0_2008_Beneficiary_Summary_File_Sample_1.csv"
PROCESSED_DIR = "data/processed"
PROCESSED_FILENAME = "beneficiaries_2008.parquet"
PROCESSED_PATH = os.path.join(PROCESSED_DIR, PROCESSED_FILENAME)

def ingest_data():
    """
    Ingests raw CMS CSV data, enforces strict types, and saves as Parquet.
    """
    print(f"\n🚀 Starting ingestion process...")
    start_time = time.time()

    # 1. Validation: Check if Source Exists
    if not os.path.exists(RAW_PATH):
        print(f"❌ CRITICAL ERROR: File not found at '{RAW_PATH}'")
        print("   -> Action: Download 'DE1_0_2008_Beneficiary_Summary_File_Sample_1.zip' from CMS.")
        print("   -> Action: Unzip it and place the CSV in the 'data/raw' folder.")
        return

    # 2. Validation: Ensure Output Directory Exists
    if not os.path.exists(PROCESSED_DIR):
        print(f"⚠️  Output directory '{PROCESSED_DIR}' not found. Creating it...")
        os.makedirs(PROCESSED_DIR)

    # 3. Lazy Load & Transform
    # We use scan_csv for memory efficiency (Lazy API)
    try:
        q = pl.scan_csv(RAW_PATH, infer_schema_length=0) # infer_schema=0 forces us to be manual/safe
        
        # Select and Cast specific columns we need for HCC scoring
        # Note: CMS columns are often capitalized
        df = (
            q.select([
                pl.col("DESYNPUF_ID").alias("member_id"),
                pl.col("BENE_BIRTH_DT").cast(pl.Utf8).alias("dob"),
                pl.col("BENE_SEX_IDENT_CD").cast(pl.Int8).alias("sex"),
                # We will need these diagnosis columns later, let's keep the raw strings
                # SynPUF has columns like SP_ALZHDMTA (Alzheimer's flag), etc.
                # For now, we stick to the core demographics to test the pipeline.
                pl.col("SP_STATE_CODE").cast(pl.Utf8).alias("state_code")
            ])
            .collect() # Execute the query
        )
        
        # 4. Save to Parquet
        df.write_parquet(PROCESSED_PATH)
        
        # 5. Success Stats
        rows = df.shape[0]
        cols = df.shape[1]
        file_size = os.path.getsize(PROCESSED_PATH) / (1024 * 1024) # Size in MB
        
        print(f"✅ SUCCESS: Data successfully transformed.")
        print(f"   - Input: {RAW_PATH}")
        print(f"   - Output: {PROCESSED_PATH}")
        print(f"   - Dimensions: {rows:,} rows x {cols} columns")
        print(f"   - File Size: {file_size:.2f} MB")
        print(f"⏱️  Total time: {round(time.time() - start_time, 2)}s")

    except Exception as e:
        print(f"❌ Error during processing: {e}")

if __name__ == "__main__":
    ingest_data()