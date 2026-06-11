"""SSML builder — escaping is a security control, test it hard."""

from backend.services.tts.ssml import build_ssml


def test_basic_ssml_structure():
    ssml = build_ssml("Hello world", "en-IN-NeerjaNeural", 1.0)
    assert '<voice name="en-IN-NeerjaNeural">' in ssml
    assert 'rate="+0%"' in ssml
    assert "Hello world" in ssml


def test_speaking_rate_mapping():
    assert 'rate="+25%"' in build_ssml("x", "v", 1.25)
    assert 'rate="-50%"' in build_ssml("x", "v", 0.5)


def test_xml_injection_is_escaped():
    """User text must never break out of the prosody element."""
    malicious = 'Hello</prosody></voice><voice name="evil">pwned'
    ssml = build_ssml(malicious, "en-US-JennyNeural", 1.0)
    assert '<voice name="evil">' not in ssml
    assert "&lt;/prosody&gt;" in ssml
    assert ssml.count("<voice") == 1


def test_ampersand_escaped():
    ssml = build_ssml("Tom & Jerry", "v", 1.0)
    assert "Tom &amp; Jerry" in ssml
