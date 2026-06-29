import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
from datetime import datetime, timedelta
import json
import gzip
import io

# --- CONFIGURACIÓN ---
st.set_page_config(
    page_title="Visor 3D - Incendios Ucrania",
    page_icon="🔥",
    layout="wide"
)

st.title("🔥 Visor 3D de Incendios en Ucrania")
st.markdown("**Datos FIRMS + DeepState** | 100% en la nube")

# ============================================================
# 1. CARGAR FIRMS (INCENDIOS)
# ============================================================
@st.cache_data(ttl=3600)
def cargar_firms():
    url = "https://raw.githubusercontent.com/jaspeado/firms-ukraine-tracker/main/fires.geojson"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        features = data.get('features', [])
        
        rows = []
        for f in features:
            props = f.get('properties', {})
            coords = f.get('geometry', {}).get('coordinates', [None, None])
            rows.append({
                'lat': coords[1] if len(coords) > 1 else None,
                'lon': coords[0] if len(coords) > 0 else None,
                'frp': props.get('frp'),
                'acq_date': props.get('acq_date'),
                'acq_time': props.get('acq_time'),
                'satellite': props.get('satellite'),
                'country': props.get('COUNTRY'),
                'oblast': props.get('NAME_1'),
                'locality': props.get('locality')
            })
        
        df = pd.DataFrame(rows)
        df['acq_date'] = pd.to_datetime(df['acq_date'])
        return df.dropna(subset=['lat', 'lon'])
    except Exception as e:
        st.error(f"❌ Error cargando FIRMS: {e}")
        return pd.DataFrame()

# ============================================================
# 2. CARGAR DEEPSTATE (DESDE GITHUB, COMPRIMIDO)
# ============================================================
@st.cache_data(ttl=3600)
def cargar_deepstate():
    """Descarga el archivo comprimido de DeepState y devuelve las fechas disponibles y los datos filtrados"""
    try:
        url = "https://raw.githubusercontent.com/cyterat/deepstate-map-data/main/deepstate-map-data.geojson.gz"
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        
        # Descomprimir en memoria
        with gzip.open(io.BytesIO(r.content), "rt", encoding="utf-8") as f:
            data = json.load(f)
        
        features = data.get('features', [])
        
        # Extraer fechas únicas
        fechas = set()
        for f in features:
            date_str = f.get('properties', {}).get('date', '')
            if date_str:
                fechas.add(date_str)
        
        fechas_ordenadas = sorted(list(fechas))
        
        return {
            'features': features,
            'fechas': fechas_ordenadas
        }
    except Exception as e:
        st.warning(f"⚠️ Error cargando DeepState: {e}")
        return None

# ============================================================
# 3. FILTRAR DEEPSTATE POR FECHA
# ============================================================
def filtrar_deepstate_por_fecha(deepstate_data, fecha_str):
    """Filtra los features de DeepState por fecha"""
    if not deepstate_data:
        return None
    
    features = deepstate_data.get('features', [])
    filtered = []
    for f in features:
        if f.get('properties', {}).get('date', '') == fecha_str:
            filtered.append(f)
    
    if filtered:
        return {
            "type": "FeatureCollection",
            "features": filtered
        }
    return None

# ============================================================
# 4. CARGAR DATOS
# ============================================================
with st.spinner("Cargando datos..."):
    df_firms = cargar_firms()
    deepstate_data = cargar_deepstate()

if df_firms.empty:
    st.warning("No se pudieron cargar los datos de FIRMS.")
    st.stop()

# ============================================================
# 5. FILTROS EN LA BARRA LATERAL
# ============================================================
st.sidebar.header("🔍 Filtros")

# --- FIRMS ---
st.sidebar.subheader("🔥 Incendios (FIRMS)")
fecha_min = df_firms['acq_date'].min().date()
fecha_max = df_firms['acq_date'].max().date()
fecha_inicio, fecha_fin = st.sidebar.date_input(
    "📅 Rango de fechas",
    value=(fecha_min, fecha_max),
    min_value=fecha_min,
    max_value=fecha_max
)

frp_min = st.sidebar.slider(
    "⚡ FRP mínimo (MW)",
    min_value=float(df_firms['frp'].min()),
    max_value=float(df_firms['frp'].max()),
    value=float(df_firms['frp'].min())
)

