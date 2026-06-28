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
    # PARCHE MAESTRO DE RED: Usamos la IP numérica directa de la NASA para saltarnos el error de DNS de GitHub
    url = f"https://169.154.128{MAP_KEY}/{source}/{BBOX}/{DAYS}"
    print(f"\n[INFO] Conectando vía IP directa a la NASA para: {source}...")
    
    # Es obligatorio inyectar el Host original en las cabeceras para que la IP funcione mediante HTTPS
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Host": "firms.modaps.eosdis.nasa.gov"
    }
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=45) as response:
            df = pd.read_csv(response)
        
        if df.empty:
            print(f"[AVISO] {source}: Respuesta vacía de la NASA.")
            return pd.DataFrame()
            
        print(f"[ÉXITO] {source}: Descargadas {len(df)} detecciones.")
        
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
            df["satellite"].astype(str) + "|" + df["latitude"].astype(str) + "|" +
            df["longitude"].astype(str) + "|" + df["acq_date"].astype(str) + "|" +
            df["acq_time"].astype(str) + "|" + df["instrument"].astype(str)
        )
        return df
        
    except Exception as e:
        print(f"[ERROR DE RED] Fallo en {source}: {e}", file=sys.stderr)
        return pd.DataFrame()

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    frames = []

    for source in SOURCES:
        df = download_source(source)
        if not df.empty:
            frames.append(df)
        time.sleep(3)

    if not frames:
        print("\n[FIN] No hay datos en esta ejecucion debido al bloqueo de red.")
        sys.exit(1)

    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["detection_id"])
    df_all = df_all.sort_values(by=["acq_date", "acq_time", "frp_num"], ascending=[False, False, False])

    gdf = gpd.GeoDataFrame(
        df_all,
        geometry=gpd.points_from_xy(df_all["longitude"], df_all["latitude"]),
        crs="EPSG:4326"
    )

    gdf.to_file(OUT_GEOJSON, driver="GeoJSON")
    print(f"\n[OK] Archivo 'fires.geojson' generado. Total: {len(gdf)}")

if __name__ == "__main__":
    main()
