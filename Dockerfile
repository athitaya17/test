FROM apache/airflow:2.9.1

USER root

RUN apt-get update && apt-get install -y \
    libgfortran5 \
    libeccodes-dev \
    && rm -rf /var/lib/apt/lists/*

USER airflow

RUN pip install --no-cache-dir \
    geopandas==1.0.1 \
    shapely==2.0.6 \
    pyproj==3.7.0 \
    netCDF4==1.7.2 \
    numpy==1.26.4 \
    psycopg2-binary==2.9.9 \
    rasterio==1.3.10 \
    rioxarray \
    herbie-data \
    cfgrib \
    eccodes \
    xarray \
    cdsapi \
    h5netcdf