satelites = df_firms['satellite'].dropna().unique().tolist()
sat_selected = st.sidebar.multiselect(
    "🛰️ Satélite",
    options=satelites,
    default=satelites
)

oblasts = df_firms['oblast'].dropna().unique().tolist()
oblasts.sort()
oblast_selected = st.sidebar.multiselect(
    "🗺️ Oblast",
    options=oblasts,
    default=[]
)

buscar_localidad = st.sidebar.text_input("📍 Buscar localidad (contiene)")

# --- DEEPSTATE ---
st.sidebar.subheader("🟥 Línea del frente (DeepState)")
if deepstate_data and deepstate_data.get('fechas'):
    fechas_disponibles = deepstate_data['fechas']
    fecha_deepstate = st.sidebar.selectbox(
        "📅 Fecha del frente",
        options=fechas_disponibles,
        index=len(fechas_disponibles) - 1
    )
else:
    fecha_deepstate = None
    st.sidebar.warning("No se pudieron cargar fechas de DeepState")

# ============================================================
# 6. CONTROL DE CAPAS Y ESTILOS
# ============================================================
st.sidebar.header("🎨 Estilo y capas")

# Capa de incendios
st.sidebar.subheader("🔥 Incendios (VIIRS)")
mostrar_puntos = st.sidebar.checkbox("Mostrar", value=True)
color_puntos = st.sidebar.color_picker("Color de puntos", "#FF0000")
opacidad_puntos = st.sidebar.slider("Opacidad", 0.0, 1.0, 0.85, 0.05)
tamano_puntos = st.sidebar.slider("Tamaño máximo de puntos", 5, 40, 25)

# Capa de DeepState
st.sidebar.subheader("🟥 Línea del frente (DeepState)")
mostrar_deepstate = st.sidebar.checkbox("Mostrar", value=True)
color_deepstate_fill = st.sidebar.color_picker("Color de relleno", "#FF0000")
opacidad_deepstate_fill = st.sidebar.slider("Opacidad relleno", 0.0, 1.0, 0.3, 0.05)
color_deepstate_line = st.sidebar.color_picker("Color de borde", "#FFFFFF")
opacidad_deepstate_line = st.sidebar.slider("Opacidad borde", 0.0, 1.0, 0.8, 0.05)

# Capa de terreno
st.sidebar.subheader("🏔️ Terreno 3D")
mostrar_terreno = st.sidebar.checkbox("Activar inclinación 3D", value=True)
inclinacion = st.sidebar.slider("Ángulo de inclinación", 0, 90, 45)

# Mapa base
st.sidebar.subheader("🛰️ Mapa base")
mostrar_satelite = st.sidebar.checkbox("Mapa satélite", value=True)

# ============================================================
# 7. APLICAR FILTROS A FIRMS
# ============================================================
df_filtrado = df_firms.copy()

df_filtrado = df_filtrado[
    (df_filtrado['acq_date'].dt.date >= fecha_inicio) &
    (df_filtrado['acq_date'].dt.date <= fecha_fin)
]
df_filtrado = df_filtrado[df_filtrado['frp'] >= frp_min]

if sat_selected:
    df_filtrado = df_filtrado[df_filtrado['satellite'].isin(sat_selected)]
if oblast_selected:
    df_filtrado = df_filtrado[df_filtrado['oblast'].isin(oblast_selected)]
if buscar_localidad:
    df_filtrado = df_filtrado[
        df_filtrado['locality'].str.contains(buscar_localidad, case=False, na=False)
    ]

df_filtrado = df_filtrado.sort_values('frp', ascending=False)

# ============================================================
# 8. FILTRAR DEEPSTATE
# ============================================================
deepstate_geojson = None
if mostrar_deepstate and deepstate_data and fecha_deepstate:
    deepstate_geojson = filtrar_deepstate_por_fecha(deepstate_data, fecha_deepstate)

# ============================================================
# 9. ESTADÍSTICAS
# ============================================================
col1, col2, col3, col4 = st.columns(4)
col1.metric("🔥 Incendios", len(df_filtrado))
col2.metric("⚡ FRP máximo", f"{df_filtrado['frp'].max():.1f} MW" if not df_filtrado.empty else "N/A")
col3.metric("📅 Fecha más reciente", df_filtrado['acq_date'].max().strftime('%Y-%m-%d') if not df_filtrado.empty else "N/A")
col4.metric("🛰️ Satélites", df_filtrado['satellite'].nunique() if not df_filtrado.empty else 0)

