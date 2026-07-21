import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(
    0,
    "/opt/airflow/dags"
)

from era5_functions import run_era5


START = datetime(2026, 6, 25)
END   = datetime(2026, 7, 11)


for i in range((END - START).days + 1):

    date = START + timedelta(days=i)

    print(
        f"=== processing "
        f"{date:%Y-%m-%d} ===",
        flush=True
    )

    try:

        run_era5(
            "instant",
            date.strftime("%Y-%m-%d")
        )

        run_era5(
            "accum",
            date.strftime("%Y-%m-%d")
        )

    except Exception as e:

        print(
            f"[ERROR] "
            f"{date:%Y-%m-%d}: {e}",
            flush=True
        )

        # รอแล้วค่อยไปวันถัดไป
        time.sleep(60)

        continue