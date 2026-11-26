"""Compressed AEF embeddings: PCA (fit on training counties only) added to the primary model, Allegheny holdout."""
import numpy as np, pandas as pd
from sklearn.decomposition import PCA
from sklearn.metrics import roc_auc_score
from swpa import aef, grid, pasda, model as M
df = grid.build().join(pasda.build()).join(aef.build())
y = M._labels(df); modern = M._modern(df) > 0; alle = (df.county == "Allegheny").values
primary = M.feature_sets(df)[M.PRIMARY]
for k in (4, 8, 16):
    pca = PCA(k, random_state=0).fit(df.loc[~alle, aef.COLS].sample(300000, random_state=0))  # fit on training counties only
    pcs = [f"aef_pc{i}" for i in range(k)]
    df[pcs] = pca.transform(df[aef.COLS])
    feats = primary + pcs
    r = [roc_auc_score(modern[alle], M._fit(df.loc[~alle, feats], y[~alle], feats, s).predict_proba(df.loc[alle, feats])[:, 1]) for s in (0, 1, 2)]
    print(f"primary + AEF PCA-{k}: modern Allegheny {np.mean(r):.3f}  (explained var {pca.explained_variance_ratio_.sum():.2f})", flush=True)
