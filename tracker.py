import os
import urllib.request
import json
import gzip
from io import BytesIO
from datetime import datetime, timezone, timedelta
import pandas as pd
import geopandas as gpd

# Configuración de FIRMS
MAP_KEY = "c7b328641d071d4f5e429e28f3f1c07d"
BBOX = "22,44,41,53"
DAYS = 5
SOURCES = ["VIIRS_NOAA21_NRT", "VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT"]

# Configuración de DeepState
URL_DEEPSTATE = "https://github.com/cyterat/deepstate-map-data/raw/main/deepstate-map-data.geojson.gz"

def download_firms_source(source):
    url = f"https://nasa.gov{MAP_KEY}/{source}/{BBOX}/{DAYS}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        df = pd.read_csv(response)
    if df.empty:
        return df
    
    df["source_query"] = source
    df["download_time_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    df["acq_time_str"] = df["acq_time"].astype(str).str.zfill(4)
    df["detection_time_utc"] = (
        df["acq_date"].astype(str) + " " +
        df["acq_time_str"].str[:2] + ":" + df["acq_time_str"].str[2:] + ":00 UTC"
    )
    df["frp_num"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0)
    df["detection_id"] = (
        df["satellite"].astype(str) + "|" + df["latitude"].astype(str) + "|" +
        df["longitude"].astype(str) + "|" + df["acq_date"].astype(str) + "|" +
        df["acq_time"].astype(str) + "|" + df["instrument"].astype(str)
    )
    return df

def main():
    os.makedirs("output", exist_ok=True)
    fecha_hoy_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ==========================================================================
    # BLOQUE A: PROCESAMIENTO PROCEDURAL DE DEEPSTATE UA
    # ==========================================================================
    print("Iniciando descarga masiva de DeepState desde GitHub...")
    try:
        response = requests.get(URL_DEEPSTATE, timeout=60) if 'requests' in globals() else None
        if not response:
            req = urllib.request.Request(URL_DEEPSTATE, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as res:
                content = res.read()
        else:
            response.raise_for_status()
            content = response.content

        print("Descomprimiendo mapa de operaciones...")
        with gzip.open(BytesIO(content), "rt", encoding="utf-8") as f:
            gdf_deepstate = gpd.read_file(f)

        # Forzar que la columna de fecha se lea de forma limpia
        gdf_deepstate["date"] = pd.to_datetime(gdf_deepstate["date"]).dt.strftime("%Y-%m-%d")
        
        # APLICAR TU FILTRO AUTOMÁTICO DE HOY
        print(f"Filtrando geometrías del frente para la fecha de hoy: {fecha_hoy_str}")
        gdf_ds_filtrado = gdf_deepstate[gdf_deepstate["date"] == fecha_hoy_str]

        # Si hoy todavía no se ha publicado el mapa (ocurre temprano), busca el de ayer
        if gdf_ds_filtrado.empty:
            fecha_ayer_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
            print(f"Reporte de hoy no disponible. Extrayendo frente de ayer: {fecha_ayer_str}")
            gdf_ds_filtrado = gdf_deepstate[gdf_deepstate["date"] == fecha_ayer_str]

        # Guardar capa del frente optimizada en la nube
        ruta_ds_salida = "output/deepstate_actualizado.geojson"
        gdf_ds_filtrado.to_file(ruta_ds_salida, driver="GeoJSON")
        print(f"✅ Capa DeepState sincronizada: {len(gdf_ds_filtrado)} polígonos del frente guardados.")

    except Exception as e:
        print(f"❌ Error crítico al procesar DeepState: {e}")

    # ==========================================================================
    # BLOQUE B: PROCESAMIENTO PROCEDURAL DE ALERTAS FIRMS (NASA)
    # ==========================================================================
    print("\nIniciando descarga de alertas térmicas de la NASA FIRMS...")
    frames = []
    for source in SOURCES:
        try:
            df = download_firms_source(source)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            print(f"Error en {source}: {e}")

    if not frames:
        print("Sin detecciones nuevas de la NASA.")
        return

    df_nuevos = pd.concat(frames, ignore_index=True)
    ruta_firms_salida = "output/fuegos_actualizados.geojson"
    
    if os.path.exists(ruta_firms_salida):
        try:
            gdf_previo = gpd.read_file(ruta_firms_salida)
            df_previo = pd.DataFrame(gdf_previo.drop(columns='geometry', errors='ignore'))
            df_total = pd.concat([df_previo, df_nuevos], ignore_index=True)
        except Exception as e:
            print(f"Aviso al leer histórico firmas: {e}")
            df_total = df_nuevos
    else:
        df_total = df_nuevos

    df_total = df_total.drop_duplicates(subset=["detection_id"])
    
    # Conservar solo los últimos 5 días móviles en el archivo vivo
    df_total["acq_date_dt"] = pd.to_datetime(df_total["acq_date"])
    limite_tiempo = datetime.now(timezone.utc) - timedelta(days=DAYS)
    df_total = df_total[df_total["acq_date_dt"] >= limite_tiempo.replace(tzinfo=None)]
    df_total.drop(columns=["acq_date_dt"], inplace=True)
    df_total = df_total.sort_values(by=["acq_date", "acq_time"], ascending=[False, False])

    gdf_firms = gpd.GeoDataFrame(
        df_total,
        geometry=gpd.points_from_xy(df_total["longitude"], df_total["latitude"]),
        crs="EPSG:4326"
    )

    # Inyección de Óblasts/Localidades heredando tu estructura del GPKG subido
    base_gpkg = "firmsconubicacion.gpkg"
    if os.path.exists(base_gpkg):
        try:
            gdf_base = gpd.read_file(base_gpkg)
            gadm_lookup = gdf_base[['COUNTRY', 'NAME_1', 'locality', 'geometry']].drop_duplicates(subset=['locality'])
            
            for col in ['COUNTRY', 'NAME_1', 'locality']:
                if col in gdf_firms.columns:
                    gdf_firms.drop(columns=[col], inplace=True)
                    
            gdf_firms = gpd.sjoin_nearest(gdf_firms, gadm_lookup, how="left", max_distance=0.15)
            gdf_firms.drop(columns=["index_right"], inplace=True, errors="ignore")
            print("✅ Óblast y localidades asignadas por proximidad.")
        except Exception as e:
            print(f"Aviso en cruce geográfico: {e}")

    # Aplicar tu filtro estricto de potencia (>100 MW)
    gdf_firms_filtrado = gdf_firms[gdf_firms["frp_num"] > 100]

    # Guardar capa de fuegos optimizada en la nube
    gdf_firms_filtrado.to_file(ruta_firms_salida, driver="GeoJSON")
    print(f"✅ Capa FIRMS sincronizada: {len(gdf_firms_filtrado)} incendios activos actuales guardados.")

if __name__ == "__main__":
    # Asegurar soporte de requests si la nube corre en un contenedor minimalista
    try:
        import requests
    except ImportError:
        pass
    main()
