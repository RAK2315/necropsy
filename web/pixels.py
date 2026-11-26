"""Turn a candidate's decoded pixel bytes into a viewable pixel buffer.

Requirement 3. The engine returns raw bytes plus geometry; this is the conversion.
decode() never raises: it returns a PixelBuffer or a RenderFailure.
"""
from dataclasses import dataclass

SUPPORTED_DEPTHS = (1, 4, 8, 24, 32)
PALETTE_LENGTH = 768
PALETTE_NAME = "pcx_palette_256"
FLIP_NOTE = "rows flipped: file declares bottom-left origin"
STORED_NOTE = "rows shown in stored order"
NO_PHOTOMETRIC = "no photometric interpretation declared; shown as BlackIsZero (0 = black)"
# Channel order of 24/32-bit pixels, from what the file declares (Requirement 3.5)
CHANNEL_NOTES = {"bgr": "BGR→RGB", "rgb": "RGB as stored",
                 "bgr-convention": "BGR→RGB (a convention: the file declares no channel order)"}
_INVERT = bytes(255 - i for i in range(256))


@dataclass(frozen=True)
class PixelBuffer:
    width: int
    height: int
    channels: str          # "grey8" (1 byte per pixel) or "rgb8" (3 bytes per pixel, R G B)
    data: bytes            # exactly width * height * bytes-per-pixel
    note: str


@dataclass(frozen=True)
class RenderFailure:
    reason: str


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _bit_table_1(black_is_one: bool) -> list:
    """For each byte value, the 8 grey bytes it expands to, most significant bit first."""
    one, zero = (0, 255) if black_is_one else (255, 0)
    return [bytes(one if (b >> (7 - k)) & 1 else zero for k in range(8)) for b in range(256)]


_TABLE_1 = {True: _bit_table_1(True), False: _bit_table_1(False)}
_TABLE_4 = [bytes(((b >> 4) * 17, (b & 0x0F) * 17)) for b in range(256)]


def _interleave(r: bytes, g: bytes, b: bytes) -> bytes:
    out = bytearray(3 * len(r))
    out[0::3], out[1::3], out[2::3] = r, g, b
    return bytes(out)


def decode(decoded, width, height, bit_depth, row_stride, probe_name,
           palette=None, bottom_left=False, channel_order="bgr", photometric=None,
           palette_name=PALETTE_NAME, no_palette_why=None, maxval=None, planes=1, header_palette=None,
           byte_order=None):
    """Return a PixelBuffer, or a RenderFailure with a reason. Never raises.

    byte_order: b"II" or b"MM", the TIFF header's two bytes; it orders the words of 16-bit TIFF grey.

    maxval: the PNM header's declared maximum. With probe_name "pnm" and bit_depth 8, 16, 24 or 48 the samples are
    scaled v * 255 // maxval (16-bit samples are big-endian words).

    planes, header_palette: PCX with planes > 1 (bit_depth is then bits per plane times planes, row_stride the whole
    scanline); header_palette is the 48 bytes at 0x10.

    channel_order: "bgr", "rgb" or "bgr-convention" (24/32 bit). photometric: None, 0 (WhiteIsZero), 1 (BlackIsZero)
    or "undeclared" (1/4/8-bit grey). palette_name names the colour source in the note; no_palette_why says why an
    8-bit colour map was not applied.
    """
    try:
        return _decode(decoded, width, height, bit_depth, row_stride, probe_name, palette, bottom_left,
                       channel_order, photometric, palette_name, no_palette_why, maxval, planes, header_palette, byte_order)
    except Exception as exc:  # last line of defence; the checks below bound every read
        return RenderFailure(f"internal error: {type(exc).__name__}")


PNM_DEPTHS = (8, 16, 24, 48)
HEADER_PALETTE_LENGTH = 48


