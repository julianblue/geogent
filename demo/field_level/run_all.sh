#!/usr/bin/env bash
# Full field-level pipeline for one window. Usage: ./run_all.sh <window> <datadir> [fetch]
#   PY  = scratch venv python (pystac-client rasterio duckdb>=1.5 scikit-learn scipy shapely pyproj pandas pyogrio matplotlib)
#   TPY = backend venv python of a feat/tessera-p1 worktree (icechunk) -- only for the fetch step
set -euo pipefail
W=$1; D=$2; cd "$(dirname "$0")"
PY=${PY:-python}; PY="$PY -W ignore"
if [[ "${3:-}" == fetch ]]; then
  $PY labels.py "$W" "$D"; $PY units.py "$W" "$D"
  ${TPY:?set TPY} tessera_extract.py "$W" "$D"
  for y in $($PY -c "from windows import *; print(*FTW_YEARS[WINDOWS['$W']['cc']])"); do $PY s2_cube.py "$W" "$y" "$D"; done
  $PY dem.py "$W" "$D"; $PY weather.py "$W" "$D"
fi
$PY units.py "$W" "$D"
$PY pheno.py "$W" "$D"
$PY cycles_ts.py "$W" "$D"
$PY features.py "$W" "$D"
for a in a1_rotation a2_phenology a3_peers a4_zones a5_anomaly a6_boundary a4b_zone_weather a8_preceding; do $PY $a.py "$W" "$D" > "$D/$W/$a.log"; done
