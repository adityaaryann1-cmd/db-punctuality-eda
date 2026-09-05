import glob
import json
import os
import sys
from datetime import datetime, timezone

import duckdb

from config import (
    DATA_DIR,
    MIN_STATION_DEPARTURES,
    OUTPUT_DIR,
    PUNCTUALITY_THRESHOLD_MIN,
    TRAIN_TYPE_WHITELIST,
)


def run_query(con, name, sql):
    """Run a query against the raw Parquet files, failing loudly on error."""
    try:
        return con.sql(sql).df()
    except Exception as e:
        raise RuntimeError(
            f"EDA query '{name}' failed against '{DATA_DIR}/*.parquet'. "
            f"Check that the raw data files are present and uncorrupted "
            f"(run `python data_check.py` if unsure). Original error: {e}"
        ) from e


def run_eda_pipeline():
    data_path = f"{DATA_DIR}/*.parquet"
    source_files = sorted(glob.glob(os.path.join(DATA_DIR, "*.parquet")))

    if not source_files:
        raise RuntimeError(
            f"No Parquet files found in '{DATA_DIR}/'. Run `python data_check.py` "
            f"first to download the source data."
        )

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    con = duckdb.connect()

    print(f"Running EDA pipeline against {len(source_files)} file(s) in {DATA_DIR}/ ...")

    # Single full scan: overall counts plus the dataset-level facts needed for
    # run_metadata.json (distinct stations/types, date span). "Operated" means
    # not cancelled -- this is the correct denominator for delay rates, unlike
    # a plain COUNT(*) which would silently include cancelled trains.
    overall_sql = f"""
    SELECT
        COUNT(*) AS total_movements,
        SUM(CASE WHEN is_canceled = False THEN 1 ELSE 0 END) AS operated_trains,
        SUM(CASE WHEN is_canceled = True THEN 1 ELSE 0 END) AS cancelled_trains,
        SUM(CASE WHEN delay_in_min >= {PUNCTUALITY_THRESHOLD_MIN} AND is_canceled = False
            THEN 1 ELSE 0 END) AS delayed_over_threshold,
        COUNT(DISTINCT station_name) AS distinct_stations,
        COUNT(DISTINCT train_type) AS distinct_train_types,
        MIN(CAST(time AS DATE)) AS min_date,
        MAX(CAST(time AS DATE)) AS max_date
    FROM '{data_path}'
    """
    overall_full = run_query(con, "overall", overall_sql)
    overall_full[
        ["total_movements", "operated_trains", "cancelled_trains", "delayed_over_threshold"]
    ].to_parquet(f"{OUTPUT_DIR}/overall.parquet")

    whitelist_sql_list = ", ".join(f"'{t}'" for t in TRAIN_TYPE_WHITELIST)

    # Delay distribution (not just the mean) and cancellation rate, by train type.
    # scheduled_trains is the type's full COUNT(*) (denominator for cancellation
    # rate); operated_trains excludes cancellations (denominator for delay rate).
    type_sql = f"""
    SELECT
        train_type,
        COUNT(*) AS scheduled_trains,
        SUM(CASE WHEN is_canceled = False THEN 1 ELSE 0 END) AS operated_trains,
        SUM(CASE WHEN is_canceled = True THEN 1 ELSE 0 END) AS cancelled_trains,
        SUM(CASE WHEN delay_in_min >= {PUNCTUALITY_THRESHOLD_MIN} AND is_canceled = False
            THEN 1 ELSE 0 END) AS delayed_over_threshold,
        AVG(delay_in_min) FILTER (WHERE is_canceled = False) AS avg_delay_minutes,
        MEDIAN(delay_in_min) FILTER (WHERE is_canceled = False) AS delay_median_min,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY delay_in_min)
            FILTER (WHERE is_canceled = False) AS delay_p90_min,
        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY delay_in_min)
            FILTER (WHERE is_canceled = False) AS delay_p99_min
    FROM '{data_path}'
    WHERE train_type IN ({whitelist_sql_list})
    GROUP BY train_type
    """
    run_query(con, "by_type", type_sql).to_parquet(f"{OUTPUT_DIR}/by_type.parquet")

    # Delay distribution by hour of scheduled departure. departure_planned_time
    # is NULL for a train's final stop on its line (no further departure), so
    # those rows are naturally excluded here.
    hour_sql = f"""
    SELECT
        EXTRACT(hour FROM departure_planned_time) AS hour_of_day,
        COUNT(*) AS operated_trains,
        AVG(delay_in_min) AS avg_delay_minutes,
        MEDIAN(delay_in_min) AS delay_median_min,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY delay_in_min) AS delay_p90_min,
        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY delay_in_min) AS delay_p99_min
    FROM '{data_path}'
    WHERE departure_planned_time IS NOT NULL AND is_canceled = False
    GROUP BY hour_of_day
    ORDER BY hour_of_day
    """
    run_query(con, "by_hour", hour_sql).to_parquet(f"{OUTPUT_DIR}/by_hour.parquet")

    # Delay rate by day of week. Uses `time` (the record's traffic date, never
    # NULL) rather than departure_planned_time, so trains that are a line's
    # final stop are still counted.
    dow_sql = f"""
    SELECT
        ISODOW(time) AS dow_num,
        DAYNAME(time) AS dow_name,
        COUNT(*) AS operated_trains,
        SUM(CASE WHEN delay_in_min >= {PUNCTUALITY_THRESHOLD_MIN} THEN 1 ELSE 0 END)
            AS delayed_over_threshold
    FROM '{data_path}'
    WHERE is_canceled = False
    GROUP BY dow_num, dow_name
    ORDER BY dow_num
    """
    run_query(con, "by_dow", dow_sql).to_parquet(f"{OUTPUT_DIR}/by_dow.parquet")

    # Worst stations by average delay, restricted to high-volume stations so a
    # handful of trains at a small stop can't dominate the ranking.
    station_sql = f"""
    SELECT
        station_name,
        COUNT(*) AS operated_departures,
        AVG(delay_in_min) AS avg_delay_minutes
    FROM '{data_path}'
    WHERE is_canceled = False
    GROUP BY station_name
    HAVING operated_departures > {MIN_STATION_DEPARTURES}
    ORDER BY avg_delay_minutes DESC
    LIMIT 15
    """
    run_query(con, "stations", station_sql).to_parquet(f"{OUTPUT_DIR}/stations.parquet")

    metadata = {
        "total_row_count": int(overall_full["total_movements"].iloc[0]),
        "operated_trains": int(overall_full["operated_trains"].iloc[0]),
        "cancelled_trains": int(overall_full["cancelled_trains"].iloc[0]),
        "distinct_stations": int(overall_full["distinct_stations"].iloc[0]),
        "distinct_train_types": int(overall_full["distinct_train_types"].iloc[0]),
        "min_date": overall_full["min_date"].iloc[0].strftime("%Y-%m-%d"),
        "max_date": overall_full["max_date"].iloc[0].strftime("%Y-%m-%d"),
        "source_file_count": len(source_files),
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    with open(f"{OUTPUT_DIR}/run_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print("\nRun metadata:")
    print(json.dumps(metadata, indent=2))
    print(f"\nEDA complete! Summary files saved to ./{OUTPUT_DIR}")


if __name__ == "__main__":
    try:
        run_eda_pipeline()
    except RuntimeError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)
