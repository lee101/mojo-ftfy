"""Unicode text repair with Mojo-accelerated mojibake transcoding."""

from __future__ import annotations

import unicodedata
import warnings
from collections.abc import Iterator
from typing import Any, BinaryIO, Callable, Literal, NamedTuple, TextIO

from . import fixes
from ._lib import repair as _mojo_repair
from .badness import badness, is_bad

__version__ = "0.1.0"


class ExplanationStep(NamedTuple):
    action: str
    parameter: str

    def __repr__(self) -> str:
        return repr(tuple(self))


class ExplainedText(NamedTuple):
    text: str
    explanation: list[ExplanationStep] | None


class TextFixerConfig(NamedTuple):
    unescape_html: str | bool = "auto"
    remove_terminal_escapes: bool = True
    fix_encoding: bool = True
    restore_byte_a0: bool = True
    replace_lossy_sequences: bool = True
    decode_inconsistent_utf8: bool = True
    fix_c1_controls: bool = True
    fix_latin_ligatures: bool = True
    fix_character_width: bool = True
    uncurl_quotes: bool = True
    fix_line_breaks: bool = True
    fix_surrogates: bool = True
    remove_control_chars: bool = True
    normalization: Literal["NFC", "NFD", "NFKC", "NFKD"] | None = "NFC"
    max_decode_length: int = 1_000_000
    explain: bool = True


FIXERS: dict[str, Callable[..., Any]] = {
    name: getattr(fixes, name)
    for name in (
        "unescape_html",
        "remove_terminal_escapes",
        "restore_byte_a0",
        "replace_lossy_sequences",
        "decode_inconsistent_utf8",
        "fix_c1_controls",
        "fix_latin_ligatures",
        "fix_character_width",
        "uncurl_quotes",
        "fix_line_breaks",
        "fix_surrogates",
        "remove_control_chars",
    )
}

_CP1252_DECODE = {
    0x80: "\u20ac", 0x82: "\u201a", 0x83: "\u0192", 0x84: "\u201e",
    0x85: "\u2026", 0x86: "\u2020", 0x87: "\u2021", 0x88: "\u02c6",
    0x89: "\u2030", 0x8A: "\u0160", 0x8B: "\u2039", 0x8C: "\u0152",
    0x8E: "\u017d", 0x91: "\u2018", 0x92: "\u2019", 0x93: "\u201c",
    0x94: "\u201d", 0x95: "\u2022", 0x96: "\u2013", 0x97: "\u2014",
    0x98: "\u02dc", 0x99: "\u2122", 0x9A: "\u0161", 0x9B: "\u203a",
    0x9C: "\u0153", 0x9E: "\u017e", 0x9F: "\u0178",
}
_CP1252_ENCODE = {char: byte for byte, char in _CP1252_DECODE.items()}


def _decode_sloppy_windows_1252(data: bytes) -> str:
    return "".join(_CP1252_DECODE.get(byte, chr(byte)) for byte in data)


def _encode_sloppy_windows_1252(text: str) -> bytes:
    result = bytearray()
    for char in text:
        codepoint = ord(char)
        if char in _CP1252_ENCODE:
            result.append(_CP1252_ENCODE[char])
        elif codepoint <= 0xFF:
            result.append(codepoint)
        elif char == "\ufffd":
            result.append(0x1A)
        else:
            raise UnicodeEncodeError("sloppy-windows-1252", text, 0, 1, "character not encodable")
    return bytes(result)


def _config_from_kwargs(config: TextFixerConfig, kwargs: dict[str, Any]) -> TextFixerConfig:
    if "fix_entities" in kwargs:
        warnings.warn(
            "`fix_entities` has been renamed to `unescape_html`",
            DeprecationWarning,
            stacklevel=2,
        )
        kwargs = kwargs.copy()
        kwargs["unescape_html"] = kwargs.pop("fix_entities")
    return config._replace(**kwargs)


