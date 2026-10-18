"""The recipe hash is the content-addressing key: it must be stable across
field-order/whitespace and must change when the recipe or its version changes."""

from datetime import date

import pytest

from geogent_backend.geo.indices import IndexName
from geogent_backend.schemas.artifact import TemporalFeaturesRecipe
from geogent_backend.schemas.embedding import EmbeddingLayerRecipe, FieldEmbeddingsRecipe
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


def _field_embeddings(**over: object) -> FieldEmbeddingsRecipe:
    base = {"field_id": 1, "start_year": 2020, "end_year": 2024}
    base.update(over)
    return FieldEmbeddingsRecipe(**base)


def _layer(**over: object) -> EmbeddingLayerRecipe:
    base = {"year": 2024, "field_id": 1}
    base.update(over)
    return EmbeddingLayerRecipe(**base)


def test_embedding_recipes_hash_stably_and_differ_by_kind() -> None:
    assert recipe_hash(_field_embeddings()) == recipe_hash(_field_embeddings())
    assert recipe_hash(_layer()) == recipe_hash(_layer())
    assert recipe_hash(_field_embeddings()) != recipe_hash(_layer())


@pytest.mark.parametrize(
    "over",
    [
        {"store_version": "v1.2"},  # a store bump busts the cache
        {"recipe_version": 2},
        {"end_year": 2023},
        {"centring": "none"},
        {"aoi_buffer_m": 500},
        {"dim": 64},
        {"field_id": 2},
    ],
)
def test_field_embeddings_hash_changes_with_every_input(over: dict) -> None:
    assert recipe_hash(_field_embeddings()) != recipe_hash(_field_embeddings(**over))


@pytest.mark.parametrize(
    "over",
    [{"store_version": "v1.2"}, {"recipe_version": 2}, {"year": 2023}, {"pad_m": 500}, {"dim": 3}],
)
def test_embedding_layer_hash_changes_with_every_input(over: dict) -> None:
    assert recipe_hash(_layer()) != recipe_hash(_layer(**over))
