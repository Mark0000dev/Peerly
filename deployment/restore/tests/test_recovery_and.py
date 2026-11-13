import hashlib
import json
from pathlib import Path

import pytest
from deployment.restore import capture_backup
from deployment.restore.accept_restore import MAX_JSON, RejectedError, digest, unique
from deployment.restore.recovery_and import GroupingError
from deployment.restore.recovery_checks import (
    catalog,
    definition_hash,
    legacy_definition_hash,
)

FIXTURE = Path(__file__).with_name("fixtures") / "check-roundtrip.json"


def pairs() -> list[dict[str, str]]:
    raw: object = json.loads(FIXTURE.read_text(), object_pairs_hook=unique)
    assert isinstance(raw, list)
    result = []
    for row in raw:
        assert isinstance(row, dict)
        value = {
            key: item for key, item in row.items() if isinstance(key, str) and isinstance(item, str)
        }
        result.append(value)
    return result


@pytest.mark.parametrize("pair", pairs())
def test_actual_native_counterexamples_preserve_raw_hashes_and_ordered_operands(
    pair: dict[str, str],
) -> None:
    source, target = pair["source_raw_definition"], pair["target_raw_definition"]
    assert hashlib.sha256(source.encode()).hexdigest() == pair["source_raw_sha256"]
    assert hashlib.sha256(target.encode()).hexdigest() == pair["target_raw_sha256"]
    assert legacy_definition_hash(source) == pair["source_format2_sha256"]
    assert legacy_definition_hash(target) == pair["target_format2_sha256"]
    assert legacy_definition_hash(source) != legacy_definition_hash(target)
    assert definition_hash(source) == definition_hash(target)
    assert definition_hash(source) != definition_hash(target.replace("<=", "<"))


@pytest.mark.parametrize(
    "changed",
    [
        "c|t|CHECK (((a > 1) OR (b < 2)) AND (c = 3))",
        "c|t|CHECK (((a > 1) AND (b < 2)) OR (c = 3))",
        "c|t|CHECK ((NOT ((a > 1) AND (b < 2))) AND (c = 3))",
        "c|t|CHECK (((b < 2) AND (a > 1)) AND (c = 3))",
        "c|t|CHECK (((a > 2) AND (b < 2)) AND (c = 3))",
        "c|t|CHECK (((a::text > '1') AND (b < 2)) AND (c = 3))",
    ],
)
def test_changed_operand_or_not_cast_and_order_do_not_collapse(changed: str) -> None:
    source = "c|t|CHECK (((a > 1) AND (b < 2)) AND (c = 3))"
    assert definition_hash(source) != definition_hash(changed)


def test_quoted_and_or_not_and_parentheses_are_opaque() -> None:
    source = "c|t|CHECK (((a = 'AND (OR) NOT') AND (\"AND\" = 'text')) AND (c = 3))"
    target = "c|t|CHECK ((a = 'AND (OR) NOT') AND (\"AND\" = 'text') AND (c = 3))"
    assert definition_hash(source) == definition_hash(target)
    assert definition_hash(source) != definition_hash(target.replace("'AND (OR) NOT'", "'OR'"))


@pytest.mark.parametrize(
    "body",
    [
        "CASE WHEN a THEN b ELSE c END",
        "a BETWEEN 1 AND 2",
        "EXISTS (SELECT 1)",
        "a IN (SELECT b FROM t)",
        "sum(a) OVER (PARTITION BY b)",
    ],
)
def test_unsupported_sql_is_left_exact(body: str) -> None:
    source = "c|t|CHECK (((a > 1) AND (b < 2)) AND (" + body + "))"
    target = "c|t|CHECK ((a > 1) AND (b < 2) AND (" + body + "))"
    assert definition_hash(source) == legacy_definition_hash(source)
    assert definition_hash(source) != definition_hash(target)


def test_only_check_constraints_are_normalized() -> None:
    source = "CREATE INDEX x ON t(a) WHERE (((a > 1) AND (b < 2)) AND (c = 3))"
    target = "CREATE INDEX x ON t(a) WHERE ((a > 1) AND (b < 2) AND (c = 3))"
    assert definition_hash(source) == legacy_definition_hash(source)
    assert definition_hash(source) != definition_hash(target)


@pytest.mark.parametrize(
    "definition",
    [
        "c|t|CHECK ((a AND b)",
        "c|t|CHECK (a AND)",
        "c|t|CHECK " + "(" * 70 + "a" + ")" * 70,
    ],
)
def test_incomplete_or_unbounded_groups_reject(definition: str) -> None:
    with pytest.raises(
        GroupingError, match=r"check_group_incomplete|check_and_operand|check_group_bound"
    ):
        definition_hash(definition)


def test_format2_not_relabelled_and_new_sql_pin_is_explicit() -> None:
    value: dict[str, object] = {
        "format": 2,
        "database": "synthetic_source",
        "heads": ["0060_report_triage"],
        "invalid_indexes": 0,
        "entries": [
            {"kind": "schema", "schema": "public", "name": "", "sha256": "a" * 64},
        ],
    }
    with pytest.raises(RejectedError, match="recovery_catalog"):
        catalog(value, value["heads"])
    value["format"] = 3
    assert catalog(value, value["heads"])
    sql = Path(capture_backup.__file__).with_name("recovery_catalog.sql")
    assert digest(sql, MAX_JSON) == capture_backup.CATALOG_SQL_SHA256
    assert b"'format',3" in capture_backup.catalog_sql(sql, "00000001-00000001-1")
