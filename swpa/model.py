"""Train and evaluate regional landslide susceptibility models on the H3 cell table.

Label: the hexagon contains an IRISE USGS 1970s landslide point.
Evaluations:
  1. Spatial block CV (folds grouped by H3 res-6 parents) -> out-of-fold score for every cell (used for maps).
  2. Leave-one-county-out: train on 11 counties, score the 12th. The honest test of "expanding" to new ground.
  3. Allegheny-only transfer: train on Allegheny alone (like the original county model), score the other 11.
  4. Independent modern test: IRISE 311 / County / City / Pitt / Forest Hills records plus PASDA's Allegheny County
     Public Works (2025) and FEMA 2018 assistance sites. None are used in training.

PASDA predictors are restricted to conditions that existed by 1975, the date of the training labels
(e.g. longwall panels and wells completed by then), so the model cannot learn from mining or drilling
that post-dates the landslides it is trained on.
"""
import json

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import config as C
from .grid import NLCD_GROUPS

TERRAIN = ["elev", "slope_mean", "slope_max", "slope_p90", "slope_std", "frac_steep", "northness", "eastness",
           "profile_curv", "plan_curv", "profile_curv_min", "plan_curv_min", "tpi_50m", "tpi_300m",
           "relief_250m", "roughness", "twi_mean", "twi_max", "hand", "dist_channel"]
LANDCOVER = [f"lc_{k}" for k in NLCD_GROUPS]
PASDA = ["mined", "dist_mined", "ug_permit", "longwall_pre1976", "well_density_pre1976",
         "road", "dist_road", "dist_state_road", "regolith_m",
         "soil_bedrock_cm", "soil_watertable_cm", "soil_hydgrp", "soil_drainage", "soil_clay", "soil_ksat",
         "soil_shrinkswell", "soil_slip_high"]
# An Allegheny-holdout ablation (ablation.py) showed only the mining layers improve prediction of modern
# landslides; roads and soils fit the 1970s map better but transfer worse, so they stay out of the primary model.
MINING = ["mined", "dist_mined", "ug_permit", "longwall_pre1976"]
BASELINE = "terrain_geo_lc"
PRIMARY = "plus_mining"
ALL_PASDA = "plus_pasda"
MODERN_COLS = ["n_modern", "n_county_pw_2025", "n_fema_ia_2018", "n_fema_pa_2018"]
NEAR_ROAD_M = 30

LGB_PARAMS = dict(objective="binary", learning_rate=0.05, n_estimators=400, num_leaves=31,
                  min_child_samples=40, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                  reg_lambda=1.0, verbose=-1, n_jobs=-1)
N_FOLDS = 5
NEG_SAMPLE = 0.25  # train on all positives + 25% of negatives; rankings (AUC) are unaffected
MIN_POS_FOR_AUC = 20


def feature_sets(df):
    geology = sorted(c for c in df.columns if c.startswith("geo_"))
    base = TERRAIN + geology + LANDCOVER
    return {"slope_only": ["slope_mean"], "terrain": TERRAIN, BASELINE: base, PRIMARY: base + MINING,
            ALL_PASDA: base + PASDA}


def _labels(df):
    return (df.n_usgs_1970s > 0).astype(int).values


def _modern(df):
    return df[[c for c in MODERN_COLS if c in df]].sum(axis=1).values


def _fit(X, y, features, seed=0):
    rng = np.random.default_rng(seed)
    keep = (y == 1) | (rng.random(len(y)) < NEG_SAMPLE)
    model = (make_pipeline(StandardScaler(), LogisticRegression()) if len(features) == 1
             else lgb.LGBMClassifier(**LGB_PARAMS, random_state=seed))
    return model.fit(X[keep], y[keep])


def _auc(y, s):
    if y.sum() < MIN_POS_FOR_AUC or y.sum() == len(y):
        return np.nan
    return float(roc_auc_score(y, s))


def capture(score, hits, frac=0.10):
    """Share of events in the top `frac` highest-scoring cells."""
    order = np.argsort(-score)
    return float(np.cumsum(hits[order])[int(len(score) * frac) - 1] / hits.sum())


def block_cv(df, features, seed=0):
    y, X = _labels(df), df[features]
    oof = np.zeros(len(df))
    cv = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    for tr, te in cv.split(X, y, groups=df.block):
        oof[te] = _fit(X.iloc[tr], y[tr], features, seed).predict_proba(X.iloc[te])[:, 1]
    return oof


def leave_one_county_out(df, features):
    y, X = _labels(df), df[features]
    out = np.zeros(len(df))
    for county in C.COUNTIES:
        te = (df.county == county).values
        out[te] = _fit(X[~te], y[~te], features).predict_proba(X[te])[:, 1]
    return out


