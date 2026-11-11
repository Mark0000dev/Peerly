import pytest
from pydantic import SecretStr, ValidationError

from studymate.bootstrap import _external_destination_configs
from studymate.config import (
    ExternalDeliveryWorkerSettings,
    PublicAssetReleaseConfiguration,
    Settings,
    SupportTelegramDeliveryConfiguration,
    UmamiDeliveryConfiguration,
)
from studymate.infrastructure.external_delivery.http_adapters import target_fingerprint


def test_destinations_require_explicit_targets_and_keep_credentials_out_of_identity() -> None:
    from uuid import uuid4

    url = SecretStr("postgresql+asyncpg://test:synthetic@localhost/synthetic_test")
    with pytest.raises(ValidationError, match="destination"):
        ExternalDeliveryWorkerSettings(_env_file=None, database_url=url)
    support = SupportTelegramDeliveryConfiguration(
        revision=1,
        chat_id=-1000000001,
        operator_origin="https://app.test",
        token=SecretStr("123:synthetic_first"),
    )
    first = ExternalDeliveryWorkerSettings(
        _env_file=None,
        database_url=url,
        umami=UmamiDeliveryConfiguration(
            revision=1, origin="https://analytics.test", website_id=uuid4()
        ),
        telegram_support=support,
    )
    rotated = first.model_copy(
        update={
            "telegram_support": support.model_copy(
                update={"token": SecretStr("123:synthetic_rotated")}
            )
        }
    )
    original = _external_destination_configs(first)
    assert tuple(target_fingerprint(value) for value in original) == tuple(
        target_fingerprint(value) for value in _external_destination_configs(rotated)
    )
    assert "synthetic_first" not in repr(first)
    assert "synthetic_first" not in repr(original)


def test_public_assets_are_explicit_immutable_and_cannot_rebind_a_release() -> None:
    release = PublicAssetReleaseConfiguration(release_id="a" * 40, asset_ids=frozenset({0, 1}))
    url = SecretStr("postgresql+asyncpg://test:synthetic@localhost/synthetic_test")
    configured = Settings(_env_file=None, database_url=url, public_asset_releases=(release,))
    assert configured.public_asset_releases == (release,)
    with pytest.raises(ValidationError, match="redefine"):
        Settings(_env_file=None, database_url=url, public_asset_releases=(release, release))
    with pytest.raises(ValidationError):
        PublicAssetReleaseConfiguration(release_id="a" * 40, asset_ids=frozenset({4096}))
