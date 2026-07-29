"""Behavioral parity checks against ftfy 6.x."""

from __future__ import annotations

import io
import inspect
import unicodedata

import pytest

upstream = pytest.importorskip("ftfy")

import mojo_ftfy as ours
from mojo_ftfy import fixes


MOJIBAKE_CASES = [
    "sÃ³",
    "âœ” No problems",
    "FranÃ§ois",
    "cafÃ©",
    "â€œquoteâ€\x9d",
    "ðŸ˜€",
    "Mona Lisa doesnâ€™t smile",
    "voilÃ le travail",
    "schÃƒÂ¶n",
    "already fine café",
    "Καλημέρα",
    "中文",
]


@pytest.mark.parametrize("text", MOJIBAKE_CASES)
def test_fix_encoding_parity(text):
    assert ours.fix_encoding(text) == upstream.fix_encoding(text)
    assert ours.fix_encoding_and_explain(text) == upstream.fix_encoding_and_explain(text)


FULL_FIX_CASES = [
    'Broken text&hellip; it&#x2019;s ﬂubberiﬁc!',
    "&macr;\\_(ã\x83\x84)_/&macr;",
    "P&EACUTE;REZ",
    "ＬＯＵＤ　ＮＯＩＳＥＳ",
    "ﬂuﬃeﬆ",
    "\u201chere\u2019s a test\u201d",
    "one\r\ntwo\rthree\u2028four\u2029five",
    "\033[36;44mblue\033[0m",
    "e\u0301",
]


@pytest.mark.parametrize("text", FULL_FIX_CASES)
def test_fix_text_and_explanation_parity(text):
    assert ours.fix_text(text) == upstream.fix_text(text)
    assert ours.fix_and_explain(text) == upstream.fix_and_explain(text)


@pytest.mark.parametrize(
    "name,text",
    [
        ("unescape_html", "&lt;tag&gt; P&EACUTE;REZ"),
        ("remove_terminal_escapes", "\033[31mred\033[0m"),
        ("uncurl_quotes", "\u201chello\u2019\u201d"),
        ("fix_latin_ligatures", "ﬂuﬃeﬆ"),
        ("fix_character_width", "Ｕﾀｰﾝ"),
        ("fix_line_breaks", "a\r\nb\rc\x85d\u2028e\u2029f"),
        ("remove_control_chars", "a\x00\x08\tb\x0b\x7fc\ufeff"),
        ("remove_bom", "\ufeff\ufeffhello"),
        ("decode_escapes", r"\u20a1 costs \x35"),
        ("fix_c1_controls", "price \x80"),
    ],
)
def test_individual_fixer_parity(name, text):
    assert getattr(fixes, name)(text) == getattr(upstream.fixes, name)(text)


@pytest.mark.parametrize(
    "name,data",
    [
        ("restore_byte_a0", b"\xc3 "),
        ("replace_lossy_sequences", b"\xc3?"),
    ],
)
def test_individual_bytes_fixer_parity(name, data):
    assert getattr(fixes, name)(data) == getattr(upstream.fixes, name)(data)


def test_decode_inconsistent_utf8_parity():
    text = "The café is called CafÃ© Paris."
    assert fixes.decode_inconsistent_utf8(text) == (
        upstream.fixes.decode_inconsistent_utf8(text)
    )


def test_surrogate_repair_parity():
    text = chr(0xD83D) + chr(0xDCA9) + chr(0xD800)
    assert fixes.fix_surrogates(text) == upstream.fixes.fix_surrogates(text)
    assert ours.fix_text(text) == upstream.fix_text(text)


@pytest.mark.parametrize("normalization", ["NFC", "NFD", "NFKC", "NFKD", None])
def test_normalization_config_parity(normalization):
    text = "e\u0301 ① µ"
    config = ours.TextFixerConfig(
        normalization=normalization,
        fix_character_width=False,
    )
    reference_config = upstream.TextFixerConfig(
        normalization=normalization,
        fix_character_width=False,
    )
    assert ours.fix_text(text, config) == upstream.fix_text(text, reference_config)


def test_config_flags_and_explain_false():
    text = "â€œﬂ\u201d"
    config = ours.TextFixerConfig(
        fix_encoding=False,
        uncurl_quotes=False,
        fix_latin_ligatures=False,
        explain=False,
    )
    result = ours.fix_and_explain(text, config)
    assert result == (text, None)


def test_html_auto_mode_parity():
    text = "<tag>&amp;</tag>\nP&eacute;rez"
    assert ours.fix_text(text) == upstream.fix_text(text)
    assert ours.fix_text(text, unescape_html=True) == upstream.fix_text(
        text, unescape_html=True
    )


def test_segmenting_parity():
    text = ("cafÃ© " * 30) + "\n" + ("FranÃ§ois " * 20)
    ours_config = ours.TextFixerConfig(max_decode_length=17)
    ref_config = upstream.TextFixerConfig(max_decode_length=17)
    assert ours.fix_text(text, ours_config) == upstream.fix_text(text, ref_config)


def test_apply_plan_replays_explanation():
    text = "Mona Lisa doesnâ€™t smile"
    fixed, plan = ours.fix_and_explain(text)
    assert plan is not None
    assert ours.apply_plan(text, plan) == fixed
    assert fixed == upstream.fix_text(text)


@pytest.mark.parametrize(
    "data",
    [
        "snowman \u2603".encode(),
        b"\xff\xfeh\x00i\x00",
        "caf\xe9\rnext".encode("latin-1"),
        b"\x93quoted\x94",
    ],
)
def test_guess_bytes_parity(data):
    assert ours.guess_bytes(data) == upstream.guess_bytes(data)


def test_fix_file_text_and_bytes_parity():
    text_lines = ["cafÃ©\n", "FranÃ§ois\n"]
    assert list(ours.fix_file(io.StringIO("".join(text_lines)))) == list(
        upstream.fix_file(io.StringIO("".join(text_lines)))
    )
    data = "cafÃ©\n".encode()
    assert list(ours.fix_file(io.BytesIO(data), encoding="utf-8")) == list(
        upstream.fix_file(io.BytesIO(data), encoding="utf-8")
    )


def test_public_signatures_match():
    for name in (
        "fix_text",
        "fix_text_segment",
        "fix_and_explain",
        "fix_encoding",
        "fix_encoding_and_explain",
        "apply_plan",
        "guess_bytes",
    ):
        assert str(inspect.signature(getattr(ours, name))) == str(
            inspect.signature(getattr(upstream, name))
        )


def test_alias_and_unicode_normalization():
    text = "cafÃ© e\u0301"
    assert ours.ftfy(text) == ours.fix_text(text)
    assert ours.fix_text(text).endswith(unicodedata.normalize("NFC", "é"))


def test_explain_unicode_parity(capsys):
    ours.explain_unicode("Aé")
    ours_output = capsys.readouterr().out
    upstream.explain_unicode("Aé")
    assert ours_output == capsys.readouterr().out


def test_bytes_are_rejected():
    with pytest.raises(UnicodeError):
        ours.fix_text(b"not Unicode")  # type: ignore[arg-type]
    with pytest.raises(UnicodeError):
        ours.guess_bytes("already Unicode")  # type: ignore[arg-type]
