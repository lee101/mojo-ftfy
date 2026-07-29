"""Load the Mojo text-repair library."""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src")
LIB = os.environ.get("MOJO_FTFY_LIB") or os.path.join(
    ROOT, "dist", "libmojo-ftfy.so"
)

I = ctypes.c_int64
_SIGNATURES = {
    "mftfy_repair": ([I, I, I, I, I], I),
    "mftfy_valid_utf8": ([I, I], I),
    "mftfy_badness": ([I, I], I),
}


class BuildError(RuntimeError):
    pass


def mojo_command() -> list[str]:
    override = os.environ.get("MOJO_FTFY_MOJO")
    if override:
        return override.split()
    found = shutil.which("mojo")
    if found:
        return [found]
    pixi = shutil.which("pixi") or os.path.expanduser("~/.pixi/bin/pixi")
    if os.path.exists(pixi):
        return [
            pixi,
            "run",
            "--manifest-path",
            os.path.join(ROOT, "pixi.toml"),
            "mojo",
        ]
    raise BuildError("mojo not found; set MOJO_FTFY_MOJO=/path/to/mojo")


def build(force: bool = False) -> str:
    if os.environ.get("MOJO_FTFY_LIB") and os.path.exists(LIB) and not force:
        return LIB
    source = os.path.join(SRC, "ftfy.mojo")
    if not force and os.path.exists(LIB):
        if os.path.getmtime(LIB) >= os.path.getmtime(source):
            return LIB
    os.makedirs(os.path.dirname(LIB), exist_ok=True)
    cmd = mojo_command() + ["build", "--emit", "shared-lib", source, "-o", LIB]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0 or not os.path.exists(LIB):
        raise BuildError((proc.stderr or proc.stdout).strip()[:4000])
    return LIB


_library: ctypes.CDLL | None = None


def lib() -> ctypes.CDLL:
    global _library
    if _library is None:
        _library = ctypes.CDLL(build())
        for name, (argtypes, restype) in _SIGNATURES.items():
            fn = getattr(_library, name)
            fn.argtypes = argtypes
            fn.restype = restype
    return _library


def repair(text: str, encoding: int) -> str | None:
    if encoding not in (0, 1):
        raise ValueError("encoding mode must be 0 (Latin-1) or 1 (Windows-1252)")
    source = text.encode("utf-8")
    if not source:
        return text
    source_address = ctypes.cast(ctypes.c_char_p(source), ctypes.c_void_p).value
    destination = bytearray(len(source))
    destination_view = (ctypes.c_uint8 * len(destination)).from_buffer(destination)
    count = lib().mftfy_repair(
        source_address,
        len(source),
        ctypes.addressof(destination_view),
        len(destination),
        encoding,
    )
    if count == -1:
        return None
    if count < 0 or count > len(destination):
        raise RuntimeError(f"Mojo repair kernel failed with status {count}")
    return destination[:count].decode("utf-8")


def valid_utf8(data: bytes) -> bool:
    if not data:
        return True
    source_address = ctypes.cast(ctypes.c_char_p(data), ctypes.c_void_p).value
    return bool(lib().mftfy_valid_utf8(source_address, len(data)))


def badness(text: str) -> int:
    if text.isascii():
        return 0
    try:
        source_bytes = text.encode("utf-8")
    except UnicodeEncodeError:
        return 0
    if not source_bytes:
        return 0
    source_address = ctypes.cast(
        ctypes.c_char_p(source_bytes), ctypes.c_void_p
    ).value
    return int(lib().mftfy_badness(source_address, len(source_bytes)))


def main() -> int:
    print(build(force="--force" in sys.argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
