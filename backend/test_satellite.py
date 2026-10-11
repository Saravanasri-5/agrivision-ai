
from pystac_client import Client

# Approximate test area near Ambasamudram, Tamil Nadu.
# This is a test point, NOT an official taluk boundary.
longitude = 77.45
latitude = 8.71
half_size = 0.03

bbox = [
    longitude - half_size,
    latitude - half_size,
    longitude + half_size,
    latitude + half_size,
]

catalog = Client.open(
    "https://earth-search.aws.element84.com/v1"
)

search = catalog.search(
    collections=["sentinel-2-l2a"],
    bbox=bbox,
    datetime="2025-01-01/2026-10-08",
    max_items=20,
)

items = list(search.items())

print(f"Scenes found: {len(items)}")

items.sort(
    key=lambda item: item.properties.get(
        "eo:cloud_cover", 100
    )
)

for item in items[:5]:
    print("-" * 50)
    print("Scene ID:", item.id)
    print("Date:", item.datetime)
    print(
        "Scene cloud cover:",
        item.properties.get("eo:cloud_cover", "Unknown"),
        "%",
    )
    print("Available assets:", list(item.assets.keys()))