import streamlit as st

st.set_page_config(page_title="Prueba Cesium", layout="wide")
st.title("🧪 Prueba de CesiumJS con Google Terrain")

# Obtener tokens desde secrets
cesium_token = st.secrets.get("CESIUM_TOKEN")
google_api_key = st.secrets.get("GOOGLE_API_KEY")

if not cesium_token or not google_api_key:
    st.error("❌ Faltan tokens en Secrets")
    st.stop()

st.write(f"✅ CESIUM_TOKEN: {cesium_token[:15]}...")
st.write(f"✅ GOOGLE_API_KEY: {google_api_key[:10]}...")

# HTML mínimo con Cesium
html_code = f"""
<!DOCTYPE html>
<html>
<head>
    <script src="https://cesium.com/downloads/cesiumjs/releases/1.128/Build/Cesium/Cesium.js">
    </script>
    <link href="https://cesium.com/downloads/cesiumjs/releases/1.128/Build/Cesium/Widgets/widgets.css" 
          rel="stylesheet">
    <style>
        html, body, #cesiumContainer {{
            width: 100%;
            height: 600px;
            margin: 0;
            padding: 0;
            overflow: hidden;
        }}
        #debug {{
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(0,0,0,0.8);
            color: #0f0;
            padding: 10px;
            font-family: monospace;
            font-size: 12px;
            z-index: 1000;
            max-width: 80%;
            max-height: 150px;
            overflow: auto;
            white-space: pre-wrap;
        }}
    </style>
</head>
<body>
    <div id="debug">🔄 Iniciando Cesium...</div>
    <div id="cesiumContainer"></div>

    <script>
        const debugEl = document.getElementById('debug');
        function log(msg) {{
            debugEl.textContent = msg + '\\n' + debugEl.textContent;
            console.log(msg);
        }}
        
        log('🔧 Token: {cesium_token[:20]}...');
        
        try {{
            // Configurar token
            Cesium.Ion.defaultAccessToken = '{cesium_token}';
            log('✅ Token configurado');
            
            // Crear visor (SIN terreno de Google primero)
            const viewer = new Cesium.Viewer('cesiumContainer', {{
                baseLayerPicker: false,
                infoBox: false,
                selectionIndicator: false,
                navigationHelpButton: false,
                timeline: false,
                animation: false,
            }});
            log('✅ Visor creado');
            
            // Intentar cargar terreno de Google
            log('🔧 Cargando Google 3D Tiles...');
            const googleTileset = new Cesium.Cesium3DTileset({{
                url: `https://tile.googleapis.com/v1/3dtiles/root.json?key={google_api_key}`
            }});
            viewer.scene.primitives.add(googleTileset);
            log('✅ Google 3D Tiles cargado');
            
            // Volar a Ucrania
            viewer.camera.flyTo({{
                destination: Cesium.Cartesian3.fromDegrees(31.0, 48.5, 2000000),
                duration: 2
            }});
            log('✅ Volando a Ucrania');
        }} catch (e) {{
            log('❌ ERROR: ' + e.message);
        }}
    </script>
</body>
</html>
"""

st.components.v1.html(html_code, height=620)
