import os
import time
import urllib.request
import sys
from datetime import datetime, timezone, timedelta

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
    
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            df = pd.read_csv(response)
        
        if df.empty:
            print(f"[AVISO] {source}: Respuesta vacía de la NASA.")
            return pd.DataFrame()
            
        print(f"[ÉXITO] {source}: Descargadas {len(df)} detecciones reales.")
        
        # Guardamos tu marca de tiempo exacta
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
        time.sleep(3)

    # PARCHE ANTI-VACÍO: Si la API por área falla por el reloj de la nube, forzamos la descarga del canal plano global de las últimas 24h
    if not frames:
        print("\n[AVISO] API por área sin respuesta. Activando pasarela de contingencia global...")
        for source in SOURCES:
            url_alt = "https://nasa.gov"
            if "NOAA21" in source:
                url_alt = "https://nasa.gov"
            elif "NOAA20" in source:
                url_alt = "https://nasa.gov"
            
            try:
                req = urllib.request.Request(url_alt, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=45) as response:
                    df_g = pd.read_csv(response)
                    if not df_g.empty:
                        # Recortamos geográficamente con tu BBOX estricto de Ucrania
                        df_fil = df_g[(df_g["latitude"] >= 44.0) & (df_g["latitude"] <= 53.0) & 
                                      (df_g["longitude"] >= 22.0) & (df_g["longitude"] <= 41.0)]
                        if not df_fil.empty:
                            df_fil["source_query"] = source
                            df_fil["frp_num"] = pd.to_numeric(df_fil["frp"], errors="coerce").fillna(0)
                            df_fil["acq_time_str"] = df_fil["acq_time"].astype(str).str.zfill(4)
                            df_fil["detection_time_utc"] = df_fil["acq_date"].astype(str) + " " + df_fil["acq_time_str"].str[:2] + ":" + df_fil["acq_time_str"].str[2:] + ":00 UTC"
                            df_fil["detection_id"] = df_fil["satellite"].astype(str) + "|" + df_fil["latitude"].astype(str) + "|" + df_fil["longitude"].astype(str)
                            frames.append(df_fil)
            except Exception:
                continue

    if not frames:
        print("\n[FALLO TOTAL] No se han podido extraer datos de la NASA.")
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
    print(f"\n[OK] Archivo 'fires.geojson' generado con éxito en la nube. Registros: {len(gdf)}")

if __name__ == "__main__":
    main()
