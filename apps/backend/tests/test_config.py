"""Settings validator behaviour around the JWT secret guardrail."""

import pytest

from geogent_backend.config import Settings


@pytest.mark.parametrize(
    "weak_secret",
    ["change-me-in-prod", "dev-only-change-me", ""],
)
def test_weak_jwt_secret_rejected_outside_development(weak_secret: str) -> None:
    with pytest.raises(ValueError, match="JWT_SECRET_KEY"):
        Settings(app_env="production", jwt_secret_key=weak_secret)


def test_weak_jwt_secret_allowed_in_development() -> None:
    s = Settings(app_env="development", jwt_secret_key="change-me-in-prod")
    assert s.jwt_secret_key == "change-me-in-prod"


def test_strong_secret_passes_in_production() -> None:
    # Any value outside _DEV_JWT_DEFAULTS satisfies the validator. The string
    # is intentionally short / low-entropy so secret scanners don't flag it.
    s = Settings(app_env="production", jwt_secret_key="not-a-default-value")
    assert s.app_env == "production"
