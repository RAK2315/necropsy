"""Shared fixtures for UI tests: the real app plus public/ on a local port, and a real-browser runner."""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from tests.conftest import REPO_ROOT

RUNNER = REPO_ROOT / "tools" / "browser_run.mjs"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    if shutil.which("node") is None:
        pytest.skip("node is not installed; browser checks need it")
    live = os.environ.get("NECROPSY_BASE_URL")   # acceptance against a deployed URL instead of a local server
    if live:
        yield live.rstrip("/") + "/"
        return
    import app as service

    site = FastAPI()
    for route in service.app.routes:          # the real API endpoints, unchanged
        site.router.routes.append(route)
    site.mount("/", StaticFiles(directory=REPO_ROOT / "public", html=True), name="public")
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(site, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(400):
        if server.started:
            break
        time.sleep(0.025)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=5)


def run_in_browser(url: str, scenario: str, rewrite: str | None = None, reduced_motion: bool = False,
                   prelude: str | None = None, viewport: str | None = None) -> dict:
    """Evaluate `scenario` (an async JS expression returning a JSON string) in a real page at `url`."""
    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "scenario.js"
        sp.write_text(scenario, encoding="utf-8")
        cmd = ["node", str(RUNNER), url, str(sp)]
        if rewrite:
            rp = Path(d) / "rewrite.js"
            rp.write_text(rewrite, encoding="utf-8")
            cmd += ["--rewrite", str(rp)]
        if prelude:
            pp = Path(d) / "prelude.js"
            pp.write_text(prelude, encoding="utf-8")
            cmd += ["--prelude", str(pp)]
        if reduced_motion:
            cmd.append("--reduced-motion")
        if viewport:
            cmd += ["--viewport", viewport]
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=120)
    lines = out.stdout.strip().splitlines()
    result = json.loads(lines[-1]) if lines else {"error": out.stderr[-500:]}
    if isinstance(result, dict) and result.get("error") == "no browser":
        pytest.skip("no Edge or Chrome found to drive")
    assert not (isinstance(result, dict) and "error" in result), result
    return result