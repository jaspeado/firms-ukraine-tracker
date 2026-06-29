import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
import gzip
from io import BytesIO
import geopandas as gpd
import math

# Configurar la página
st.set_page_config(
    page_title="Visor 3D - Ucrania",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Visor 3D Dinámico - Alertas Térmicas en Ucrania")
st.markdown("**Terreno 3D fotorrealista de Google** | Datos FIRMS (últimas 48h, FRP > 10 MW)")

# --- Cargar datos desde GitHub ---
@st.cache_data(ttl=3600)
def cargar_datos():
    """Carga los datos desde GitHub"""
    try:
        url_fires = "https://raw.githubusercontent.com/jaspeado/firms-ukraine-tracker/main/fires.geojson"
        response_fires = requests.get(url_fires, timeout=30)
        response_fires.raise_for_status()
        fires_data = response_fires.json()
        return fires_data
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
    
    # --- FILTRO 1: Últimas 48 horas ---
    df['date'] = pd.to_datetime(df['date'])
    fecha_limite = datetime.now() - timedelta(hours=48)
    df_filtrado = df[df['date'] >= fecha_limite]
    
    st.info(f"📅 Puntos en últimas 48h: **{len(df_filtrado)}** (de {len(df)} totales)")
    
    # --- FILTRO 2: FRP > 10 MW ---
    df_filtrado = df_filtrado[df_filtrado['frp'] > 10]
    st.info(f"🔥 Puntos con FRP > 10 MW: **{len(df_filtrado)}**")
    
    # --- DEDUPLICACIÓN: Agrupar por coordenadas (redondeadas a 3 decimales) ---
    # Esto elimina detecciones redundantes de diferentes satélites en el mismo lugar
    df_filtrado['lat_round'] = df_filtrado['lat'].round(3)
    df_filtrado['lon_round'] = df_filtrado['lon'].round(3)
    
    # Agrupar y quedarse con el de mayor FRP en cada ubicación
    df_deduplicado = df_filtrado.loc[
        df_filtrado.groupby(['lat_round', 'lon_round'])['frp'].idxmax()
    ].copy()
    
    # Ordenar por FRP (mayor a menor)
    df_deduplicado = df_deduplicado.sort_values('frp', ascending=False)
    
    # Limitar a 500 puntos para rendimiento
    if len(df_deduplicado) > 500:
        df_deduplicado = df_deduplicado.head(500)
        st.info(f"📊 Mostrando los **500** puntos con mayor FRP (de {len(df_deduplicado)} únicos)")
    else:
        st.info(f"📊 Mostrando **{len(df_deduplicado)}** puntos únicos")
    
    num_fires = len(df_deduplicado)
    
    # --- RECONSTRUIR GEOJSON ---
    filtered_features = []
    for _, row in df_deduplicado.iterrows():
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row['lon'], row['lat']]
            },
            "properties": {
                "frp": row['frp'],
                "acq_date": row['date'].strftime('%Y-%m-%d'),
                "satellite": row.get('satellite', 'VIIRS')
            }
        }
        filtered_features.append(feature)
    
    fire_geojson = {
        "type": "FeatureCollection",
        "features": filtered_features
    }
    
    # --- ESTADÍSTICAS ---
    col1, col2, col3 = st.columns(3)
    col1.metric("🔥 Puntos únicos", f"{num_fires:,}")
    col2.metric("📅 Últimas 48h", "Filtro activo")
    col3.metric("⚡ FRP > 10 MW", "Filtro activo")
    
    # --- Obtener tokens desde secrets ---
    cesium_token = st.secrets.get("CESIUM_TOKEN")
    google_api_key = st.secrets.get("GOOGLE_API_KEY")
    
    with st.expander("🔧 Diagnóstico (solo para ti)", expanded=False):
        if cesium_token:
            st.success(f"✅ CESIUM_TOKEN: {cesium_token[:15]}... (longitud: {len(cesium_token)})")
        else:
            st.error("❌ CESIUM_TOKEN no encontrado")
        
        if google_api_key:
            st.success(f"✅ GOOGLE_API_KEY: {google_api_key[:10]}... (longitud: {len(google_api_key)})")
        else:
            st.error("❌ GOOGLE_API_KEY no encontrado")
        
        st.write("📊 **Resumen del procesamiento:**")
        st.write(f"- Total original: {len(df)} puntos")
        st.write(f"- Últimas 48h: {len(df_filtrado)} puntos")
        st.write(f"- FRP > 10 MW: {len(df_deduplicado)} puntos únicos")
        st.write(f"- Mostrando: {num_fires} puntos")
    
    if not cesium_token or not google_api_key:
        st.error("❌ Faltan tokens en Secrets. Configura CESIUM_TOKEN y GOOGLE_API_KEY.")
        st.stop()
    
    # --- Crear el HTML con CesiumJS ---
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <title>Visor 3D Ucrania</title>
        <style>
            html, body, #cesiumContainer {{
                width: 100%;
                height: 550px;
                margin: 0;
                padding: 0;
                overflow: hidden;
            }}
            #info {{
                position: absolute;
                top: 10px;
                left: 10px;
                background: rgba(0,0,0,0.7);
                color: white;
                padding: 8px 14px;
                border-radius: 5px;
                font-family: Arial, sans-serif;
                font-size: 12px;
                z-index: 1000;
                pointer-events: none;
            }}
        </style>
    </head>
    <body>
        <div id="info">
            <strong>🌍 Visor 3D</strong> | {num_fires} incendios | FRP > 10 MW | 48h
        </div>
        <div id="cesiumContainer"></div>

        <script src="https://cesium.com/downloads/cesiumjs/releases/1.128/Build/Cesium/Cesium.js">
        </script>
        <link href="https://cesium.com/downloads/cesiumjs/releases/1.128/Build/Cesium/Widgets/widgets.css" 
              rel="stylesheet">

        <script>
            // --- CONFIGURACIÓN ---
            Cesium.Ion.defaultAccessToken = '{cesium_token}';
            
            // --- CREAR VISOR ---
            const viewer = new Cesium.Viewer('cesiumContainer', {{
                terrainProvider: new Cesium.TerrainProvider({{
                    url: `https://api.cesium.com/v1/terrain?access_token=${{Cesium.Ion.defaultAccessToken}}`
                }}),
                baseLayerPicker: false,
                infoBox: false,
                selectionIndicator: false,
                navigationHelpButton: false,
                timeline: false,
                animation: false,
            }});
            
            // --- AÑADIR TERRENO DE GOOGLE ---
            try {{
                const googleTileset = new Cesium.Cesium3DTileset({{
                    url: `https://tile.googleapis.com/v1/3dtiles/root.json?key={google_api_key}`
                }});
                viewer.scene.primitives.add(googleTileset);
                console.log('✅ Google 3D Tiles cargado');
            }} catch (e) {{
                console.warn('⚠️ Error cargando Google 3D Tiles:', e);
            }}
            
            // --- CARGAR INCENDIOS (DEDUPLICADOS) ---
            const fireData = {json.dumps(fire_geojson)};
            
            try {{
                const fireSource = await Cesium.GeoJsonDataSource.load(fireData, {{
                    markerColor: Cesium.Color.RED,
                    markerSize: 8,
                    clampToGround: true,
                    stroke: Cesium.Color.ORANGE,
                    fill: Cesium.Color.RED.withAlpha(0.6),
                    strokeWidth: 2,
                }});
                viewer.dataSources.add(fireSource);
                console.log('✅ Incendios cargados: ' + fireData.features.length);
            }} catch (e) {{
                console.warn('⚠️ Error cargando incendios:', e);
            }}
            
            // --- VOLAR A UCRANIA ---
            viewer.camera.flyTo({{
                destination: Cesium.Cartesian3.fromDegrees(31.0, 48.5, 2000000),
                duration: 2
            }});
        </script>
    </body>
    </html>
    """
    
    # Mostrar el visor 3D
    st.iframe(html_code, width='stretch', height=570)
    
    # --- Tabla de datos (mostrando FRP más alto primero) ---
    with st.expander("📊 Datos detallados (FRP > 10 MW, últimos 48h)"):
        # Mostrar solo las columnas relevantes
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
    st.warning("⏳ No se pudieron cargar los datos. Verifica la conexión a internet.")

st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666; font-size: 12px;">
    Datos: FIRMS (NASA) | Terreno 3D: Google Map Tiles | Filtros: 48h, FRP > 10 MW, deduplicado
    </div>
    """,
    unsafe_allow_html=True
)