def _decode_pcx_planar(decoded, width, height, bit_depth, row_stride, planes, header_palette):
    """PCX scanlines of `planes` planes (Requirements 16.1, 16.2). bit_depth is bits per plane times planes.

    8 bits per plane, 3 or 4 planes: R, G, B planes (a fourth is ignored). 1 bit per plane, 2 to 4 planes: the planes'
    bits form the index, plane 0 lowest, into the 16-entry RGB palette the header declares at 0x10.
    """
    per_plane, rem = divmod(bit_depth, planes)
    layout = f"PCX with {planes} planes of {per_plane} bits"
    if rem or not ((per_plane == 8 and planes in (3, 4)) or (per_plane == 1 and 2 <= planes <= 4)):
        return RenderFailure(f"no renderer for {layout}")
    plane_len, rem = divmod(row_stride, planes)
    if rem or plane_len < -(-(width * per_plane) // 8) or len(decoded) < row_stride * height:
        return RenderFailure("inconsistent geometry")
    d = bytes(decoded)
    if per_plane == 8:
        r, g, b = bytearray(), bytearray(), bytearray()
        for y in range(height):
            o = y * row_stride
            r += d[o: o + width]
            g += d[o + plane_len: o + plane_len + width]
            b += d[o + 2 * plane_len: o + 2 * plane_len + width]
        return PixelBuffer(width, height, "rgb8", _interleave(r, g, b),
                           f"{layout} · R, G, B planes{'; fourth plane ignored' if planes == 4 else ''} · {STORED_NOTE}")
    if not (isinstance(header_palette, (bytes, bytearray)) and len(header_palette) == HEADER_PALETTE_LENGTH):
        return RenderFailure(f"no renderer for {layout}: no 16-entry header palette")
    p = bytes(header_palette)
    out = bytearray()
    for y in range(height):
        o = y * row_stride
        for x in range(width):
            idx = 0
            for k in range(planes):
                idx |= ((d[o + k * plane_len + (x >> 3)] >> (7 - (x & 7))) & 1) << k
            out += p[idx * 3: idx * 3 + 3]
    return PixelBuffer(width, height, "rgb8", bytes(out),
                       f"{layout} · index from plane bits, plane 0 lowest · palette: PCX header (0x10) · {STORED_NOTE}")


def _decode_pnm(decoded, width, height, bit_depth, row_stride, maxval):
    """PNM grey (8, 16) and RGB (24, 48) samples, each shown as v * 255 // maxval (Requirement 16.1)."""
    if not 1 <= maxval <= 65535:
        return RenderFailure("inconsistent geometry")
    per = 1 if bit_depth in (8, 24) else 2            # bytes per sample
    channels = 1 if bit_depth in (8, 16) else 3
    used = width * channels * per
    if row_stride < used or len(decoded) < row_stride * height:
        return RenderFailure("inconsistent geometry")
    d = bytes(decoded)
    raw = b"".join(d[r * row_stride: r * row_stride + used] for r in range(height))
    if per == 1:
        table = bytes(min(255, v * 255 // maxval) for v in range(256))
        samples = raw.translate(table)
        word = "8-bit samples"
    else:
        samples = bytes(min(255, ((raw[i] << 8) | raw[i + 1]) * 255 // maxval) for i in range(0, len(raw), 2))
        word = "16-bit big-endian samples"
    if channels == 1:
        return PixelBuffer(width, height, "grey8", samples,
                           f"PNM grey · {word} · v×255//{maxval} · {STORED_NOTE}")
    data = _interleave(samples[0::3], samples[1::3], samples[2::3])
    return PixelBuffer(width, height, "rgb8", data,
                       f"PNM RGB as stored · {word} · v×255//{maxval} · {STORED_NOTE}")


TIFF_RGB_NO_RENDERER = {36: "12-bit RGB TIFF", 48: "16-bit RGB TIFF"}


def _decode_tiff_grey(decoded, width, height, bit_depth, row_stride, byte_order, photometric):
    """TIFF grey at 12 or 16 bits, each sample shown as v * 255 // (2^bits - 1) (Requirement 16.1).

    16 bits: a word in the declared byte order (b"II" little, b"MM" big). 12 bits: packed most significant bit first,
    so a pair of samples is three bytes, (b0 << 4) | (b1 >> 4) and ((b1 & 15) << 8) | b2; the byte order does not apply.
    """
    top = (1 << bit_depth) - 1
    used = -(-(width * bit_depth) // 8)
    if row_stride < used or len(decoded) < row_stride * height:
        return RenderFailure("inconsistent geometry")
    d = bytes(decoded)
    out = bytearray()
    if bit_depth == 16:
        if byte_order not in (b"II", b"MM"):
            return RenderFailure("no renderer for 16-bit grey TIFF: byte order not declared")
        hi, lo = (1, 0) if byte_order == b"II" else (0, 1)
        for y in range(height):
            o = y * row_stride
            for x in range(width):
                out.append(((d[o + 2 * x + hi] << 8 | d[o + 2 * x + lo]) * 255) // top)
        order = "little-endian (II)" if byte_order == b"II" else "big-endian (MM)"
        word = f"16-bit {order} samples"
    else:
        for y in range(height):
            o = y * row_stride
            for x in range(width):
                i = o + (x * 3) // 2
                v = (d[i] << 4 | d[i + 1] >> 4) if x % 2 == 0 else ((d[i] & 15) << 8 | d[i + 1])
                out.append((v * 255) // top)
        word = "12-bit samples packed most significant bit first"
    data, pi = _grey(bytes(out), photometric)
    return PixelBuffer(width, height, "grey8", data, f"TIFF grey · {word} · v×255//{top} · {pi or 'grey'} · {STORED_NOTE}")


def _grey(data, photometric):
    """Apply the declared photometric interpretation to grey levels; returns (data, note fragment)."""
    if photometric == 0:
        return data.translate(_INVERT), "WhiteIsZero (photometric 0)"
    if photometric == 1:
        return data, "BlackIsZero (photometric 1)"
    if photometric == "undeclared":
        return data, NO_PHOTOMETRIC
    return data, None


def _decode(decoded, width, height, bit_depth, row_stride, probe_name, palette, bottom_left,
            channel_order, photometric, palette_name, no_palette_why, maxval=None, planes=1, header_palette=None,
            byte_order=None):
    if not isinstance(decoded, (bytes, bytearray)):
        return RenderFailure("inconsistent geometry")
    if not all(_is_int(v) and v > 0 for v in (width, height, bit_depth, row_stride)):
        return RenderFailure("inconsistent geometry")
    if probe_name == "pcx" and _is_int(planes) and planes > 1:
        return _decode_pcx_planar(decoded, width, height, bit_depth, row_stride, planes, header_palette)
    if probe_name == "pnm" and bit_depth in PNM_DEPTHS and _is_int(maxval):
        return _decode_pnm(decoded, width, height, bit_depth, row_stride, maxval)
    if probe_name == "tiff" and bit_depth in (12, 16):
        return _decode_tiff_grey(decoded, width, height, bit_depth, row_stride, byte_order, photometric)
    if probe_name == "tiff" and bit_depth in TIFF_RGB_NO_RENDERER:
        return RenderFailure(f"no renderer for {TIFF_RGB_NO_RENDERER[bit_depth]} ({bit_depth}-bit pixels)")
    if bit_depth not in SUPPORTED_DEPTHS:
        return RenderFailure(f"no renderer for {bit_depth}-bit pixels")
    used = -(-(width * bit_depth) // 8)               # bytes of pixel data in one row
    if row_stride < used or len(decoded) < row_stride * height:
        return RenderFailure("inconsistent geometry")

    d = bytes(decoded)
    rows = [d[r * row_stride: r * row_stride + used] for r in range(height)]   # padding dropped
    if bottom_left:
        rows.reverse()
    orientation = FLIP_NOTE if bottom_left else STORED_NOTE

    if bit_depth == 1:
        black_is_one = probe_name in ("pbm", "pnm")   # plain P1 is black-is-one through the PBM path (Requirement 16.4)
        t = _TABLE_1[black_is_one]
        data = b"".join(b"".join(t[b] for b in row)[:width] for row in rows)
        colour = "1 = black (PBM)" if black_is_one else "grey, 1 = white"
        data, pi = _grey(data, photometric)
        if pi:
            colour = pi
        return PixelBuffer(width, height, "grey8", data, f"1-bit · {colour} · {orientation}")
    if bit_depth == 4:
        data = b"".join(b"".join(_TABLE_4[b] for b in row)[:width] for row in rows)
        data, pi = _grey(data, photometric)
        return PixelBuffer(width, height, "grey8", data, f"4-bit · {pi or 'grey'} · {orientation}")
    if bit_depth == 8:
        idx = b"".join(rows)
        if isinstance(palette, (bytes, bytearray)) and len(palette) == PALETTE_LENGTH:
            p = bytes(palette)
            data = _interleave(idx.translate(p[0::3]), idx.translate(p[1::3]), idx.translate(p[2::3]))
            return PixelBuffer(width, height, "rgb8", data, f"8-bit · palette: {palette_name} · {orientation}")
        if no_palette_why:
            return PixelBuffer(width, height, "grey8", idx, f"8-bit · {no_palette_why}; indices shown as grey · {orientation}")
        idx, pi = _grey(idx, photometric)
        return PixelBuffer(width, height, "grey8", idx, f"8-bit · {pi or 'greyscale; no palette'} · {orientation}")
    # 24 and 32 bit: three channels in the declared order (a fourth byte is not used); shown as R, G, B
    step = bit_depth // 8
    raw = b"".join(rows)
    if channel_order == "rgb":
        data = _interleave(raw[0::step], raw[1::step], raw[2::step])
    else:
        data = _interleave(raw[2::step], raw[1::step], raw[0::step])
    order = CHANNEL_NOTES.get(channel_order, CHANNEL_NOTES["bgr"])
    extra = "; fourth byte ignored" if step == 4 else ""
    return PixelBuffer(width, height, "rgb8", data, f"{bit_depth}-bit · {order}{extra} · {orientation}")
