"""Independent re-measurement of the corpus trace in design.md.

Written by Claude Code from .kiro/specs/structure-inference-engine/requirements.md
alone (Req 1 closure gate, Req 2 probes, Req 3 revision, Req 4 generic search).
It does not import or copy the engine or any other measurement script. It is an
audit tool for the spec's recorded numbers, not product code.

Deliberately omitted because they cannot change the counts measured here:
deadline handling (Req 5.1-5.2), coherence (Req 11), rejection detail beyond the
reason string. The shared 10,000-check cap (Req 5.3) is enforced.

Usage: python spike/verify_independent.py   -> writes spike/VERIFY.md
"""

import struct
from dataclasses import dataclass, field, replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLES = HERE / "samples"
SEARCH_CAP = 10_000

# Trailer Registry (Req 1.5): name, length, marker, origins it applies to.
TRAILERS = [("pcx_palette_256", 769, 0x0C, {"pcx", "generic"})]


@dataclass(frozen=True)
class Hyp:
    width: int
    height: int
    bit_depth: int
    header_size: int
    row_alignment: int
    encoding: str
    data_end: object  # int or None (declared only)
    origin: str
    bounds: object = None  # (xmin, ymin, xmax, ymax) or None
    path: tuple = ()
    fields: tuple = field(default=(), compare=False)

    def key(self):
        return (self.width, self.height, self.bit_depth, self.header_size,
                self.row_alignment, self.encoding, self.data_end)


class CapExceeded(Exception):
    pass


class Counter:
    def __init__(self):
        self.checks = 0

    def tick(self):
        if self.checks + 1 > SEARCH_CAP:
            raise CapExceeded
        self.checks += 1


# ---------------------------------------------------------------- Req 1

