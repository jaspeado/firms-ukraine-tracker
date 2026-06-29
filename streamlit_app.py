import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import os
from datetime import datetime, timedelta

# Configurar la página
st.set_page_config(
    page_title="Visor 3D - Ucrania",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Visor 3D - Alertas Térmicas en Ucrania")
st.markdown("**Mapa 3D con columnas proporcionales al FRP** | Datos FIRMS (últimas 48h, FRP > 10 MW)")

# --- CONFIGURAR MAPBOX TOKEN (opcional) ---
MAPBOX_TOKEN = st.secrets.get("MAPBOX_TOKEN", "")
if MAPBOX_TOKEN:
    os.environ["MAPBOX_API_KEY"] = MAPBOX_TOKEN

# --- Cargar datos desde GitHub ---
@st.cache_data(ttl=3600)
def cargar_datos():
    try:
        url = "https://raw.githubusercontent.com/jaspeado/firms-ukraine-tracker/main/fires.geojson"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"❌ Error al cargar datos: {e}")
        return None

with st.spinner("Cargando y procesando datos..."):
    fires_data = cargar_datos()

if not fires_data:
    st.warning("⏳ No se pudieron cargar los datos.")
    st.stop()

# --- PROCESAR DATOS ---
features = fires_data.get('features', [])
fire_points = []
for feature in features:
    coords = feature['geometry']['coordinates']
    props = feature['properties']
    fire_points.append({
        'lat': coords[1],
        'lon': coords[0],
        'frp': props.get('frp', 0),
        'date': props.get('acq_date', ''),
        'satellite': props.get('satellite', '')
    })

df = pd.DataFrame(fire_points)

if df.empty:
    st.warning("No hay datos disponibles")
    st.stop()

# --- FILTROS ---
df['date'] = pd.to_datetime(df['date'])
fecha_limite = datetime.now() - timedelta(hours=48)
df = df[df['date'] >= fecha_limite]
df = df[df['frp'] > 10]

# --- DEDUPLICACIÓN ---
df['lat_r'] = df['lat'].round(3)
df['lon_r'] = df['lon'].round(3)
df = df.loc[df.groupby(['lat_r', 'lon_r'])['frp'].idxmax()].copy()
df = df.sort_values('frp', ascending=False).head(500)

num_fires = len(df)
st.info(f"🔥 Mostrando **{num_fires}** puntos únicos con FRP > 10 MW en últimas 48h")

# --- ESTADÍSTICAS ---
col1, col2, col3 = st.columns(3)
col1.metric("🔥 Puntos únicos", f"{num_fires:,}")
col2.metric("📅 Últimas 48h", "Filtro activo")
col3.metric("⚡ FRP > 10 MW", "Filtro activo")

# --- PREPARAR DATOS PARA PYDECK ---
# Color por intensidad FRP (rojo más intenso = más FRP)
max_frp = df['frp'].max()
df['r'] = 255
df['g'] = (255 * (1 - (df['frp'] / max_frp))).astype(int).clip(0, 200)
df['b'] = 0
df['a'] = 200
df['radius'] = (df['frp'] / max_frp * 8000 + 2000).astype(int)
df['elevation'] = (df['frp'] * 50).astype(int)  # Altura proporcional al FRP

# --- CAPA DE COLUMNAS 3D ---
layer = pdk.Layer(
    "ColumnLayer",
    data=df,
    get_position=["lon", "lat"],
    get_elevation="elevation",
    elevation_scale=1,
    radius="radius",
    get_fill_color=["r", "g", "b", "a"],
    pickable=True,
    auto_highlight=True,
)

# --- VISTA INICIAL ---
view_state = pdk.ViewState(
    latitude=48.5,
    longitude=32.0,
    zoom=5,
    pitch=45,  # Inclinación para efecto 3D
    bearing=0,
)

# --- TOOLTIP ---
tooltip = {
    "html": """
    <b>🔥 FRP:</b> {frp} MW<br>
    <b>📅 Fecha:</b> {date}<br>
    <b>🛰️ Satélite:</b> {satellite}
    """,
    "style": {
        "background": "rgba(0,0,0,0.8)",
        "color": "white",
        "fontSize": "12px",
        "padding": "8px"
    }
}

# --- ELEGIR ESTILO DE MAPA ---
if MAPBOX_TOKEN:
    map_style = "mapbox://styles/mapbox/satellite-streets-v12"
else:
    map_style = "light"  # OpenStreetMap (sin token)

# --- CREAR MAPA ---
deck = pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    tooltip=tooltip,
    map_style=map_style,
)

# --- MOSTRAR MAPA ---
st.pydeck_chart(deck, use_container_width=True)

# --- TABLA DE DATOS ---
with st.expander("📊 Datos detallados (FRP > 10 MW, últimos 48h)"):
    df_mostrar = df[['lat', 'lon', 'frp', 'date', 'satellite']].copy()
    df_mostrar = df_mostrar.sort_values('frp', ascending=False)
    st.dataframe(df_mostrar, use_container_width=True)
    
    csv = df_mostrar.to_csv(index=False).encode('utf-8')
    st.download_button(
        "⬇️ Descargar CSV",
        csv,
        "fires_data_filtrado.csv",
        "text/csv",
        key='download-csv'
    )

st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666; font-size: 12px;">
    Datos: FIRMS (NASA) | Visualización: pydeck 3D | Columnas = intensidad FRP
    </div>
    """,
    unsafe_allow_html=True
)
