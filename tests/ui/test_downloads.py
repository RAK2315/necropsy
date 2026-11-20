"""Downloads (Requirement 17): the PNG is the pixel buffer at native size, the data region is the file's bytes.

Clicks the real controls in a real browser and captures the files the page hands to the browser. The PNG is
decoded here with the standard library only, so the comparison does not depend on the browser that made it.
"""
import base64
import struct
import zlib

from necropsy.engine import Engine
from tests.conftest import REPO_ROOT, corpus_bytes
from tests.ui.conftest import run_in_browser
from web.serialise import to_payload

EXT = REPO_ROOT / "spike" / "samples" / "external"


def decode_png(data: bytes):
    """(width, height, RGBA bytes) for an 8-bit, non-interlaced RGB or RGBA PNG. Raises on anything else."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, ihdr = 8, b"", None
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat += body
        pos += 12 + n
    w, h, depth, ctype, _, _, interlace = ihdr
    assert depth == 8 and ctype in (2, 6) and interlace == 0, ihdr
    bpp = 4 if ctype == 6 else 3
    raw = zlib.decompress(idat)
    stride = w * bpp
    out, prev, i = bytearray(), bytearray(stride), 0
    for _ in range(h):
        f, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        if bpp == 3:
            for x in range(w):
                out += line[3 * x:3 * x + 3] + b"\xff"
        else:
            out += line
    return w, h, bytes(out)


def rgba_of_render(render) -> bytes:
    raw = base64.b64decode(render["data_b64"])
    if render["channels"] == "grey8":
        return b"".join(bytes((v, v, v, 255)) for v in raw)
    return b"".join(raw[i:i + 3] + b"\xff" for i in range(0, len(raw), 3))


def scenario(sample: str, card: int | None) -> str:
    target = "document.querySelector('.exam-right .card-dl')" if card is None \
        else f"document.querySelectorAll('.card')[{card}].querySelector('.card-dl')"
    wait = "document.querySelector('.exam-right:not(.pending) .card-dl')" if card is None else "document.querySelectorAll('.card').length"
    return f"""
(async () => {{
  await __until(() => document.querySelector('.pick'), 'start');
  [...document.querySelectorAll('.pick')].find(b => b.textContent === {sample!r}).click();
  const skip = await __until(() => document.querySelector('.rp-bar button[title="Skip to the end"]'), 'replay');
  if (!skip.disabled) skip.click();
  await __until(() => {wait}, 'result');
  const row = {target};
  row.querySelector('[data-act="png"]').click();
  await __until(() => __blobs.length === 1 && __blobs[0].b64 && __blobs[0].name, 'png');
  row.querySelector('[data-act="data"]').click();
  await __until(() => __blobs.length === 2 && __blobs[1].b64 && __blobs[1].name, 'data');
  return JSON.stringify({{ blobs: __blobs, selected: document.querySelectorAll('.card.open').length }});
}})()
"""


def check(base_url, sample, data, cand_index, card):
    payload = to_payload(Engine().run(data), data, 1.0)
    c = payload["candidates"][cand_index]
    got = run_in_browser(base_url, scenario(sample, card))
    png, region = got["blobs"]
    g = f"{sample}_{c['width']}x{c['height']}_{c['bit_depth']}bit"
    assert png["name"] == f"{g}.png" and png["type"] == "image/png"
    w, h, rgba = decode_png(base64.b64decode(png["b64"]))
    assert (w, h) == (c["width"], c["height"]), f"PNG is {w}x{h}, not native {c['width']}x{c['height']}"
    assert rgba == rgba_of_render(c["render"]), "PNG pixels differ from the pixel buffer"
    assert region["name"] == f"{g}_data_{c['data_start']}-{c['data_end']}.bin"
    assert base64.b64decode(region["b64"]) == data[c["data_start"]:c["data_end"]], "data region differs from the file's bytes"
    return got, c


def test_resolved_png_and_data_region(base_url):
    data = (EXT / "external_a").read_bytes()
    _, c = check(base_url, "external_a", data, 0, None)
    # independent ground truth: the source image Pillow encoded
    raw = (EXT / "source.ppm").read_bytes().split(b"\n", 3)[3]
    assert rgba_of_render(c["render"]) == b"".join(raw[i:i + 3] + b"\xff" for i in range(0, len(raw), 3))
    assert (c["data_start"], c["data_end"]) == (128, 393)       # still RLE-encoded, as stored


def test_ambiguity_card_png_and_data_region_without_selecting_the_card(base_url):
    data = corpus_bytes("mystery_d")
    got, _ = check(base_url, "mystery_d", data, 1, 1)           # the second card, so card 0 is not special
    assert got["selected"] == 0, "a download click selected the card"
