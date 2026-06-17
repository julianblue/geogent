"""The recipe hash is the content-addressing key: it must be stable across
field-order/whitespace and must change when the recipe or its version changes."""

from datetime import date

from geogent_backend.geo.indices import IndexName
from geogent_backend.schemas.artifact import TemporalFeaturesRecipe
from geogent_backend.services.artifact_service import recipe_hash


def _recipe(**over: object) -> TemporalFeaturesRecipe:
    base = {
        "field_id": 1,
        "index": IndexName.ndvi,
        "start_date": date(2025, 4, 1),
        "end_date": date(2025, 9, 30),
        "max_cloud_cover": 20,
        "max_scenes": 60,
    }
    base.update(over)
    return TemporalFeaturesRecipe(**base)


def test_identical_recipes_hash_equal() -> None:
    assert recipe_hash(_recipe()) == recipe_hash(_recipe())


def test_different_field_changes_hash() -> None:
    assert recipe_hash(_recipe()) != recipe_hash(_recipe(field_id=2))


def test_different_index_changes_hash() -> None:
    assert recipe_hash(_recipe()) != recipe_hash(_recipe(index=IndexName.evi))


def test_recipe_version_busts_hash() -> None:
    assert recipe_hash(_recipe()) != recipe_hash(_recipe(recipe_version=2))