def _try_fix(
    name: str,
    text: str,
    config: TextFixerConfig,
    steps: list[ExplanationStep] | None,
) -> str:
    if not getattr(config, name):
        return text
    fixed = FIXERS[name](text)
    if steps is not None and fixed != text:
        steps.append(ExplanationStep("apply", name))
    return fixed


def _restore_candidate(text: str, encoding: str, config: TextFixerConfig) -> str | None:
    try:
        data = (
            text.encode("latin-1")
            if encoding == "latin-1"
            else _encode_sloppy_windows_1252(text)
        )
    except UnicodeEncodeError:
        return None
    restored = fixes.restore_byte_a0(data) if config.restore_byte_a0 else data
    if config.replace_lossy_sequences and encoding.startswith("sloppy"):
        restored = fixes.replace_lossy_sequences(restored)
    try:
        return restored.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _fix_encoding_one_step(
    text: str, config: TextFixerConfig
) -> tuple[str, list[ExplanationStep]]:
    score = badness(text)
    if not text or score == 0:
        return text, []

    for encoding, mode in (("latin-1", 0), ("sloppy-windows-1252", 1)):
        fixed = _mojo_repair(text, mode)
        transcoded = False
        if fixed is None and config.restore_byte_a0:
            fixed = _restore_candidate(text, encoding, config)
            transcoded = fixed is not None
        if fixed is not None and fixed != text and badness(fixed) < score:
            plan = [ExplanationStep("encode", encoding)]
            if transcoded:
                plan.append(ExplanationStep("transcode", "restore_byte_a0"))
            plan.append(ExplanationStep("decode", "utf-8"))
            return fixed, plan

    if config.decode_inconsistent_utf8:
        fixed = fixes.decode_inconsistent_utf8(text)
        if fixed != text and badness(fixed) < score:
            return fixed, [ExplanationStep("apply", "decode_inconsistent_utf8")]

    if config.fix_c1_controls and any("\x80" <= char <= "\x9f" for char in text):
        return fixes.fix_c1_controls(text), [
            ExplanationStep("transcode", "fix_c1_controls")
        ]
    return text, []


def fix_encoding_and_explain(
    text: str, config: TextFixerConfig | None = None, **kwargs: Any
) -> ExplainedText:
    if config is None:
        config = TextFixerConfig()
    if isinstance(text, bytes):
        raise UnicodeError("ftfy expects Unicode text, not bytes")
    config = _config_from_kwargs(config, kwargs)
    if not config.fix_encoding:
        return ExplainedText(text, [])
    plan: list[ExplanationStep] = []
    while True:
        fixed, steps = _fix_encoding_one_step(text, config)
        if fixed == text:
            return ExplainedText(text, plan)
        text = fixed
        plan.extend(steps)


def fix_encoding(
    text: str, config: TextFixerConfig | None = None, **kwargs: Any
) -> str:
    if config is None:
        config = TextFixerConfig(explain=False)
    config = _config_from_kwargs(config, kwargs)
    return fix_encoding_and_explain(text, config).text


def fix_and_explain(
    text: str, config: TextFixerConfig | None = None, **kwargs: Any
) -> ExplainedText:
    if config is None:
        config = TextFixerConfig()
    if isinstance(text, bytes):
        raise UnicodeError("ftfy expects Unicode text, not bytes")
    config = _config_from_kwargs(config, kwargs)
    if config.unescape_html == "auto" and "<" in text:
        config = config._replace(unescape_html=False)
    steps: list[ExplanationStep] | None = [] if config.explain else None

    while True:
        original = text
        text = _try_fix("unescape_html", text, config, steps)
        if config.fix_encoding:
            encoded = fix_encoding_and_explain(text, config)
            text = encoded.text
            if steps is not None and encoded.explanation:
                steps.extend(encoded.explanation)
        for name in (
            "fix_c1_controls",
            "fix_latin_ligatures",
            "fix_character_width",
            "uncurl_quotes",
            "fix_line_breaks",
            "fix_surrogates",
            "remove_terminal_escapes",
            "remove_control_chars",
        ):
            text = _try_fix(name, text, config, steps)
        if config.normalization is not None:
            fixed = unicodedata.normalize(config.normalization, text)
            if steps is not None and fixed != text:
                steps.append(ExplanationStep("normalize", config.normalization))
            text = fixed
        if text == original:
            return ExplainedText(text, steps)


