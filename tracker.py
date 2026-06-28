import os
import urllib.request
import json
import gzip
from io import BytesIO
from datetime import datetime, timezone, timedelta
import pandas as pd
import gpd = None  # Se manejará dinámicamente

# Intentar importar geopandas de manera segura
try:
    import geopandas as gpd
except ImportError:
    gpd = None

# Configuración de la NASA FIRMS
MAP_KEY = "c7b328641d071d4f5e429e28f3f1c07d"
BBOX = "22,44,41,53"
DAYS = 5
SOURCES = ["VIIRS_NOAA21_NRT", "VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT"]

# Configuración de DeepState
URL_DEEPSTATE = "https://github.com"

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
    # BLOQUE A: PROCESAMIENTO DE DEEPSTATE UA
    # ==========================================================================
    print("Descargando datos de DeepState...")
    try:
        req = urllib.request.Request(URL_DEEPSTATE, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as res:
            content = res.read()

        with gzip.open(BytesIO(content), "rt", encoding="utf-8") as f:
            gdf_deepstate = gpd.read_file(f)

        gdf_deepstate["date"] = pd.to_datetime(gdf_deepstate["date"]).dt.strftime("%Y-%m-%d")
        gdf_ds_filtrado = gdf_deepstate[gdf_deepstate["date"] == fecha_hoy_str]

        if gdf_ds_filtrado.empty:
            fecha_ayer_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
            gdf_ds_filtrado = gdf_deepstate[gdf_deepstate["date"] == fecha_ayer_str]

        gdf_ds_filtrado.to_file("output/deepstate_actualizado.geojson", driver="GeoJSON")
        print("✅ Capa DeepState guardada.")
    except Exception as e:
        print(f"Aviso en DeepState: {e}")

    # ==========================================================================
    # BLOQUE B: PROCESAMIENTO DE ALERTAS FIRMS (NASA)
    # ==========================================================================
    print("\nDescargando alertas térmicas de la NASA...")
    frames = []
    for source in SOURCES:
        try:
            df = download_firms_source(source)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            print(f"Error en {source}: {e}")

    if not frames:
        print("Sin alertas térmicas registradas.")
        return

    df_all = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["detection_id"])
    
    # Conservar los últimos 5 días móviles para no colapsar la pantalla
    df_all["acq_date_dt"] = pd.to_datetime(df_all["acq_date"])
    limite_tiempo = datetime.now(timezone.utc) - timedelta(days=DAYS)
    df_all = df_all[df_all["acq_date_dt"] >= limite_tiempo.replace(tzinfo=None)]
    df_all.drop(columns=["acq_date_dt"], inplace=True)

    # ==========================================================================
    # NUEVO FILTRO SOLICITADO: POTENCIA > 10 MW
    # ==========================================================================
    df_filtrado = df_all[df_all["frp_num"] > 10]
    print(f"Registrados {len(df_filtrado)} focos térmicos tácticos superiores a 10 MW.")

    if not df_filtrado.empty and gpd is not None:
        gdf_firms = gpd.GeoDataFrame(
            df_filtrado,
            geometry=gpd.points_from_xy(df_filtrado["longitude"], df_filtrado["latitude"]),
            crs="EPSG:4326"
        )
        
        # Intentar cargar tu base para heredar nombres si está en la raíz
        if os.path.exists("firmsconubicacion.gpkg"):
            try:
                base = gpd.read_file("firmsconubicacion.gpkg")
                lookup = base[['COUNTRY', 'NAME_1', 'locality', 'geometry']].drop_duplicates(subset=['locality'])
                gdf_firms = gpd.sjoin_nearest(gdf_firms, lookup, how="left", max_distance=0.15)
                gdf_firms.drop(columns=["index_right"], inplace=True, errors="ignore")
                print("✅ Atributos de ubicación asignados de forma adaptativa.")
            except Exception as e:
                print(f"Aviso en indexación espacial: {e}")
        else:
            # Si no está el archivo, creamos las columnas vacías para que tus etiquetas de QGIS no den error
            gdf_firms["COUNTRY"] = "UA"
            gdf_firms["NAME_1"] = "Zona Frente"
            gdf_firms["locality"] = "Foco Activo"

        gdf_firms.to_file("output/fuegos_actualizados.geojson", driver="GeoJSON")
        print("✅ Capa FIRMS guardada correctamente.")
    else:
        print("No se pudo estructurar el GeoJSON por falta de registros o librerías.")

if __name__ == "__main__":
    main()
