"""UTF-8 validation and common single-byte mojibake repair."""

from std.sys.info import simd_width_of as simdwidthof

comptime BPtr = UnsafePointer[UInt8, AnyOrigin[mut=True]]


def is_continuation(byte: Int) -> Bool:
    return byte >= 0x80 and byte <= 0xBF


def ascii_prefix(src: BPtr, n: Int) -> Int:
    comptime W = simdwidthof[DType.float64]()
    var i = 0
    while i + W <= n:
        var chunk = src.load[width=W](i).cast[DType.int64]()
        if (chunk & 0x80).reduce_add() != 0:
            break
        i += W
    while i < n and Int(src[i]) <= 0x7F:
        i += 1
    return i


def valid_utf8(src: BPtr, n: Int) -> Bool:
    var i = ascii_prefix(src, n)
    while i < n:
        var a = Int(src[i])
        if a <= 0x7F:
            i = ascii_prefix(src + i, n - i) + i
        elif a >= 0xC2 and a <= 0xDF:
            if i + 1 >= n or not is_continuation(Int(src[i + 1])):
                return False
            i += 2
        elif a >= 0xE0 and a <= 0xEF:
            if i + 2 >= n:
                return False
            var b = Int(src[i + 1])
            var c = Int(src[i + 2])
            if not is_continuation(c):
                return False
            if a == 0xE0:
                if b < 0xA0 or b > 0xBF:
                    return False
            elif a == 0xED:
                if b < 0x80 or b > 0x9F:
                    return False
            elif not is_continuation(b):
                return False
            i += 3
        elif a >= 0xF0 and a <= 0xF4:
            if i + 3 >= n:
                return False
            var b = Int(src[i + 1])
            if not is_continuation(Int(src[i + 2])) or not is_continuation(Int(src[i + 3])):
                return False
            if a == 0xF0:
                if b < 0x90 or b > 0xBF:
                    return False
            elif a == 0xF4:
                if b < 0x80 or b > 0x8F:
                    return False
            elif not is_continuation(b):
                return False
            i += 4
        else:
            return False
    return True


def cp1252_byte(codepoint: Int) -> Int:
    if codepoint <= 0x7F or (codepoint >= 0xA0 and codepoint <= 0xFF):
        return codepoint
    if codepoint >= 0x80 and codepoint <= 0x9F:
        return codepoint
    if codepoint == 0x20AC:
        return 0x80
    if codepoint == 0x201A:
        return 0x82
    if codepoint == 0x0192:
        return 0x83
    if codepoint == 0x201E:
        return 0x84
    if codepoint == 0x2026:
        return 0x85
    if codepoint == 0x2020:
        return 0x86
    if codepoint == 0x2021:
        return 0x87
    if codepoint == 0x02C6:
        return 0x88
    if codepoint == 0x2030:
        return 0x89
    if codepoint == 0x0160:
        return 0x8A
    if codepoint == 0x2039:
        return 0x8B
    if codepoint == 0x0152:
        return 0x8C
    if codepoint == 0x017D:
        return 0x8E
    if codepoint == 0x2018:
        return 0x91
    if codepoint == 0x2019:
        return 0x92
    if codepoint == 0x201C:
        return 0x93
    if codepoint == 0x201D:
        return 0x94
    if codepoint == 0x2022:
        return 0x95
    if codepoint == 0x2013:
        return 0x96
    if codepoint == 0x2014:
        return 0x97
    if codepoint == 0x02DC:
        return 0x98
    if codepoint == 0x2122:
        return 0x99
    if codepoint == 0x0161:
        return 0x9A
    if codepoint == 0x203A:
        return 0x9B
    if codepoint == 0x0153:
        return 0x9C
    if codepoint == 0x017E:
        return 0x9E
    if codepoint == 0x0178:
        return 0x9F
    return -1


def decode_codepoint(src: BPtr, i: Int, a: Int) -> Int:
    if a <= 0x7F:
        return a
    if a <= 0xDF:
        return ((a & 0x1F) << 6) | (Int(src[i + 1]) & 0x3F)
    if a <= 0xEF:
        return ((a & 0x0F) << 12) | ((Int(src[i + 1]) & 0x3F) << 6) | (Int(src[i + 2]) & 0x3F)
    return ((a & 0x07) << 18) | ((Int(src[i + 1]) & 0x3F) << 12) | ((Int(src[i + 2]) & 0x3F) << 6) | (Int(src[i + 3]) & 0x3F)


def repair(src: BPtr, n: Int, dst: BPtr, dst_capacity: Int, encoding: Int) -> Int:
    if not valid_utf8(src, n):
        return -2
    var i = 0
    var written = 0
    while i < n:
        var a = Int(src[i])
        var width = 1
        if a >= 0xF0:
            width = 4
        elif a >= 0xE0:
            width = 3
        elif a >= 0xC2:
            width = 2
        var codepoint = decode_codepoint(src, i, a)
        var byte = codepoint if encoding == 0 else cp1252_byte(codepoint)
        if encoding == 0 and codepoint > 0xFF:
            return -1
        if byte < 0 or byte > 0xFF:
            return -1
        if written >= dst_capacity:
            return -3
        dst[written] = UInt8(byte)
        written += 1
        i += width
    if not valid_utf8(dst, written):
        return -1
    return written


def mojibake_weight(codepoint: Int) -> Int:
    if codepoint == 0xFFFD or (codepoint >= 0x80 and codepoint <= 0x9F):
        return 2
    if (
        codepoint == 0x00C2
        or codepoint == 0x00C3
        or codepoint == 0x00D0
        or codepoint == 0x00D1
        or codepoint == 0x00D8
        or codepoint == 0x00D9
        or codepoint == 0x00E2
        or codepoint == 0x00E3
        or codepoint == 0x00F0
        or codepoint == 0x00CE
        or codepoint == 0x00CF
    ):
        return 1
    return 0


def mojibake_badness(src: BPtr, n: Int) -> Int:
    if not valid_utf8(src, n):
        return n + 1
    var score = 0
    var i = ascii_prefix(src, n)
    while i < n:
        var a = Int(src[i])
        var width = 1
        if a >= 0xF0:
            width = 4
        elif a >= 0xE0:
            width = 3
        elif a >= 0xC2:
            width = 2
        score += mojibake_weight(decode_codepoint(src, i, a))
        i += width
        if i < n and Int(src[i]) <= 0x7F:
            i = ascii_prefix(src + i, n - i) + i
    return score


@export("mftfy_repair")
def mftfy_repair(
    src_addr: Int, n: Int, dst_addr: Int, dst_capacity: Int, encoding: Int
) abi("C") -> Int:
    if n < 0 or dst_capacity < 0 or encoding < 0 or encoding > 1:
        return -3
    if n == 0:
        return 0
    if src_addr == 0 or dst_addr == 0:
        return -3
    return repair(
        BPtr(unsafe_from_address=src_addr),
        n,
        BPtr(unsafe_from_address=dst_addr),
        dst_capacity,
        encoding,
    )


@export("mftfy_valid_utf8")
def mftfy_valid_utf8(src_addr: Int, n: Int) abi("C") -> Int:
    if n < 0:
        return 0
    if n == 0:
        return 1
    if src_addr == 0:
        return 0
    return 1 if valid_utf8(BPtr(unsafe_from_address=src_addr), n) else 0


@export("mftfy_badness")
def mftfy_badness(src_addr: Int, n: Int) abi("C") -> Int:
    if n < 0 or (n > 0 and src_addr == 0):
        return -1
    if n == 0:
        return 0
    return mojibake_badness(BPtr(unsafe_from_address=src_addr), n)
