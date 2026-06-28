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
    # 1. Intentar URL original de tu script (API por área)
    url_primaria = f"https://nasa.gov{MAP_KEY}/{source}/{BBOX}/{DAYS}"
    
    # Mapeo de fuentes para los servidores de contingencia global en abierto de la NASA (Últimas 24h/7d)
    # Si la IP de GitHub está bloqueada en la API, usamos sus ficheros planos de libre descarga
    url_contingencia = "https://nasa.gov"
    if "NOAA21" in source:
        url_contingencia = "https://nasa.gov"
    elif "NOAA20" in source:
        url_contingencia = "https://nasa.gov"

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    df = pd.DataFrame()

    # Intento A: Tu API original con un timeout estricto para que no congele el servidor
    try:
        print(f"\n[Intento API] Consultando {source}...")
        req = urllib.request.Request(url_primaria, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            df = pd.read_csv(response)
            if not df.empty:
                print(f"-> Éxito vía API: {len(df)} filas.")
                return df
    except Exception as e:
        print(f"-> API bloqueada o sin respuesta por la IP de GitHub: {e}")

    # Intento B: Si el intento A falló por el bloqueo de red, atacamos los servidores de datos abiertos globales y filtramos en local
    try:
        print(f"[Intento Contingencia] Descargando réplica global para {source}...")
        req = urllib.request.Request(url_contingencia, headers=headers)
        with urllib.request.urlopen(req, timeout=25) as response:
            df_global = pd.read_csv(response)
            if not df_global.empty:
                # Aplicamos tu cuadro de coordenadas estricto de Ucrania sobre el mapa global descargado
                df = df_global[(df_global["latitude"] >= 44.0) & (df_global["latitude"] <= 53.0) & 
                               (df_global["longitude"] >= 22.0) & (df_global["longitude"] <= 41.0)]
                print(f"-> Éxito vía Contingencia: {len(df)} filas encontradas en tu BBOX.")
                return df
    except Exception as e:
        print(f"-> Error crítico en servidor de contingencia: {e}")

    return pd.DataFrame()

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    frames = []

    for source in SOURCES:
        try:
            df = download_source(source)
            if not df.empty:
                frames.append(df)
            time.sleep(1)
        except Exception as e:
            print(f"ERROR en procesamiento de {source}: {e}")

    if not frames:
        print("\n[Fallo de Flujo] Ningún satélite ha podido retornar datos por bloqueo total de red.")
        return

    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["detection_id"])
    df_all = df_all.sort_values(by=["acq_date", "acq_time", "frp_num"], ascending=[False, False, False])

    # Forzar columnas mínimas necesarias que exige tu visor para evitar problemas de tipos de datos
    df_all["frp_num"] = pd.to_numeric(df_all["frp"], errors="coerce").fillna(0)
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    if "detection_time_utc" not in df_all.columns:
        df_all["acq_time_str"] = df_all["acq_time"].astype(str).str.zfill(4)
        df_all["detection_time_utc"] = (
            df_all["acq_date"].astype(str) + " " + df_all["acq_time_str"].str[:2] + ":" + df_all["acq_time_str"].str[2:] + ":00 UTC"
        )
    if "detection_id" not in df_all.columns:
        df_all["detection_id"] = (
            df_all["satellite"].astype(str) + "|" + df_all["latitude"].astype(str) + "|" + df_all["longitude"].astype(str)
        )

    gdf = gpd.GeoDataFrame(
        df_all,
        geometry=gpd.points_from_xy(df_all["longitude"], df_all["latitude"]),
        crs="EPSG:4326"
    )

    # Guardado seguro compatible con entornos Linux virtuales sin drivers locales de bases de datos complejos
    gdf.to_file(OUT_GPKG, layer=LAYER_NAME, driver="GPKG", engine="fiona")
    print(f"\n[ÉXITO] GeoPackage generado en el disco virtual de GitHub. Total único: {len(gdf)}")

if __name__ == "__main__":
    main()