# ============================================================
# 10. PREPARAR DATOS PARA PYDECK
# ============================================================
if not df_filtrado.empty:
    max_frp = df_filtrado['frp'].max() or 1
    df_filtrado['radius'] = (df_filtrado['frp'] / max_frp * tamano_puntos * 200 + 500).astype(int)
    
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return [int(hex_color[i:i+2], 16) for i in (0, 2, 4)]
    
    color_rgb = hex_to_rgb(color_puntos)
    df_filtrado['color_r'] = color_rgb[0]
    df_filtrado['color_g'] = color_rgb[1]
    df_filtrado['color_b'] = color_rgb[2]
    df_filtrado['color_a'] = int(opacidad_puntos * 255)

# ============================================================
# 11. CAPAS
# ============================================================
layers = []

# 1. Incendios
if mostrar_puntos and not df_filtrado.empty:
    puntos_layer = pdk.Layer(
        "ScatterplotLayer",
        data=df_filtrado,
        get_position=["lon", "lat"],
        get_radius="radius",
        get_fill_color=["color_r", "color_g", "color_b", "color_a"],
        pickable=True,
        auto_highlight=True,
        radius_min_pixels=3,
        radius_max_pixels=tamano_puntos,
        stroked=True,
        get_line_color=[255, 255, 0, 180],
        get_line_width=2,
    )
    layers.append(puntos_layer)

# 2. DeepState
if mostrar_deepstate and deepstate_geojson and deepstate_geojson.get('features'):
    fill_rgb = hex_to_rgb(color_deepstate_fill)
    line_rgb = hex_to_rgb(color_deepstate_line)
    
    fill_color = fill_rgb + [int(opacidad_deepstate_fill * 255)]
    line_color = line_rgb + [int(opacidad_deepstate_line * 255)]
    
    deepstate_layer = pdk.Layer(
        "GeoJsonLayer",
        data=deepstate_geojson,
        get_fill_color=fill_color,
        get_line_color=line_color,
        line_width_min_pixels=1.5,
        pickable=True,
        auto_highlight=True,
    )
    layers.append(deepstate_layer)

# ============================================================
# 12. MAPA
# ============================================================
view_state = pdk.ViewState(
    latitude=48.5,
    longitude=32.0,
    zoom=5.5,
    pitch=inclinacion if mostrar_terreno else 0,
    bearing=0,
)

tooltip = {
    "html": """
    <b>🔥 FRP:</b> {frp} MW<br>
    <b>📅 Fecha:</b> {acq_date}<br>
    <b>🛰️ Satélite:</b> {satellite}<br>
    <b>📍 Localidad:</b> {locality}<br>
    <b>🗺️ Oblast:</b> {oblast}
    """,
    "style": {
        "background": "rgba(0,0,0,0.8)",
        "color": "white",
        "fontSize": "12px",
        "padding": "8px",
        "borderRadius": "4px"
    }
}

if mostrar_satelite:
    map_style = "satellite"
else:
    map_style = "light"

if layers:
    st.pydeck_chart(pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        tooltip=tooltip,
        map_style=map_style,
    ), use_container_width=True)
else:
    st.info("No hay capas activas para mostrar.")

# ============================================================
# 13. TABLA DE DATOS
# ============================================================
with st.expander("📊 Datos detallados", expanded=False):
    if not df_filtrado.empty:
        st.dataframe(
            df_filtrado[['acq_date', 'frp', 'satellite', 'oblast', 'locality', 'lat', 'lon']],
            use_container_width=True
        )
        
        csv = df_filtrado.to_csv(index=False).encode('utf-8')
        st.download_button(
            "⬇️ Descargar CSV filtrado",
            csv,
            "incendios_filtrados.csv",
            "text/csv",
            key='download-csv'
        )

# ============================================================
# 14. RESUMEN POR OBLAST
# ============================================================
with st.expander("📈 Resumen por oblast", expanded=False):
    if not df_filtrado.empty:
        resumen = df_filtrado.groupby('oblast').agg(
            count=('frp', 'count'),
            frp_max=('frp', 'max'),
            frp_total=('frp', 'sum')
        ).sort_values('count', ascending=False)
        st.dataframe(resumen, use_container_width=True)

st.markdown("---")
st.markdown("Datos: FIRMS (NASA) | DeepStateMap | 100% en la nube")
