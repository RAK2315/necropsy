"""Local development server: the real app plus public/ at the root. Not deployed.

python tools/serve.py   then open http://127.0.0.1:8765/
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn
from fastapi.staticfiles import StaticFiles

from app import app

app.mount("/", StaticFiles(directory=ROOT / "public", html=True), name="public")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")