"""SSML construction for Azure Speech.

All user text is XML-escaped before templating — never interpolate raw
input into SSML, or a user can inject arbitrary speech-engine directives.
"""

from xml.sax.saxutils import escape


def build_ssml(text: str, azure_voice: str, speaking_rate: float = 1.0) -> str:
    rate_pct = f"{int(round((speaking_rate - 1.0) * 100)):+d}%"
    safe_text = escape(text)
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
        f'<voice name="{azure_voice}">'
        f'<prosody rate="{rate_pct}">{safe_text}</prosody>'
        "</voice></speak>"
    )
