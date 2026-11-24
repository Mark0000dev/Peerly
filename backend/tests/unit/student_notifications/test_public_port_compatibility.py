"""Offline preservation checks for the public notification composition."""

import hashlib
import json
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from studymate.export_openapi import build_schema


def mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    result: dict[str, object] = {}
    for key, item in value.items():
        assert isinstance(key, str)
        result[key] = item
    return result


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


async def test_all_original_public_paths_and_schemas_survive_core_port() -> None:
    baseline: object = json.loads(
        Path(__file__).with_name("public_contract_baseline.json").read_text()
    )
    expected = mapping(baseline)
    expected_paths = mapping(expected["paths"])
    expected_schemas = mapping(expected["schemas"])
    schema = await build_schema()
    paths = mapping(schema["paths"])
    schemas = mapping(mapping(schema["components"])["schemas"])
    assert paths.keys() == expected_paths.keys() | {
        "/api/v1/auth/native/start",
        "/api/v1/auth/native/return",
        "/api/v1/auth/native/exchange",
        "/api/v1/me/notification-delivery",
        "/api/v1/me/notification-delivery/{installation_id}",
    }
    for path, original in expected_paths.items():
        current = mapping(paths[path])
        if path == "/api/v1/auth/logout":
            post = mapping(current["post"])
            parameters = post["parameters"]
            assert isinstance(parameters, list)
            post["parameters"] = [
                item
                for item in parameters
                if mapping(item)["name"] != "x-notification-installation"
            ]
            responses = mapping(post["responses"])
            success = mapping(responses["204"])
            headers = mapping(success.pop("headers"))
            assert set(headers) == {"X-Notification-Retirement"}
            responses["204"] = success
            post["responses"] = responses
            current["post"] = post
        assert digest(current) == original, path
    for name, original in expected_schemas.items():
        assert digest(schemas[name]) == original, name


def test_released_migration_history_keeps_exact_order_and_one_head() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))
    assert scripts.get_heads() == ["0064_notification_subscriptions"]
    chain = (
        ("0061_native_login", "0060_report_triage"),
        ("0062_google_display", "0061_native_login"),
        ("0063_student_notifications", "0062_google_display"),
        ("0064_notification_subscriptions", "0063_student_notifications"),
    )
    for revision, predecessor in chain:
        script = scripts.get_revision(revision)
        assert script is not None
        assert script.down_revision == predecessor
