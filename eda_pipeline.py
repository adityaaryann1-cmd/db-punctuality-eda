import os
import duckdb

def run_eda_pipeline():
    data_path = "db_data_2026/*.parquet"
    out_dir = "eda_results"
    os.makedirs(out_dir, exist_ok=True)

    print("Running EDA GroupBys on 2026 dataset...")

    # 1. Overall Punctuality (The 6-min rule baseline)
    query_overall = f"""
    SELECT 
        COUNT(*) as total_trains,
        SUM(CASE WHEN delay_in_min >= 6 AND is_canceled = False THEN 1 ELSE 0 END) as delayed_over_6,
        SUM(CAST(is_canceled AS INT)) as cancelled_trains
    FROM '{data_path}'
    """
    duckdb.sql(query_overall).df().to_parquet(f"{out_dir}/overall.parquet")

    # 2. Delay by Train Type (Filter out noise, keep main types)
    query_type = f"""
    SELECT 
        train_type,
        COUNT(*) as volume,
        SUM(CASE WHEN delay_in_min >= 6 AND is_canceled = False THEN 1 ELSE 0 END) as delayed_over_6
    FROM '{data_path}'
    WHERE train_type IN ('ICE', 'IC', 'EC', 'RE', 'RB', 'S')
    GROUP BY train_type
    """
    duckdb.sql(query_type).df().to_parquet(f"{out_dir}/by_type.parquet")

# 3. Delay by Hour of Day (The Rush Hour Effect)
    query_hour = f"""
    SELECT 
        EXTRACT(hour FROM departure_planned_time) as hour_of_day,
        AVG(delay_in_min) as avg_delay_minutes
    FROM '{data_path}'
    WHERE departure_planned_time IS NOT NULL AND is_canceled = False
    GROUP BY hour_of_day
    ORDER BY hour_of_day
    """
    duckdb.sql(query_hour).df().to_parquet(f"{out_dir}/by_hour.parquet")

# 4. Worst Stations by Average Delay (Minimum 5000 trains to avoid statistical noise)
    query_station = f"""
    SELECT 
        station_name,
        COUNT(*) as total_departures,
        AVG(delay_in_min) as avg_delay_minutes
    FROM '{data_path}'
    WHERE is_canceled = False
    GROUP BY station_name
    HAVING total_departures > 5000
    ORDER BY avg_delay_minutes DESC
    LIMIT 15
    """
    duckdb.sql(query_station).df().to_parquet(f"{out_dir}/stations.parquet")

    print(f"EDA Complete! Summary files saved to ./{out_dir}")

if __name__ == "__main__":
    run_eda_pipeline()