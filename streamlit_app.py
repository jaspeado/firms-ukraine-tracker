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
    url = "https://nasa.gov"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as res:
            df = pd.read_csv(res)
    except Exception:
        try:
            url_alt = "https://nasa.gov"
            req_alt = urllib.request.Request(url_alt, headers=headers)
            with urllib.request.urlopen(req_alt, timeout=30) as res_alt:
                df = pd.read_csv(res_alt)
        except Exception:
            return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()
        
    df["frp_num"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0)
    return df[df["frp_num"] > 10]

# LA LÍNEA CRUCIAL QUE FALTABA: Definir la variable del mapa
df_fuegos = descargar_datos_nasa()

# 3. RENDERIZADO DEL MAPA INTERACTIVO 3D
if df_fuegos.empty:
    st.warning("No se han detectado focos activos en las coordenadas seleccionadas en las últimas horas.")
else:
    st.write(f"Mostrando {len(df_fuegos)} alertas térmicas reales procesadas de forma autónoma.")

    layer_fuegos = pdk.Layer(
        "ColumnLayer",
        df_fuegos,
        get_position="[longitude, latitude]",
        get_elevation="frp_num",
        elevation_scale=150,
        radius=2000,
        get_fill_color="[230, 0, 0, 160]",  # Rojo translúcido fijado explícitamente
        pickable=True,
        auto_highlight=True,
    )

    vista_inicial = pdk.ViewState(
        latitude=48.3794,
        longitude=31.1656,
        zoom=5.5,
        pitch=45,
        bearing=0
    )

    st.pydeck_chart(pdk.Deck(
        layers=[layer_fuegos],
        initial_view_state=vista_inicial,
        map_style="mapbox://styles/mapbox/dark-v10",
        tooltip={"text": "Latitud: {latitude}\nLongitud: {longitude}\nPotencia: {frp} MW\nHora Satélite: {acq_time}"}
    ))
