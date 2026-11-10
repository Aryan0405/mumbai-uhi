import json, pandas as pd
g = json.load(open("data/app/cells_app_r2.geojson"))
F = g["features"]
P = pd.DataFrame([f["properties"] for f in F]).set_index("cell_id")
ix = pd.read_csv("data/processed/cells_index.csv").set_index("cell_id")
sn = pd.read_csv("data/processed/cells_index_sens.csv").set_index("cell_id")
mo = pd.read_csv("data/processed/cells_index_month.csv").set_index("cell_id")
ok = True
def chk(n, c):
    global ok
    ok &= bool(c)
    print(("PASS " if c else "FAIL ") + n)
chk("1794 features", len(F) == 1794)
chk("ids match index", set(P.index) == set(ix.index))
chk("ids match sens", set(P.index) == set(sn.index))
for col, tol in [("lst_mean",5e-5),("ndvi_mean",5e-5),("ndbi_mean",5e-5),("H",5e-5),("S",5e-5),("E_raw",5e-5),("index_primary",5e-5),("index_noexp",5e-5),("pop",5e-3),("pop_density_land",5e-2)]:
    chk(col, (P[col] - ix.loc[P.index, col]).abs().max() <= tol + 1e-12)
for col in ["rank_primary","rank_noexp","zone_primary","zone_noexp","thin_obs","zero_pop","low_confidence"]:
    chk(col, (P[col] == ix.loc[P.index, col]).all())
for col in ["zone_robust","zone_fragile","zone_count"]:
    chk(col, (P[col] == sn.loc[P.index, col]).all())
for col in ["zone_primary_march","zone_primary_aprmay"]:
    chk(col, (P[col] == mo.loc[P.index, col]).all())
for col in ["lst_march_c","lst_aprmay_c","index_primary_march","index_primary_aprmay"]:
    chk(col, (P[col] - mo.loc[P.index, col]).abs().max() <= 5e-5 + 1e-12)
chk("month_class equal", P["month_class"].fillna("x").eq(mo.loc[P.index, "month_class"].fillna("x")).all())
chk("sums 180/107/73/83", (P.zone_primary.sum(), P.zone_robust.sum(), P.zone_fragile.sum(), P.thin_obs.sum()) == (180,107,73,83))
print("ALL PASS" if ok else "SOMETHING FAILED")