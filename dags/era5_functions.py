# =========================================================
# era5_function.py
# ERA5 Incremental Sync Pipeline
# =========================================================

import os
import time
import tempfile
from datetime import datetime, timedelta

import cdsapi
import numpy as np
import rasterio
import xarray as xr

from rasterio.transform import from_bounds

from era5_logger import setup_logger

from era5_config import (
    BASE_NC, BASE_TIF, VAR_MAP, JOBS, AREA, DATASET,
    MAX_RETRY, RETRY_SLEEP, LOOKBACK_DAYS,
)


# =========================================================
# PATH
# =========================================================

def nc_path(date, job):
    return f"{BASE_NC}/_raw/{date:%Y/%m/%d}/{job}_{date:%Y%m%d}.nc"


def tif_path(date, short):
    return f"{BASE_TIF}/{date:%Y/%m/%d}/{short}_{date:%Y%m%d}.tif"


# =========================================================
# TIME
# =========================================================

def get_time_dim(ds):
    for dim in ds.sizes:
        if "time" in dim.lower():
            return dim
    raise ValueError("Time dimension not found")


def normalize_times(values):
    return [
        np.datetime64(t, "h").astype("datetime64[s]").astype(datetime)
        for t in values
    ]


# =========================================================
# DOWNLOAD CDS
# =========================================================

def load_cds(client, date, variables, log):
    params = {
        "product_type": "reanalysis",
        "year": date.strftime("%Y"),
        "month": date.strftime("%m"),
        "day": date.strftime("%d"),
        "time": [f"{h:02d}:00" for h in range(24)],
        "area": AREA,
        "format": "netcdf",
        "variable": variables,
    }

    fd, tmp = tempfile.mkstemp(suffix=".nc")
    os.close(fd)

    try:
        for attempt in range(1, MAX_RETRY + 1):
            try:
                log.info(f"CDS download {date:%Y-%m-%d} attempt {attempt}/{MAX_RETRY}")

                client.retrieve(DATASET, params, tmp)

                with xr.open_dataset(tmp, decode_times=True) as ds:
                    ds = ds.load()

                time_dim = get_time_dim(ds)

                log.info(f"CDS available: {date:%Y-%m-%d} | {ds.sizes[time_dim]} timestep(s)")

                return ds

            except Exception as e:
                error = str(e)

                # -------------------------------------------------
                # CDS ยังไม่มีข้อมูลวันนั้น ไม่ต้อง retry
                # -------------------------------------------------
                if "None of the data you have requested is available yet" in error:
                    log.info(f"CDS data not available yet: {date:%Y-%m-%d}")
                    return None

                # -------------------------------------------------
                # Error อื่น เช่น network / 502 ให้ retry
                # -------------------------------------------------
                log.warning(f"CDS download failed: {error}")

                if attempt < MAX_RETRY:
                    time.sleep(RETRY_SLEEP)

        return None

    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# =========================================================
# SYNC ONE DATE
# =========================================================

