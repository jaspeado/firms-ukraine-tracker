import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import numpy as np
from datetime import datetime, timedelta
import json

# Configurar la página
st.set_page_config(
    page_title="Visor 3D - Ucrania",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Visor 3D - Alertas Térmicas en Ucrania")
st.markdown("**Mapa 3D con pydeck** | Datos FIRMS (últimas 48h, FRP > 10 MW)")

# --- Cargar datos desde GitHub ---
@st.cache_data(ttl=3600)
def cargar_datos():
    try:
        url_fires = "https://raw.githubusercontent.com/jaspeado/firms-ukraine-tracker/main/fires.geojson"
        response_fires = requests.get(url_fires, timeout=30)
        response_fires.raise_for_status()
        return response_fires.json()
    except Exception as e:
        st.error(f"❌ Error al cargar datos: {e}")
        return None

with st.spinner("Cargando y procesando datos..."):
    fires_data = cargar_datos()

if fires_data:
    features = fires_data.get('features', [])
    
    # --- CONVERTIR A DATAFRAME ---
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
    df_filtrado = df[df['date'] >= fecha_limite]
    df_filtrado = df_filtrado[df_filtrado['frp'] > 10]
    
    # --- DEDUPLICACIÓN ---
    df_filtrado['lat_round'] = df_filtrado['lat'].round(3)
    df_filtrado['lon_round'] = df_filtrado['lon'].round(3)
    df_deduplicado = df_filtrado.loc[
        df_filtrado.groupby(['lat_round', 'lon_round'])['frp'].idxmax()
    ].copy()
    df_deduplicado = df_deduplicado.sort_values('frp', ascending=False)
    
    if len(df_deduplicado) > 500:
        df_deduplicado = df_deduplicado.head(500)
    
    num_fires = len(df_deduplicado)
    st.info(f"🔥 Mostrando **{num_fires}** puntos únicos con FRP > 10 MW en últimas 48h")
    
    # --- ESTADÍSTICAS ---
    col1, col2, col3 = st.columns(3)
    col1.metric("🔥 Puntos únicos", f"{num_fires:,}")
    col2.metric("📅 Últimas 48h", "Filtro activo")
    col3.metric("⚡ FRP > 10 MW", "Filtro activo")
    
    # --- PREPARAR DATOS PARA PYDECK ---
    # Normalizar FRP para el tamaño de los puntos
    min_frp = df_deduplicado['frp'].min()
    max_frp = df_deduplicado['frp'].max()
    
    if max_frp > min_frp:
        df_deduplicado['size'] = 5 + (df_deduplicado['frp'] - min_frp) / (max_frp - min_frp) * 45
    else:
        df_deduplicado['size'] = 10
    
    # Crear columna de altura (opcional, para efecto 3D)
    df_deduplicado['height'] = df_deduplicado['frp'] / 5
    
    # --- CREAR MAPA 3D CON PYDECK ---
    
    # Capa de puntos (ScatterplotLayer)
    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_deduplicado,
        get_position='[lon, lat]',
        get_color='[255, 50, 50, 200]',
        get_radius='size * 100',  # Tamaño en metros
        pickable=True,
        auto_highlight=True,
        radius_min_pixels=3,
        radius_max_pixels=20,
    )
    
    # Capa de columnas (ColumnLayer) para efecto 3D
    column_layer = pdk.Layer(
        "ColumnLayer",
        data=df_deduplicado,
        get_position='[lon, lat]',
        get_elevation='height * 100',
        get_color='[255, 100, 50, 200]',
        pickable=True,
        auto_highlight=True,
        radius=50,
        elevation_scale=1,
    )
    
    # Vista inicial (centrada en Ucrania con inclinación 3D)
    view_state = pdk.ViewState(
        latitude=48.5,
        longitude=31.0,
        zoom=6,
        pitch=45,  # Inclinación para ver en 3D
        bearing=0,
    )
    
    # Crear el mapa
    deck = pdk.Deck(
        layers=[scatter_layer, column_layer],
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/satellite-v9",  # Mapa satelital
        tooltip={
            "html": "<b>🔥 FRP:</b> {frp} MW<br/><b>📅 Fecha:</b> {date}<br/><b>🛰️ Satélite:</b> {satellite}",
            "style": {"color": "white", "font-family": "Arial", "font-size": "14px"}
        },
    )
    
    # --- MOSTRAR MAPA ---
    st.pydeck_chart(deck, use_container_width=True)
    
    # --- TABLA DE DATOS ---
    with st.expander("📊 Datos detallados (FRP > 10 MW, últimos 48h)"):
        df_mostrar = df_deduplicado[['lat', 'lon', 'frp', 'date', 'satellite']].copy()
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
else:
    st.warning("⏳ No se pudieron cargar los datos.")

st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666; font-size: 12px;">
    Datos: FIRMS (NASA) | Visualización: pydeck 3D | Filtros: 48h, FRP > 10 MW, deduplicado
    </div>
    """,
    unsafe_allow_html=True
)
