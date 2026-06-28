import os
import time
import urllib.request
from datetime import datetime, timezone

import pandas as pd
import geopandas as gpd

MAP_KEY = "c7b328641d071d4f5e429e28f3f1c07d"
BBOX = "22,44,41,53"
DAYS = 5

SOURCES = [
    "VIIRS_NOAA21_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_SNPP_NRT",
]

OUT_DIR = "."
OUT_GPKG = os.path.join(OUT_DIR, "fires.gpkg")
LAYER_NAME = "fires"

def download_source(source):
    url = f"https://nasa.gov{MAP_KEY}/{source}/{BBOX}/{DAYS}"
    print(f"\nConsultando: {url}")
    
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        df = pd.read_csv(response)

    if df.empty:
        print(f"{source}: sin detecciones")
        return df

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    df["source_query"] = source
    df["download_time_utc"] = now_utc
    df["acq_time_str"] = df["acq_time"].astype(str).str.zfill(4)

    df["detection_time_utc"] = (
        df["acq_date"].astype(str)
        + " "
        + df["acq_time_str"].str[:2]
        + ":"
        + df["acq_time_str"].str[2:]
        + ":00 UTC"
    )

    df["frp_num"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0)

    df["detection_id"] = (
        df["satellite"].astype(str)
        + "|"
        + df["latitude"].astype(str)
        + "|"
        + df["longitude"].astype(str)
        + "|"
        + df["acq_date"].astype(str)
        + "|"
        + df["acq_time"].astype(str)
        + "|"
        + df["instrument"].astype(str)
    )

    print(f"{source}: {len(df)} detecciones")
    return df

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    frames = []

    for source in SOURCES:
        try:
            df = download_source(source)
            if not df.empty:
                frames.append(df)
            time.sleep(2)
        except Exception as e:
            print(f"ERROR en {source}: {e}")

    if not frames:
        print("\nNo se encontraron detecciones en la API.")
        return

    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["detection_id"])
    df_all = df_all.sort_values(by=["acq_date", "acq_time", "frp_num"], ascending=[False, False, False])

    gdf = gpd.GeoDataFrame(
        df_all,
        geometry=gpd.points_from_xy(df_all["longitude"], df_all["latitude"]),
        crs="EPSG:4326"
    )

    # PARCHE CLAVE: Forzamos el motor 'fiona' para evitar que Linux aborte la creación del gpkg
    try:
        import fiona
        gdf.to_file(OUT_GPKG, layer=LAYER_NAME, driver="GPKG", engine="fiona")
    except ImportError:
        gdf.to_file(OUT_GPKG, layer=LAYER_NAME, driver="GPKG")

    print(f"\nGeoPackage generado con éxito en la nube. Total único: {len(gdf)}")

if __name__ == "__main__":
    main()