def sync_date(client, job, date, log):
    variables = JOBS[job]
    nc = nc_path(date, job)

    log.info(f"--- SYNC {job} {date:%Y%m%d} ---")

    # -----------------------------------------------------
    # 1. โหลดข้อมูลล่าสุดจาก CDS
    # -----------------------------------------------------
    cds = load_cds(client, date, variables, log)

    if cds is None:
        return

    cds_time_dim = get_time_dim(cds)
    cds_times = set(normalize_times(cds[cds_time_dim].values))

    # -----------------------------------------------------
    # 2. อ่าน timestep ที่มีอยู่ใน Local
    # -----------------------------------------------------
    local_times = set()

    if os.path.exists(nc):
        try:
            with xr.open_dataset(nc, decode_times=True) as local:
                local_time_dim = get_time_dim(local)
                local_times = set(normalize_times(local[local_time_dim].values))

        except Exception as e:
            log.warning(f"Cannot read local NC: {e}")

    # -----------------------------------------------------
    # 3. หา timestep ใหม่
    # -----------------------------------------------------
    new_times = sorted(cds_times - local_times)

    if not new_times:
        log.info("No new timestep")
        cds.close()
        return

    log.info(f"New timestep: {len(new_times)}")

    new_ds = cds.sel({cds_time_dim: [np.datetime64(t) for t in new_times]})

    # -----------------------------------------------------
    # 4. รวมข้อมูลใหม่เข้ากับ NC เดิม
    # -----------------------------------------------------
    tmp_nc = nc + ".tmp"
    merged = None

    try:
        if os.path.exists(nc):
            with xr.open_dataset(nc, decode_times=True) as old:
                old = old.load()

            merged = xr.concat([old, new_ds], dim=cds_time_dim)

        else:
            merged = new_ds.load()

        merged = merged.sortby(cds_time_dim).drop_duplicates(cds_time_dim)

        os.makedirs(os.path.dirname(nc), exist_ok=True)

        merged.to_netcdf(tmp_nc)
        os.replace(tmp_nc, nc)

        log.info(f"NC updated: {nc} | {merged.sizes[cds_time_dim]} timestep(s)")

    except Exception as e:
        log.error(f"NC update failed: {e}")

        if os.path.exists(tmp_nc):
            os.remove(tmp_nc)

        return

    finally:
        if merged is not None:
            try:
                merged.close()
            except Exception:
                pass

        cds.close()

    # -----------------------------------------------------
    # 5. สร้าง TIF ใหม่ให้ตรงกับ NC
    # -----------------------------------------------------
    convert_tif(nc, variables, date, log)


# =========================================================
# CONVERT NC → TIF
# =========================================================

def convert_tif(nc, variables, date, log):
    try:
        with xr.open_dataset(nc, decode_times=True) as ds:
            time_dim = get_time_dim(ds)
            n = ds.sizes[time_dim]

            lon = ds.longitude.values
            lat = ds.latitude.values

            flip = lat[0] < lat[-1]

            if flip:
                lat = lat[::-1]

            transform = from_bounds(
                float(lon.min()), float(lat.min()),
                float(lon.max()), float(lat.max()),
                len(lon), len(lat),
            )

            for variable in variables:
                short = VAR_MAP[variable]

                if short not in ds:
                    log.warning(f"Variable not found: {short}")
                    continue

                data = ds[short].values.astype(np.float32)

                if flip:
                    data = data[:, ::-1, :]

                out = tif_path(date, short)
                tmp_tif = out + ".tmp"

                os.makedirs(os.path.dirname(out), exist_ok=True)

                with rasterio.open(
                    tmp_tif, "w",
                    driver="GTiff",
                    height=len(lat),
                    width=len(lon),
                    count=n,
                    dtype="float32",
                    crs="EPSG:4326",
                    transform=transform,
                    compress="LZW",
                    nodata=np.nan,
                ) as dst:
                    for band in range(n):
                        dst.write(data[band], band + 1)

                os.replace(tmp_tif, out)

                log.info(f"TIF updated: {short} | bands={n}")

    except Exception as e:
        log.error(f"TIF conversion failed: {e}")


# =========================================================
# ENTRY POINT
# =========================================================

def run_era5(job_name, date_str=None):
    if job_name not in JOBS:
        raise ValueError(f"Unknown job: {job_name}")

    client = cdsapi.Client()
    log = setup_logger()

    # -----------------------------------------------------
    # กรณี Backfill รับวันที่จาก backfill.py
    # -----------------------------------------------------
    if date_str:
        date = datetime.strptime(date_str, "%Y-%m-%d")

        log.info(f"=== START ERA5 BACKFILL job={job_name} date={date_str} ===")

        sync_date(client, job_name, date, log)

        log.info(f"=== END ERA5 BACKFILL job={job_name} date={date_str} ===")

        return

    # -----------------------------------------------------
    # กรณี Airflow ปกติ ตรวจย้อนหลัง 6 วัน
    # -----------------------------------------------------
    latest_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    log.info(f"=== START ERA5 SYNC job={job_name} ===")

    for i in range(LOOKBACK_DAYS):
        date = latest_date - timedelta(days=i)
        sync_date(client, job_name, date, log)

    log.info(f"=== END ERA5 SYNC job={job_name} ===")