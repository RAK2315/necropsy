"""Build the emitted spec folder as a ZIP, in memory. Nothing is written to disk."""
import io
import zipfile

_FIXED_TIME = (2026, 1, 1, 0, 0, 0)     # fixed so the same spec always gives the same bytes


def build_zip(spec) -> bytes:
    """ZIP holding <slug>/<file> for each emitted file, text as UTF-8 without a BOM."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in spec.files:
            info = zipfile.ZipInfo(f"{spec.slug}/{name}", date_time=_FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, text.encode("utf-8"))
    return buf.getvalue()