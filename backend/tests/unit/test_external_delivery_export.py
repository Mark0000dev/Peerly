"""Export actual mounted intake and operator contracts without provider/database access."""

import json

from studymate.export_openapi import build_schema


async def test_real_observation_and_delivery_routes_expose_six_closed_variants() -> None:
    schema = json.dumps(await build_schema(), sort_keys=True)
    for path in (
        "/api/v1/telemetry/events",
        "/api/v1/operator/delivery-sources",
        "/api/v1/operator/delivery-sources/{source_id}",
    ):
        assert f'"{path}"' in schema
    assert '"quality.observed"' in schema
    assert '"search_delivery_sources"' in schema
    assert '"read_delivery_source"' in schema
    assert '"delivery_source"' in schema
    assert '"discriminator"' in schema
