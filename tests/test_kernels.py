from __future__ import annotations

import ctypes

import pytest

from mojo_ftfy import _lib


@pytest.mark.parametrize(
    "data,valid",
    [
        (b"", True),
        (b"ASCII", True),
        ("é".encode(), True),
        ("\U0001f600".encode(), True),
        (b"\x80", False),
        (b"\xc0\x80", False),
        (b"\xe0\x80\x80", False),
        (b"\xed\xa0\x80", False),
        (b"\xf4\x90\x80\x80", False),
        (b"\xf0\x9f\x98", False),
    ],
)
def test_utf8_validator(data, valid):
    assert _lib.valid_utf8(data) is valid


def test_raw_latin1_repair():
    assert _lib.repair("cafÃ©", 0) == "café"
    assert _lib.repair("café", 0) is None


def test_raw_windows_1252_repair():
    assert _lib.repair("âœ”", 1) == "\u2714"
    assert _lib.repair("ðŸ˜€", 1) == "\U0001f600"


def test_repair_rejects_unknown_encoding():
    with pytest.raises(ValueError):
        _lib.repair("cafÃ©", 2)


def test_ffi_rejects_invalid_pointers_lengths_and_capacity():
    library = _lib.lib()
    assert library.mftfy_valid_utf8(0, 0) == 1
    assert library.mftfy_valid_utf8(0, 1) == 0
    assert library.mftfy_valid_utf8(0, -1) == 0
    assert library.mftfy_badness(0, 0) == 0
    assert library.mftfy_badness(0, 1) == -1
    assert library.mftfy_repair(0, 0, 0, 0, 0) == 0
    assert library.mftfy_repair(0, 1, 0, 0, 0) == -3

    source = "cafÃ©".encode()
    source_view = (ctypes.c_uint8 * len(source)).from_buffer_copy(source)
    destination = (ctypes.c_uint8 * len(source))()
    assert library.mftfy_repair(
        ctypes.addressof(source_view),
        len(source),
        ctypes.addressof(destination),
        1,
        0,
    ) == -3


@pytest.mark.parametrize("length", [1, 3, 4, 5, 7, 8, 9, 15, 16, 17, 31, 32, 33])
def test_utf8_validator_simd_tail_boundaries(length):
    prefix = b"a" * length
    assert _lib.valid_utf8(prefix)
    assert _lib.valid_utf8(prefix + b"\xc3\xa9" + prefix)
    assert not _lib.valid_utf8(prefix + b"\x00\x80")
    assert _lib.badness("a" * length + "Ã") == 1


def test_utf8_validator_does_not_stop_at_nul():
    assert _lib.valid_utf8(b"before\x00after")
    assert not _lib.valid_utf8(b"before\x00\x80")


def test_ascii_badness_skips_ffi(monkeypatch):
    def fail_if_called():
        raise AssertionError("ASCII should not cross the FFI boundary")

    monkeypatch.setattr(_lib, "lib", fail_if_called)
    assert _lib.badness("plain ASCII 123") == 0
