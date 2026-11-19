"""NECROPSY UI: Analysis service. Thin web layer over the unchanged engine."""
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from necropsy.engine import Engine

MAX_UPLOAD = 65_536

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _too_large() -> JSONResponse:
    return JSONResponse(
        {"error": "file_too_large", "limit_bytes": MAX_UPLOAD,
         "message": f"The file is larger than the {MAX_UPLOAD:,} byte limit."},
        status_code=413,
    )


async def _read_body(request: Request) -> bytes | None:
    """Read the body, stopping as soon as it exceeds the cap. None means too large."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_UPLOAD:
        return None
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_UPLOAD:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


@app.post("/api/analyze")
async def analyze(request: Request):
    data = await _read_body(request)
    if data is None:
        return _too_large()
    start = time.perf_counter()
    result = Engine(deadline_seconds=5.0).run(data)
    engine_ms = (time.perf_counter() - start) * 1000.0
    return {"status": result.status, "total_checks": result.total_checks,
            "engine_ms": round(engine_ms, 2)}


@app.exception_handler(Exception)
async def _unexpected(_request: Request, exc: Exception):
    return JSONResponse({"error": type(exc).__name__}, status_code=500)