"""Train on the 11 non-Allegheny counties, score Allegheny against modern records. One fit per variant."""
import numpy as np, pandas as pd
from sklearn.metrics import roc_auc_score
from swpa import grid, pasda, model as M
df = grid.build().join(pasda.build())
fs = M.feature_sets(df); base = fs[M.BASELINE]
groups = {"mining": ["mined", "dist_mined", "ug_permit", "longwall_pre1976"], "wells": ["well_density_pre1976"],
          "roads": ["road", "dist_road", "dist_state_road"], "regolith": ["regolith_m"],
          "soils_no_slip": [c for c in M.PASDA if c.startswith("soil_") and c != "soil_slip_high"],
          "soil_slip": ["soil_slip_high"]}
variants = {"baseline": base, **{f"+{g}": base + c for g, c in groups.items()},
            "all_pasda": base + M.PASDA, "all_pasda_minus_slip": base + [c for c in M.PASDA if c != "soil_slip_high"]}
y = M._labels(df); modern = M._modern(df) > 0; alle = (df.county == "Allegheny").values
near = (df.dist_road <= M.NEAR_ROAD_M).values
rows = []
for name, feats in variants.items():
    aucs = []
    for seed in (0, 1, 2):
        s = M._fit(df.loc[~alle, feats], y[~alle], feats, seed).predict_proba(df.loc[alle, feats])[:, 1]
        aucs.append((roc_auc_score(y[alle], s), roc_auc_score(modern[alle], s), roc_auc_score(modern[alle & near], s[near[alle]])))
    a = np.mean(aucs, 0)
    rows.append(dict(variant=name, usgs_allegheny=a[0], modern_allegheny=a[1], modern_near_road=a[2]))
    print(rows[-1], flush=True)
pd.DataFrame(rows).round(3).to_csv("outputs/ablation_allegheny_holdout.csv", index=False)
