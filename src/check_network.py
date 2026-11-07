"""Check 1: Network reachability to Planetary Computer and WorldPop."""
import requests
from smoke_helpers import PC_HOST, WP_HOST, banner


def run():
    banner("1. NETWORK")
    results = {}
    for name, url in [("planetarycomputer.microsoft.com", PC_HOST),
                      ("data.worldpop.org", WP_HOST)]:
        try:
            r = requests.get(url, timeout=30)
            size = len(r.content)
            print(f"{name}: HTTP {r.status_code}, response_size={size} bytes, url={url}")
            results[name] = {"status": r.status_code, "size": size, "ok": r.status_code < 400}
            if r.status_code >= 400:
                print(f"  FAIL: HTTP {r.status_code}")
        except Exception as e:
            print(f"{name}: ERROR {type(e).__name__}: {e}")
            results[name] = {"error": str(e), "ok": False}
    return results
