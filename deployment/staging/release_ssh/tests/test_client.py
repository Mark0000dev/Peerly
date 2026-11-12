"""Actual disposable local agent/key loading; dummy transport, NO SSH connection."""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import sys
from typing import TYPE_CHECKING

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from deployment.staging.release_ssh import client
from deployment.staging.release_ssh.broker import AdmissionError
from deployment.staging.release_ssh.tests.test_admission import body

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [0, 7])
async def test_client_loads_unregistered_key_in_owned_agent_and_cleans_it(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    host = "staging.example.invalid"
    blob = (
        struct.pack(">I", len(b"ssh-ed25519")) + b"ssh-ed25519" + struct.pack(">I", 32) + bytes(32)
    )
    known = host + " ssh-ed25519 " + base64.b64encode(blob).decode()
    # Disposable synthetic key, never authorized on any host or account. Generated
    # and consumed in memory; no existing/deployment credential is read.
    private = (
        Ed25519PrivateKey.generate()
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            serialization.NoEncryption(),
        )
        .decode()
    )
    observed: list[Path] = []
    calls: list[str] = []
    program = (
        "import json,os,stat,subprocess,sys;from pathlib import Path;"
        'loaded=subprocess.run(["/usr/bin/ssh-add","-l"],capture_output=True);'
        "assert loaded.returncode==0 and len(loaded.stdout.splitlines())==1;"
        "assert stat.S_IMODE(Path(sys.argv[1]).stat().st_mode)==0o600;"
        'assert "ssh-ed25519" in Path(sys.argv[1]).read_text();'
        "assert set(p.name for p in Path(sys.argv[1]).parent.iterdir())=="
        '{"known_hosts","agent.sock"};'
        "data=json.loads(sys.stdin.buffer.read());"
        'print(json.dumps({"protocol":1,"outcome":"verified",'
        '"attempt":str(data["run_id"])+"-"+str(data["run_attempt"])}))'
    )
    program += f";sys.exit({status})"

    def argv(host: str, agent: Path, known_file: Path) -> tuple[str, ...]:
        observed.extend([agent, known_file])
        calls.append(host)
        return (sys.executable, "-c", program, str(known_file))

    monkeypatch.setattr(client, "ssh_arguments", argv)
    if status:
        with pytest.raises(AdmissionError, match="ssh_failed_or_unknown_no_retry"):
            await client.send(json.dumps(body()).encode(), host, known, private)
    else:
        await client.send(json.dumps(body()).encode(), host, known, private)
    assert calls == [host]
    assert observed
    for path in observed:
        assert not await asyncio.to_thread(path.exists)
