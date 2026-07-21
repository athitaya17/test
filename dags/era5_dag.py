# =========================================================
# dag_era5.py
# Airflow DAG — ERA5 download pipeline
# schedule: ทุก 1 ชั่วโมง
# =========================================================

import sys
sys.path.insert(0, "/opt/airflow/dags")

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from era5_functions import run_era5
from era5_rh import run_rh

# =========================================================
# DEFAULT ARGS
# =========================================================

default_args = {
    "owner":            "era5",
    "retries":          0,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
    "email_on_retry":   False,
    "depends_on_past":  False,
    "execution_timeout": timedelta(minutes=60),
}


# =========================================================
# DAG
# =========================================================

with DAG(
    dag_id            = "era5_download_pipeline",
    # description       = "ดาวน์โหลด ERA5 จาก CDS ทุก 1 ชั่วโมง",
    default_args      = default_args,
    start_date        = datetime(2024, 1, 1),
    schedule_interval = "@hourly",
    catchup           = False,
    max_active_runs   = 1,
    tags              = ["era5", "ecmwf", "climate"],
) as dag:

    # --------------------------------------------------
    # Task: instant
    # d2m, t2m, u10, v10, blh, sp
    # ค่า ณ เวลานั้น ไม่ต้องแปลง
    # --------------------------------------------------
    task_instant = PythonOperator(
        task_id         = "era5_instant",
        python_callable = run_era5,
        op_kwargs       = {
            "job_name":       "instant",
        },
    )

#     era5_rh = PythonOperator(
#         task_id="era5_rh",
#         python_callable=run_rh,
#         op_kwargs={
#         "execution_date": "{{ ds }}"
#     },
# )

    # --------------------------------------------------
    # Task: accum
    # tp — ฝนสะสม ต้องทำ deaccumulation ก่อนใช้
    # --------------------------------------------------
    task_accum = PythonOperator(
        task_id         = "era5_accum",
        python_callable = run_era5,
        op_kwargs       = {
            "job_name":       "accum",
        },
    )


    # instant ก่อน แล้วค่อย accum
    task_instant >> task_accum