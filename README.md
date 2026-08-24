# mojo-ftfy

`mojo-ftfy` is a standalone Unicode text-repair library with the common
mojibake transcode and UTF-8 validation loops implemented in Mojo. Its Python
package is named `mojo_ftfy` so that it can be installed beside the upstream
[`ftfy`](https://github.com/rspeer/python-ftfy) package for parity testing.

The project targets ftfy 6.3.1 behavior for the covered API. It does not import
ftfy at runtime.

## Coverage

The covered top-level API is:

- `fix_text`, `fix_text_segment`, `fix_and_explain`
- `fix_encoding`, `fix_encoding_and_explain`
- `TextFixerConfig`, `ExplanationStep`, and `ExplainedText`
- `apply_plan`, `fix_file`, `guess_bytes`, `explain_unicode`, and the `ftfy`
  alias

The `mojo_ftfy.fixes` module covers HTML entity decoding, terminal escape
removal, quote uncurving, Latin ligatures, character width, line breaks,
surrogates, control characters, BOM removal, escape decoding, C1 repair,
lossy-sequence repair, altered non-breaking spaces, and inconsistent embedded
UTF-8. Unicode normalization supports NFC, NFD, NFKC, and NFKD.

The compiled repair paths cover UTF-8 that was incorrectly decoded as Latin-1
or Windows-1252, including repeated corruption such as `schÃƒÂ¶n`. These are
the dominant mojibake paths on Western-language data. Unlike upstream ftfy,
this release does not attempt whole-string recovery through Windows-1250,
Windows-1251, Windows-1253, Windows-1254, Windows-1257, ISO-8859-2, MacRoman,
or CP437. Its mojibake suspicion score is deliberately smaller and more
conservative than ftfy's generated heuristic.

## Install

```bash
pixi install
pixi run build
```

The build produces `dist/libmojo-ftfy.so`. Run the verified example with:

```bash
pixi run python -c 'from mojo_ftfy import fix_text; print(fix_text("Mona Lisa doesnâ€™t smile"))'
```

Output:

```text
Mona Lisa doesn't smile
```

## Tests

```bash
pixi run build
pixi run test
```

The suite compares behavior and explanation plans directly with the installed
ftfy 6.3.1 package, and separately tests invalid UTF-8 edge cases against
published UTF-8 validity rules.

## Benchmarks

Measured with `pixi run bench` on an Intel Xeon E5-2697 v4 at 2.30 GHz,
Linux x86_64, Python 3.13.14. Times are the best of five runs on identical
input; speedup is ftfy time divided by mojo-ftfy time.

| case | mojo-ftfy | ftfy 6.3.1 | speedup |
|---|---:|---:|---:|
| Latin-1 mojibake, 1.2M chars | 26.37 ms | 448.04 ms | 16.99x |
| Windows-1252 mojibake, 1.4M chars | 26.75 ms | 608.52 ms | 22.75x |
| double mojibake, 1.0M chars | 32.07 ms | 363.53 ms | 11.34x |
| clean ASCII, 1.2M chars | 0.004 ms | 2.26 ms | 554.89x |

ASCII input is rejected from the repair path using Python's cached string-kind
metadata, so it does not allocate a UTF-8 buffer or cross the FFI boundary.
Inside Mojo, UTF-8 validation and badness scoring skip ASCII runs with SIMD and
use a scalar tail for the remainder.

There is no parallel or GPU path. The repair kernels are variable-width,
branch-heavy streaming scans with low arithmetic intensity (below roughly two
operations per byte moved); splitting them would require boundary scans and
output coordination, while device transfer and launch overhead would dominate.

## How it works

Python encodes each non-ASCII candidate segment into a contiguous UTF-8 `bytes`
buffer. ctypes borrows that buffer without copying it and passes the source
address, byte count, destination address, destination capacity, and encoding
mode across the C ABI. The exported functions reject invalid lengths, modes,
capacities, and null pointers before constructing Mojo pointers.
The Mojo shared library reconstructs
`UnsafePointer[UInt8, AnyOrigin[mut=True]]` values, decodes the source UTF-8 one
codepoint at a time, maps each codepoint back to its proposed single-byte
value, and validates the resulting bytes as strict UTF-8 before accepting the
repair. The destination is a preallocated Python `bytearray` exposed directly
to ctypes, so the ABI does not allocate or transfer ownership.

Unicode database operations remain in Python's `unicodedata`; this preserves
complete normalization and character-width behavior without duplicating the
Unicode Character Database in the shared library.

## License

The project is MIT licensed. Portions of the Unicode fixer tables and behavior
are derived from ftfy, Copyright 2023 Robyn Speer, under Apache-2.0; see
`THIRD_PARTY_NOTICES.md`.
