import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
import gzip
from io import BytesIO
import geopandas as gpd

# Configurar la página
st.set_page_config(
    page_title="Visor 3D - Ucrania",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Visor 3D Dinámico - Alertas Térmicas en Ucrania")
st.markdown("**Terreno 3D de Cesium ion** | Datos FIRMS (últimas 48h, FRP > 10 MW)")

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
    
    # --- RECONSTRUIR GEOJSON ---
    filtered_features = []
    for _, row in df_deduplicado.iterrows():
        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row['lon'], row['lat']]},
            "properties": {
                "frp": row['frp'],
                "acq_date": row['date'].strftime('%Y-%m-%d'),
                "satellite": row.get('satellite', 'VIIRS')
            }
        }
        filtered_features.append(feature)
    
    fire_geojson = {"type": "FeatureCollection", "features": filtered_features}
    
    # --- ESTADÍSTICAS ---
    col1, col2, col3 = st.columns(3)
    col1.metric("🔥 Puntos únicos", f"{num_fires:,}")
    col2.metric("📅 Últimas 48h", "Filtro activo")
    col3.metric("⚡ FRP > 10 MW", "Filtro activo")
    
    # --- OBTENER TOKEN DE CESIUM ---
    cesium_token = st.secrets.get("CESIUM_TOKEN")
    
    if not cesium_token:
        st.error("❌ Falta CESIUM_TOKEN en Secrets. Configúralo en Streamlit Cloud.")
        st.stop()
    
    # --- HTML CON CESIUM Y TERRENO PROPIO ---
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <title>Visor 3D Ucrania</title>
        <style>
            html, body, #cesiumContainer {{
                width: 100%;
                height: 100%;
                margin: 0;
                padding: 0;
                overflow: hidden;
            }}
            .cesium-viewer {{
                width: 100%;
                height: 100%;
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
            <strong>🌍 Visor 3D</strong> | {num_fires} incendios | Terreno Cesium
        </div>
        <div id="cesiumContainer"></div>

        <script src="https://cesium.com/downloads/cesiumjs/releases/1.128/Build/Cesium/Cesium.js">
        </script>
        <link href="https://cesium.com/downloads/cesiumjs/releases/1.128/Build/Cesium/Widgets/widgets.css" 
              rel="stylesheet">

        <script>
            // --- CONFIGURACIÓN ---
            Cesium.Ion.defaultAccessToken = '{cesium_token}';
            
            // --- CREAR VISOR CON TERRENO DE CESIUM ---
            const viewer = new Cesium.Viewer('cesiumContainer', {{
                terrainProvider: new Cesium.CesiumTerrainProvider({{
                    url: 'https://assets.cesium.com/1/'
                }}),
                baseLayerPicker: false,
                infoBox: false,
                selectionIndicator: false,
                navigationHelpButton: false,
                timeline: false,
                animation: false,
            }});
            
            // --- CARGAR INCENDIOS ---
            const fireData = {json.dumps(fire_geojson)};
            
            try {{
                Cesium.GeoJsonDataSource.load(fireData, {{
                    markerColor: Cesium.Color.RED,
                    markerSize: 8,
                    clampToGround: true,
                    stroke: Cesium.Color.ORANGE,
                    fill: Cesium.Color.RED.withAlpha(0.6),
                    strokeWidth: 2,
                }}).then(function(dataSource) {{
                    viewer.dataSources.add(dataSource);
                    console.log('✅ Incendios cargados: ' + fireData.features.length);
                }});
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
    
    # --- USAR st.components.v1.html (más estable para Cesium) ---
    st.components.v1.html(html_code, height=600, scrolling=False)
    
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
    Datos: FIRMS (NASA) | Terreno 3D: Cesium ion | Filtros: 48h, FRP > 10 MW, deduplicado
    </div>
    """,
    unsafe_allow_html=True
)
