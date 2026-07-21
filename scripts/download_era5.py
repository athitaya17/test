import cdsapi
import xarray as xr
import rioxarray
import rasterio
from rasterio.transform import from_bounds

import numpy as np
import os
import time

from datetime import datetime, timedelta


# =========================================
# MAIN
# =========================================
def main():

    # =====================================
    # DATE
    # =====================================
    DATE = datetime.utcnow() - timedelta(days=7)

    Y = DATE.strftime("%Y")
    M = DATE.strftime("%m")
    D = DATE.strftime("%d")
    DSTR = f"{Y}{M}{D}"

    # =====================================
    # PATH
    # =====================================
    BASE_NC = "/opt/airflow/data//era5/ecmwf/nc"
    BASE_TIF = "/opt/airflow/data//era5/ecmwf/tif"

    RAW = os.path.join(
        BASE_NC,
        "_raw",
        Y,
        M,
        D
    )

    os.makedirs(RAW, exist_ok=True)

    # =====================================
    # VARIABLES
    # =====================================
    VAR_MAP = {
        "2m_temperature": "t2m",
        "2m_dewpoint_temperature": "d2m",
        "surface_pressure": "sp",
        "boundary_layer_height": "blh",
        "10m_u_component_of_wind": "u10",
        "10m_v_component_of_wind": "v10",
        "total_precipitation": "tp",
    }

    # =====================================
    # COMMON REQUEST
    # =====================================
    COMMON = {
        "product_type": "reanalysis",

        "year": Y,
        "month": M,
        "day": D,

        "time": [
            f"{h:02d}:00"
            for h in range(24)
        ],

        # SEA
        "area": [28, 91, 0, 112],

        "format": "netcdf",
    }

    # =====================================
    # ECMWF CLIENT
    # =====================================
    client = cdsapi.Client()

    # =====================================
    # JOBS
    # =====================================
    JOBS = [

        {
            "name": "instant",

            "path": os.path.join(
                RAW,
                f"instant_{DSTR}.nc"
            ),

            "dataset": "reanalysis-era5-single-levels",

            "params": {
                **COMMON,

                "variable": [
                    v for v in VAR_MAP
                    if v != "total_precipitation"
                ]
            },

            "varmap": {
                v: VAR_MAP[v]
                for v in VAR_MAP
                if v != "total_precipitation"
            }
        },

        {
            "name": "accum",

            "path": os.path.join(
                RAW,
                f"accum_{DSTR}.nc"
            ),

            "dataset": "reanalysis-era5-single-levels",

            "params": {
                **COMMON,

                "variable": [
                    "total_precipitation"
                ]
            },

            "varmap": {
                "total_precipitation": "tp"
            }
        }
    ]

    # =====================================
    # LOOP JOBS
    # =====================================
    for job in JOBS:

        print("=" * 60)
        print("JOB:", job["name"])
        print("=" * 60)

        success = False

        for retry in range(5):

            try:

                print(f"TRY {retry+1}/5")

                # =================================
                # REMOVE OLD
                # =================================
                if os.path.exists(job["path"]):

                    os.remove(job["path"])

                # =================================
                # DOWNLOAD
                # =================================
                print("DOWNLOAD START")

                client.retrieve(
                    job["dataset"],
                    job["params"],
                    job["path"]
                )

                print("DOWNLOAD COMPLETE")

                # =================================
                # OPEN
                # =================================
                ds = xr.open_dataset(
                    job["path"],
                    decode_times=False
                )

                # =================================
                # TIME DIM
                # =================================
                time_dim = (
                    "valid_time"
                    if "valid_time" in ds.dims
                    else "time"
                )

                ntime = ds.sizes[time_dim]

                print("TIMESTEPS:", ntime)

                if ntime != 24:

                    raise ValueError(
                        f"Incomplete data: {ntime}"
                    )

                # =================================
                # LOOP VARIABLES
                # =================================
                for v, short in job["varmap"].items():

                    print(f"\nVARIABLE: {v}")

                    if short not in ds:

                        print("SKIP:", short)

                        continue

                    # =============================
                    # LOOP HOURS
                    # =============================
                    for h in range(24):

                        try:

                            print(f"HOUR {h:02d}")

                            # =====================
                            # OUTPUT PATH
                            # =====================
                            out_nc = os.path.join(
                                BASE_NC,
                                v,
                                Y,
                                M,
                                D,
                                f"{h:02d}",
                                f"{v}_{DSTR}_{h:02d}.nc"
                            )

                            out_tif = os.path.join(
                                BASE_TIF,
                                v,
                                Y,
                                M,
                                D,
                                f"{h:02d}",
                                f"{v}_{DSTR}_{h:02d}.tif"
                            )

                            os.makedirs(
                                os.path.dirname(out_nc),
                                exist_ok=True
                            )

                            os.makedirs(
                                os.path.dirname(out_tif),
                                exist_ok=True
                            )

                            # =====================
                            # SELECT HOUR
                            # =====================
                            da = ds[short].isel(
                                {time_dim: h}
                            )

                            # =====================
                            # FLOAT32
                            # =====================
                            da = da.astype(np.float32)

                            # =====================
                            # SAVE NC
                            # =====================
                            da.to_dataset(
                                name=short
                            ).to_netcdf(out_nc)

                            print("NC OK")

                            # =====================
                            # GET COORDS
                            # =====================
                            lon = da.longitude.values
                            lat = da.latitude.values

                            data = da.values

                            # =====================
                            # FLIP LAT
                            # =====================
                            if lat[0] > lat[-1]:

                                lat = lat[::-1]
                                data = np.flipud(data)

                            # =====================
                            # TRANSFORM
                            # =====================
                            transform = from_bounds(
                                lon.min(),
                                lat.min(),
                                lon.max(),
                                lat.max(),
                                len(lon),
                                len(lat)
                            )

                            # =====================
                            # SAVE TIF
                            # =====================

                            # rename dims
                            hourly_tif = da.rename({
                                "longitude": "x",
                                "latitude": "y"
                            })

                            # remove extra dims
                            hourly_tif = hourly_tif.squeeze()

                            # float32
                            hourly_tif = hourly_tif.astype("float32")

                            # ERA5 latitude ต้องเรียงจากบนลงล่าง (descending) สำหรับ raster
                            if hourly_tif.y.values[0] < hourly_tif.y.values[-1]:
                                hourly_tif = hourly_tif.sortby("y", ascending=False)

                            # spatial dims
                            hourly_tif = hourly_tif.rio.set_spatial_dims(
                                x_dim="x",
                                y_dim="y"
                            )

                            # CRS
                            hourly_tif = hourly_tif.rio.write_crs("EPSG:4326")

                            # export tif
                            hourly_tif.rio.to_raster(out_tif)

                            print("TIF SAVED:", out_tif)

                            print("TIF SAVED:", out_tif)
                        except Exception as e:

                            print(
                                f"TIF ERROR {v} {h:02d}:",
                                e
                            )

                ds.close()

                success = True

                print("JOB COMPLETE")

                break

            except Exception as e:

                print("JOB ERROR:", e)

                time.sleep(60)

        if not success:

            raise RuntimeError(
                f"FAILED JOB: {job['name']}"
            )

    print("=" * 60)
    print("ERA5 PIPELINE COMPLETE")
    print("=" * 60)


# =========================================
# RUN
# =========================================
if __name__ == "__main__":

    main()