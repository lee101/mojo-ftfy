"""Benchmark mojo-ftfy against upstream ftfy on identical text."""

from __future__ import annotations

import math
import os
import platform
import sys
import time

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"
    ),
)

import ftfy as upstream  # noqa: E402
import mojo_ftfy as ours  # noqa: E402


def timeit(function, repeat: int = 5) -> float:
    best = math.inf
    for _ in range(repeat):
        start = time.perf_counter()
        function()
        best = min(best, time.perf_counter() - start)
    return best


def machine() -> str:
    model = "unknown CPU"
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as cpuinfo:
            for line in cpuinfo:
                if line.startswith("model name"):
                    model = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    return f"{model}; {platform.system()} {platform.machine()}; Python {platform.python_version()}"


def main() -> None:
    cases = [
        ("Latin-1 mojibake, 1.2M chars", "cafÃ© " * 200_000),
        (
            "Windows-1252 mojibake, 1.4M chars",
            "Mona Lisa doesnâ€™t smile. " * 50_000,
        ),
        ("double mojibake, 1.0M chars", "schÃƒÂ¶n " * 100_000),
        ("clean ASCII, 1.2M chars", "plain text and numbers 123 " * 50_000),
    ]
    print(f"Machine: {machine()}")
    print()
    print("| case | mojo-ftfy | ftfy 6.3.1 | speedup |")
    print("|---|---:|---:|---:|")
    for name, text in cases:
        expected = upstream.fix_encoding(text)
        assert ours.fix_encoding(text) == expected
        ours.fix_encoding(text)
        mojo_time = timeit(lambda: ours.fix_encoding(text))
        upstream_time = timeit(lambda: upstream.fix_encoding(text))
        ratio = upstream_time / mojo_time
        mojo_display = (
            f"{mojo_time * 1e3:.3f} ms"
            if mojo_time < 1e-3
            else f"{mojo_time * 1e3:.2f} ms"
        )
        print(
            f"| {name} | {mojo_display} | "
            f"{upstream_time * 1e3:.2f} ms | {ratio:.2f}x |"
        )


if __name__ == "__main__":
    main()
