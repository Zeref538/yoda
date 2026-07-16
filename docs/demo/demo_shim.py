"""Pyodide backend shim for the YODA browser demo.

Installs a minimal fake `fastapi` module (just enough for yoda.web to import
unchanged), then exposes `dispatch()` — an async bridge the demo page's JS
calls instead of fetch(). The entire pipeline (profiler, planner, executor,
verifier) runs in the visitor's browser via WebAssembly; uploaded files never
leave their machine, which is the same guarantee as the real tool.

The LLM planner cannot run in a browser (no Ollama): urllib fails instantly
in Pyodide, so LLMPlanner falls back to the deterministic rule-based planner
— the demo banner says so.
"""

from __future__ import annotations

import inspect
import json
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------- fastapi stub
fastapi = types.ModuleType("fastapi")
responses = types.ModuleType("fastapi.responses")

ROUTES: dict[tuple[str, str], object] = {}


class _App:
    def __init__(self, **kw): ...

    def _register(self, method, path, **kw):
        def deco(fn):
            ROUTES[(method, path)] = fn
            return fn
        return deco

    def get(self, path, **kw):
        return self._register("GET", path, **kw)

    def post(self, path, **kw):
        return self._register("POST", path, **kw)


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = ""):
        self.status_code, self.detail = status_code, detail
        super().__init__(detail)


class UploadFile:
    def __init__(self, filename: str, raw: bytes):
        self.filename, self._raw = filename, raw

    async def read(self) -> bytes:
        return self._raw


def File(*a, **kw):  # noqa: N802 — matches fastapi's signature
    return None


class Response:
    def __init__(self, content=b"", media_type="application/octet-stream", **kw):
        self.body = content if isinstance(content, bytes) else str(content).encode()
        self.media_type = media_type


class HTMLResponse(Response):
    pass


class FileResponse(Response):
    def __init__(self, path, filename=None, media_type=None, **kw):
        self.body = Path(path).read_bytes()
        self.media_type = media_type or "application/octet-stream"
        self.filename = filename or Path(path).name


fastapi.FastAPI = _App
fastapi.File = File
fastapi.HTTPException = HTTPException
fastapi.UploadFile = UploadFile
responses.Response = Response
responses.HTMLResponse = HTMLResponse
responses.FileResponse = FileResponse
fastapi.responses = responses
sys.modules["fastapi"] = fastapi
sys.modules["fastapi.responses"] = responses

import yoda.web  # noqa: E402  (registers all routes into ROUTES)


class _DemoPlanner:
    """Stands in for LLMPlanner in the browser: no Ollama exists here, so
    every plan comes from the deterministic rule-based baseline. The outcome
    says so, and the page banner explains it."""

    def __init__(self, model: str | None = None, **kw):
        self.last_outcome = {
            "source": "rule_based (browser demo — install locally for the AI planner)",
            "attempts": 0, "errors": []}

    def plan(self, profile, instruction=None, col=None):
        steps = yoda.web.RuleBasedPlanner().plan(profile)
        if col:
            steps = [s for s in steps if s.get("col") in (col, None)]
        return steps


yoda.web.LLMPlanner = _DemoPlanner
ROUTES[("GET", "/api/models")] = lambda: {"models": []}


def _json_safe(obj) -> str:
    """json string safe for JS JSON.parse: NaN/Infinity become null."""
    raw = json.dumps(obj, default=str)
    return json.dumps(json.loads(raw, parse_constant=lambda _: None))


async def dispatch(method: str, path: str, query_json: str = "{}",
                   body_json: str = "null", file_name: str = "",
                   file_bytes=None) -> dict:
    """Bridge for JS: returns {"status", "kind": "json"|"bytes"|"text",
    "data", "filename", "media_type"}. `file_bytes` is a JS Uint8Array."""
    fn = ROUTES.get((method, path))
    if fn is None:
        return {"status": 404, "kind": "json",
                "data": json.dumps({"detail": f"no route {method} {path}"})}
    query = json.loads(query_json)
    body = json.loads(body_json)
    try:
        sig = inspect.signature(fn)
        kwargs = {}
        for pname, p in sig.parameters.items():
            if isinstance(p.default, UploadFile) or pname == "file":
                raw = bytes(file_bytes.to_py()) if hasattr(file_bytes, "to_py") \
                    else bytes(file_bytes or b"")
                kwargs[pname] = UploadFile(file_name or "data.csv", raw)
            elif pname == "body":
                kwargs[pname] = body or {}
            elif pname in query:
                kwargs[pname] = query[pname]
            elif p.default is not inspect.Parameter.empty:
                kwargs[pname] = p.default
        result = fn(**kwargs)
        if inspect.iscoroutine(result):
            result = await result
    except HTTPException as exc:
        return {"status": exc.status_code, "kind": "json",
                "data": json.dumps({"detail": exc.detail})}
    except Exception as exc:  # surface anything else as a 500 with detail
        return {"status": 500, "kind": "json",
                "data": json.dumps({"detail": f"{type(exc).__name__}: {exc}"})}

    if isinstance(result, FileResponse):
        return {"status": 200, "kind": "bytes", "data": result.body,
                "filename": result.filename, "media_type": result.media_type}
    if isinstance(result, Response):
        return {"status": 200, "kind": "text",
                "data": result.body.decode("utf-8"),
                "media_type": result.media_type}
    return {"status": 200, "kind": "json", "data": _json_safe(result)}
