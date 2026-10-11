
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from pystac_client import Client

# Approximate test area near Ambasamudram.
# This is NOT an official taluk boundary.
lon, lat = 77.45, 8.71
half_size = 0.03

bbox = [
    lon - half_size,
    lat - half_size,
    lon + half_size,
    lat + half_size,
]

print("Searching for Sentinel-2 satellite data...")

catalog = Client.open(
    "https://earth-search.aws.element84.com/v1"
)

items = list(
    catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime="2026-01-01/2026-10-08",
        max_items=30,
    ).items()
)

if not items:
    raise RuntimeError("No satellite scenes found for this area.")

items.sort(
    key=lambda item: item.properties.get("eo:cloud_cover", 100)
)

item = items[0]

print("\n--- SATELLITE INFORMATION ---")
print("Scene:", item.id)
print("Acquisition date:", item.datetime)
print("Scene-wide cloud cover:",
      item.properties.get("eo:cloud_cover"), "%")


def read_band(asset_name):
    """Read a satellite band for the test area."""
    with rasterio.open(item.assets[asset_name].href) as src:
        bounds = transform_bounds(
            "EPSG:4326",
            src.crs,
            *bbox,
            densify_pts=11,
        )

        window = from_bounds(
            *bounds,
            transform=src.transform,
        )

        window = window.round_offsets().round_lengths()

        data = src.read(
            1,
            window=window,
            masked=True,
        ).astype("float32")

        transform = src.window_transform(window)
        crs = src.crs

    # Read scaling information from the STAC asset metadata.
    band_metadata = item.assets[asset_name].extra_fields.get(
        "raster:bands", [{}]
    )[0]

    scale = band_metadata.get("scale", 1.0)
    offset = band_metadata.get("offset", 0.0)

    raw = np.asarray(data.filled(np.nan), dtype="float32")
    nodata_mask = np.ma.getmaskarray(data) | (raw == 0)

    reflectance = raw * scale + offset
    reflectance[nodata_mask] = np.nan

    return reflectance, transform, crs, nodata_mask


print("\nReading red and NIR bands...")

red, red_transform, red_crs, red_nodata = read_band("red")
nir, nir_transform, nir_crs, nir_nodata = read_band("nir")

# Align the 20 m scene-classification band with the 10 m red-band grid.
print("Aligning cloud/classification pixels...")

with rasterio.open(item.assets["scl"].href) as scl_src:
    with WarpedVRT(
        scl_src,
        crs=red_crs,
        transform=red_transform,
        width=red.shape[1],
        height=red.shape[0],
        resampling=Resampling.nearest,
    ) as aligned_scl:
        scl = aligned_scl.read(1, masked=True)

scl_data = np.asarray(scl.filled(0))

if red.shape != nir.shape or red.shape != scl_data.shape:
    raise RuntimeError(
        f"Band alignment failed: red={red.shape}, "
        f"nir={nir.shape}, scl={scl_data.shape}"
    )

# SCL classes excluded:
# 0 = no data, 1 = saturated/defective, 3 = cloud shadow,
# 8 = medium-probability cloud, 9 = high-probability cloud,
# 10 = cirrus, 11 = snow/ice.
invalid_scl = np.isin(scl_data, [0, 1, 3, 8, 9, 10, 11])

valid = (
    np.isfinite(red)
    & np.isfinite(nir)
    & (red > 0)
    & (nir > 0)
    & ~red_nodata
    & ~nir_nodata
    & ~np.ma.getmaskarray(scl)
    & ~invalid_scl
)

denominator = nir + red
valid &= np.isfinite(denominator) & (denominator != 0)

ndvi = np.full(red.shape, np.nan, dtype="float32")

ndvi[valid] = (
    (nir[valid] - red[valid])
    / denominator[valid]
)

# NDVI should theoretically fall between -1 and +1.
valid_ndvi = np.isfinite(ndvi)
valid_ndvi &= (ndvi >= -1) & (ndvi <= 1)
ndvi[~valid_ndvi] = np.nan

total_pixels = ndvi.size
usable_pixels = int(np.isfinite(ndvi).sum())

print("\n--- REAL SATELLITE NDVI RESULTS ---")
print("Aligned image dimensions:", ndvi.shape)
print("Total pixels:", total_pixels)
print("Usable pixels:", usable_pixels)

if total_pixels:
    print(
        "Usable pixel fraction:",
        round(100 * usable_pixels / total_pixels, 2),
        "%",
    )

if usable_pixels:
    print("Mean NDVI:", round(float(np.nanmean(ndvi)), 4))
    print("Minimum NDVI:", round(float(np.nanmin(ndvi)), 4))
    print("Maximum NDVI:", round(float(np.nanmax(ndvi)), 4))
    print("\nSUCCESS: NDVI calculation completed.")
else:
    print("No usable pixels. Try a different satellite scene.")

print(
    "\nNote: This is a satellite-derived vegetation measurement "
    "for an approximate test area, not a verified crop classification."
)