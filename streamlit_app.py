import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Visor 3D - Ucrania",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Visor 3D - Alertas Térmicas en Ucrania")
st.markdown("**Datos FIRMS (últimas 48h, FRP > 10 MW)**")

# --- Cargar datos ---
@st.cache_data(ttl=3600)
def cargar_datos():
    url = "https://raw.githubusercontent.com/jaspeado/firms-ukraine-tracker/main/fires.geojson"
    r = requests.get(url, timeout=30)
    return r.json()

with st.spinner("Cargando datos..."):
    data = cargar_datos()
    features = data.get('features', [])

    fire_points = []
    for f in features:
        coords = f['geometry']['coordinates']
        props = f['properties']
        fire_points.append({
            'lat': coords[1],
            'lon': coords[0],
            'frp': props.get('frp', 0),
            'date': props.get('acq_date', ''),
            'satellite': props.get('satellite', '')
        })

df = pd.DataFrame(fire_points)
df['date'] = pd.to_datetime(df['date'])
df = df[df['date'] >= datetime.now() - timedelta(hours=48)]
df = df[df['frp'] > 10]

# Deduplicar por coordenadas
df['lat_r'] = df['lat'].round(3)
df['lon_r'] = df['lon'].round(3)
df = df.loc[df.groupby(['lat_r', 'lon_r'])['frp'].idxmax()].copy()
df = df.sort_values('frp', ascending=False).head(500)

num_fires = len(df)

st.info(f"🔥 Mostrando **{num_fires}** puntos únicos con FRP > 10 MW en últimas 48h")

col1, col2, col3 = st.columns(3)
col1.metric("🔥 Puntos únicos", f"{num_fires:,}")
col2.metric("📅 Últimas 48h", "Activo")
col3.metric("⚡ FRP > 10 MW", "Activo")

# --- Mapa 3D con pydeck ---

# Tamaño de puntos según FRP
max_frp = df['frp'].max() or 1
df['radius'] = (df['frp'] / max_frp * 5000 + 1000).astype(int)
df['color_r'] = 255
df['color_g'] = (255 * (1 - (df['frp'] / max_frp) * 0.8)).astype(int).clip(50, 255)
df['color_b'] = 0
df['color_a'] = 200

layer = pdk.Layer(
    "ScatterplotLayer",
    data=df,
    get_position=["lon", "lat"],
    get_radius="radius",
    get_fill_color=["color_r", "color_g", "color_b", "color_a"],
    pickable=True,
    auto_highlight=True,
    radius_min_pixels=3,
    radius_max_pixels=25,
    stroked=True,
    get_line_color=[255, 255, 0, 180],
    get_line_width=2,
)

view_state = pdk.ViewState(
    latitude=48.5,
    longitude=32.0,
    zoom=5.5,
    pitch=45,
    bearing=0,
)

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

st.pydeck_chart(pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    tooltip=tooltip,
    map_style="satellite",
), use_container_width=True)

# --- Tabla de datos ---
with st.expander("📊 Datos detallados"):
    df_show = df[['lat', 'lon', 'frp', 'date', 'satellite']].sort_values('frp', ascending=False)
    st.dataframe(df_show, use_container_width=True)
    st.download_button(
        "⬇️ Descargar CSV",
        df_show.to_csv(index=False).encode('utf-8'),
        "fires_filtrado.csv",
        "text/csv"
    )

st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666; font-size: 12px;">
    Datos: FIRMS (NASA) | Visualización: pydeck 3D | Filtros: 48h, FRP > 10 MW
    </div>
    """,
    unsafe_allow_html=True
)
