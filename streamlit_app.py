import streamlit as st
import pandas as pd
import geopandas as gpd
import pydeck as pdk
import os

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

st.title("🛰️ Visor 3D Dinámico (Procesado en la Nube)")

ARCHIVO_GPKG = "fires.gpkg"

if not os.path.exists(ARCHIVO_GPKG):
    st.warning("El servidor de GitHub Actions está ejecutando la primera descarga. Espera 1 minuto...")
else:
    try:
        gdf = gpd.read_file(ARCHIVO_GPKG, layer="fires")
        df_fuegos = pd.DataFrame(gdf.drop(columns="geometry"))
        df_fuegos["latitude"] = gdf.geometry.y
        df_fuegos["longitude"] = gdf.geometry.x
        
        st.success(f"Monitoreo activo: {len(df_fuegos)} alertas térmicas cargadas desde el GeoPackage de la nube.")

        layer_fuegos = pdk.Layer(
            "ColumnLayer",
            df_fuegos,
            get_position="[longitude, latitude]",
            get_elevation="frp_num",
            elevation_scale=100,
            radius=1500,
            get_fill_color=[255, 0, 0, 160],
            pickable=True,
            auto_highlight=True,
        )

        vista_inicial = pdk.ViewState(
            latitude=48.3794,
            longitude=31.1656,
            zoom=5.8,
            pitch=45,
            bearing=0
        )

        st.pydeck_chart(pdk.Deck(
            layers=[layer_fuegos],
            initial_view_state=vista_inicial,
            map_style="mapbox://styles/mapbox/dark-v10",
            tooltip={
                "text": "ID: {detection_id}\nSatélite: {satellite}\nFecha/Hora: {detection_time_utc}\nPotencia: {frp} MW"
            }
        ))
    except Exception as e:
        st.error(f"Error procesando cartografía: {e}")
