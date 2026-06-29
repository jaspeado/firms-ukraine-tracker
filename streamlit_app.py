import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
from datetime import datetime, timedelta

# Configurar la página
st.set_page_config(
    page_title="Visor 3D - Ucrania",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Visor 3D con Terreno Real (Sin Mapbox)")
st.markdown("**Terreno 3D** | Datos FIRMS (últimas 48h, FRP > 10 MW)")

# --- Cargar datos desde GitHub ---
# (La función cargar_datos() es la misma que antes)
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
# (El procesamiento de datos es el mismo que antes)
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

df['date'] = pd.to_datetime(df['date'])
fecha_limite = datetime.now() - timedelta(hours=48)
df = df[df['date'] >= fecha_limite]
df = df[df['frp'] > 10]

df['lat_r'] = df['lat'].round(3)
df['lon_r'] = df['lon'].round(3)
df = df.loc[df.groupby(['lat_r', 'lon_r'])['frp'].idxmax()].copy()
df = df.sort_values('frp', ascending=False).head(500)

num_fires = len(df)
st.info(f"🔥 Mostrando **{num_fires}** puntos únicos con FRP > 10 MW en últimas 48h")

col1, col2, col3 = st.columns(3)
col1.metric("🔥 Puntos únicos", f"{num_fires:,}")
col2.metric("📅 Últimas 48h", "Filtro activo")
col3.metric("⚡ FRP > 10 MW", "Filtro activo")

# --- PREPARAR DATOS PARA PYDECK ---
# Tamaño de los puntos según FRP
max_frp = df['frp'].max()
if max_frp == 0:
    max_frp = 1

df['radius'] = (df['frp'] / max_frp * 5000 + 2000).astype(int)
df['color_r'] = 255
df['color_g'] = (255 * (1 - (df['frp'] / max_frp) * 0.8)).astype(int).clip(50, 255)
df['color_b'] = 0
df['color_a'] = 200

# --- CAPA DE TERRENO 3D (CON DATOS PÚBLICOS) ---
terrain_layer = pdk.Layer(
    "TerrainLayer",
    elevation_decoder={
        "rScaler": 256,
        "gScaler": 1,
        "bScaler": 1 / 256,
        "offset": -32768
    },
    # Usar una fuente pública de datos de elevación
    elevation_data="https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
    # Opcional: una textura de satélite sin token (puede ser más lenta)
    # texture="https://api.mapbox.com/v4/mapbox.satellite/{z}/{x}/{y}@2x.png?access_token=NO_TOKEN",
    elevation_bounds=[-11000, 11000],
    bounds=[-180, -85, 180, 85],
    opacity=1.0,
)

# --- CAPA DE PUNTOS ---
point_layer = pdk.Layer(
    "ScatterplotLayer",
    data=df,
    get_position=["lon", "lat"],
    get_radius="radius",
    get_fill_color=["color_r", "color_g", "color_b", "color_a"],
    pickable=True,
    auto_highlight=True,
    radius_min_pixels=3,
    radius_max_pixels=20,
    stroked=True,
    get_line_color=[255, 255, 0, 200],
    get_line_width=2,
)

# --- VISTA INICIAL ---
view_state = pdk.ViewState(
    latitude=48.5,
    longitude=32.0,
    zoom=5.5,
    pitch=60,
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
        "padding": "8px",
        "borderRadius": "4px"
    }
}

# --- CREAR MAPA CON TERRENO 3D ---
deck = pdk.Deck(
    layers=[terrain_layer, point_layer],
    initial_view_state=view_state,
    tooltip=tooltip,
    # Usar un mapa base sin token de Mapbox
    map_style="satellite",
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
    Datos: FIRMS (NASA) | Terreno 3D: Terrarium (público) | Puntos: incendios con FRP > 10 MW
    </div>
    """,
    unsafe_allow_html=True
)
