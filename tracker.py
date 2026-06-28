import os
import time
import urllib.request
import sys
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
OUT_GEOJSON = os.path.join(OUT_DIR, "fires.geojson")

def download_source(source):
    url = f"https://nasa.gov{MAP_KEY}/{source}/{BBOX}/{DAYS}"
    print(f"[INFO] Conectando a la NASA para: {source}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            df = pd.read_csv(response)
        if df.empty:
            return pd.DataFrame()
        
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        df["source_query"] = source
        df["download_time_utc"] = now_utc
        df["acq_time_str"] = df["acq_time"].astype(str).str.zfill(4)
        df["detection_time_utc"] = (
            df["acq_date"].astype(str) + " " + df["acq_time_str"].str[:2] + ":" + df["acq_time_str"].str[2:] + ":00 UTC"
        )
        df["frp_num"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0)
        df["detection_id"] = (
            df["satellite"].astype(str) + "|" + df["latitude"].astype(str) + "|" +
            df["longitude"].astype(str) + "|" + df["acq_date"].astype(str) + "|" +
            df["acq_time"].astype(str) + "|" + df["instrument"].astype(str)
        )
        return df
    except Exception as e:
        print(f"[ERROR] {source}: {e}")
        return pd.DataFrame()

def main():
    frames = []
    for source in SOURCES:
        df = download_source(source)
        if not df.empty:
            frames.append(df)
        time.sleep(2)

    if not frames:
        print("No se encontraron detecciones.")
        sys.exit(1)

    df_all = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["detection_id"])
    gdf = gpd.GeoDataFrame(df_all, geometry=gpd.points_from_xy(df_all["longitude"], df_all["latitude"]), crs="EPSG:4326")
    gdf.to_file(OUT_GEOJSON, driver="GeoJSON")
    print(f"[OK] Archivo generado con {len(gdf)} filas.")

if __name__ == "__main__":
    main()
