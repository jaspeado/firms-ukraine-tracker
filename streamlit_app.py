import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="Visor 3D - Ucrania", page_icon="🌍", layout="wide")
st.title("🌍 Visor 3D Dinámico - Alertas Térmicas en Ucrania")
st.markdown("**Terreno 3D Mundial de Cesium** | Datos FIRMS (últimas 48h, FRP > 10 MW)")

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

features = fires_data.get('features', [])
fire_points = []
for feature in features:
    coords = feature['geometry']['coordinates']
    props = feature['properties']
    fire_points.append({
        'lat': coords[1], 'lon': coords[0],
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

cesium_token = st.secrets.get("CESIUM_TOKEN", "")
if not cesium_token:
    st.error("❌ Falta CESIUM_TOKEN en Secrets.")
    st.stop()

puntos_cesium = []
for _, row in df.iterrows():
    puntos_cesium.append({
        'lon': row['lon'], 'lat': row['lat'],
        'frp': round(row['frp'], 1),
        'size': max(6, min(22, row['frp'] / 10)),
        'date': row['date'].strftime('%Y-%m-%d')
    })

html_code = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
html, body, #cesiumContainer {{ width:100%; height:100%; margin:0; padding:0; overflow:hidden; background:#0d1b2a; }}
#info {{
    position:absolute; top:10px; left:10px;
    background:rgba(0,0,0,0.8); color:#fff;
    padding:8px 14px; border-radius:6px;
    font:12px Arial,sans-serif; z-index:999; pointer-events:none;
}}
#status {{
    position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
    background:rgba(0,0,0,0.9); color:#fff;
    padding:20px 40px; border-radius:10px;
    font:14px Arial,sans-serif; z-index:1000; text-align:center;
}}
</style>
</head>
<body>
<div id="cesiumContainer"></div>
<div id="info">⏳ Iniciando...</div>
<div id="status">⏳ Cargando CesiumJS...</div>
<script>
(function() {{
    const TOKEN = '{cesium_token}';
    const PUNTOS = {json.dumps(puntos_cesium)};
    const NUM = {num_fires};

    const infoEl = document.getElementById('info');
    const statusEl = document.getElementById('status');

    function setStatus(msg) {{
        if (!msg) {{ statusEl.style.display = 'none'; return; }}
        statusEl.textContent = msg;
    }}
    function setInfo(msg) {{ infoEl.textContent = msg; }}

    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://cesium.com/downloads/cesiumjs/releases/1.128/Build/Cesium/Widgets/widgets.css';
    document.head.appendChild(link);

    const script = document.createElement('script');
    script.src = 'https://cesium.com/downloads/cesiumjs/releases/1.128/Build/Cesium/Cesium.js';
    script.onerror = () => setStatus('❌ No se pudo cargar CesiumJS');
    script.onload = function() {{
        setStatus('⏳ Inicializando visor...');
        try {{
            Cesium.Ion.defaultAccessToken = TOKEN;

            // Viewer SIN imageryProvider para evitar crashes al inicio
            const viewer = new Cesium.Viewer('cesiumContainer', {{
                imageryProvider: false,
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

            // ── IMAGERY ──────────────────────────────────────────────
            // Intento 1: Bing via Ion asset 2 (funciona con cualquier token Ion válido)
            Cesium.IonImageryProvider.fromAssetId(2)
            .then(function(p) {{
                viewer.imageryLayers.addImageryProvider(p);
                setInfo('🛰️ Imagery OK');
            }})
            .catch(function() {{
                // Intento 2: ArcGIS World Imagery (async, no constructor)
                return Cesium.ArcGisMapServerImageryProvider.fromUrl(
                    'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
                );
            }})
            .then(function(p) {{
                if (p && p.constructor && p.constructor.name !== 'IonImageryProvider') {{
                    viewer.imageryLayers.addImageryProvider(p);
                    setInfo('🛰️ Imagery ArcGIS OK');
                }}
            }})
            .catch(function() {{
                // Intento 3: OSM (también async en 1.128)
                Cesium.OpenStreetMapImageryProvider.fromUrl('https://tile.openstreetmap.org/')
                .then(function(p) {{
                    viewer.imageryLayers.addImageryProvider(p);
                    setInfo('🗺️ Usando OpenStreetMap');
                }})
                .catch(function() {{
                    setInfo('⚠️ Sin mapa base');
                }});
            }});

            // ── TERRENO ───────────────────────────────────────────────
            Cesium.createWorldTerrainAsync({{ requestVertexNormals: true }})
            .then(function(t) {{ viewer.terrainProvider = t; }})
            .catch(function(e) {{ console.warn('Terrain:', e); }});

            // ── PUNTOS ───────────────────────────────────────────────
            PUNTOS.forEach(function(p) {{
                viewer.entities.add({{
                    position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, 0),
                    point: {{
                        pixelSize: p.size,
                        color: Cesium.Color.RED.withAlpha(0.9),
                        outlineColor: Cesium.Color.YELLOW,
                        outlineWidth: 2,
                        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
                        disableDepthTestDistance: Number.POSITIVE_INFINITY,
                    }},
                    properties: {{ frp: p.frp, date: p.date }}
                }});
            }});

            // ── CÁMARA: setView es instantáneo, no depende de async ──
            viewer.camera.setView({{
                destination: Cesium.Cartesian3.fromDegrees(32.0, 48.5, 700000),
            }});

            // ── CLICK ─────────────────────────────────────────────────
            new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas)
            .setInputAction(function(e) {{
                const hit = viewer.scene.pick(e.position);
                if (hit && hit.id && hit.id.properties) {{
                    const p = hit.id.properties;
                    alert('🔥 FRP: ' + p.frp.getValue() + ' MW\\n📅 ' + p.date.getValue());
                }}
            }}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

            setStatus('');
            setInfo('🌍 ' + NUM + ' incendios | FRP > 10 MW | Clic para detalles');

        }} catch(err) {{
            setStatus('❌ ' + err.message);
            console.error(err);
        }}
    }};
    document.head.appendChild(script);
}})();
</script>
</body>
</html>"""

st.components.v1.html(html_code, height=650, scrolling=False)

with st.expander("📊 Datos detallados (FRP > 10 MW, últimos 48h)"):
    df_show = df[['lat','lon','frp','date','satellite']].sort_values('frp', ascending=False)
    st.dataframe(df_show, use_container_width=True)
    st.download_button("⬇️ Descargar CSV",
        df_show.to_csv(index=False).encode('utf-8'),
        "fires_filtrado.csv", "text/csv")

st.markdown("---")
st.markdown(
    '<div style="text-align:center;color:#666;font-size:12px;">'
    'Datos: FIRMS (NASA) | Terreno: Cesium World Terrain | Imagery: Ion/ArcGIS/OSM'
    '</div>', unsafe_allow_html=True)
