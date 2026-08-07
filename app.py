import streamlit as st
import pandas as pd
import plotly.express as px

# --- PAGE CONFIG ---
st.set_page_config(page_title="DB Punctuality EDA", layout="wide")
st.title("Deutsche Bahn Punctuality: Exploratory Data Analysis")
st.markdown("An independent EDA of partial-year 2026 (Jan-Jul) Deutsche Bahn timetable data, analyzing delays beyond the official 6-minute threshold.")

# --- LOAD EDA DATA ---
@st.cache_data
def load_data():
    overall_df = pd.read_parquet("eda_results/overall.parquet")
    type_df = pd.read_parquet("eda_results/by_type.parquet")
    hour_df = pd.read_parquet("eda_results/by_hour.parquet")
    station_df = pd.read_parquet("eda_results/stations.parquet")
    return overall_df, type_df, hour_df, station_df

try:
    overall_df, type_df, hour_df, station_df = load_data()
except FileNotFoundError:
    st.error("Data not found. Please run `python eda_pipeline.py` first.")
    st.stop()

# --- 1. OVERALL PUNCTUALITY ---
st.subheader("1. The Baseline: How often are trains actually late?")
total = overall_df['total_trains'].iloc[0]
late = overall_df['delayed_over_6'].iloc[0]
cancelled = overall_df['cancelled_trains'].iloc[0]

late_pct = (late / total) * 100
canc_pct = (cancelled / total) * 100

col1, col2, col3 = st.columns(3)
col1.metric("Total Train Movements Processed", f"{total:,.0f}")
col2.metric("Delayed ≥ 6 Minutes", f"{late_pct:.1f}%")
col3.metric("Cancelled", f"{canc_pct:.1f}%")

st.divider()

# --- 2. TRAIN TYPES ---
st.subheader("2. Delay Rates by Train Category")
# Calculate the percentage of delayed trains within each specific train type
type_df['delay_rate_pct'] = (type_df['delayed_over_6'] / type_df['volume']) * 100
type_df = type_df.sort_values('delay_rate_pct', ascending=False)

fig_type = px.bar(
    type_df, x='train_type', y='delay_rate_pct', 
    text_auto='.1f',
    labels={'train_type': 'Train Type', 'delay_rate_pct': '% Delayed ≥ 6 Min'},
    color='delay_rate_pct', color_continuous_scale='Reds'
)
fig_type.update_layout(showlegend=False)
st.plotly_chart(fig_type, use_container_width=True)

st.divider()

# --- 3. THE RUSH HOUR EFFECT ---
st.subheader("3. Average Delays by Hour of Day")
fig_hour = px.line(
    hour_df, x='hour_of_day', y='avg_delay_minutes',
    markers=True,
    labels={'hour_of_day': 'Hour of Day (24h)', 'avg_delay_minutes': 'Average Delay (Minutes)'}
)
# Add red shading to highlight typical commuter rush hours (7-9 AM and 4-6 PM)
fig_hour.add_vrect(x0=7, x1=9, fillcolor="red", opacity=0.1, layer="below", line_width=0)
fig_hour.add_vrect(x0=16, x1=18, fillcolor="red", opacity=0.1, layer="below", line_width=0)
st.plotly_chart(fig_hour, use_container_width=True)

st.divider()

# --- 4. STATION BOTTLENECKS ---
st.subheader("4. The Bottlenecks: Worst Stations for Delays")
st.markdown("*Filtered for high-volume stations (>5,000 recorded departures).*")

# Note: Using the corrected 'station_name' column here!
fig_station = px.bar(
    station_df, x='avg_delay_minutes', y='station_name', orientation='h',
    labels={'avg_delay_minutes': 'Average Delay (Minutes)', 'station_name': 'Station'},
    color='avg_delay_minutes', color_continuous_scale='Reds'
)
# Sort the bars so the worst station is at the top
fig_station.update_layout(yaxis={'categoryorder':'total ascending'})
st.plotly_chart(fig_station, use_container_width=True)