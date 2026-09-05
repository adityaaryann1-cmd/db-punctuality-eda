import json
import os

import pandas as pd
import plotly.express as px
import streamlit as st

from config import MIN_STATION_DEPARTURES, OUTPUT_DIR, PUNCTUALITY_THRESHOLD_MIN

st.set_page_config(page_title="DB Punctuality EDA", layout="wide")
st.title("Deutsche Bahn Punctuality: Exploratory Data Analysis")
st.markdown(
    "An independent EDA of partial-year 2026 (Jan-Jul) Deutsche Bahn timetable data, "
    f"analyzing delays against DB's own official punctuality threshold of {PUNCTUALITY_THRESHOLD_MIN} minutes."
)

REQUIRED_FILES = [
    "overall.parquet",
    "by_type.parquet",
    "by_hour.parquet",
    "by_dow.parquet",
    "stations.parquet",
    "run_metadata.json",
]


def interpret_extremes(df, label_col, value_col, unit="", higher_is_worse=True, metric_name="value"):
    """One-sentence takeaway naming the worst/best category and the gap between them."""
    worst_idx = df[value_col].idxmax() if higher_is_worse else df[value_col].idxmin()
    best_idx = df[value_col].idxmin() if higher_is_worse else df[value_col].idxmax()
    worst, best = df.loc[worst_idx], df.loc[best_idx]
    gap = abs(worst[value_col] - best[value_col])
    direction = "highest" if higher_is_worse else "lowest"
    return (
        f"**{worst[label_col]}** has the {direction} {metric_name} at "
        f"{worst[value_col]:.1f}{unit}, vs **{best[label_col]}**'s {best[value_col]:.1f}{unit} "
        f"(the best performer) -- a gap of {gap:.1f}{unit}."
    )


@st.cache_data
def load_data():
    missing = [f for f in REQUIRED_FILES if not os.path.exists(os.path.join(OUTPUT_DIR, f))]
    if missing:
        raise FileNotFoundError(missing)
    frames = {
        "overall": pd.read_parquet(f"{OUTPUT_DIR}/overall.parquet"),
        "type": pd.read_parquet(f"{OUTPUT_DIR}/by_type.parquet"),
        "hour": pd.read_parquet(f"{OUTPUT_DIR}/by_hour.parquet"),
        "dow": pd.read_parquet(f"{OUTPUT_DIR}/by_dow.parquet"),
        "station": pd.read_parquet(f"{OUTPUT_DIR}/stations.parquet"),
    }
    with open(f"{OUTPUT_DIR}/run_metadata.json") as f:
        frames["metadata"] = json.load(f)
    return frames


try:
    data = load_data()
except FileNotFoundError as e:
    missing = e.args[0] if e.args and isinstance(e.args[0], list) else REQUIRED_FILES
    st.error(
        f"Missing summary file(s): {', '.join(missing)}. "
        f"Run `python eda_pipeline.py` first to generate them in `{OUTPUT_DIR}/`."
    )
    st.stop()

overall_df = data["overall"]
type_df = data["type"]
hour_df = data["hour"]
dow_df = data["dow"]
station_df = data["station"]
meta = data["metadata"]

st.caption(
    f"Dataset: {meta['total_row_count']:,} scheduled train movements, "
    f"{meta['min_date']} to {meta['max_date']}, across {meta['distinct_stations']:,} stations "
    f"and {meta['source_file_count']} monthly source files."
)

st.divider()

# --- 1. Baseline ---------------------------------------------------------
st.subheader("1. The Baseline: How often are trains actually late?")

total_movements = overall_df["total_movements"].iloc[0]
operated = overall_df["operated_trains"].iloc[0]
cancelled = overall_df["cancelled_trains"].iloc[0]
delayed = overall_df["delayed_over_threshold"].iloc[0]

delay_rate_pct = (delayed / operated) * 100
cancel_rate_pct = (cancelled / total_movements) * 100

col1, col2, col3 = st.columns(3)
col1.metric("Scheduled Train Movements (incl. cancellations)", f"{total_movements:,.0f}")
col2.metric(
    f"Delayed ≥ {PUNCTUALITY_THRESHOLD_MIN} Min (% of trains that ran)",
    f"{delay_rate_pct:.1f}%",
)
col3.metric("Cancelled (% of scheduled movements)", f"{cancel_rate_pct:.1f}%")
st.caption(
    f"Denominator for the delay rate is **operated trains** ({operated:,.0f}), i.e. scheduled "
    f"movements minus the {cancelled:,.0f} that were cancelled. Cancelled trains have no delay "
    f"value and are excluded from the delay rate, not counted as on-time."
)

st.divider()

# --- 2. Delay rate by train type -----------------------------------------
st.subheader("2. Delay Rates by Train Category")
type_df["delay_rate_pct"] = (type_df["delayed_over_threshold"] / type_df["operated_trains"]) * 100
type_df_sorted = type_df.sort_values("delay_rate_pct", ascending=False)

