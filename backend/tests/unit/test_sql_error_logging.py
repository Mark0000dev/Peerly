import json
import logging
import sys
from types import FunctionType

import pytest
from sqlalchemy.exc import DBAPIError

from studymate.infrastructure.observability.logging import SafeJsonFormatter

CANARY = "PRIVATE_SQL_PARAMETERS_MESSAGE_CANARY"
FRAME_LIMIT = 20


class DriverFailureError(Exception):
    def __init__(self, code: object) -> None:
        self.sqlstate = code
        super().__init__(CANARY)


def payload(error: Exception) -> dict[str, object]:
    try:
        raise error
    except Exception:
        record = logging.LogRecord(
            "uvicorn.error", logging.ERROR, __file__, 1, CANARY, (), sys.exc_info()
        )
        result = json.loads(SafeJsonFormatter().format(record))
        assert isinstance(result, dict)
        assert CANARY not in json.dumps(result)
        return result


def test_dbapi_reports_root_type_sqlstate_without_any_sql_or_private_text() -> None:
    error = DBAPIError(CANARY, {"private": CANARY}, DriverFailureError("42P01"), False)
    value = payload(error)
    assert value["error_type"] == "DriverFailureError"
    assert value["database_error_code"] == "42P01"
    assert value["event"] == "runtime_error"


@pytest.mark.parametrize("code", [None, 42, True, "42p01", "42P01-private", "\uff14\uff12P01", ""])
def test_malformed_sqlstate_never_leaves_formatter(code: object) -> None:
    value = payload(DBAPIError(CANARY, {}, DriverFailureError(code), False))
    assert "database_error_code" not in value


def test_exception_groups_and_chained_dbapi_preserve_driver_type_and_code() -> None:
    error = DBAPIError(CANARY, {}, DriverFailureError("26000"), False)
    value = payload(ExceptionGroup(CANARY, [error]))
    assert value["database_error_code"] == "26000"
    assert value["error_type"] == "DriverFailureError"


def test_cyclic_exception_chain_is_bounded() -> None:
    first, second = RuntimeError(CANARY), ValueError(CANARY)
    first.__cause__ = second
    second.__cause__ = first
    value = payload(first)
    assert value["error_type"] == "ValueError"
    assert "database_error_code" not in value


def deep_driver(count: int) -> None:
    if count:
        deep_driver(count - 1)
    else:
        raise DBAPIError(CANARY, {}, DriverFailureError("42P05"), False)


def application_caller() -> None:
    deep_driver(40)


def test_application_frame_survives_long_driver_tail_with_original_bound() -> None:
    application = FunctionType(
        application_caller.__code__,
        {
            "__name__": "studymate.application.synthetic",
            "deep_driver": deep_driver,
        },
    )
    try:
        application()
    except DBAPIError:
        record = logging.LogRecord(
            "uvicorn.error", logging.ERROR, __file__, 1, CANARY, (), sys.exc_info()
        )
        result = SafeJsonFormatter().format(record)
    else:
        pytest.fail("Synthetic driver failure was not raised")
    value = json.loads(result)
    assert len(value["stack"]) <= FRAME_LIMIT
    assert any(frame["function"] == "application_caller" for frame in value["stack"])
    assert value["stack"][-1]["function"] == "deep_driver"
    assert CANARY not in result
