"""Standalone check of app/sentinel.py (needs internet).
Run from the backend folder with your venv Python: python test_sentinel_service.py
Prints a summary and saves the overlay as ndvi_overlay_test.png (open it to look at it)."""
import base64
import json
import time

from app import sentinel

# Same demo area as the app's "Ambasamudram Taluk" preset (approximate box, NOT an official boundary).
AOI = {"type": "Polygon",
       "coordinates": [[[77.45, 8.68], [77.52, 8.68], [77.52, 8.73], [77.45, 8.73], [77.45, 8.68]]]}

t0 = time.time()
res = sentinel.compute_ndvi(AOI, days_back=90)
print(f"Finished in {time.time() - t0:.1f} s (cached={res['cached']})")

print("\n--- SCENE ---")
print(json.dumps(res["scene"], indent=2))
print("\n--- COVERAGE (inside the polygon) ---")
print(json.dumps(res["coverage"], indent=2))
print("\n--- NDVI (usable land pixels) ---")
print(json.dumps(res["ndvi"], indent=2))
print("\n--- SCENES COMPARED ---")
for c in res["processing"]["candidates_evaluated"]:
    print(c["id"], c["datetime"][:10], "scene cloud", c["scene_cloud_cover_pct"],
          "| polygon clear (SCL est.)", c["polygon_clear_pct_scl_estimate"])
print("\nScale/offset used:", res["processing"]["reflectance_scale_offset"])

ov = res["overlay"]
print("\nOverlay bounds [[south, west],[north, east]]:", ov["bounds"], "| size", ov["width"], "x", ov["height"])
with open("ndvi_overlay_test.png", "wb") as f:
    f.write(base64.b64decode(ov["png_data_url"].split(",", 1)[1]))
print("Saved ndvi_overlay_test.png")

# Basic self-checks (these print PASS/FAIL; they do not prove the NDVI is 'correct').
c = res["coverage"]
checks = {
    "NDVI stats within [-1, 1]": -1 <= res["ndvi"]["min"] <= res["ndvi"]["max"] <= 1,
    "usable pixels <= polygon pixels": c["usable_pixels"] <= c["polygon_pixels_10m"],
    "scale is 0.0001 (typical L2A)": abs(res["processing"]["reflectance_scale_offset"]["red"][0] - 0.0001) < 1e-9,
    "overlay bounds inside the requested box": (ov["bounds"][0][1] >= 77.449 and ov["bounds"][1][1] <= 77.521
                                                 and ov["bounds"][0][0] >= 8.679 and ov["bounds"][1][0] <= 8.731),
}
print()
for k, v in checks.items():
    print("PASS" if v else "FAIL", "-", k)
