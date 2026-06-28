import streamlit as st
import pandas as pd
import geopandas as gpd
import pydeck as pdk
import urllib.request
import os
import time
from datetime import datetime, timezone

# --- CONFIGURACIÓN IDÉNTICA A TU SCRIPT LOCAL ---
MAP_KEY = "c7b328641d071d4f5e429e28f3f1c07d"
BBOX = "22,44,41,53"
DAYS = 5
SOURCES = [
    "VIIRS_NOAA21_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_SNPP_NRT",
]

# --- 1. CONTROL DE ACCESO PRIVADO ---
try:
    PASSWORD_SECRETA = st.secrets["CONTRASENA_SECRETA"]
except Exception:
    PASSWORD_SECRETA = "1234"

st.set_page_config(page_title="Consola Táctica Privada 3D", layout="wide")

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.title("🔒 Acceso Restringido")
    password = st.text_input("Introduce la clave secreta de acceso:", type="password")
    if st.button("Entrar"):
        if password == PASSWORD_SECRETA:
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Clave incorrecta. Acceso denegado.")
    st.stop()

# --- 2. PROCESAMIENTO EN LA NUBE REPLICANDO TU LÓGICA ---
st.title("🛰️ Visor 3D Dinámico (Procesado en la Nube)")

def download_source(source):
    # Usamos exactamente tu misma URL por AREA
    url = (
        f"https://nasa.gov"
        f"{MAP_KEY}/{source}/{BBOX}/{DAYS}"
    )

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(req, timeout=60) as response:
        df = pd.read_csv(response)

    if df.empty:
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

    # Tu misma ID de detección única para evitar duplicados entre satélites
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

    return df

@st.cache_data(ttl=900)  # Actualiza automáticamente cada 15 minutos en la nube
def obtener_datos_completos():
    frames = []
    for source in SOURCES:
        try:
            df = download_source(source)
            if not df.empty:
                frames.append(df)
            time.sleep(1)
        except Exception as e:
            st.error(f"Error descargando {source}: {e}")

    if not frames:
        return pd.DataFrame()

    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["detection_id"])
    df_all = df_all.sort_values(
        by=["acq_date", "acq_time", "frp_num"],
        ascending=[False, False, False]
    )
    return df_all

df_fuegos = obtener_datos_completos()

# --- 3. RENDERIZADO DEL MAPA INTERACTIVO 3D ---
if df_fuegos.empty:
    st.warning("No se encontraron detecciones en la consulta a la NASA.")
else:
    st.success(f"Monitoreo activo: {len(df_fuegos)} detecciones únicas en los últimos {DAYS} días.")

    # Capa 3D: Cilindros con altura real proporcional a tu columna 'frp_num'
    layer_fuegos = pdk.Layer(
        "ColumnLayer",
        df_fuegos,
        get_position="[longitude, latitude]",
        get_elevation="frp_num",
        elevation_scale=100,  # Escalado visual para las columnas 3D
        radius=1500,          # Grosor del foco en metros
        get_fill_color=[255, 0, 0, 180],  # Rojo táctico translúcido
        pickable=True,
        auto_highlight=True,
    )

    # Centrado inicial de la cámara en el frente de Ucrania con inclinación 3D (Pitch)
    vista_inicial = pdk.ViewState(
        latitude=48.3794,
        longitude=31.1656,
        zoom=5.8,
        pitch=45,  # Ángulo de inclinación de la cámara para ver las 3 dimensiones
        bearing=0
    )

    # Despliegue del mapa con tu información al pasar el ratón
    st.pydeck_chart(pdk.Deck(
        layers=[layer_fuegos],
        initial_view_state=vista_inicial,
        map_style="mapbox://styles/mapbox/dark-v10",
        tooltip={
            "text": "ID: {detection_id}\nSatélite: {satellite}\nFecha/Hora: {detection_time_utc}\nPotencia (FRP): {frp} MW"
        }
    ))
