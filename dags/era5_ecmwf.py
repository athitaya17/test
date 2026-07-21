from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import subprocess

default_args = {
    "owner": "era5",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

def run_download():
    subprocess.run(
        ["python", "/opt/airflow/scripts/download_era5.py"],
        check=True,
        capture_output=False
    )

with DAG(
    dag_id="era5_ecmwf_download",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["ERA5", "ECMWF"],
) as dag:

    download_task = PythonOperator(
        task_id="download_era5",
        python_callable=run_download,
    )