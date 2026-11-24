from datetime import UTC, datetime
from uuid import uuid4

import httpx2 as httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from studymate.domain.student_notifications.capabilities import Platform
from studymate.domain.student_notifications.delivery import Delivery, Kind, Outcome
from studymate.infrastructure.student_notifications.providers import (
    ProviderKeyMaterial,
    PushProviders,
    WebPushConfiguration,
    b64,
    encrypted_webpush,
    selection_from_keys,
    status_outcome,
    unb64,
)


def test_rfc8291_section5_exact_encrypted_record() -> None:
    # Official public RFC example keys, NOT credentials/provider configuration.
    expected = unb64(
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
        "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
        "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
    )
    sender = ec.derive_private_key(
        int.from_bytes(unb64("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"), ec.SECP256R1()
    )
    public = unb64(
        "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
    )
    body = encrypted_webpush(
        b"When I grow up, I want to be a watermelon",
        public,
        unb64("BTBZMqHH6r4Tts7J_aSIgg"),
        sender=sender,
        salt=expected[:16],
    )
    assert body == expected


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (201, Outcome.ACCEPTED),
        (410, Outcome.REJECTED),
        (429, Outcome.RETRYABLE),
        (503, Outcome.UNKNOWN),
    ],
)
def test_provider_response_semantics_preserve_ambiguity(status: int, outcome: Outcome) -> None:
    assert status_outcome(status) == outcome


def test_provider_selection_default_is_unconfigured_and_partial_configuration_fails() -> None:
    assert selection_from_keys().web is None
    with pytest.raises(ValueError, match="Partial Web Push"):
        selection_from_keys(ProviderKeyMaterial(contact="mailto:synthetic@example.invalid"))


async def test_webpush_actual_boundary_encodes_only_metadata_and_rejects_unconfigured_hosts() -> (
    None
):
    received: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(201)

    private = ec.generate_private_key(ec.SECP256R1())
    from cryptography.hazmat.primitives import serialization

    public = b64(
        private.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    )
    delivery = Delivery(uuid4(), uuid4(), Kind.MESSAGE, datetime(2027, 1, 1, tzinfo=UTC))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = PushProviders(
            client,
            WebPushConfiguration(
                ec.generate_private_key(ec.SECP256R1()),
                "mailto:synthetic@example.invalid",
                ("push.example.invalid",),
            ),
        )
        assert (
            await provider.send(
                delivery,
                Platform.WEB,
                "https://push.example.invalid/opaque",
                public,
                b64(bytes(range(16))),
            )
            == Outcome.ACCEPTED
        )
        assert (
            await provider.send(
                delivery, Platform.WEB, "https://127.0.0.1/private", public, b64(bytes(range(16)))
            )
            == Outcome.REJECTED
        )
    assert len(received) == 1
    assert received[0].headers["Content-Encoding"] == "aes128gcm"
    assert b"New message" not in received[0].content
    assert b"PRIVATE_CHAT_BODY" not in received[0].content
