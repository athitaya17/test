# =========================================================
# era5_logger.py
# =========================================================

import logging
import os

LOG_DIR  = "/opt/airflow/era5/logs"
LOG_FILE = os.path.join(LOG_DIR, "era5.log")


def setup_logger() -> logging.Logger:
    """
    log รวมไฟล์เดียว era5.log
    ต่อท้ายทุกครั้งที่รัน ไม่ลบทิ้ง
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger("era5")

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        fmt     = "%(asctime)s [%(levelname)s] %(message)s",
        datefmt = "%Y-%m-%d %H:%M:%S",
    )

    # console
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # file — รวมอันเดียว ต่อท้ายเรื่อยๆ
    fh = logging.FileHandler(
        LOG_FILE,
        mode     = "a",
        encoding = "utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger