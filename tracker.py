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
    print(f"\n[INFO] Conectando a la NASA para: {source}...")
    
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    
    # CONTROL REAL: Si la NASA cuelga o da error, se imprime en la consola para saber qué pasa
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            df = pd.read_csv(response)
        
        if df.empty:
            print(f"[AVISO] {source}: Respuesta vacía de la NASA.")
            return pd.DataFrame()
            
        print(f"[ÉXITO] {source}: Descargadas {len(df)} detecciones reales.")
        
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
        print(f"[ERROR CRÍTICO] Fallo de red en {source}: {e}", file=sys.stderr)
        return pd.DataFrame()

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    frames = []

    for source in SOURCES:
        df = download_source(source)
        if not df.empty:
            frames.append(df)
        time.sleep(3)  # Más margen de espera para el servidor de la nube

    if not frames:
        print("\n[FIN] El flujo se detiene: Ninguno de los 3 satélites ha devuelto datos en la nube hoy.")
        # Salida controlada para que el YML sepa por qué no hay archivo
        sys.exit(0)

    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["detection_id"])
    df_all = df_all.sort_values(by=["acq_date", "acq_time", "frp_num"], ascending=[False, False, False])

    gdf = gpd.GeoDataFrame(
        df_all,
        geometry=gpd.points_from_xy(df_all["longitude"], df_all["latitude"]),
        crs="EPSG:4326"
    )

    # Guardamos en GeoJSON (texto plano inmune a los drivers corruptos de Linux)
    gdf.to_file(OUT_GEOJSON, driver="GeoJSON")
    print(f"\n[OK] Archivo 'fires.geojson' creado con éxito. Registros: {len(gdf)}")

if __name__ == "__main__":
    main()