def fix_text_segment(
    text: str, config: TextFixerConfig | None = None, **kwargs: Any
) -> str:
    if config is None:
        config = TextFixerConfig(explain=False)
    config = _config_from_kwargs(config, kwargs)
    return fix_and_explain(text, config).text


def fix_text(
    text: str, config: TextFixerConfig | None = None, **kwargs: Any
) -> str:
    if config is None:
        config = TextFixerConfig(explain=False)
    config = _config_from_kwargs(config, kwargs)
    if isinstance(text, bytes):
        raise UnicodeError("ftfy expects Unicode text, not bytes")
    pieces: list[str] = []
    position = 0
    while position < len(text):
        textbreak = text.find("\n", position) + 1
        if textbreak == 0:
            textbreak = len(text)
        if textbreak - position > config.max_decode_length:
            textbreak = position + config.max_decode_length
        segment = text[position:textbreak]
        if config.unescape_html == "auto" and "<" in segment:
            config = config._replace(unescape_html=False)
        pieces.append(fix_and_explain(segment, config).text)
        position = textbreak
    return "".join(pieces)


ftfy = fix_text


def fix_file(
    input_file: TextIO | BinaryIO,
    encoding: str | None = None,
    config: TextFixerConfig | None = None,
    **kwargs: Any,
) -> Iterator[str]:
    if config is None:
        config = TextFixerConfig()
    config = _config_from_kwargs(config, kwargs)
    for line in input_file:
        if isinstance(line, bytes):
            if encoding is None:
                line, encoding = guess_bytes(line)
            else:
                line = line.decode(encoding)
        yield fix_text_segment(line, config)


def guess_bytes(bstring: bytes) -> tuple[str, str]:
    if isinstance(bstring, str):
        raise UnicodeError("guess_bytes expects bytes, not Unicode text")
    if bstring.startswith((b"\xfe\xff", b"\xff\xfe")):
        return bstring.decode("utf-16"), "utf-16"
    try:
        return bstring.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    if b"\r" in bstring and b"\n" not in bstring:
        return bstring.decode("macroman"), "macroman"
    return _decode_sloppy_windows_1252(bstring), "sloppy-windows-1252"


def apply_plan(text: str, plan: list[tuple[str, str]]) -> str:
    obj: str | bytes = text
    for operation, parameter in plan:
        if operation == "encode":
            if parameter == "sloppy-windows-1252":
                obj = _encode_sloppy_windows_1252(obj)  # type: ignore[arg-type]
            else:
                obj = obj.encode(parameter)  # type: ignore[union-attr]
        elif operation == "decode":
            obj = obj.decode(parameter)  # type: ignore[union-attr]
        elif operation in ("transcode", "apply"):
            obj = FIXERS[parameter](obj)
        elif operation == "normalize":
            obj = unicodedata.normalize(parameter, obj)  # type: ignore[arg-type]
        else:
            raise ValueError(f"Unknown plan step: {operation!r}")
    return obj  # type: ignore[return-value]


def explain_unicode(text: str) -> None:
    for char in text:
        display = char if char.isprintable() else char.encode("unicode-escape").decode("ascii")
        width = (
            sum(
                0
                if unicodedata.combining(item)
                else 2
                if unicodedata.east_asian_width(item) in ("W", "F")
                else 1
                for item in display
            )
        )
        padded = display + " " * max(0, 7 - width)
        print(
            f"U+{ord(char):04X}  {padded} "
            f"[{unicodedata.category(char)}] {unicodedata.name(char, '<unknown>')}"
        )


__all__ = [
    "ExplanationStep", "ExplainedText", "FIXERS", "TextFixerConfig",
    "apply_plan", "badness", "explain_unicode", "fix_and_explain",
    "fix_encoding", "fix_encoding_and_explain", "fix_file", "fix_text",
    "fix_text_segment", "fixes", "ftfy", "guess_bytes", "is_bad",
]
