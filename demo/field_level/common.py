"""Shared helpers: crop groups from HCAT codes, smoothing, spatial blocks."""

import json

import numpy as np
from scipy.signal import savgol_filter

GRID = np.arange(1, 366, 5)  # 5-day DOY grid


def group(code, name=""):
    """Agronomic group from an HCAT3 code (hierarchical, 10 digits)."""
    c = str(code or "")
    n = (name or "").upper()
    if c.startswith("330101") and c != "3301010600":
        if c.startswith("33010106"):
            return "maize"
        return "winter cereal" if c.endswith("01") or "WINTER" in n else "spring cereal"
    if c == "3301010600" or c == "3301090400":
        return "maize"
    if c.startswith("33010700") or c.startswith("33010800") or c.startswith("33010612"):
        return "field veg"
    if c.startswith("330103"):
        return "potato"
    if c.startswith("33012907"):
        return "sugar beet"
    if c.startswith("330116") or c.startswith("330102"):
        return "legume"
    if c.startswith("330106") or c.startswith("330114"):
        return "oilseed/pumpkin"
    if c.startswith("330111"):
        return "fallow"
    if c.startswith("3399") and "UNKNOWN" in n:
        return "other"
    if c.startswith("330109") or c.startswith("3302") or c.startswith("3399"):
        return "grass/forage"
    if c.startswith("3303"):
        return "permanent"
    if c.startswith("3305"):
        return "greenhouse"
    return "other"


ARABLE = {"winter cereal", "spring cereal", "maize", "field veg", "potato", "sugar beet", "legume", "oilseed/pumpkin"}
CEREAL = {"winter cereal", "spring cereal"}


def smooth(doy, v, grid=GRID):
    ok = np.isfinite(v)
    if ok.sum() < 8:
        return None
    s = np.interp(grid, doy[ok], v[ok])
    return savgol_filter(s, 7, 2)


def blocks(cx, cy, km=2):
    return (np.asarray(cx) // (km * 1000)).astype(int) * 1000 + (np.asarray(cy) // (km * 1000)).astype(int)


def load(path):
    return json.load(open(path))
