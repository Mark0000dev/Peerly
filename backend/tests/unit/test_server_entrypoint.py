import pytest
import uvicorn

from studymate import server


def test_server_cli_uses_factory_and_content_free_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    configured: list[bool] = []
    called: list[bool] = []

    def run(app: str, **options: object) -> None:
        assert app == "studymate.bootstrap:create_app"
        assert options["factory"] is True
        assert options["host"] == "127.0.0.1"
        assert options["reload"] is True
        assert options["access_log"] is False
        assert isinstance(options["log_config"], dict)
        called.append(True)

    monkeypatch.setattr(server, "configure_logging", lambda: configured.append(True))
    monkeypatch.setattr(uvicorn, "run", run)
    server.main(["--reload"])
    assert configured == [True]
    assert called == [True]
