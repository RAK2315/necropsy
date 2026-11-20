"""Property 16: declared trailer offsets are total and minimal (task 18.4).

The model below is written from the text of Requirement 1.15 only. It does not
call or mirror any code in necropsy/engine/trailers.py.
"""
from __future__ import annotations

import struct

from hypothesis import given, settings, strategies as st

from necropsy.engine.trailers import match_trailer, trailer_data_end

SIG = b"TRUEVISION-XFILE.\x00"
ORIGINS = ["pcx", "tga", "generic", "pbm", "tiff"]
OOB = "field_out_of_bounds"


# ------------------------------------------------------------------ model
def model(data: bytes, H: int):
    """Requirement 1.15 for origin "tga". Returns None (no footer match),
    "error" (field_out_of_bounds) or the expected data_end."""
    n = len(data)
    F = n - 26
    if F < H or data[F + 8:F + 26] != SIG:
        return None
    E = struct.unpack_from("<I", data, F)[0]
    D = struct.unpack_from("<I", data, F + 4)[0]
    declared = [E, D]
    if E != 0 and H <= E < F:
        # E+2 <= F+2 <= n, so the size read is inside the file.
        size = struct.unpack_from("<H", data, E)[0]
        if size < 495 or E + size > F:
            return "error"
        for off in (482, 486, 490):
            declared.append(struct.unpack_from("<I", data, E + off)[0])
    for o in declared:
        if o != 0 and not (H <= o < F):
            return "error"
    return min([F] + [o for o in declared if o != 0])


# ------------------------------------------------------- never raises
# Feature: structure-inference-engine, Property 16: Declared trailer offsets are total and minimal
# **Validates: Requirements 1.3, 1.15, 6.4**
@settings(max_examples=100, deadline=None)
@given(
    data=st.binary(max_size=65536),
    header_size=st.integers(min_value=-5, max_value=70000),
    origin=st.sampled_from(ORIGINS),
)
def test_property_16_never_raises_arbitrary_bytes(data, header_size, origin):
    data_end, name, error = trailer_data_end(data, header_size, origin)
    assert error in (None, OOB)
    if name is None:
        assert data_end == len(data)
        assert error is None
    if name == "pcx_palette_256":
        assert (data_end, name) == match_trailer(data, header_size, origin)
        assert error is None


# Feature: structure-inference-engine, Property 16: Declared trailer offsets are total and minimal
# **Validates: Requirements 1.3, 1.15, 6.4**
@settings(max_examples=100, deadline=None)
@given(
    tail=st.binary(max_size=60),
    header_size=st.integers(min_value=0, max_value=40),
    origin=st.sampled_from(["tga", "generic"]),
    value=st.integers(min_value=0, max_value=2**32 - 1),
)
def test_property_16_never_raises_footer_shaped(tail, header_size, origin, value):
    data = tail + struct.pack("<II", value, value) + SIG
    data_end, name, error = trailer_data_end(data, header_size, origin)
    assert error in (None, OOB)
    assert name in (None, "tga2_footer")


# -------------------------------------------------- structured generator
KINDS = ["zero", "inrange", "belowH", "atF", "aboveF", "ext", "huge"]
# Weighted so that valid extension areas are reached often.
INNER = ["zero", "zero", "inrange", "inrange", "belowH", "atF", "aboveF", "huge"]
EXT = ["ext"] * 8 + KINDS
DEV = ["zero"] * 4 + ["inrange"] * 2 + [k for k in KINDS if k != "ext"]


def _resolve(kind, draw, H, F, p):
    if kind == "zero":
        return 0
    if kind == "inrange":
        return draw(st.integers(min_value=H, max_value=F - 1)) if F > H else 0
    if kind == "belowH":
        return H - 1 if H > 0 else 2**32 - 1
    if kind == "atF":
        return F
    if kind == "aboveF":
        return F + draw(st.integers(min_value=1, max_value=1000))
    if kind == "ext":
        return p
    return 2**32 - 1


