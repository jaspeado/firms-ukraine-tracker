import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
import gzip
from io import BytesIO
import geopandas as gpd

# Configurar la página
st.set_page_config(
    page_title="Visor 3D - Ucrania con Terreno Real",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Visor 3D Dinámico - Frente y Alertas Térmicas en Ucrania")
st.markdown("**Terreno 3D fotorrealista de Google** | Datos actualizados diariamente desde FIRMS y DeepState")

# --- Cargar datos desde GitHub ---
@st.cache_data(ttl=3600)
def cargar_datos():
    """Carga los datos desde GitHub"""
    try:
        url_fires = "https://raw.githubusercontent.com/jaspeado/firms-ukraine-tracker/main/fires.geojson"
        response_fires = requests.get(url_fires, timeout=30)
        response_fires.raise_for_status()
        fires_data = response_fires.json()
        
        try:
            url_front = "https://raw.githubusercontent.com/cyterat/deepstate-map-data/main/deepstate-map-data.geojson.gz"
            response_front = requests.get(url_front, timeout=60)
            response_front.raise_for_status()
            
            with gzip.open(BytesIO(response_front.content), "rt", encoding="utf-8") as f:
                gdf = gpd.read_file(f)
            
            gdf['date'] = pd.to_datetime(gdf['date'])
            fecha_reciente = gdf['date'].max()
            front_data = gdf[gdf['date'] == fecha_reciente]
            front_geojson = json.loads(front_data.to_json())
        except:
            front_geojson = None
        
        return fires_data, front_geojson
    except Exception as e:
        st.error(f"❌ Error al cargar datos: {e}")
        return None, None

with st.spinner("Cargando datos y preparando terreno 3D..."):
    fires_data, front_geojson = cargar_datos()

if fires_data:
    num_fires = len(fires_data.get('features', []))
    
    col1, col2, col3 = st.columns(3)
    col1.metric("🔥 Alertas térmicas", f"{num_fires:,}")
    col2.metric("📅 Última actualización", datetime.now().strftime("%Y-%m-%d %H:%M"))
    col3.metric("🛰️ Satélites", "VIIRS (3 sensores)")
    
    # --- Obtener tokens desde secrets ---
    cesium_token = st.secrets.get("CESIUM_TOKEN")
    google_api_key = st.secrets.get("GOOGLE_API_KEY")
    
    # --- DEPURACIÓN: Mostrar estado de los tokens ---
    with st.expander("🔧 Diagnóstico (solo para ti)", expanded=False):
        if cesium_token:
            st.success(f"✅ CESIUM_TOKEN: {cesium_token[:15]}... (longitud: {len(cesium_token)})")
        else:
            st.error("❌ CESIUM_TOKEN no encontrado en secrets")
        
        if google_api_key:
            st.success(f"✅ GOOGLE_API_KEY: {google_api_key[:10]}... (longitud: {len(google_api_key)})")
        else:
            st.error("❌ GOOGLE_API_KEY no encontrado en secrets")
    
    if not cesium_token or not google_api_key:
        st.error("❌ Faltan tokens en Secrets. Configura CESIUM_TOKEN y GOOGLE_API_KEY.")
        st.stop()
    
    # --- Preparar datos para Cesium ---
    fire_geojson = {
        "type": "FeatureCollection",
        "features": fires_data.get('features', [])
    }
    
    # --- Crear el HTML con CesiumJS (con depuración) ---
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
            #debug {{
                position: absolute;
                bottom: 10px;
                left: 10px;
                background: rgba(0,0,0,0.8);
                color: #0f0;
                padding: 10px;
                font-family: monospace;
                font-size: 12px;
                z-index: 1000;
                max-width: 80%;
                max-height: 100px;
                overflow: auto;
                white-space: pre-wrap;
                pointer-events: none;
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
            <strong>🌍 Visor 3D</strong> | {num_fires} incendios | Terreno Google
        </div>
        <div id="debug">🔄 Iniciando Cesium...</div>
        <div id="cesiumContainer"></div>

        <script src="https://cesium.com/downloads/cesiumjs/releases/1.128/Build/Cesium/Cesium.js">
        </script>
        <link href="https://cesium.com/downloads/cesiumjs/releases/1.128/Build/Cesium/Widgets/widgets.css" 
              rel="stylesheet">

        <script>
            const debugEl = document.getElementById('debug');
            function logDebug(msg) {{
                debugEl.textContent = msg + '\\n' + debugEl.textContent;
                console.log(msg);
            }}
            
            logDebug('🔧 Iniciando...');
            logDebug('📡 Cesium token: {cesium_token[:20]}...');
            
            // --- CONFIGURACIÓN ---
            try {{
                Cesium.Ion.defaultAccessToken = '{cesium_token}';
                logDebug('✅ Token Cesium configurado');
            }} catch (e) {{
                logDebug('❌ Error configurando token: ' + e.message);
            }}
            
            // --- CREAR VISOR CON TERRENO 3D ---
            try {{
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
                logDebug('✅ Visor Cesium creado');
                
                // --- AÑADIR TERRENO FOTORREALISTA DE GOOGLE ---
                try {{
                    logDebug('🔧 Cargando Google 3D Tiles...');
                    const googleTileset = new Cesium.Cesium3DTileset({{
                        url: `https://tile.googleapis.com/v1/3dtiles/root.json?key={google_api_key}`
                    }});
                    viewer.scene.primitives.add(googleTileset);
                    logDebug('✅ Google 3D Tiles cargado correctamente');
                }} catch (e) {{
                    logDebug('⚠️ Error cargando Google 3D Tiles: ' + e.message);
                }}
                
                // --- CARGAR INCENDIOS ---
                try {{
                    logDebug('🔧 Cargando incendios...');
                    const fireData = {json.dumps(fire_geojson)};
                    const fireSource = await Cesium.GeoJsonDataSource.load(fireData, {{
                        markerColor: Cesium.Color.RED,
                        markerSize: 10,
                        clampToGround: true,
                        stroke: Cesium.Color.ORANGE,
                        fill: Cesium.Color.RED.withAlpha(0.6),
                        strokeWidth: 2,
                    }});
                    viewer.dataSources.add(fireSource);
                    logDebug('✅ Incendios cargados: ' + fireData.features.length);
                }} catch (e) {{
                    logDebug('⚠️ Error cargando incendios: ' + e.message);
                }}
                
                // --- VOLAR A UCRANIA ---
                viewer.camera.flyTo({{
                    destination: Cesium.Cartesian3.fromDegrees(31.0, 48.5, 2000000),
                    duration: 2
                }});
                logDebug('✅ Visor 3D listo');
            }} catch (e) {{
                logDebug('❌ Error creando visor: ' + e.message);
            }}
        </script>
    </body>
    </html>
    """
    
    # Mostrar el visor 3D
    st.components.v1.html(html_code, height=570)
    
    # --- Tabla de datos ---
    with st.expander("📊 Datos detallados"):
        fire_points = []
        for feature in fires_data.get('features', []):
            coords = feature['geometry']['coordinates']
            props = feature['properties']
            fire_points.append({
                'Latitud': coords[1],
                'Longitud': coords[0],
                'FRP': props.get('frp', 0),
                'Fecha': props.get('acq_date', ''),
                'Satélite': props.get('satellite', '')
            })
        df = pd.DataFrame(fire_points)
        st.dataframe(df, use_container_width=True)
        
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "⬇️ Descargar CSV",
            csv,
            "fires_data.csv",
            "text/csv",
            key='download-csv'
        )
else:
    st.warning("⏳ No se pudieron cargar los datos. Verifica la conexión a internet.")

st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666; font-size: 12px;">
    Datos: FIRMS (NASA) y DeepStateMap | Terreno 3D: Google Map Tiles | Procesado en la nube
    </div>
    """,
    unsafe_allow_html=True
)
