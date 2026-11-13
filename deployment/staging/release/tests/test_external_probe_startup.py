"""Run exact probe strings with synthetic asyncpg that rejects managed-PG startup.

Child receives only fake settings/modules, never actual DB/provider credentials.
Read-only repeatable-read transaction must precede every SELECT; close is tested
on successful queries and on query failure. No server or container is started.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import TYPE_CHECKING

import pytest
from deployment.staging.release.external_probe import EXTERNAL_DATABASE, EXTERNAL_REGISTRY
from deployment.staging.release.native import owned_command

if TYPE_CHECKING:
    from pathlib import Path

DRIVER = """import atexit,json,os
EVENTS=[]
closed=False
inside=False
class CantChangeRuntimeParamError(RuntimeError): pass
@atexit.register
def report(): print(json.dumps({'events':EVENTS,'closed':closed,'inside':inside}))
async def connect(dsn,*,timeout,command_timeout,**kwargs):
 EVENTS.append('connect')
 if 'server_settings' in kwargs:
  raise CantChangeRuntimeParamError('unsupported startup parameter')
 assert dsn==os.environ['EXPECTED_DSN']
 assert timeout==5 and command_timeout==5
 assert kwargs==({'ssl':False} if os.environ['SSL_DISABLED']=='yes' else {})
 return Connection()
class Transaction:
 async def __aenter__(self):
  global inside
  inside=True; EVENTS.append('enter_readonly_repeatable_read')
 async def __aexit__(self,*args):
  global inside
  inside=False; EVENTS.append('exit_transaction')
class Connection:
 def transaction(self,*,readonly,isolation):
  assert readonly is True and isolation=='repeatable_read'
  return Transaction()
 async def fetchval(self,query):
  assert inside
  if query=="SELECT set_config('statement_timeout','5000',true)":
   EVENTS.append('set_statement');return '5000'
  if query=="SELECT set_config('lock_timeout','1000',true)":
   EVENTS.append('set_lock');return '1000'
  if query=="SELECT current_setting('transaction_read_only')":
   EVENTS.append('check_readonly');return 'off' if os.environ['FAULT']=='readonly' else 'on'
  assert query=='SELECT current_database()'
  assert EVENTS[-1]=='check_readonly'
  EVENTS.append('database')
  return 'stage'
 async def fetch(self,query):
  assert inside and query.startswith('SELECT ')
  if query=='SELECT version_num FROM public.alembic_version':
   EVENTS.append('schema')
   if os.environ['FAULT']=='query': raise RuntimeError('synthetic readonly query failure')
   return [{'version_num':'0060_report_triage'}]
  assert query==("SELECT sink,revision,encode(fingerprint,'hex') AS fingerprint "
   "FROM public.external_delivery_destinations ORDER BY sink,revision")
  EVENTS.append('registry')
  return [{'sink':'umami','revision':1,'fingerprint':'c'*64}]
 async def close(self):
  global closed
  closed=True; EVENTS.append('close')
"""
SETTINGS = """import os
class Secret:
 def get_secret_value(self): return os.environ['DATABASE_URL']
class ExternalDeliveryWorkerSettings:
 database_url=Secret()
"""
BOOTSTRAP = """class Sink:
 value='umami'
class Destination:
 sink=Sink()
 revision=1
class Configuration:
 destination=Destination()
def _external_destination_configs(settings): return (Configuration(),)
"""
FINGERPRINT = """def target_fingerprint(configuration): return bytes.fromhex('c'*64)
"""


def fake_modules(root: Path) -> None:
    files = {
        "asyncpg.py": DRIVER,
        "studymate/config.py": SETTINGS,
        "studymate/bootstrap.py": BOOTSTRAP,
        "studymate/infrastructure/external_delivery/http_adapters/configuration.py": FINGERPRINT,
    }
    for name, body in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
        for parent in target.parents:
            if parent == root:
                break
            (parent / "__init__.py").touch()


@pytest.mark.parametrize(
    "script", [EXTERNAL_DATABASE, EXTERNAL_REGISTRY], ids=["configured", "registry"]
)
@pytest.mark.parametrize("failure", ["none", "query", "readonly"])
@pytest.mark.parametrize("ssl_disabled", [False, True])
def test_managed_startup_and_readonly_transaction_preserved(
    tmp_path: Path, script: str, failure: str, ssl_disabled: bool
) -> None:
    fake_modules(tmp_path)
    query = "application_name=probe%20stage&application_name=repeat&options=-c%20x%3Dy"
    raw = "postgresql+asyncpg://user:p%40ss@synthetic.invalid/stage?" + query
    if ssl_disabled:
        raw += "&ssl=disable"

    async def run_probe() -> tuple[int, bytes]:
        async with asyncio.timeout(5):
            result = await owned_command(
                (sys.executable, "-c", script),
                cwd=str(tmp_path),
                env={
                    "PYTHONPATH": str(tmp_path),
                    "DATABASE_URL": raw,
                    "EXPECTED_DSN": "postgresql://user:p%40ss@synthetic.invalid/stage?" + query,
                    "SSL_DISABLED": "yes" if ssl_disabled else "no",
                    "FAULT": failure,
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )
        return result.returncode, result.stdout

    code, output = asyncio.run(run_probe())
    lines = output.splitlines()
    trace = json.loads(lines[-1])
    assert trace["closed"] is True
    assert trace["inside"] is False
    expected = [
        "connect",
        "enter_readonly_repeatable_read",
        "set_statement",
        "set_lock",
        "check_readonly",
    ]
    if failure != "readonly":
        expected.extend(["database", "schema"])
    if failure != "none":
        assert code != 0
    else:
        assert code == 0
        expected.append("registry")
        result = json.loads(lines[0])
        assert result["heads"] == ["0060_report_triage"]
        assert result["registered"] == [{"sink": "umami", "revision": 1, "fingerprint": "c" * 64}]
        if script == EXTERNAL_DATABASE:
            assert result["configured"] == result["registered"]
        else:
            assert "configured" not in result
    assert trace["events"] == [*expected, "exit_transaction", "close"]


@pytest.mark.parametrize(
    "script", [EXTERNAL_DATABASE, EXTERNAL_REGISTRY], ids=["configured", "registry"]
)
@pytest.mark.parametrize(
    "query",
    ["ssl=disable&ssl=disable", "ssl=disable&sslmode=disable", "ssl=require", "SSL=disable"],
)
def test_ambiguous_or_unreviewed_ssl_rejected_before_connect(
    tmp_path: Path, script: str, query: str
) -> None:
    fake_modules(tmp_path)

    async def run_probe() -> tuple[int, bytes]:
        async with asyncio.timeout(5):
            result = await owned_command(
                (sys.executable, "-c", script),
                cwd=str(tmp_path),
                env={
                    "PYTHONPATH": str(tmp_path),
                    "DATABASE_URL": "postgresql+asyncpg://synthetic.invalid/stage?" + query,
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )
        return result.returncode, result.stdout

    code, output = asyncio.run(run_probe())
    assert code != 0
    trace = json.loads(output.splitlines()[-1])
    assert trace["events"] == []
    assert trace["closed"] is False
    assert trace["inside"] is False
