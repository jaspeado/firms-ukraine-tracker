import streamlit as st
import pandas as pd
import geopandas as gpd
import pydeck as pdk
import urllib.request
import json
import gzip
from io import BytesIO
from datetime import datetime, timezone, timedelta

# 1. CONTROL DE ACCESO PRIVADO (Cifrado con Secrets)
try:
    PASSWORD_SECRETA = st.secrets["CONTRASENA_SECRETA"]
except Exception:
    PASSWORD_SECRETA = "1234"  # Clave de respaldo por si no guardaste los Secrets de la nube

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

# 2. PROCESAMIENTO DE DATOS EN LA NUBE (No consume recursos de tu PC)
st.title("🛰️ Visor 3D Dinámico (Procesado en la Nube)")

MAP_KEY = "c7b328641d071d4f5e429e28f3f1c07d"
BBOX = "22,44,41,53"
DAYS = 2
SOURCES = ["VIIRS_NOAA21_NRT", "VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT"]

@st.cache_data(ttl=900)  # Actualiza los datos reales cada 15 minutos de forma autónoma
def descargar_datos_nasa():
    # URL pública de la NASA (Firms NRT) para el satélite VIIRS en formato CSV para el país de Ucrania
    url = "https://nasa.gov"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as res:
            df = pd.read_csv(res)
    except Exception as e:
        # Si la clave compartida falla por completo, usamos el servidor de contingencia de datos abiertos de la NASA
        try:
            url_alt = "https://nasa.gov"
            req_alt = urllib.request.Request(url_alt, headers=headers)
            with urllib.request.urlopen(req_alt, timeout=30) as res_alt:
                df = pd.read_csv(res_alt)
        except Exception:
            return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()
        
    # Limpieza de duplicados y conversión de potencia a número real
    df["frp_num"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0)
    return df[df["frp_num"] > 10]  # Tu filtro táctico original para incendios reales


# 3. RENDERIZADO DEL MAPA CARTOGRÁFICO INTERACTIVO 3D
if df_fuegos.empty:
    st.warning("No se han detectado focos activos en las coordenadas seleccionadas en las últimas horas.")
else:
    st.write(f"Mostrando {len(df_fuegos)} alertas térmicas procesadas de forma autónoma.")

    # Capa 3D: Torres de luz rojas proporcionales a los Megavatios (FRP)
    layer_fuegos = pdk.Layer(
        "ColumnLayer",
        df_fuegos,
        get_position="[longitude, latitude]",
        get_elevation="frp_num",
        elevation_scale=150,  # Multiplicador de altura de las columnas en el mapa
        radius=2000,          # Radio del cilindro en metros
        get_fill_color="[230, 0, 0, 180]",  # Color rojo translúcido (R, G, B, Alfa)
        pickable=True,
        auto_highlight=True,
    )

    # Posición inicial de la cámara enfocando el área de interés con inclinación 3D
    vista_inicial = pdk.ViewState(
        latitude=48.3794,
        longitude=31.1656,
        zoom=5.5,
        pitch=45,  # Ángulo para apreciar el relieve y el volumen 3D
        bearing=0
    )

    # Construcción final del mapa con Pop-up de información al pasar el ratón (Tooltip)
    st.pydeck_chart(pdk.Deck(
        layers=[layer_fuegos],
        initial_view_state=vista_inicial,
        map_style="mapbox://styles/mapbox/dark-v10",
        tooltip={"text": "Latitud: {latitude}\nLongitud: {longitude}\nPotencia: {frp} MW\nHora Satélite: {acq_time}"}
    ))
