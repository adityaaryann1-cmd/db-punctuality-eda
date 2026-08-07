import os
import urllib.request
import duckdb
import pandas as pd

def fetch_and_inspect_2026_data():
    # 1. Create a local directory to hold the massive dataset
    data_dir = "db_data_2026"
    os.makedirs(data_dir, exist_ok=True)
    
    # 2. List the available months for this year (Jan through Jul)
    months = ["01", "02", "03", "04", "05", "06", "07"]
    
    print("--- Phase 1a: Downloading 2026 Data ---")
    print(f"Files will be saved to: ./{data_dir}/")
    
    for month in months:
        filename = f"data-2026-{month}.parquet"
        filepath = os.path.join(data_dir, filename)
        # Using the standard Hugging Face URL structure for this repo
        url = f"https://huggingface.co/datasets/piebro/deutsche-bahn-data/resolve/main/monthly_processed_data/{filename}"
        
        if os.path.exists(filepath):
            print(f"[{month}/2026] {filename} already exists. Skipping download.")
        else:
            print(f"[{month}/2026] Downloading {filename} (approx 600MB)...")
            try:
                urllib.request.urlretrieve(url, filepath)
                print(f" -> Successfully saved {filename}")
            except Exception as e:
                print(f" -> Failed to download {filename}. Error: {e}")

    # 3. Use DuckDB to inspect the entire year instantly without crashing RAM
    print("\n--- Phase 1b: DuckDB Full Year Inspection ---")
    print("Connecting DuckDB to all 2026 Parquet files simultaneously...")
    
    try:
        # We use a wildcard (*.parquet) to query all 7 months as if they were one giant table
        row_count_query = f"SELECT COUNT(*) FROM '{data_dir}/*.parquet'"
        row_count = duckdb.sql(row_count_query).fetchone()[0]
        print(f"\nTotal Rows for 2026: {row_count:,}")
        
        # Pull just the first 5 rows into Pandas to check the schema
        preview_query = f"SELECT * FROM '{data_dir}/*.parquet' LIMIT 5"
        preview_df = duckdb.sql(preview_query).df()
        
        print("\nColumn Datatypes:")
        print(preview_df.dtypes)
        
        print("\nFirst 5 Rows Snapshot:")
        print(preview_df)
        
        print("\nPhase 1 Complete! The 2026 dataset is ready for Phase 2 (Cleaning).")
        
    except Exception as e:
        print(f"\nError querying data with DuckDB: {e}")

if __name__ == "__main__":
    fetch_and_inspect_2026_data()