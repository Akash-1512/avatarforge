"""Multi-language voice resolution and SSML locale correctness."""

import pytest

from backend.services.tts.ssml import build_ssml
from backend.services.tts.voices import resolve_voice, supported_languages


def test_resolve_hindi_professional_female():
    v = resolve_voice("professional_female", "hi")
    assert v.azure_voice == "hi-IN-SwaraNeural"
    assert v.locale == "hi-IN"


def test_resolve_marathi_and_tamil():
    assert resolve_voice("professional_male", "mr").azure_voice == "mr-IN-ManoharNeural"
    assert resolve_voice("professional_female", "ta").locale == "ta-IN"


def test_unknown_language_falls_back_to_english():
    v = resolve_voice("professional_female", "xx")
    assert v.locale == "en-IN"  # the role's English baseline


def test_unknown_role_falls_back_to_default_role():
    v = resolve_voice("nonexistent_role", "en")
    assert v.azure_voice == "en-IN-NeerjaNeural"


def test_ssml_carries_locale():
    v = resolve_voice("professional_female", "hi")
    ssml = build_ssml("नमस्ते", v.azure_voice, 1.0, locale=v.locale)
    assert 'xml:lang="hi-IN"' in ssml
    assert "hi-IN-SwaraNeural" in ssml


def test_ssml_escapes_injection_in_any_language():
    ssml = build_ssml("<script>alert(1)</script>", "hi-IN-SwaraNeural", 1.0, locale="hi-IN")
    assert "<script>" not in ssml
    assert "&lt;script&gt;" in ssml


def test_supported_languages_includes_india_locales():
    langs = supported_languages("professional_female")
    assert {"en", "hi", "mr", "ta"}.issubset(set(langs))


@pytest.mark.parametrize("lang", ["en", "hi", "mr", "ta", "es", "fr", "de"])
def test_every_advertised_language_resolves(lang):
    v = resolve_voice("professional_female", lang)
    assert v.azure_voice and v.locale
