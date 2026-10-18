"""Tahap 2: unduh VV (dB) Sentinel-1 Teluk Balikpapan sebagai GeoTIFF float32 + masker laut.
Pemakaian: python 02_unduh_citra.py 2018-04-01 [scale_m]
Keluaran: data/s1_vv_db_<tgl>_<scale>m.tif (band1 = VV dB difilter median 3x3, band2 = laut 1/0)
"""
import os, sys, numpy as np, ee, rasterio
from rasterio.transform import from_origin

ee.Initialize(project="bledos")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from situs import BBOX, CRS, ORBIT, ERA5_HOUR, LOOK_AZ, SPILL, YEARS, INNER, DATA, RESULTS, NAME as SITUS, SPILL_REF
DATE = sys.argv[1] if len(sys.argv) > 1 else "2018-04-01"
SCALE = int(sys.argv[2]) if len(sys.argv) > 2 else 10
W, S, E, N = BBOX
AOI = ee.Geometry.Rectangle([W, S, E, N])

d0 = ee.Date(DATE)
img = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(AOI)
       .filterDate(d0, d0.advance(1, "day")).filter(ee.Filter.eq("instrumentMode", "IW"))
       .select("VV").mosaic())                       # GEE S1_GRD sudah terkalibrasi sigma0 dB
vv = img.focalMedian(1.5, "square", "pixels").rename("VV")   # filter speckle sederhana
water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gt(50).unmask(0)
# laut = air permanen JRC; daratan & sungai kecil -> 0
stack = vv.addBands(water.rename("sea").toFloat()).clip(AOI)

# grid UTM tetap
proj_aoi = AOI.transform(CRS, 1).bounds(1, CRS).coordinates().get(0).getInfo()
xs, ys = [p[0] for p in proj_aoi], [p[1] for p in proj_aoi]
x0, y1 = np.floor(min(xs)), np.ceil(max(ys))
nx, ny = int((max(xs) - x0) // SCALE), int((y1 - min(ys)) // SCALE)
print(f"grid {nx}x{ny} px @ {SCALE} m")

TILE = 1024
out = np.full((2, ny, nx), np.nan, dtype=np.float32)
for ty in range(0, ny, TILE):
    for tx in range(0, nx, TILE):
        w, h = min(TILE, nx - tx), min(TILE, ny - ty)
        req = {"expression": stack, "fileFormat": "NUMPY_NDARRAY", "bandIds": ["VV", "sea"],
               "grid": {"dimensions": {"width": w, "height": h},
                        "affineTransform": {"scaleX": SCALE, "shearX": 0, "translateX": x0 + tx * SCALE,
                                            "shearY": 0, "scaleY": -SCALE, "translateY": y1 - ty * SCALE},
                        "crsCode": CRS}}
        arr = ee.data.computePixels(req)
        out[0, ty:ty + h, tx:tx + w] = arr["VV"]
        out[1, ty:ty + h, tx:tx + w] = arr["sea"]
        print(" tile", ty, tx, end="\r")

path = os.path.join(DATA, f"s1_vv_db_{DATE}_{SCALE}m.tif")
with rasterio.open(path, "w", driver="GTiff", width=nx, height=ny, count=2, dtype="float32",
                   crs=CRS, transform=from_origin(x0, y1, SCALE, SCALE), compress="deflate", nodata=np.nan) as dst:
    dst.write(out); dst.set_band_description(1, "VV_dB_median3"); dst.set_band_description(2, "sea_JRC_occ50")
v = out[0][out[1] > 0]
print("\nsaved", path, "| VV dB laut: p2=%.1f p50=%.1f p98=%.1f" % tuple(np.nanpercentile(v, [2, 50, 98])))
