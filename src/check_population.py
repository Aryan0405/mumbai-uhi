"""Check 4: WorldPop India 2020 constrained - discover, download once, crop."""
import os
import re
import shutil
import tempfile
import numpy as np
import requests
import rasterio
from rasterio.windows import Window
from smoke_helpers import WP_BASE, BOX, banner


RAW_DIR = "data/population/raw"
TIF_NAME = "ind_ppp_2020_constrained.tif"


def _discover():
    r = requests.get(WP_BASE + "/", timeout=60)
    subfolders = re.findall(r'href="([^"/]+)/"', r.text)
    sub = None
    for cand in subfolders:
        if cand.lower() in ("maxar_v1", "bsgm"):
            sub = cand
            break
    if sub is None:
        raise RuntimeError("No maxar_v1/BSGM subfolder under 2020/")
    r2 = requests.get(f"{WP_BASE}/{sub}/", timeout=60)
    folders2 = re.findall(r'href="([^"/]+)/"', r2.text)
    if "IND" not in folders2:
        raise RuntimeError("No IND folder")
    r3 = requests.get(f"{WP_BASE}/{sub}/IND/", timeout=60)
    tifs = re.findall(r'href="(ind_ppp_2020_constrained\.tif)"', r3.text)
    if not tifs:
        raise RuntimeError("ind_ppp_2020_constrained.tif not found")
    resolved_url = f"{WP_BASE}/{sub}/IND/{tifs[0]}"
    hr = requests.head(resolved_url, timeout=30, allow_redirects=True)
    return resolved_url, int(hr.headers.get("Content-Length", 0) or 0), hr.status_code


def _ensure_downloaded(resolved_url, size, status):
    os.makedirs(RAW_DIR, exist_ok=True)
    local = os.path.join(RAW_DIR, TIF_NAME)
    if os.path.exists(local):
        print(f"Reusing existing download: {local} ({os.path.getsize(local)} bytes)")
        return local
    print(f"Downloading {resolved_url} ({size} bytes)...")
    with requests.get(resolved_url, stream=True, timeout=600) as rr:
        rr.raise_for_status()
        with open(local, "wb") as f:
            shutil.copyfileobj(rr.raw, f)
    print(f"Download complete: {local} ({os.path.getsize(local)} bytes)")
    print(f"HEAD status: {status}, Content-Length: {size}")
    print("Keeping original in data/population/raw/ (not deleted).")
    return local


def _crop(local):
    with rasterio.open(local) as src:
        nodata = src.nodata
        r0, c0 = src.index(BOX["lon_min"], BOX["lat_min"])
        r1, c1 = src.index(BOX["lon_max"], BOX["lat_max"])
        row_off = min(int(r0), int(r1))
        col_off = min(int(c0), int(c1))
        height = abs(int(r1) - int(r0)) + 1
        width = abs(int(c1) - int(c0)) + 1
        window = Window(col_off, row_off, width, height)
        arr = src.read(1, window=window)
    return arr, nodata


def run():
    banner("4. POPULATION (WorldPop India 2020 constrained)")
    try:
        resolved_url, size, status = _discover()
        print(f"Resolved URL: {resolved_url}")
        print(f"HEAD: HTTP {status}, Content-Length={size}")
        local = _ensure_downloaded(resolved_url, size, status)
        arr, nodata = _crop(local)
        valid = arr[arr != nodata] if nodata is not None else arr
        valid = valid[np.isfinite(valid)]
        s = float(valid.sum())
        print(f"Cropped to box: shape={arr.shape}, nodata={nodata}")
        print(f"  valid_pixels={valid.size}, sum={s:.2f}")
        print(f"  min={float(valid.min()):.2f}, max={float(valid.max()):.2f}")
        in_range = 11.0e6 <= s <= 14.5e6
        print(f"  Rule (11.0M-14.5M): {'PASS' if in_range else 'FAIL'} "
              f"(sum={s:.2f})")
        print("  NOTE: sum includes sea/areas outside BMC boundary; box != BMC.")
        return {"shape": arr.shape, "nodata": nodata, "sum": s,
                "min": float(valid.min()), "max": float(valid.max()),
                "rule_pass": in_range, "downloaded_to": local}
    except Exception as ex:
        print(f"Population step ERROR: {type(ex).__name__}: {ex}")
        return {"error": str(ex)}
