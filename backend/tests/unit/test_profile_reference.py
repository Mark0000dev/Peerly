import pytest

from studymate.application.profiles.reference_data import ReadProfileReferenceData
from studymate.domain.language_data import LANGUAGE_CHOICES, SUPPORTED_LANGUAGES
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL
from tests.unit.test_profile_use_cases import Store


async def test_profile_reference_is_authoritative_complete_and_optional() -> None:
    result = await ReadProfileReferenceData(Store(), Sha256SessionHasher())(CREDENTIAL)
    assert {item.code for item in result.languages} == SUPPORTED_LANGUAGES
    assert dict(LANGUAGE_CHOICES)["en"] == "English"
    assert dict(LANGUAGE_CHOICES)["ms"] == "Malay"
    assert dict(LANGUAGE_CHOICES)["ta"] == "Tamil"
    assert result.max_languages > 0
    assert result.university == "APU Malaysia"


@pytest.mark.parametrize("code", ["zz", "not-a-language", "bh"])
def test_unsupported_reference_keys_are_not_fabricated(code: str) -> None:
    assert code not in SUPPORTED_LANGUAGES
