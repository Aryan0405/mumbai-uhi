"""Check 5: Environment imports + versions."""
from smoke_helpers import banner


def run():
    banner("5. ENVIRONMENT IMPORTS")
    mods = [
        ("geopandas", "geopandas"),
        ("rasterio", "rasterio"),
        ("scikit-learn", "sklearn"),
        ("streamlit", "streamlit"),
        ("pystac_client", "pystac_client"),
        ("planetary_computer", "planetary_computer"),
    ]
    all_ok = True
    for label, mod in mods:
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "unknown")
            print(f"{label}: OK version={ver}")
        except Exception as e:
            print(f"{label}: IMPORT FAILED {type(e).__name__}: {e}")
            all_ok = False
    print(f"REQUIRED {'PASSED' if all_ok else 'FAILED'}: all imports clean")
    return {"ok": all_ok}
