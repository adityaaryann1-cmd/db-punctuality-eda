"""Central configuration for the DB punctuality EDA project.

Single source of truth for values shared between data_check.py, eda_pipeline.py
and app.py, so a change (e.g. adding a month) only has to happen in one place.
"""

# Deutsche Bahn's own definition of punctuality: a train is counted as "on
# time" if it departs/arrives less than 6 minutes after the scheduled time.
# This is DB's official reporting threshold, not an arbitrary cutoff chosen
# for this project, so delay rates here are directly comparable to DB's own
# published punctuality figures.
PUNCTUALITY_THRESHOLD_MIN = 6

# Stations need a minimum volume before their average delay is meaningful;
# below this a handful of extreme delays can swing the average sharply.
MIN_STATION_DEPARTURES = 5000

# The raw data contains ~100 train_type codes, including replacement buses
# and rare regional services. Restrict breakdowns to the passenger rail
# categories a general audience recognizes.
TRAIN_TYPE_WHITELIST = ["ICE", "IC", "EC", "RE", "RB", "S"]

DATA_DIR = "db_data_2026"
OUTPUT_DIR = "eda_results"

DATA_YEAR = 2026
DATA_MONTHS = [f"{m:02d}" for m in range(1, 8)]  # Jan-Jul 2026, the range currently published

HF_BASE_URL = "https://huggingface.co/datasets/piebro/deutsche-bahn-data/resolve/main/monthly_processed_data"

# Real monthly files are ~550-650MB; anything far smaller indicates a
# truncated/failed download that should be re-fetched rather than reused.
MIN_EXPECTED_FILE_SIZE_BYTES = 100 * 1024 * 1024
