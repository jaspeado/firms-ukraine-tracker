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
OUT_GEOJSON = os.path.join(OUT_DIR, "fires.geojson")

def download_source(source):
    # 1. Tu URL original de la API
    url_api = f"https://nasa.gov{MAP_KEY}/{source}/{BBOX}/{DAYS}"
    
    # 2. URLs de contingencia pública directa (Inmunes al bloqueo de IP de GitHub)
    url_publica = "https://nasa.gov"
    if "NOAA21" in source:
        url_publica = "https://nasa.gov"
    elif "NOAA20" in source:
        url_publica = "https://nasa.gov"

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # INTENTO 1: Intentamos tu API original
    try:
        print(f"Intentando API para {source}...")
        req = urllib.request.Request(url_api, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            df = pd.read_csv(response)
            if not df.empty:
                print(f"-> Éxito vía API: {len(df)} filas.")
                return df
    except Exception as e:
        print(f"-> API rechazada o bloqueada por la NASA: {e}")

    # INTENTO 2: Si la API bloquea a GitHub, nos bajamos el archivo público global y lo recortamos con tu BBOX
    try:
        print(f"API bloqueada. Usando canal público directo para {source}...")
        req = urllib.request.Request(url_publica, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            df_global = pd.read_csv(response)
            if not df_global.empty:
                # Filtramos el CSV global usando exactamente tus coordenadas (BBOX) de Ucrania
                df = df_global[(df_global["latitude"] >= 44.0) & (df_global["latitude"] <= 53.0) & 
                               (df_global["longitude"] >= 22.0) & (df_global["longitude"] <= 41.0)]
                print(f"-> Éxito vía Canal Público: {len(df)} filas en tu zona de conflicto.")
                return df
    except Exception as e:
        print(f"-> Error crítico en canal público: {e}")

    return pd.DataFrame()

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
        print("\nNo se pudieron obtener datos de ningún satélite.")
        return

    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["latitude", "longitude", "acq_time"])
    df_all = df_all.sort_values(by=["acq_date", "acq_time"], ascending=[False, False])

    # Aseguramos todas tus variables idénticas de formato para Pydeck
    df_all["frp_num"] = pd.to_numeric(df_all["frp"], errors="coerce").fillna(0)
    df_all["acq_time_str"] = df_all["acq_time"].astype(str).str.zfill(4)
    df_all["detection_time_utc"] = (
        df_all["acq_date"].astype(str) + " " + df_all["acq_time_str"].str[:2] + ":" + df_all["acq_time_str"].str[2:] + ":00 UTC"
    )
    df_all["detection_id"] = (
        df_all["satellite"].astype(str) + "|" + df_all["latitude"].astype(str) + "|" + df_all["longitude"].astype(str)
    )

    gdf = gpd.GeoDataFrame(
        df_all,
        geometry=gpd.points_from_xy(df_all["longitude"], df_all["latitude"]),
        crs="EPSG:4326"
    )

    gdf.to_file(OUT_GEOJSON, driver="GeoJSON")
    print(f"\n[ÉXITO] Archivo generado. Total de focos reales en el frente: {len(gdf)}")

if __name__ == "__main__":
    main()