def round_up(n, a):
    return -(-n // a) * a


def row_stride(w, bpp, align):
    return round_up(-(-(w * bpp) // 8), align)


def find_trailer(data, header_size, origin):
    for name, length, marker, origins in TRAILERS:
        if origin not in origins:
            continue
        start = len(data) - length
        if start >= header_size and data[start] == marker:
            return name, start
    return None, None


def rle_pcx_decode_len(region, max_out):
    """Req 1.9-1.11. Returns 'ok', 'overrun', 'underrun' or 'unconsumed'."""
    out = 0
    pos = 0
    n = len(region)
    while pos < n:
        if out == max_out:
            return "unconsumed"
        b = region[pos]
        if b >= 0xC0:
            if pos + 1 >= n:
                return "underrun"
            count = b & 0x3F
            if out + count > max_out:
                return "overrun"
            out += count
            pos += 2
        else:
            if out + 1 > max_out:
                return "overrun"
            out += 1
            pos += 1
    return "ok" if out == max_out else "underrun"


def check_closure(h, data):
    """Returns (closed, reason, info). Pure; never raises on valid ints."""
    if (h.width <= 0 or h.height <= 0 or h.bit_depth <= 0
            or h.row_alignment not in (1, 2, 4)
            or h.header_size < 0 or h.header_size > len(data)):
        return False, "degenerate_hypothesis", {}
    trailer = None
    if h.data_end is not None:
        if h.data_end > len(data) or h.data_end < h.header_size:
            return False, "field_out_of_bounds", {}
        end = h.data_end
    else:
        trailer, tstart = find_trailer(data, h.header_size, h.origin)
        end = tstart if trailer else len(data)
    stride = row_stride(h.width, h.bit_depth, h.row_alignment)
    expected = stride * h.height
    info = {"region": (h.header_size, end), "trailer": trailer,
            "stride": stride, "expected": expected}
    if h.encoding == "none":
        if end - h.header_size == expected:
            return True, None, info
        return False, "arithmetic_mismatch", info
    if h.encoding == "rle_pcx":
        r = rle_pcx_decode_len(data[h.header_size:end], expected)
        if r == "ok":
            return True, None, info
        return False, "decoder_" + r, info
    return False, "unsupported_encoding", info


# ---------------------------------------------------------------- Req 2

def u(fmt, data, off):
    return struct.unpack_from(fmt, data, off)[0]


def probe_pcx(data):
    if len(data) < 128 or data[0] != 0x0A or data[2] not in (0, 1):
        return None, []
    xmin, ymin, xmax, ymax = (u("<H", data, o) for o in (4, 6, 8, 10))
    bpl = u("<H", data, 0x42)
    rej = []
    if not (xmax >= xmin and ymax >= ymin and bpl > 0):
        rej.append("probe_precondition_failed")
    enc = "none" if data[2] == 0 else "rle_pcx"
    seed = Hyp(xmax, ymax, data[3], 128, 1, enc, None, "pcx",
               bounds=(xmin, ymin, xmax, ymax))
    return seed, rej


def probe_tga(data):
    if len(data) < 18 or data[1] not in (0, 1) or data[2] not in (1, 2, 3, 9, 10, 11):
        return None, []
    id_len, cmt, itype = data[0], data[1], data[2]
    cml = u("<H", data, 5)
    ces = data[7]
    w, h, bpp = u("<H", data, 0x0C), u("<H", data, 0x0E), data[0x10]
    header = 18 + id_len + cmt * cml * (-(-ces // 8))
    enc = "none" if itype in (1, 2, 3) else "rle_tga"
    rej = [] if (w > 0 and h > 0) else ["probe_precondition_failed"]
    return Hyp(w, h, bpp, header, 1, enc, None, "tga"), rej


def probe_pbm(data):
    if len(data) < 7 or data[:3] != b"P4\n":
        return None, []
    window = data[:1024]
    pos = 3
    while pos < len(window):
        nl = window.find(b"\n", pos)
        if nl < 0:
            break
        line = window[pos:nl]
        if line.startswith(b"#"):
            pos = nl + 1
            continue
        tokens = line.split()
        if len(tokens) == 2 and all(t.isdigit() for t in tokens):
            return Hyp(int(tokens[0]), int(tokens[1]), 1, nl + 1, 1, "none",
                       None, "pbm"), []
        break
    return Hyp(0, 0, 1, 3, 1, "none", None, "pbm"), ["probe_precondition_failed"]


def probe_tiff(data):
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        return None, []
    o = "<" if data[:2] == b"II" else ">"
    if u(o + "H", data, 2) != 42:
        return None, []
    rej = []
    tags = {}
    ifd = u(o + "I", data, 4)
    if ifd + 2 > len(data):
        rej.append("field_out_of_bounds")
    else:
        count = u(o + "H", data, ifd)
        for k in range(count):
            e = ifd + 2 + 12 * k
            if e + 12 > len(data):
                rej.append("field_out_of_bounds")
                break
            tag, typ, cnt = u(o + "H", data, e), u(o + "H", data, e + 2), u(o + "I", data, e + 4)
            if cnt != 1 or typ not in (3, 4):
                continue
            tags[tag] = u(o + ("H" if typ == 3 else "I"), data, e + 8)
    if any(t not in tags for t in (256, 257, 258, 273, 279)) or tags.get(277, 1) != 1:
        rej.append("probe_precondition_failed")
    comp, spp = tags.get(259, 1), tags.get(277, 1)
    so, sbc = tags.get(273, 0), tags.get(279, 0)
    enc = "none" if comp == 1 else f"tiff_compression_{comp}"
    seed = Hyp(tags.get(256, 0), tags.get(257, 0), tags.get(258, 0) * spp,
               so, 1, enc, so + sbc, "tiff")
    return seed, rej


PROBES = [("pcx", probe_pcx), ("tga", probe_tga), ("pbm", probe_pbm), ("tiff", probe_tiff)]


# ---------------------------------------------------------------- Req 3

def s_inclusive_bounds(h):
    if h.bounds is None:
        return []
    xmin, ymin, xmax, ymax = h.bounds
    return [replace(h, width=xmax - xmin + 1, height=ymax - ymin + 1)]


def s_rle_pcx(h):
    if h.origin == "pcx" and h.encoding == "none":
        return [replace(h, encoding="rle_pcx")]
    return []


def s_row_padding(h):
    return [replace(h, row_alignment=a) for a in (2, 4) if a != h.row_alignment]


STRATEGIES = [("inclusive_bounds", s_inclusive_bounds), ("rle_pcx", s_rle_pcx),
              ("row_padding_variants", s_row_padding)]


# ---------------------------------------------------------------- Req 4

FMTS = [("<H", 2), (">H", 2), ("<I", 4), (">I", 4), ("<i", 4), (">i", 4)]
DEPTHS = {1, 4, 8, 16, 24, 32}


def rle_output_len(region):
    """Run-length output of the whole region without allocating; None if truncated."""
    out, pos, n = 0, 0, len(region)
    while pos < n:
        b = region[pos]
        if b >= 0xC0:
            if pos + 1 >= n:
                return None
            out += b & 0x3F
            pos += 2
        else:
            out += 1
            pos += 1
    return out


def generic_search(data, counter, log):
    closers = []
    for L in range(4, 257, 4):
        if L >= len(data):
            break
        dims = {}
        for fmt, size in FMTS:
            for off in range(0, L - size + 1):
                v = u(fmt, data, off)
                if v > 0:
                    dims.setdefault(v, []).append((fmt, off))
        depths = {}
        for off in range(L):
            if data[off] in DEPTHS:
                depths.setdefault(data[off], []).append(off)
        trailer, tstart = find_trailer(data, L, "generic")
        end = tstart if trailer else len(data)
        encodings = [("none", end - L)]
        if trailer:
            s = rle_output_len(data[L:end])
            if s is not None:
                encodings.append(("rle_pcx", s))
        for enc, S in encodings:
            if S <= 0:
                continue
            for W, wreads in dims.items():
                for B in depths:
                    stride = -(-(W * B) // 8)
                    if S % stride:
                        continue
                    H = S // stride
                    if H not in dims:
                        continue
                    hreads = dims[H]
                    if not any(wo != ho for _, wo in wreads for _, ho in hreads):
                        continue
                    h = Hyp(W, H, B, L, 1, enc, None, "generic")
                    counter.tick()
                    ok, reason, info = check_closure(h, data)
                    log.append((h, ok, reason))
                    if ok:
                        closers.append((h, info, wreads, hreads, depths[B]))
    return closers


# ---------------------------------------------------------------- engine

def run(data):
    counter = Counter()
    log = []
    try:
        matched, seeds = [], []
        for name, probe in PROBES:
            seed, _rej = probe(data)
            if seed is not None:
                matched.append(name)
                seeds.append(seed)

        closed = {}
        for s in seeds:
            counter.tick()
            ok, reason, info = check_closure(s, data)
            log.append((s, ok, reason))
            if ok and s.key() not in closed:
                closed[s.key()] = (s, info)
        if closed:
            stage = "probe"
            closers = list(closed.values())
        elif seeds:
            stage, closers = revise(seeds, data, counter, log)
        else:
            stage = "generic"
            closers = [(c[0], c[1]) for c in generic_search(data, counter, log)]
    except CapExceeded:
        return {"matched": matched, "status": "FAILED", "stage": "search_cap_exceeded",
                "closers": [], "checks": counter.checks, "log": log}

    if not closers:
        status = "FAILED"
    elif len(closers) == 1:
        status = "RESOLVED"
    else:
        status = "UNRESOLVED_AMBIGUITY"
    return {"matched": matched, "status": status, "stage": stage,
            "closers": closers, "checks": counter.checks, "log": log}


def enumerate_pairs(frontier, order):
    """Req 3.2 'apply every strategy, in the order listed, to every hypothesis'
    admits two loop nestings. Both are measured; see VERIFY.md."""
    if order == "strategy-major":
        return [(s, h) for s in STRATEGIES for h in frontier]
    return [(s, h) for h in frontier for s in STRATEGIES]


ORDER = "strategy-major"


def revise(seeds, data, counter, log):
    seen = {s.key() for s in seeds}
    frontier = list(seeds)
    for depth in range(1, 4):
        nxt, closers = [], []
        for (sname, strat), h in enumerate_pairs(frontier, ORDER):
            for c in strat(h):
                c = replace(c, path=h.path + (sname,))
                if c.key() in seen:
                    continue
                seen.add(c.key())
                counter.tick()
                ok, reason, info = check_closure(c, data)
                log.append((c, ok, reason))
                nxt.append(c)
                if ok:
                    closers.append((c, info))
        if closers:
            return f"revision depth {depth}", closers
        frontier = nxt
    return "revision (exhausted)", []


# ---------------------------------------------------------------- report

# design.md "Corpus Trace (measured)": (closing, checks)
DESIGN = {"mystery_a": (1, 1), "mystery_b": (1, 4), "mystery_c": (1, 1),
          "mystery_d": (18, 18), "mystery_e": (1, 1), "mystery_f": (8, 8),
          "mystery_g": (8, 8), "mystery_h": (1, 10), "mystery_i": (1, 10)}

# requirements.md Req 7: (status, stage prefix, required candidate fields)
REQ7 = {
    "mystery_a": ("RESOLVED", "probe", dict(width=4, height=4, bit_depth=1, header_size=7, path=())),
    "mystery_b": ("RESOLVED", "revision", dict(width=8, height=8, bit_depth=8, header_size=128,
                                               encoding="rle_pcx", path=("inclusive_bounds",))),
    "mystery_c": ("RESOLVED", "probe", dict(width=16, height=16, bit_depth=24, header_size=18, path=())),
    "mystery_d": ("UNRESOLVED_AMBIGUITY", "generic", dict(width=8, height=8, bit_depth=8,
                                                          header_size=40, encoding="none")),
    "mystery_e": ("RESOLVED", "probe", dict(width=8, height=8, bit_depth=8, header_size=86, path=())),
    "mystery_f": ("UNRESOLVED_AMBIGUITY", "generic", dict(width=12, height=10, bit_depth=8,
                                                          header_size=12, encoding="none")),
    "mystery_g": ("UNRESOLVED_AMBIGUITY", "generic", dict(width=8, height=8, bit_depth=24,
                                                          header_size=20, encoding="none")),
    "mystery_h": ("RESOLVED", "revision", dict(width=6, height=6, bit_depth=8, header_size=128,
                                               row_alignment=4,
                                               path=("inclusive_bounds", "row_padding_variants"))),
    "mystery_i": ("RESOLVED", "revision", dict(width=8, height=8, bit_depth=8, header_size=128,
                                               encoding="rle_pcx", path=("inclusive_bounds", "rle_pcx"))),
}


def describe(h, info):
    s = (f"{h.width}x{h.height}, {h.bit_depth} bpp, header {h.header_size}, "
         f"align {h.row_alignment}, {h.encoding}, stride {info['stride']}, "
         f"region [{info['region'][0]}, {info['region'][1]})")
    if info.get("trailer"):
        s += f", trailer {info['trailer']}"
    s += f", path {list(h.path)}"
    return s


def matches(h, want):
    return all(getattr(h, k) == v for k, v in want.items())


def main():
    global ORDER
    order_rows = ["", "## Revision enumeration order (Req 3.2)", "",
                  "Req 3.2 can be read with either loop nesting. Both reach the same hypotheses",
                  "and the same counts; only the recorded `revision_path` differs, because Req 3.3",
                  "keeps the first path to reach a key and skips the other as a duplicate.", "",
                  "| File | Nesting | Closing | Checks | revision_path | Req 7 path |",
                  "|---|---|---|---|---|---|"]
    for name in ("mystery_b", "mystery_h", "mystery_i"):
        data = (SAMPLES / name).read_bytes()
        for order in ("strategy-major", "hypothesis-major"):
            ORDER = order
            r = run(data)
            paths = "; ".join(str(list(h.path)) for h, _ in r["closers"])
            want = REQ7[name][2]["path"]
            ok = all(h.path == want for h, _ in r["closers"]) and r["closers"]
            order_rows.append(f"| {name} | {order} | {len(r['closers'])} | {r['checks']} | "
                              f"{paths} | {'matches' if ok else '**differs**'} |")
    ORDER = "hypothesis-major"
    lines = ["# Independent verification of the corpus trace", "",
             "Generated by `spike/verify_independent.py`, an independent implementation of",
             "Req 1-4 of `.kiro/specs/structure-inference-engine/requirements.md`, written",
             "without reference to the engine or to any other measurement script.", "",
             "## Summary", "",
             "| File | Probes matched | Outcome | Stage | Closing | Checks | design.md (closing / checks) | Agrees | Req 7 |",
             "|---|---|---|---|---|---|---|---|---|"]
    detail = []
    for name in sorted(DESIGN):
        data = (SAMPLES / name).read_bytes()
        r = run(data)
        n = len(r["closers"])
        d_close, d_checks = DESIGN[name]
        agree = "yes" if (n, r["checks"]) == (d_close, d_checks) else "**NO**"
        st, stage, want = REQ7[name]
        req_ok = (r["status"] == st and r["stage"].startswith(stage)
                  and any(matches(h, want) for h, _ in r["closers"]))
        lines.append(f"| {name} | {', '.join(r['matched']) or 'none'} | {r['status']} | "
                     f"{r['stage']} | {n} | {r['checks']} | {d_close} / {d_checks} | {agree} | "
                     f"{'pass' if req_ok else '**FAIL**'} |")
        detail += [f"### {name} ({len(data)} bytes)", "",
                   f"- Probes matched: {', '.join(r['matched']) or 'none'}",
                   f"- Outcome: {r['status']}, stage {r['stage']}",
                   f"- Closure checks: {r['checks']}",
                   f"- Closing hypotheses ({n}):", ""]
        for i, (h, info) in enumerate(r["closers"], 1):
            flag = "  <- Req 7 expected" if matches(h, want) else ""
            detail.append(f"  {i}. {describe(h, info)}{flag}")
        rejected = [(h, reason) for h, ok, reason in r["log"] if not ok]
        if rejected:
            detail += ["", f"- Rejected ({len(rejected)}):", ""]
            for h, reason in rejected:
                detail.append(f"  - {h.width}x{h.height}, {h.bit_depth} bpp, header {h.header_size}, "
                              f"align {h.row_alignment}, {h.encoding}, path {list(h.path)}: {reason}")
        detail.append("")
    lines.insert(7, "Summary and detail use hypothesis-major revision order; see the order section.")
    lines.insert(8, "")
    out = lines + order_rows + ["", "## Per-file detail", ""] + detail
    (HERE / "VERIFY.md").write_text("\n".join(out), encoding="utf-8", newline="\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
