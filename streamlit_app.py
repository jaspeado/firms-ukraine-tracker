import streamlit as st
import pandas as pd
import geopandas as gpd
import pydeck as pdk
import urllib.request
import json
import gzip
from io import BytesIO
from datetime import datetime, timezone, timedelta

# 1. CONTROL DE ACCESO PRIVADO
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

# 2. PROCESAMIENTO DE DATOS EN LA NUBE
st.title("🛰️ Visor 3D Dinámico (Procesado en la Nube)")

@st.cache_data(ttl=900)
def descargar_datos_nasa():
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # 1. Descarga del archivo oficial global de incendios de las últimas 24 horas de la NASA
    try:
        url_24h = "https://nasa.gov"
        req = urllib.request.Request(url_24h, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as res:
            df = pd.read_csv(res)
            if not df.empty:
                # Recorte geográfico estricto del frente de Ucrania usando tu BBOX original
                df = df[(df["latitude"] >= 44.0) & (df["latitude"] <= 53.0) & 
                        (df["longitude"] >= 22.0) & (df["longitude"] <= 41.0)]
                df["frp_num"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0)
                return df[df["frp_num"] > 10]
    except Exception:
        pass

    # 2. Servidor API de respaldo secundario por si falla el enlace global directo
    try:
        url_backup = "https://nasa.gov"
        req = urllib.request.Request(url_backup, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as res:
            df = pd.read_csv(res)
            if not df.empty:
                df["frp_num"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0)
                return df[df["frp_num"] > 10]
    except Exception:
        return pd.DataFrame()

    return pd.DataFrame()

# Llamada oficial a la función de la NASA
df_fuegos = descargar_datos_nasa()

# 3. RENDERIZADO DEL MAPA INTERACTIVO 3D (PYDECK)
if df_fuegos is None or df_fuegos.empty:
    st.warning("No se han detectado focos activos en las coordenadas seleccionadas en las últimas horas.")
else:
    st.write(f"Mostrando {len(df_fuegos)} alertas térmicas reales procesadas de forma autónoma.")

    # Capa 3D: Columnas rojas tridimensionales proporcionales a la potencia térmica (FRP)
    layer_fuegos = pdk.Layer(
        "ColumnLayer",
        df_fuegos,
        get_position="[longitude, latitude]",
        get_elevation="frp_num",
        elevation_scale=150,  # Multiplicador de la altura visual de las columnas
        radius=2000,          # Ancho del cilindro en metros
        get_fill_color="[230, 0, 0, 180]",  # Rojo translúcido táctico
        pickable=True,
        auto_highlight=True,
    )

    # Enfoque inicial de la cámara centrado en el mapa con perspectiva 3D
    vista_inicial = pdk.ViewState(
        latitude=48.3794,
        longitude=31.1656,
        zoom=5.5,
        pitch=45,  # Ángulo de inclinación necesario para apreciar el relieve en 3D
        bearing=0
    )

    # Inyección final en la interfaz web con visualización de datos flotante (Tooltip)
    st.pydeck_chart(pdk.Deck(
        layers=[layer_fuegos],
        initial_view_state=vista_inicial,
        map_style="mapbox://styles/mapbox/dark-v10",
        tooltip={"text": "Latitud: {latitude}\nLongitud: {longitude}\nPotencia: {frp} MW\nHora Satélite: {acq_time}"}
    ))
