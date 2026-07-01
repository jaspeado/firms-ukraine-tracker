
import os
import time
import sys
from datetime import datetime, timezone
import pandas as pd
import geopandas as gpd
import requests
from io import StringIO
 
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
UBICACIONES_URL = "https://raw.githubusercontent.com/jaspeado/firms-ukraine-tracker/main/ubicaciones.geojson"
 
 
def download_source(source):
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{source}/{BBOX}/{DAYS}"
    print(f"\n[INFO] Conectando a la NASA para: {source}...")
    print(f"[Ruta] {url}")
 
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
 
    try:
        response = requests.get(url, headers=headers, timeout=45)
        if response.status_code != 200:
            print(f"[ERROR] Código de estado de la NASA: {response.status_code}")
            return pd.DataFrame()
 
        df = pd.read_csv(StringIO(response.text))
 
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
            df["satellite"].astype(str) + "|" +
            df["latitude"].astype(str) + "|" +
            df["longitude"].astype(str) + "|" +
            df["acq_date"].astype(str) + "|" +
            df["acq_time"].astype(str)
        )
        return df
 
    except Exception as e:
        print(f"[ERROR DE RED] Fallo en {source}: {e}", file=sys.stderr)
        return pd.DataFrame()
 
 
def enriquecer_con_ubicacion(gdf):
    print("\n[INFO] Cargando ubicaciones para enriquecer con región...")
    try:
        gdf_ubicaciones = gpd.read_file(UBICACIONES_URL)
        print(f"[INFO] {len(gdf_ubicaciones)} polígonos cargados")
 
        # Columnas que necesitamos
        columnas = ['geometry', 'NAME_1']
        if 'NAME_2' in gdf_ubicaciones.columns:
            gdf_ubicaciones['locality'] = gdf_ubicaciones['NAME_2']
            columnas.append('locality')
        else:
            gdf_ubicaciones['locality'] = gdf_ubicaciones['NAME_1']
            columnas.append('locality')
 
        # Unión espacial
        gdf = gpd.sjoin(
            gdf,
            gdf_ubicaciones[columnas],
            how='left',
            predicate='within'
        )
 
        # Limpiar columnas sobrantes de la unión
        gdf = gdf.drop(columns=['index_right'], errors='ignore')
        gdf['NAME_1'] = gdf['NAME_1'].fillna('')
        gdf['locality'] = gdf['locality'].fillna('')
 
        ubicados = (gdf['NAME_1'] != '').sum()
        print(f"[OK] Puntos con región asignada: {ubicados}/{len(gdf)}")
 
    except Exception as e:
        print(f"[ADVERTENCIA] No se pudo enriquecer con ubicaciones: {e}")
        gdf['NAME_1'] = ''
        gdf['locality'] = ''
 
    return gdf
 
 
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
 
    frames = []
    for source in SOURCES:
        df = download_source(source)
        if not df.empty:
            frames.append(df)
        time.sleep(3)
 
    if not frames:
        print("\n[FIN] No se pudieron obtener datos. Revisa la URL o las coordenadas.")
        sys.exit(1)
 
    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["detection_id"])
    df_all = df_all.sort_values(
        by=["acq_date", "acq_time", "frp_num"],
        ascending=[False, False, False]
    )
 
    gdf = gpd.GeoDataFrame(
        df_all,
        geometry=gpd.points_from_xy(df_all["longitude"], df_all["latitude"]),
        crs="EPSG:4326"
    )
 
    # ============================================================
    # ENRIQUECIMIENTO CON REGIÓN Y LOCALIDAD
    # ============================================================
    gdf = enriquecer_con_ubicacion(gdf)
 
    gdf.to_file(OUT_GEOJSON, driver="GeoJSON")
    print(f"\n[OK] Archivo 'fires.geojson' generado con éxito. Total: {len(gdf)}")
    print(f"[OK] Puntos con NAME_1: {(gdf['NAME_1'] != '').sum()}")
 
 
if __name__ == "__main__":
    main()
