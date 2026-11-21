"""Decode the sample PCX with parser_pcx and write recovered.png.

Pillow is used only to write the PNG, never to decode.
"""
from pathlib import Path

from PIL import Image

import parser_pcx

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "../../../spike/samples/real/pillow_odd_stride.pcx"


def main():
    data = SAMPLE.resolve().read_bytes()
    r = parser_pcx.parse(data)
    if not r["ok"]:
        raise SystemExit("parse failed: %r" % (r["error"],))

    # NOT IN THE SPEC: the spec names the trailer (pcx_palette_256, 769 bytes,
    # signature 0x0C) but never says how to use it. Taking the 768 bytes after
    # the 0x0C signature as 256 R,G,B entries is outside knowledge.
    assert r["trailer"] == "pcx_palette_256"
    pal = data[r["data_end"] + 1 : r["data_end"] + 769]
    assert len(pal) == 768

    img = Image.frombytes("P", (r["width"], r["height"]), r["pixels"])
    img.putpalette(pal)
    out = HERE / "recovered.png"
    img.convert("RGB").save(out)
    print("wrote", out, img.size)


if __name__ == "__main__":
    main()
