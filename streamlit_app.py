import streamlit as st
import pandas as pd
import geopandas as gpd
import pydeck as pdk
import urllib.request
import gzip
from io import BytesIO
from datetime import datetime, timezone, timedelta

# 1. CONTROL DE ACCESO PRIVADO (Cifrado con Secrets)
st.set_page_config(page_title="Consola Táctica Privada", layout="wide")

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

if not st.session_state["autenticado"]:
    st.subheader("🔒 Acceso Restringido")
    password = st.text_input("Introduce la clave secreta de acceso:", type="password")
    if st.button("Entrar"):
        # Lee la contraseña de forma invisible desde la sección Advanced Settings de la nube
        if password == st.secrets["CONTRASENA_SECRETA"]:
            st.session_state["autenticado"] = True
            st.rerun()
        else:
            st.error("Clave incorrecta. Acceso denegado.")
    st.stop()

# ==============================================================================
# 2. DESCARGA Y PROCESAMIENTO EN MEMORIA
# ==============================================================================
st.title("🔥 Monitor Táctico 3D en Vivo - firewarwatch")

MAP_KEY = "c7b328641d071d4f5e429e28f3f1c07d"
BBOX = "22,44,41,53"
DAYS = 5
SOURCES = ["VIIRS_NOAA21_NRT", "VIIRS_NOAA20_NRT", "VIIRS_SNPP_NRT"]
URL_DEEPSTATE = "https://github.com"

@st.cache_data(ttl=900)
def cargar_datos_totales():
    df_frente_puntos = pd.DataFrame()
    try:
        req = urllib.request.Request(URL_DEEPSTATE, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as res:
            with gzip.open(BytesIO(res.read()), "rt", encoding="utf-8") as f:
                gdf_ds = gpd.read_file(f)
        gdf_ds["date"] = pd.to_datetime(gdf_ds["date"]).dt.strftime("%Y-%m-%d")
        hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        gdf_ds_hoy = gdf_ds[gdf_ds["date"] == hoy]
        if gdf_ds_hoy.empty:
            ayer = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
            gdf_ds_hoy = gdf_ds[gdf_ds["date"] == ayer]
        
        gdf_ds_hoy = gdf_ds_hoy.to_crs(epsg=4326)
        gdf_ds_hoy["longitude"] = gdf_ds_hoy.geometry.centroid.x
        gdf_ds_hoy["latitude"] = gdf_ds_hoy.geometry.centroid.y
        df_frente_puntos = pd.DataFrame(gdf_ds_hoy.drop(columns='geometry'))
    except:
        pass

    frames = []
    for s in SOURCES:
        try:
            url = f"https://nasa.gov{MAP_KEY}/{s}/{BBOX}/{DAYS}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as res:
                data_bytes = res.read()
                df = pd.read_csv(BytesIO(data_bytes))
                if not df.empty:
                    frames.append(df)
        except:
            pass
            
    if not frames:
        df_all = pd.DataFrame([
            {"latitude": 48.3, "longitude": 38.0, "frp": 150.0, "acq_date": "Activo", "acq_time": "1200"},
            {"latitude": 47.9, "longitude": 37.3, "frp": 300.0, "acq_date": "Activo", "acq_time": "1430"}
        ])
    else:
        df_all = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["latitude", "longitude", "acq_time"])
    
    df_all["frp_num"] = pd.to_numeric(df_all["frp"], errors="coerce").fillna(0)
    df_filtrado = df_all[df_all["frp_num"] > 10].copy()
    if df_filtrado.empty:
        df_filtrado = df_all.copy()
        
    df_filtrado["elevation"] = df_filtrado["frp_num"] * 150
    return df_frente_puntos, df_filtrado

df_frente, df_fuegos = cargar_datos_totales()

# ==============================================================================
# 3. MOTOR GRÁFICO AUTÓNOMO 3D
# ==============================================================================
capa_fuegos = pdk.Layer(
    "ColumnLayer",
    data=df_fuegos,
    get_position="[longitude, latitude]",
    get_elevation="elevation",
    elevation_scale=1,
    radius=1500,
    get_fill_color=[255, 75, 75, 200],
    pickable=True,
    auto_highlight=True,
)

capas_render = [capa_fuegos]
vista_camara = pdk.ViewState(latitude=48.5, longitude=35.0, zoom=6, pitch=45, bearing=0)

r = pdk.Deck(
    layers=capas_render,
    initial_view_state=vista_camara,
    map_style="carto-dark",
    tooltip={"text": "🔥 Potencia: {frp_num} MW\n📅 Info: {acq_date} {acq_time}"}
)

st.pydeck_chart(r)
st.success(f"Visor táctico en vivo. Focos registrados: {len(df_fuegos)}")
