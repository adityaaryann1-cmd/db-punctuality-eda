import os
import urllib.request

import duckdb

from config import (
    DATA_DIR,
    DATA_MONTHS,
    DATA_YEAR,
    HF_BASE_URL,
    MIN_EXPECTED_FILE_SIZE_BYTES,
)


def download_with_progress(url, dest_path):
    """Stream to a .part file and rename atomically, so a crash mid-download
    never leaves a truncated file at the final path."""
    part_path = dest_path + ".part"
    with urllib.request.urlopen(url) as response:
        total = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024
        with open(part_path, "wb") as f:
            while chunk := response.read(chunk_size):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r    {downloaded / 1e6:,.0f}MB / {total / 1e6:,.0f}MB ({pct:.0f}%)", end="", flush=True)
                else:
                    print(f"\r    {downloaded / 1e6:,.0f}MB", end="", flush=True)
    print()
    os.replace(part_path, dest_path)


def fetch_and_inspect_2026_data():
    os.makedirs(DATA_DIR, exist_ok=True)

    print("--- Phase 1a: Downloading Data ---")
    print(f"Files will be saved to: ./{DATA_DIR}/")

    downloaded, skipped, failed = [], [], []

    for month in DATA_MONTHS:
        filename = f"data-{DATA_YEAR}-{month}.parquet"
        filepath = os.path.join(DATA_DIR, filename)
        url = f"{HF_BASE_URL}/{filename}"

        if os.path.exists(filepath) and os.path.getsize(filepath) >= MIN_EXPECTED_FILE_SIZE_BYTES:
            print(f"[{month}/{DATA_YEAR}] {filename} already exists ({os.path.getsize(filepath) / 1e6:,.0f}MB). Skipping.")
            skipped.append(filename)
            continue

        if os.path.exists(filepath):
            print(f"[{month}/{DATA_YEAR}] {filename} exists but is smaller than the expected "
                  f"{MIN_EXPECTED_FILE_SIZE_BYTES / 1e6:,.0f}MB floor -- likely a truncated download. Re-fetching.")

        print(f"[{month}/{DATA_YEAR}] Downloading {filename}...")
        try:
            download_with_progress(url, filepath)
            size = os.path.getsize(filepath)
            if size < MIN_EXPECTED_FILE_SIZE_BYTES:
                raise IOError(
                    f"Downloaded file is only {size / 1e6:,.0f}MB, below the "
                    f"{MIN_EXPECTED_FILE_SIZE_BYTES / 1e6:,.0f}MB sanity floor."
                )
            print(f" -> Successfully saved {filename} ({size / 1e6:,.0f}MB)")
            downloaded.append(filename)
        except Exception as e:
            print(f" -> Failed to download {filename}. Error: {e}")
            failed.append(filename)

    print("\n--- Download Summary ---")
    print(f"Downloaded: {len(downloaded)} ({', '.join(downloaded) if downloaded else 'none'})")
    print(f"Already present: {len(skipped)} ({', '.join(skipped) if skipped else 'none'})")
    if failed:
        print(f"Failed: {len(failed)} ({', '.join(failed)})")

    print("\n--- Phase 1b: DuckDB Full Year Inspection ---")
    print("Connecting DuckDB to all downloaded Parquet files simultaneously...")

    try:
        row_count_query = f"SELECT COUNT(*) FROM '{DATA_DIR}/*.parquet'"
        row_count = duckdb.sql(row_count_query).fetchone()[0]
        print(f"\nTotal Rows: {row_count:,}")

        # Pull just the first 5 rows into Pandas to check the schema
        preview_query = f"SELECT * FROM '{DATA_DIR}/*.parquet' LIMIT 5"
        preview_df = duckdb.sql(preview_query).df()

        print("\nColumn Datatypes:")
        print(preview_df.dtypes)

        print("\nFirst 5 Rows Snapshot:")
        print(preview_df)

        print("\nPhase 1 Complete! The dataset is ready for Phase 2 (python eda_pipeline.py).")

    except Exception as e:
        print(f"\nError querying data with DuckDB: {e}")


if __name__ == "__main__":
    fetch_and_inspect_2026_data()
