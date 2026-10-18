"""Study windows shared by every field_level script."""

WINDOWS = {
    # name: (lon_min, lat_min, lon_max, lat_max), UTM EPSG, FTW country code (None = EuroCrops only)
    "marchfeld": dict(bbox=(16.54, 48.22, 16.66, 48.29), epsg=32633, cc="at", dem="N48_00_E016_00"),
    "traun_enns": dict(bbox=(14.38, 48.12, 14.50, 48.19), epsg=32633, cc="at", dem="N48_00_E014_00"),
    # Uckermark, around the committed EuroCrops sample; FTW de_bb has 2010-2023 (no 2024/25)
    "uckermark": dict(bbox=(13.82, 53.26, 13.98, 53.34), epsg=32633, cc="de_bb", dem="N53_00_E013_00"),
}
FTW_YEARS = {"at": list(range(2019, 2026)), "de_bb": list(range(2019, 2024))}
PRED_COUNTRY = {"at": "AT/Austria", "de_bb": "DE/Germany"}
YEARS = list(range(2019, 2026))
