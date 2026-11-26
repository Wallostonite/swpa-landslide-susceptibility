"""Southwestern Pennsylvania (IRISE study area) landslide susceptibility pipeline.

    python run.py            # everything (cached steps are skipped)
    python run.py fetch      # download inputs only
    python run.py features   # terrain derivatives + H3 cell tables, county by county
    python run.py train      # models, metrics, maps
    python run.py --force    # rebuild terrain and cell tables
"""
import sys

from swpa import config as C
from swpa import fetch, grid, maps, model, pasda


def main(args):
    force = "--force" in args
    steps = [a for a in args if not a.startswith("--")] or ["fetch", "features", "train"]
    if "fetch" in steps:
        fetch.all_inputs()
        pasda.download()
    if "features" in steps:
        grid.build(force=force)
        pasda.build(force=force)
    if "train" in steps:
        risk, _, table, importance = model.run(grid.build().join(pasda.build()))
        maps.build(risk, table, importance)
        print(f"Outputs in {C.OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
