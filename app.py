"""NECROPSY UI: Analysis service. Thin web layer over the unchanged engine."""
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from necropsy.emit import EmittedSpec, emit_spec
from necropsy.engine import Engine
from web.serialise import to_payload
from web.speczip import build_zip

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


def _analyse(data: bytes) -> dict:
    start = time.perf_counter()
    result = Engine(deadline_seconds=5.0).run(data)
    engine_ms = (time.perf_counter() - start) * 1000.0
    return to_payload(result, data, engine_ms)


def _spec_zip(data: bytes):
    result = Engine(deadline_seconds=5.0).run(data)
    return emit_spec(result, data)


@app.post("/api/analyze")
async def analyze(request: Request):
    data = await _read_body(request)
    if data is None:
        return _too_large()
    return await run_in_threadpool(_analyse, data)


@app.post("/api/spec.zip")
async def spec_zip(request: Request):
    data = await _read_body(request)
    if data is None:
        return _too_large()
    spec = await run_in_threadpool(_spec_zip, data)
    if not isinstance(spec, EmittedSpec):
        return JSONResponse({"error": "nothing_recovered", "message": getattr(spec, "message", "")},
                            status_code=404)
    return Response(build_zip(spec), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{spec.slug}.zip"'})


@app.exception_handler(Exception)
async def _unexpected(_request: Request, exc: Exception):
    return JSONResponse({"error": type(exc).__name__}, status_code=500)