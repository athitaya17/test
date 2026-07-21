import os
from datetime import datetime, timedelta

import numpy as np
import rasterio
import xarray as xr
from rasterio.transform import from_bounds

from era5_logger import setup_logger
from era5_config import (
    BASE_NC,
    BASE_TIF,
    LOOKBACK_DAYS,
)


# =========================================================
# PATHS
# =========================================================

def instant_nc_path(y, m, d, dstr):
    return f"{BASE_NC}/_raw/{y}/{m}/{d}/instant_{dstr}.nc"


def rh_nc_path(y, m, d, dstr):
    return f"{BASE_NC}/rh/{y}/{m}/{d}/rh_{dstr}.nc"


def rh_tif_path(y, m, d, dstr):
    return f"{BASE_TIF}/{y}/{m}/{d}/rh_{dstr}.tif"


# =========================================================
# HELPERS
# =========================================================

def _time_dim(ds):
    for dim in ds.sizes:
        if "time" in dim.lower():
            return dim
    return "time"


# =========================================================
# RH FORMULA
# =========================================================

def calc_rh(t2m, d2m):

    T = t2m - 273.15
    Td = d2m - 273.15

    rh = (
        100.0
        * np.exp((17.625 * Td) / (243.04 + Td))
        / np.exp((17.625 * T) / (243.04 + T))
    )

    return np.clip(rh, 0, 100).astype(np.float32)


# =========================================================
# NC
# =========================================================

def create_rh_nc(src_nc, out_nc, log):

    if os.path.exists(out_nc):
        log.info(f"RH nc exists: {out_nc}")
        return

    try:

        with xr.open_dataset(src_nc) as ds:

            if "t2m" not in ds:
                log.error("t2m missing")
                return

            if "d2m" not in ds:
                log.error("d2m missing")
                return

            rh = calc_rh(
                ds["t2m"].values,
                ds["d2m"].values
            )

            ds_rh = xr.Dataset(
                {
                    "rh": (
                        ds["t2m"].dims,
                        rh
                    )
                },
                coords=ds.coords
            )

            ds_rh["rh"].attrs = {
                "long_name": "2 metre relative humidity",
                "units": "%"
            }

            os.makedirs(
                os.path.dirname(out_nc),
                exist_ok=True
            )

            tmp = out_nc + ".tmp"

            ds_rh.to_netcdf(tmp)

            os.replace(tmp, out_nc)

            log.info(f"RH nc created: {out_nc}")

    except Exception as e:
        log.error(f"create_rh_nc error: {e}")


# =========================================================
# TIF
# =========================================================

def create_rh_tif(src_nc, out_tif, log):

    try:

        with xr.open_dataset(src_nc) as ds:

            tdim = _time_dim(ds)

            lon = ds.longitude.values
            lat = ds.latitude.values

            flip = lat[0] < lat[-1]

            lat_s = lat[::-1] if flip else lat

            rh = ds["rh"].values.astype(np.float32)

            if flip:
                rh = rh[:, ::-1, :]

            transform = from_bounds(
                lon.min(),
                lat_s.min(),
                lon.max(),
                lat_s.max(),
                len(lon),
                len(lat_s)
            )

            n = ds.sizes[tdim]

            os.makedirs(
                os.path.dirname(out_tif),
                exist_ok=True
            )

            tmp = out_tif + ".tmp"

            with rasterio.open(
                tmp,
                "w",
                driver="GTiff",
                height=len(lat_s),
                width=len(lon),
                count=n,
                dtype="float32",
                crs="EPSG:4326",
                transform=transform,
                compress="LZW",
                nodata=np.nan,
                photometric="MINISBLACK",
            ) as dst:

                for i in range(n):
                    dst.write(rh[i], i + 1)

            os.replace(tmp, out_tif)

            log.info(f"RH tif created: {out_tif}")

    except Exception as e:
        log.error(f"create_rh_tif error: {e}")


# =========================================================
# PROCESS DAY
# =========================================================

def process_day(dt, log):

    y = dt.strftime("%Y")
    m = dt.strftime("%m")
    d = dt.strftime("%d")
    dstr = dt.strftime("%Y%m%d")

    src_nc = instant_nc_path(
        y,
        m,
        d,
        dstr
    )

    if not os.path.exists(src_nc):
        log.warning(f"missing instant nc: {src_nc}")
        return

    out_nc = rh_nc_path(
        y,
        m,
        d,
        dstr
    )

    out_tif = rh_tif_path(
        y,
        m,
        d,
        dstr
    )

    create_rh_nc(
        src_nc,
        out_nc,
        log
    )

    create_rh_tif(
        out_nc,
        out_tif,
        log
    )


# =========================================================
# ENTRY
# =========================================================

def run_rh(execution_date):

    log = setup_logger()

    base = datetime.strptime(
        execution_date,
        "%Y-%m-%d"
    )

    for i in range(LOOKBACK_DAYS):

        dt = base - timedelta(days=i)

        process_day(
            dt,
            log
        )

# =========================================================
# BACKFILL
# =========================================================

def run_rh_backfill(start_date, end_date):

    log = setup_logger()

    start = datetime.strptime(
        start_date,
        "%Y-%m-%d"
    )

    end = datetime.strptime(
        end_date,
        "%Y-%m-%d"
    )

    dt = start

    total = 0

    while dt <= end:

        log.info(
            f"RH backfill: {dt.strftime('%Y-%m-%d')}"
        )

        process_day(
            dt,
            log
        )

        total += 1

        dt += timedelta(days=1)

    log.info(
        f"RH backfill completed ({total} days)"
    )


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    run_rh_backfill(
        "2026-03-01",
        "2026-05-27"
    )