def allegheny_transfer(df, features):
    y, X = _labels(df), df[features]
    tr = (df.county == "Allegheny").values
    return _fit(X[tr], y[tr], features).predict_proba(X)[:, 1]  # Allegheny rows themselves are in-sample


def per_county(df, scores):
    """ROC-AUC per county for each score column, against USGS labels and modern records."""
    rows = []
    usgs, modern = _labels(df), (_modern(df) > 0).astype(int)
    for county in C.COUNTIES:
        m = (df.county == county).values
        row = dict(county=county, cells=int(m.sum()), usgs_cells=int(usgs[m].sum()), modern_cells=int(modern[m].sum()))
        for name, s in scores.items():
            row[f"auc_usgs__{name}"] = _auc(usgs[m], s[m])
            row[f"auc_modern__{name}"] = _auc(modern[m], s[m])
        rows.append(row)
    return pd.DataFrame(rows)


def run(df):
    fs = feature_sets(df)
    y = _labels(df)
    modern_n = _modern(df)
    modern = modern_n > 0
    near_road = (df.dist_road <= NEAR_ROAD_M).values
    print(f"Training on {len(df):,} cells, {y.sum():,} with a USGS landslide ({y.mean():.2%})")
    scores, results = {}, {}
    for name, feats in fs.items():
        print(f"  block CV: {name}")
        scores[f"cv_{name}"] = block_cv(df, feats)
    for name in ["slope_only", BASELINE, PRIMARY, ALL_PASDA]:
        print(f"  leave-one-county-out: {name}")
        scores[f"loco_{name}"] = leave_one_county_out(df, fs[name])
    for name in [BASELINE, PRIMARY]:
        print(f"  Allegheny-only transfer: {name}")
        scores[f"allegheny_only_{name}"] = allegheny_transfer(df, fs[name])

    # Modern records are nearly all in Allegheny, so they are scored against Allegheny cells.
    alle = (df.county == "Allegheny").values
    for key, s in scores.items():
        transfer = key.startswith("allegheny_only")
        scope = ~alle if transfer else np.ones(len(df), bool)  # transfer: USGS scored out-of-county only
        ar = alle & near_road
        results[key] = dict(
            usgs_roc_auc=_auc(y[scope], s[scope]),
            usgs_pr_auc=float(average_precision_score(y[scope], s[scope])),
            usgs_top10_capture=capture(s[scope], y[scope].astype(float)),
            # Modern records are independent of the USGS labels, so they are a fair test for every model.
            modern_roc_auc_allegheny=_auc(modern[alle], s[alle]),
            modern_roc_auc_allegheny_near_road=_auc(modern[ar], s[ar]),
            modern_top10_capture_allegheny=capture(s[alle], modern_n[alle].astype(float)),
        )
        r = results[key]
        print(f"    {key:34s} USGS AUC {r['usgs_roc_auc']:.3f}  PR {r['usgs_pr_auc']:.3f} | modern (Allegheny) "
              f"AUC {r['modern_roc_auc_allegheny']:.3f}, near roads {r['modern_roc_auc_allegheny_near_road']:.3f}")

    county_table = per_county(df, scores)
    final = lgb.LGBMClassifier(**LGB_PARAMS)
    keep = (y == 1) | (np.random.default_rng(0).random(len(y)) < NEG_SAMPLE)
    feats = fs[PRIMARY]
    final.fit(df.loc[keep, feats], y[keep])
    contrib = final.predict(df.loc[keep, feats], pred_contrib=True)[:, :-1]
    importance = pd.DataFrame({"feature": feats, "mean_abs_shap": np.abs(contrib).mean(0)}
                              ).sort_values("mean_abs_shap", ascending=False)
    final.booster_.save_model(str(C.OUT / f"model_{PRIMARY}.txt"))

    out = df[["county", "block", "n_usgs_1970s", "n_nasa", "slope_mean"]].copy()
    out["n_modern"] = modern_n.astype("int32")
    for key, s in scores.items():
        out[f"risk_{key}"] = s.astype("float32")
    primary = pd.Series(scores[f"cv_{PRIMARY}"], index=df.index)
    out["risk_pct"] = primary.rank(pct=True).astype("float32")
    # Within-county ranking: better for local screening where 1970s mapping was sparse (e.g. Fayette).
    out["risk_pct_county"] = primary.groupby(df.county).rank(pct=True).astype("float32")
    out.to_parquet(C.OUT / "cells_risk.parquet")
    county_table.to_csv(C.OUT / "per_county_metrics.csv", index=False)
    importance.to_csv(C.OUT / "feature_importance.csv", index=False)
    (C.OUT / "metrics.json").write_text(json.dumps(results, indent=2))
    return out, results, county_table, importance