@st.composite
def tga2_files(draw):
    H = draw(st.integers(min_value=0, max_value=40))
    p = draw(st.integers(min_value=H, max_value=700) if draw(st.integers(0, 9)) else st.integers(min_value=0, max_value=700))
    prefix = draw(st.binary(min_size=p, max_size=p))
    has_area = draw(st.booleans())
    area = b""
    if has_area:
        area_len = draw(st.sampled_from([0, 2, 100, 494, 495, 495, 495, 496, 497, 520, 520]))
        area = bytearray(draw(st.binary(min_size=area_len, max_size=area_len)) if area_len < 100 else bytes(area_len))
    F = p + len(area)
    if has_area:
        area_len = len(area)
        size = draw(st.sampled_from([area_len, area_len, area_len, 
            0, 494, 495, 496, area_len, area_len + 1, max(area_len - 1, 0),
            draw(st.integers(min_value=0, max_value=65535)),
        ]))
        if area_len >= 2:
            struct.pack_into("<H", area, 0, size)
        for off in (482, 486, 490):
            if area_len >= off + 4:
                v = _resolve(draw(st.sampled_from(INNER)), draw, H, F, p)
                struct.pack_into("<I", area, off, v)
    e_kind = draw(st.sampled_from(EXT)) if has_area else draw(st.sampled_from([k for k in KINDS if k != "ext"]))
    ext = _resolve(e_kind, draw, H, F, p)
    dev = _resolve(draw(st.sampled_from(DEV)), draw, H, F, p)
    sig = SIG if draw(st.integers(min_value=0, max_value=9)) else draw(st.binary(min_size=18, max_size=18))
    # Footer: <I extension_area_offset @0, <I developer_area_offset @4, signature @8.
    return bytes(prefix) + bytes(area) + struct.pack("<II", ext, dev) + sig, H


# Feature: structure-inference-engine, Property 16: Declared trailer offsets are total and minimal
# **Validates: Requirements 1.3, 1.15, 6.4**
@settings(max_examples=100, deadline=None)
@given(tga2_files())
def test_property_16_matches_independent_model(case):
    data, H = case
    n = len(data)
    expected = model(data, H)
    data_end, name, error = trailer_data_end(data, H, "tga")
    if expected is None:
        assert (data_end, name, error) == (n, None, None)
    elif expected == "error":
        assert name == "tga2_footer"
        assert error == OOB
    else:
        assert error is None
        assert name == "tga2_footer"
        assert H <= data_end <= n - 26
        assert data_end == expected


# Feature: structure-inference-engine, Property 16: Declared trailer offsets are total and minimal
# **Validates: Requirements 1.3, 1.15, 6.4**
@settings(max_examples=100, deadline=None)
@given(tga2_files())
def test_property_16_generic_origin_agrees_when_pcx_cannot_match(case):
    data, H = case
    # The pcx entry needs len(data) - 769 >= H; below that only tga2_footer can match.
    if len(data) - 769 >= H:
        return
    assert trailer_data_end(data, H, "generic") == trailer_data_end(data, H, "tga")


# ------------------------------------------------------ fixed examples
def _file(ext=0, dev=0, area=b"", gap=b"", H=18):
    body = bytes(H) + bytes(64) + gap
    p = len(body)
    return body + area + struct.pack("<II", ext, dev) + SIG, p


def test_examples_against_model():
    data, _ = _file()
    assert trailer_data_end(data, 18, "tga") == (82, "tga2_footer", None)
    data, _ = _file(dev=82, gap=bytes(10))
    assert trailer_data_end(data, 18, "tga") == (82, "tga2_footer", None)
    data, _ = _file(dev=10)
    assert trailer_data_end(data, 18, "tga")[2] == OOB
    data, _ = _file(dev=82)  # F == 82, offset at F
    assert trailer_data_end(data, 18, "tga")[2] == OOB
