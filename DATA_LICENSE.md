# Data License

This repository contains two kinds of material, licensed separately:

| Material | Where | License |
|---|---|---|
| Source code | `swpa/`, `run.py`, `ablation.py`, `aef_experiment.py`, `aef_pca.py` | MIT License, see [`LICENSE`](LICENSE) |
| Derived data products | `outputs/` (figures, metric tables, interactive map, and any model outputs you regenerate) | Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0), subject to the third-party conditions below |

Raw third-party data are **not** included. They are downloaded from the original providers when the pipeline runs
and remain under their providers' terms, summarized in [`DATA_SOURCES.md`](DATA_SOURCES.md).

## Derived data products: CC BY-SA 4.0

The susceptibility scores, maps and metrics in `outputs/` are derived works of the input datasets.
They are released under the
[Creative Commons Attribution-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-sa/4.0/).
You may share and adapt them for any purpose permitted below, provided that you:

1. **Give credit** to this project and to the underlying data providers (a suggested credit line is at the end of
   this file);
2. **Indicate changes** you make; and
3. **Share adaptations** under the same or a compatible license.

ShareAlike is used because the training labels come from the IRISE Regional Landslide Inventory, which the
University of Pittsburgh publishes under a Creative Commons Attribution-ShareAlike license.

## Third-party conditions that travel with the outputs

The CC BY-SA 4.0 grant above covers only the rights held by the author of this project. It does not remove
conditions that the original data providers attach to their data. In particular:

- **No commercial use of products built on PA DEP mining data without permission.** The primary model uses PA
  Department of Environmental Protection coal-mining layers (mined-out areas, historic underground-mine permits,
  longwall panels), whose terms state "Not for commercial use or resale." The susceptibility outputs are
  therefore provided for research, education and other non-commercial uses. Anyone wishing to use them
  commercially should first confirm permission with PA DEP.
- **Credit and modification notices for PA DCNR geology.** The Pennsylvania Bureau of Geological Survey (DCNR)
  requires credit for its bedrock geology and bedrock-surface data, a description of any modifications, and no
  implication that modified products were reviewed or approved by the Bureau. The required credit and the
  modifications are documented in `DATA_SOURCES.md`; keep that information with any redistribution.
- **NRCS acknowledgment.** Products derived from SSURGO soil data should acknowledge the USDA Natural Resources
  Conservation Service.
- **CC BY 4.0 attribution for AlphaEarth embeddings.** Results of the foundation-model experiment
  (`outputs/aef_*.csv`) derive from the AlphaEarth Foundations Satellite Embedding dataset, produced by Google
  and Google DeepMind under CC BY 4.0. No embedding values are included in this repository.
- **Provider disclaimers.** The Commonwealth of Pennsylvania (PA DEP, PennDOT, PA DCNR) and Allegheny County
  provide their data as is, without warranty, and require users to hold them harmless from claims arising from
  use of the data. Those disclaimers continue to apply to any use of the derived outputs.

## Disclaimer for the derived products

The outputs are **relative rankings of landslide susceptibility** produced by a statistical model trained on
1970s landslide mapping. They are not calibrated probabilities, are not a hazard or risk assessment for any
specific property, and are not a substitute for site-specific geotechnical investigation. Known limitations
(uneven label density between counties, coarse geology, static susceptibility only) are described in the
README. The outputs are not intended for regulatory, permitting, siting, insurance or lending decisions.

THE DERIVED PRODUCTS ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
WITHOUT LIMITATION WARRANTIES OF ACCURACY, COMPLETENESS, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
IN NO EVENT SHALL THE AUTHOR OR THE DATA PROVIDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY
ARISING FROM THE USE OF THESE PRODUCTS.

This summary is provided for convenience and is not legal advice. Where it differs from a provider's own terms,
the provider's terms govern.

## Suggested credit line

> Landslide susceptibility for southwestern Pennsylvania (SWPA Landslide Model), CC BY-SA 4.0. Derived from the
> IRISE Regional Landslide Inventory (University of Pittsburgh, CC BY-SA), USGS 3DEP elevation, USGS/MRLC NLCD 2021,
> PA DCNR Bureau of Geological Survey bedrock geology, and PA Department of Environmental Protection coal-mining
> data (via PASDA). Modifications are described in DATA_SOURCES.md.