fig_type = px.bar(
    type_df_sorted, x="train_type", y="delay_rate_pct",
    text_auto=".1f",
    labels={"train_type": "Train Type", "delay_rate_pct": f"% Delayed ≥ {PUNCTUALITY_THRESHOLD_MIN} Min (of operated trains)"},
    color="delay_rate_pct", color_continuous_scale="Reds",
)
fig_type.update_layout(showlegend=False)
st.plotly_chart(fig_type, use_container_width=True)
st.markdown(interpret_extremes(type_df_sorted, "train_type", "delay_rate_pct", unit=" pp", metric_name="delay rate"))

st.divider()

# --- 3. Cancellation rate by train type -----------------------------------
st.subheader("3. Cancellation Rates by Train Category")
type_df["cancellation_rate_pct"] = (type_df["cancelled_trains"] / type_df["scheduled_trains"]) * 100
cancel_df_sorted = type_df.sort_values("cancellation_rate_pct", ascending=False)

fig_cancel = px.bar(
    cancel_df_sorted, x="train_type", y="cancellation_rate_pct",
    text_auto=".1f",
    labels={"train_type": "Train Type", "cancellation_rate_pct": "% Cancelled (of scheduled movements)"},
    color="cancellation_rate_pct", color_continuous_scale="Reds",
)
fig_cancel.update_layout(showlegend=False)
st.plotly_chart(fig_cancel, use_container_width=True)
st.markdown(interpret_extremes(cancel_df_sorted, "train_type", "cancellation_rate_pct", unit=" pp", metric_name="cancellation rate"))

st.divider()

# --- 4. Delay distribution by train type ----------------------------------
st.subheader("4. Delay Distribution by Train Category (Mean Hides the Tail)")
dist_cols = ["train_type", "avg_delay_minutes", "delay_median_min", "delay_p90_min", "delay_p99_min"]
dist_df = type_df[dist_cols].rename(columns={
    "avg_delay_minutes": "Mean", "delay_median_min": "Median",
    "delay_p90_min": "P90", "delay_p99_min": "P99",
})
fig_dist = px.bar(
    dist_df.melt(id_vars="train_type", var_name="Statistic", value_name="Delay (min)"),
    x="train_type", y="Delay (min)", color="Statistic", barmode="group",
    labels={"train_type": "Train Type"},
)
st.plotly_chart(fig_dist, use_container_width=True)
p99_gap = (type_df["delay_p99_min"] - type_df["avg_delay_minutes"]).max()
worst_tail = type_df.loc[(type_df["delay_p99_min"] - type_df["avg_delay_minutes"]).idxmax(), "train_type"]
st.markdown(
    f"For **{worst_tail}**, the 99th-percentile delay is {p99_gap:.1f} minutes above the mean, "
    f"showing the mean alone understates how bad the worst-case delays get for this category."
)

st.divider()

# --- 5. Delays by hour of day ---------------------------------------------
st.subheader("5. Delays by Hour of Day")
fig_hour = px.line(
    hour_df, x="hour_of_day", y=["avg_delay_minutes", "delay_median_min", "delay_p90_min", "delay_p99_min"],
    markers=True,
    labels={"hour_of_day": "Hour of Day (24h)", "value": "Delay (Minutes)", "variable": "Statistic"},
)
fig_hour.add_vrect(x0=7, x1=9, fillcolor="red", opacity=0.1, layer="below", line_width=0)
fig_hour.add_vrect(x0=16, x1=18, fillcolor="red", opacity=0.1, layer="below", line_width=0)
st.plotly_chart(fig_hour, use_container_width=True)
st.markdown(interpret_extremes(hour_df, "hour_of_day", "avg_delay_minutes", unit=" min", metric_name="average delay"))

st.divider()

# --- 6. Delay rate by day of week -----------------------------------------
st.subheader("6. Delay Rate by Day of Week")
dow_df["delay_rate_pct"] = (dow_df["delayed_over_threshold"] / dow_df["operated_trains"]) * 100
dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
dow_df_plot = dow_df.set_index("dow_name").reindex(dow_order).reset_index()

fig_dow = px.bar(
    dow_df_plot, x="dow_name", y="delay_rate_pct",
    text_auto=".1f",
    labels={"dow_name": "Day of Week", "delay_rate_pct": f"% Delayed ≥ {PUNCTUALITY_THRESHOLD_MIN} Min"},
    color="delay_rate_pct", color_continuous_scale="Reds",
)
fig_dow.update_layout(showlegend=False)
st.plotly_chart(fig_dow, use_container_width=True)
st.markdown(interpret_extremes(dow_df, "dow_name", "delay_rate_pct", unit=" pp", metric_name="delay rate"))

st.divider()

# --- 7. Worst stations ------------------------------------------------------
st.subheader("7. The Bottlenecks: Worst Stations for Delays")
st.markdown(f"*Filtered for high-volume stations (>{MIN_STATION_DEPARTURES:,} recorded operated departures).*")

fig_station = px.bar(
    station_df, x="avg_delay_minutes", y="station_name", orientation="h",
    labels={"avg_delay_minutes": "Average Delay (Minutes)", "station_name": "Station"},
    color="avg_delay_minutes", color_continuous_scale="Reds",
)
fig_station.update_layout(yaxis={"categoryorder": "total ascending"})
st.plotly_chart(fig_station, use_container_width=True)
st.markdown(interpret_extremes(station_df, "station_name", "avg_delay_minutes", unit=" min", metric_name="average delay"))
