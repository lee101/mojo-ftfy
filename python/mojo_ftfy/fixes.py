"""Individual Unicode repair functions exposed by ftfy.

Some tables and patterns are derived from ftfy 6.3.1 under Apache-2.0. See
THIRD_PARTY_NOTICES.md.
"""

from __future__ import annotations

import codecs
import html
import re
import unicodedata

_HTML_ENTITY_RE = re.compile(r"&#?[0-9A-Za-z]{1,24};")
_ANSI_RE = re.compile("\033\\[((?:\\d|;)*)([a-zA-Z])")
_SINGLE_QUOTE_RE = re.compile("[\u02bc\u2018-\u201b]")
_DOUBLE_QUOTE_RE = re.compile("[\u201c-\u201f]")
_ESCAPE_SEQUENCE_RE = re.compile(
    r"(\\U........|\\u....|\\x..|\\[0-7]{1,3}|\\N\{[^}]+\}|\\[\\'\"abfnrtv])"
)
_A_GRAVE_WORD_RE = re.compile(b"\xc3 (?! |quele|quela|quilo|s )")
_ALTERED_UTF8_RE = re.compile(
    b"[\xc2\xc3\xc5\xce\xd0\xd9][ ]"
    b"|[\xe2\xe3][ ][\x80-\x84\x86-\x9f\xa1-\xbf]"
    b"|[\xe0-\xe3][\x80-\x84\x86-\x9f\xa1-\xbf][ ]"
    b"|[\xf0][ ][\x80-\xbf][\x80-\xbf]"
    b"|[\xf0][\x80-\xbf][ ][\x80-\xbf]"
    b"|[\xf0][\x80-\xbf][\x80-\xbf][ ]"
)
_LOSSY_UTF8_RE = re.compile(
    b"[\xc2-\xdf][\x1a]|[\xc2-\xc3][?]|"
    b"\xed[\xa0-\xaf][\x1a?]\xed[\xb0-\xbf][\x1a?\x80-\xbf]|"
    b"\xed[\xa0-\xaf][\x1a?\x80-\xbf]\xed[\xb0-\xbf][\x1a?]|"
    b"[\xe0-\xef][\x1a?][\x1a\x80-\xbf]|"
    b"[\xe0-\xef][\x1a\x80-\xbf][\x1a?]|"
    b"[\xf0-\xf4][\x1a?][\x1a\x80-\xbf][\x1a\x80-\xbf]|"
    b"[\xf0-\xf4][\x1a\x80-\xbf][\x1a?][\x1a\x80-\xbf]|"
    b"[\xf0-\xf4][\x1a\x80-\xbf][\x1a\x80-\xbf][\x1a?]|\x1a"
)

_LIGATURES = {
    ord("Ĳ"): "IJ", ord("ĳ"): "ij", ord("ŉ"): "ʼn",
    ord("Ǳ"): "DZ", ord("ǲ"): "Dz", ord("ǳ"): "dz",
    ord("Ǆ"): "DŽ", ord("ǅ"): "Dž", ord("ǆ"): "dž",
    ord("Ǉ"): "LJ", ord("ǈ"): "Lj", ord("ǉ"): "lj",
    ord("Ǌ"): "NJ", ord("ǋ"): "Nj", ord("ǌ"): "nj",
    ord("ﬀ"): "ff", ord("ﬁ"): "fi", ord("ﬂ"): "fl",
    ord("ﬃ"): "ffi", ord("ﬄ"): "ffl", ord("ﬅ"): "ſt", ord("ﬆ"): "st",
}


def _build_html_entities() -> dict[str, str]:
    entities: dict[str, str] = {}
    for name, char in html.entities.html5.items():
        if name.endswith(";"):
            entities["&" + name] = char
            if name == name.lower():
                upper = "&" + name.upper()
                if html.unescape(upper) == upper:
                    entities[upper] = char.upper()
    return entities


_HTML_ENTITIES = _build_html_entities()


def unescape_html(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        entity = match.group(0)
        if entity in _HTML_ENTITIES:
            return _HTML_ENTITIES[entity]
        if entity.startswith("&#"):
            decoded = html.unescape(entity)
            return entity if ";" in decoded else decoded
        return entity

    return _HTML_ENTITY_RE.sub(replace, text)


def remove_terminal_escapes(text: str) -> str:
    return _ANSI_RE.sub("", text)


def uncurl_quotes(text: str) -> str:
    return _SINGLE_QUOTE_RE.sub("'", _DOUBLE_QUOTE_RE.sub('"', text))


def fix_latin_ligatures(text: str) -> str:
    return text.translate(_LIGATURES)


def fix_character_width(text: str) -> str:
    pieces = []
    for char in text:
        codepoint = ord(char)
        if codepoint == 0x3000 or 0xFF01 <= codepoint < 0xFFF0:
            pieces.append(unicodedata.normalize("NFKC", char))
        else:
            pieces.append(char)
    return "".join(pieces)


def fix_line_breaks(text: str) -> str:
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u2028", "\n")
        .replace("\u2029", "\n")
        .replace("\x85", "\n")
    )


def fix_surrogates(text: str) -> str:
    result: list[str] = []
    i = 0
    while i < len(text):
        codepoint = ord(text[i])
        if 0xD800 <= codepoint <= 0xDBFF and i + 1 < len(text):
            low = ord(text[i + 1])
            if 0xDC00 <= low <= 0xDFFF:
                result.append(chr(0x10000 + (codepoint - 0xD800) * 0x400 + low - 0xDC00))
                i += 2
                continue
        result.append("\ufffd" if 0xD800 <= codepoint <= 0xDFFF else text[i])
        i += 1
    return "".join(result)


def remove_control_chars(text: str) -> str:
    def keep(char: str) -> bool:
        codepoint = ord(char)
        return not (
            0 <= codepoint <= 8
            or codepoint == 0x0B
            or 0x0E <= codepoint <= 0x1F
            or codepoint == 0x7F
            or 0x206A <= codepoint <= 0x206F
            or codepoint == 0xFEFF
            or 0xFFF9 <= codepoint <= 0xFFFC
        )

    return "".join(char for char in text if keep(char))


def remove_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def decode_escapes(text: str) -> str:
    return _ESCAPE_SEQUENCE_RE.sub(
        lambda match: codecs.decode(match.group(0), "unicode-escape"), text
    )


def restore_byte_a0(byts: bytes) -> bytes:
    byts = _A_GRAVE_WORD_RE.sub(b"\xc3\xa0 ", byts)
    return _ALTERED_UTF8_RE.sub(
        lambda match: match.group(0).replace(b"\x20", b"\xa0"), byts
    )


def replace_lossy_sequences(byts: bytes) -> bytes:
    return _LOSSY_UTF8_RE.sub("\ufffd".encode(), byts)


def fix_c1_controls(text: str) -> str:
    from . import _decode_sloppy_windows_1252

    return re.sub(
        r"[\x80-\x9f]",
        lambda match: _decode_sloppy_windows_1252(
            match.group(0).encode("latin-1")
        ),
        text,
    )


def decode_inconsistent_utf8(text: str) -> str:
    from . import fix_encoding

    def replace(match: re.Match[str]) -> str:
        if match.start() == 0 and match.end() == len(text):
            return match.group(0)
        return fix_encoding(match.group(0))

    return re.sub(
        r"[\x80-\u024f\u2000-\u214f]+",
        replace,
        text,
    )
