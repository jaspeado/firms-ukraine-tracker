import json
import requests
from shapely.geometry import box

print("📥 Descargando fires.geojson...")
url = "https://raw.githubusercontent.com/jaspeado/firms-ukraine-tracker/main/fires.geojson"
response = requests.get(url)
data = response.json()

print(f"✅ {len(data['features'])} puntos cargados")

new_features = []
for feature in data['features']:
    coords = feature['geometry']['coordinates']
    lon, lat = coords[0], coords[1]
    
    size = 0.02
    half = size / 2
    polygon = box(lon - half, lat - half, lon + half, lat + half)
    
    new_feature = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [list(polygon.exterior.coords)]
        },
        "properties": feature['properties']
    }
    new_features.append(new_feature)

with open('fires_polygons.geojson', 'w') as f:
    json.dump({"type": "FeatureCollection", "features": new_features}, f, indent=2)

print(f"✅ Creados {len(new_features)} polígonos")
print("📁 Archivo guardado: fires_polygons.geojson")
