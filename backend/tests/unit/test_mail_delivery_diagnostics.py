import json
import sys
from io import BytesIO
from pathlib import Path

import pytest
from deployment.backend.mail_delivery_diagnostics import (
    MAX_HEADER_BYTES,
    MAX_LINE_BYTES,
    InvalidHeadersError,
    diagnose,
    main,
)


def test_privacy_and_body_not_read() -> None:
    stream = BytesIO(
        b"From: secret-local@example.test\r\n"
        b"Subject: OTP 728193 https://private.test/token\r\n"
        b"Authorization: credential-secret\r\n"
        b"Authentication-Results: private-host; spf=pass smtp.mailfrom=secret@example.test;\r\n"
        b" dkim=pass header.d=example.test; dmarc=fail action=quarantine; compauth=fail\r\n"
        b"X-Forefront-Antispam-Report: CIP:192.0.2.1;SCL:9;SFV:SPM;CAT:HPHSH;\r\n"
        b"\r\nBODY-NEVER-READ"
    )
    report = diagnose(stream)
    encoded = json.dumps(dict(report))
    for secret in ("secret", "728193", "https:", "private", "example.test", "192.0.2.1", "BODY"):
        assert secret not in encoded
    assert stream.read() == b"BODY-NEVER-READ"
    assert report["authentication"] == [
        {
            "spf": ["pass"],
            "dkim": ["pass"],
            "dmarc": ["fail"],
            "dmarc_action": ["quarantine"],
            "compauth": ["fail"],
        }
    ]
    assert report["filtering"] == [{"scl": ["9"], "sfv": ["spm"], "cat": ["hphsh"]}]
    assert report["delivery"] == "unknown_requires_recipient_evidence"


@pytest.mark.parametrize(
    "outcome",
    [
        "pass",
        "fail",
        "none",
        "softfail",
        "temperror",
        "permerror",
        "neutral",
        "softpass",
        "bestguesspass",
    ],
)
def test_auth_distinctions(outcome: str) -> None:
    report = diagnose(BytesIO(f"Authentication-Results: mx; spf={outcome}\n\n".encode()))
    assert report["authentication"] == [{"spf": [outcome]}]


def test_conflicts_and_unknown_results() -> None:
    report = diagnose(
        BytesIO(
            b"Authentication-Results: mx; dkim=pass; dkim=fail; spf=unexpected\n"
            b"Authentication-Results: mx2; dmarc=pass; compauth=softpass\n"
            b"X-MS-Exchange-Organization-SCL: 912873\n"
            b"X-Forefront-Antispam-Report: SFV:SKQ;CAT:private-secret;\n\n"
        )
    )
    assert report["authentication"] == [
        {"dkim": ["pass", "fail"], "spf": ["unknown"]},
        {"dmarc": ["pass"], "compauth": ["softpass"]},
    ]
    assert report["filtering"] == [{"scl": ["unknown"]}, {"sfv": ["skq"], "cat": ["unknown"]}]


@pytest.mark.parametrize(
    "claim",
    [
        'mx; spf=fail reason="; dmarc=pass"',
        "mx; spf=fail (note; dmarc=pass)",
        "mx; spf=pass (nested (private))",
    ],
)
def test_complex_syntax_never_becomes_false_pass(claim: str) -> None:
    report = diagnose(BytesIO(f"Authentication-Results: {claim}\n\n".encode()))
    assert report["authentication"] == [{}]


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"From: private",
        b"bad\n\n",
        b" folded\n\n",
        b"Bad Name: private\n\n",
        b"From: bad\x00private\n\n",
        b"From: bad\rprivate\n\n",
        b"From: \xff\n\n",
        b"X: " + b"a" * MAX_LINE_BYTES + b"\n\n",
        (b"X: " + b"a" * 100 + b"\n") * (MAX_HEADER_BYTES // 100) + b"\n",
    ],
)
def test_rejects_malformed_and_bounded(raw: bytes) -> None:
    stream = BytesIO(raw)
    with pytest.raises(InvalidHeadersError, match=r"^invalid_or_oversized_headers$"):
        diagnose(stream)
    assert stream.tell() <= MAX_HEADER_BYTES + 1


def test_missing_and_untrusted_headers() -> None:
    report = diagnose(BytesIO(b"ARC-Authentication-Results: mx; dmarc=pass\nX: opaque\n\n"))
    assert report["authentication"] == []
    assert report["filtering"] == []
    assert report["evidence"] == "untrusted_header_claims_only"


def test_empty_headers_stop_at_separator() -> None:
    stream = BytesIO(b"\nnever read")
    diagnose(stream)
    assert stream.tell() == 1


@pytest.mark.parametrize(("raw", "exit_code"), [(b"X: private\n\nBODY", 0), (b"invalid\n\n", 2)])
def test_cli_safe_output_and_no_body_read(
    raw: bytes,
    exit_code: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "synthetic.headers"
    source.write_bytes(raw)
    with source.open("rb", buffering=0) as stream:
        monkeypatch.setattr(sys, "stdin", stream)
        assert main() == exit_code
        if exit_code == 0:
            assert stream.read() == b"BODY"
    captured = capsys.readouterr()
    assert "private" not in captured.out + captured.err
    if exit_code == 0:
        assert json.loads(captured.out)["delivery"] == "unknown_requires_recipient_evidence"
        assert captured.err == ""
    else:
        assert captured.out == ""
        assert captured.err == "invalid_or_unreadable_headers\n"


def test_cli_invalid_descriptor_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "synthetic.headers"
    source.write_bytes(b"\n")
    stream = source.open("rb", buffering=0)
    stream.close()
    monkeypatch.setattr(sys, "stdin", stream)
    invalid_input_exit = 2
    assert main() == invalid_input_exit
    assert capsys.readouterr().err == "invalid_or_unreadable_headers\n"


def test_exact_total_bound_and_line_bound() -> None:
    # Build headers exactly at the size ceiling, including the final separator.
    line = b"X:" + b"a" * (MAX_LINE_BYTES - 3) + b"\n"
    raw = line * (MAX_HEADER_BYTES // MAX_LINE_BYTES - 1)
    raw += b"X:" + b"a" * (MAX_LINE_BYTES - 4) + b"\n\n"
    assert len(raw) == MAX_HEADER_BYTES
    diagnose(BytesIO(raw))
    with pytest.raises(InvalidHeadersError, match=r"^invalid_or_oversized_headers$"):
        diagnose(BytesIO(raw[:-1] + b" \n"))
