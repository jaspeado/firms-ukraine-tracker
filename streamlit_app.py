import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
import math

# Configurar la página
st.set_page_config(
    page_title="Visor 3D - Ucrania",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Visor 3D Dinámico - Alertas Térmicas en Ucrania")
st.markdown("**Terreno 3D Mundial de Cesium** | Datos FIRMS (últimas 48h, FRP > 10 MW)")

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
    
    # --- OBTENER TOKEN DE CESIUM ---
    cesium_token = st.secrets.get("CESIUM_TOKEN")
    
    if not cesium_token:
        st.error("❌ Falta CESIUM_TOKEN en Secrets. Configúralo en Streamlit Cloud.")
        st.stop()
    
    # --- Preparar datos para Cesium ---
    puntos_cesium = []
    for _, row in df_deduplicado.iterrows():
        size = max(6, min(22, row['frp'] / 10))
        puntos_cesium.append({
            'lon': row['lon'],
            'lat': row['lat'],
            'frp': round(row['frp'], 1),
            'size': size,
            'date': row['date'].strftime('%Y-%m-%d')
        })
    
    # --- HTML CON CESIUM (CON EL FIX DE CLAUDE) ---
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
                background: #000;
            }}
            #info {{
                position: absolute;
                top: 10px;
                left: 10px;
                background: rgba(0,0,0,0.75);
                color: white;
                padding: 8px 14px;
                border-radius: 6px;
                font-family: Arial, sans-serif;
                font-size: 12px;
                z-index: 999;
                pointer-events: none;
            }}
            #status {{
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: rgba(0,0,0,0.85);
                color: white;
                padding: 16px 32px;
                border-radius: 8px;
                font-family: Arial, sans-serif;
                font-size: 15px;
                z-index: 1000;
            }}
        </style>
    </head>
    <body>
        <div id="cesiumContainer"></div>
        <div id="info">⏳ Iniciando Cesium...</div>
        <div id="status">⏳ Cargando CesiumJS y terreno 3D...</div>

        <script>
            (function() {{
                const TOKEN = '{cesium_token}';
                const PUNTOS = {json.dumps(puntos_cesium)};

                function setStatus(msg, hide) {{
                    const el = document.getElementById('status');
                    if (hide) {{ el.style.display = 'none'; return; }}
                    el.textContent = msg;
                    el.style.display = 'block';
                }}

                // --- CARGAR CSS ---
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = 'https://cesium.com/downloads/cesiumjs/releases/1.128/Build/Cesium/Widgets/widgets.css';
                document.head.appendChild(link);

                // --- CARGAR JS ---
                const script = document.createElement('script');
                script.src = 'https://cesium.com/downloads/cesiumjs/releases/1.128/Build/Cesium/Cesium.js';

                script.onerror = function() {{
                    setStatus('❌ Error: No se pudo cargar CesiumJS.');
                }};

                script.onload = function() {{
                    setStatus('⏳ Inicializando visor...');
                    try {{
                        Cesium.Ion.defaultAccessToken = TOKEN;

                        // --- CREAR VISOR ---
                        const viewer = new Cesium.Viewer('cesiumContainer', {{
                            baseLayerPicker: false,
                            infoBox: false,
                            selectionIndicator: false,
                            navigationHelpButton: false,
                            timeline: false,
                            animation: false,
                            geocoder: false,
                            homeButton: false,
                            sceneModePicker: false,
                        }});

                        // --- ✅ FIX PRINCIPAL: async terrain loading (Cesium >= 1.110) ---
                        Cesium.createWorldTerrainAsync({{
                            requestVertexNormals: true,
                            requestWaterMask: false,
                        }}).then(function(terrain) {{
                            viewer.terrainProvider = terrain;
                            document.getElementById('info').textContent = '✅ Terreno 3D cargado';
                            console.log('✅ Terreno cargado correctamente');
                        }}).catch(function(err) {{
                            document.getElementById('info').textContent = '⚠️ Terreno no disponible — puntos visibles igualmente';
                            console.warn('Terrain error:', err);
                        }});

                        // --- IMAGEN DE SATÉLITE (ESRI) ---
                        viewer.imageryLayers.removeAll();
                        viewer.imageryLayers.addImageryProvider(
                            new Cesium.ArcGisMapServerImageryProvider({{
                                url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
                            }})
                        );

                        // --- AÑADIR PUNTOS ---
                        PUNTOS.forEach(function(p) {{
                            viewer.entities.add({{
                                position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, 0),
                                point: {{
                                    pixelSize: p.size,
                                    color: Cesium.Color.fromCssColorString('#FF3300').withAlpha(0.9),
                                    outlineColor: Cesium.Color.YELLOW,
                                    outlineWidth: 2,
                                    heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
                                    disableDepthTestDistance: Number.POSITIVE_INFINITY,
                                }},
                                properties: {{ frp: p.frp, date: p.date }}
                            }});
                        }});

                        // --- VOLAR A UCRANIA ---
                        viewer.camera.flyTo({{
                            destination: Cesium.Cartesian3.fromDegrees(32.0, 48.5, 500000),
                            duration: 2.5
                        }});

                        // --- CLIC PARA INFORMACIÓN ---
                        const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
                        handler.setInputAction(function(e) {{
                            const hit = viewer.scene.pick(e.position);
                            if (hit && hit.id && hit.id.properties) {{
                                const p = hit.id.properties;
                                alert('🔥 FRP: ' + p.frp.getValue() + ' MW\\n📅 Fecha: ' + p.date.getValue());
                            }}
                        }}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

                        setStatus('', true);
                        document.getElementById('info').textContent =
                            '🌍 {num_fires} incendios | FRP > 10 MW | Clic para detalles';

                    }} catch(err) {{
                        setStatus('❌ Error: ' + err.message);
                        console.error(err);
                    }}
                }};

                document.head.appendChild(script);
            }})();
        </script>
    </body>
    </html>
    """
    
    # --- MOSTRAR VISOR ---
    st.components.v1.html(html_code, height=650, scrolling=False)
    
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
    Datos: FIRMS (NASA) | Terreno 3D: Cesium World Terrain (async) | Renderizado: iframe con fix
    </div>
    """,
    unsafe_allow_html=True
)
