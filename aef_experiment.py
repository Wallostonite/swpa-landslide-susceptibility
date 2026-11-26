"""Do AlphaEarth foundation-model embeddings add anything to the hand-built landslide features?

Test 1 (same as ablation.py): train on the 11 non-Allegheny counties, score Allegheny, 3 seeds.
  Scored against USGS 1970s slides, all modern records, modern records dated 2018 or later (which the 2017
  embeddings cannot have seen), and modern records within 30 m of a road.
Test 2: spatial block CV over all 12 counties, median within-county ROC-AUC against USGS labels.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from swpa import aef, fetch, grid, pasda
from swpa import config as C
from swpa import model as M

df = grid.build().join(pasda.build()).join(aef.build())
fs = M.feature_sets(df)
primary = fs[M.PRIMARY]
AEF = aef.COLS
variants = {
    "primary (terrain+geo+lc+mining)": primary,
    "primary + AEF": primary + AEF,
    "primary, AEF instead of land cover": [c for c in primary if not c.startswith("lc_")] + AEF,
    "slope + AEF": ["slope_mean"] + AEF,
    "AEF only": AEF,
}

# Modern records dated 2018 or later (IRISE year, County PW date; FEMA sites are from the 2018 event).
inv = fetch.irise()
inv = inv[(inv.group == "modern") & (inv.Year >= 2018)]
pw = gpd.read_file(pasda.SRC / "allegheny_pw_landslides_2025.gpkg")
pw = pw[pd.to_datetime(pw.Date_Occurred, unit="ms", errors="coerce").dt.year >= 2018]
tp = pasda.allegheny_test_points()
fema = tp[tp.source.str.startswith("FEMA")]
late_cells = set(grid.point_cells(inv)) | set(grid.point_cells(pw)) | set(grid.point_cells(fema))

y = M._labels(df)
modern = M._modern(df) > 0
late = df.index.isin(late_cells)
alle = (df.county == "Allegheny").values
near = (df.dist_road <= M.NEAR_ROAD_M).values
print(f"Allegheny cells {alle.sum():,}; modern {modern[alle].sum()}, dated 2018+ {late[alle].sum()}")

rows = []
for name, feats in variants.items():
    aucs = []
    for seed in (0, 1, 2):
        s = M._fit(df.loc[~alle, feats], y[~alle], feats, seed).predict_proba(df.loc[alle, feats])[:, 1]
        a = alle
        aucs.append([roc_auc_score(y[a], s), roc_auc_score(modern[a], s),
                     roc_auc_score(late[a], s), roc_auc_score(modern[a & near], s[near[a]])])
    m = np.mean(aucs, 0)
    rows.append(dict(variant=name, n_features=len(feats), usgs_allegheny=m[0], modern_allegheny=m[1],
                     modern_2018plus=m[2], modern_near_road=m[3]))
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in rows[-1].items()}, flush=True)
holdout = pd.DataFrame(rows).round(3)
holdout.to_csv(C.OUT / "aef_allegheny_holdout.csv", index=False)

print("Spatial block CV (median within-county AUC vs USGS labels)")
cv_rows = []
for name in ["primary (terrain+geo+lc+mining)", "primary + AEF", "AEF only"]:
    oof = M.block_cv(df, variants[name])
    per = [M._auc(y[(df.county == c).values], oof[(df.county == c).values]) for c in C.COUNTIES]
    cv_rows.append(dict(variant=name, median_within_county=np.nanmedian(per),
                        modern_allegheny=roc_auc_score(modern[alle], oof[alle]),
                        modern_2018plus=roc_auc_score(late[alle], oof[alle])))
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in cv_rows[-1].items()}, flush=True)
pd.DataFrame(cv_rows).round(3).to_csv(C.OUT / "aef_block_cv.csv", index=False)
