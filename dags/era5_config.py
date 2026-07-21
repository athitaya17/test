# =========================================================
# era5_config.py
# =========================================================

# =====================================
# PATHS
# =====================================
BASE_NC  = "/opt/airflow/era5/ecmwf/data/nc"
BASE_TIF = "/opt/airflow/era5/ecmwf/data/tif"

# =====================================
# VARIABLES
# long name (CDS) → short name (file)
# =====================================
VAR_MAP = {
    "2m_temperature":           "t2m",
    "2m_dewpoint_temperature":  "d2m",
    "surface_pressure":         "sp",
    "boundary_layer_height":    "blh",
    "10m_u_component_of_wind":  "u10",
    "10m_v_component_of_wind":  "v10",
    "total_precipitation":     "tp",
}

# =====================================
# JOBS
# instant = ค่า ณ เวลานั้น ไม่ต้องแปลง
# accum   = ค่าสะสม ต้องทำ deaccumulation
# rh      = คำนวณจาก t2m + d2m
# =====================================
JOBS = {
    "instant": [
        "2m_temperature",
        "2m_dewpoint_temperature",
        "surface_pressure",
        "boundary_layer_height",
        "10m_u_component_of_wind",
        "10m_v_component_of_wind",
    ],
    "accum": [
        "total_precipitation",
    ],

}

# =====================================
# AREA  [N, W, S, E]
# =====================================
AREA = [28, 91, 0, 112]

# =====================================
# DATASET
# =====================================
DATASET = "reanalysis-era5-single-levels"

# =====================================
# RETRY
# =====================================
MAX_RETRY   = 3
RETRY_SLEEP = 60   # seconds

# =====================================
# LOOKBACK
# ย้อนหลังกี่วัน ต่อ 1 รอบ
# =====================================
LOOKBACK_DAYS = 6