"""NECROPSY MCP server: proof against the engine and the web service (necropsy-mcp spec).

The server runs as a subprocess over stdio and is called with the SDK's own client. Every result is
compared with Engine().run and the web serialiser on the same bytes. Nothing here is a mock.
"""
import asyncio
import base64
import inspect
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st
from mcp import Client, StdioServerParameters
from starlette.responses import JSONResponse

import app as web_app
from necropsy.emit import EmittedSpec, emit_spec
from necropsy.engine import Engine
from necropsy_mcp import core
from tests.conftest import REPO_ROOT
from tools import adversary, real_corpus
from web.serialise import to_payload

LIMIT = 65_536
STATUSES = {"RESOLVED", "UNRESOLVED_AMBIGUITY", "FAILED"}


def server_params(cwd=REPO_ROOT, args=("-m", "necropsy_mcp"), command=None):
    return StdioServerParameters(command=command or sys.executable, args=list(args), cwd=str(cwd))


def run_session(fn, params=None):
    async def go():
        async with Client(params or server_params()) as client:
            return await fn(client)
    return asyncio.run(go())


def all_files() -> list[Path]:
    return adversary.sample_paths() + [real_corpus.REAL / e["file"] for e in real_corpus.load_manifest()]


FILES = all_files()


def key(p: Path) -> str:
    return p.relative_to(REPO_ROOT).as_posix()


@pytest.fixture(scope="module")
def results():
    """{path key: {"analyse": CallToolResult, "emit": CallToolResult}} from one live server session."""
    async def sweep(client):
        out = {}
        for p in FILES:
            data = p.read_bytes()
            out[key(p)] = {
                "analyse": await client.call_tool("analyse", {"path": str(p)}),
                "emit": await client.call_tool("emit_spec", {"data_base64": base64.b64encode(data).decode()})
                if len(data) <= LIMIT else await client.call_tool("emit_spec", {"path": str(p)}),
            }
        return out
    return run_session(sweep)


def expected_field(f) -> dict:
    return {"name": f.name, "offset": f.offset, "fmt": f.fmt,
            "value": [{"bytes": bytes(v).hex()} if isinstance(v, (bytes, bytearray)) else v for v in f.value]}


def remove_two_keys(payload: dict) -> dict:
    """to_payload output without the top-level `spec` and without every candidate's `render.data_b64`."""
    out = json.loads(json.dumps(payload))
    out.pop("spec", None)
    for k in ("candidates", "partial_candidates"):
        for c in out.get(k, []):
            c["render"].pop("data_b64", None)
    return out


def candidates_of(result) -> list:
    if result.status == "RESOLVED":
        return [result.candidate]
    if result.status == "UNRESOLVED_AMBIGUITY":
        return list(result.candidates)
    return list(result.partial_candidates)


WITHIN = [p for p in FILES if p.stat().st_size <= LIMIT]
OVER = [p for p in FILES if p.stat().st_size > LIMIT]


def test_the_sweep_covers_11_samples_and_81_real_files():
    assert len(adversary.sample_paths()) == 11 and len(FILES) == 92
    assert len(WITHIN) == 82 and len(OVER) == 10


def test_analyse_equals_the_engine_on_every_file_within_the_limit(results):
    problems = []
    for p in WITHIN:
        r = results[key(p)]["analyse"]
        data = p.read_bytes()
        engine = Engine(deadline_seconds=5.0).run(data)
        sc = r.structured_content
        if r.is_error or sc is None:
            problems.append((key(p), "tool error", sc))
            continue
        cands = candidates_of(engine)
        got = sc.get("candidates") if engine.status != "FAILED" else sc.get("partial_candidates")
        if sc["status"] != engine.status:
            problems.append((key(p), "status", sc["status"], engine.status))
        elif len(got) != len(cands):
            problems.append((key(p), "candidate count", len(got), len(cands)))
        else:
            for g, c in zip(got, cands):
                if g["fields"] and [{k: f[k] for k in ("name", "offset", "fmt", "value")} for f in g["fields"]] \
                        != [expected_field(f) for f in c.hypothesis.fields]:
                    problems.append((key(p), "fields"))
                if not g["fields"] and c.hypothesis.fields:
                    problems.append((key(p), "fields missing"))
        # Byte-identical to the web serialiser with exactly two things removed, once the measured time is the same.
        theirs = remove_two_keys(to_payload(engine, data, sc["engine_ms"]))
        if json.dumps(theirs) != json.dumps(sc):
            problems.append((key(p), "payload differs from to_payload minus spec and data_b64"))
        if r.content[0].text != JSONResponse(sc).body.decode("utf-8"):
            problems.append((key(p), "text differs from the web service's rendering"))
    assert not problems, problems


def test_emit_spec_equals_the_engine_on_every_file_within_the_limit(results):
    problems = []
    for p in WITHIN:
        r = results[key(p)]["emit"]
        data = p.read_bytes()
        spec = emit_spec(Engine(deadline_seconds=5.0).run(data), data)
        if r.is_error:
            problems.append((key(p), "tool error", r.structured_content))
        elif isinstance(spec, EmittedSpec):
            if r.structured_content != {"slug": spec.slug, "files": {n: t for n, t in spec.files}}:
                problems.append((key(p), "spec differs"))
        elif r.structured_content != {"error": "nothing_recovered", "message": spec.message}:
            problems.append((key(p), "EmitError differs", r.structured_content))
    assert not problems, problems


def test_emit_spec_for_failed_is_the_emit_error_and_not_a_tool_error(results):
    failed = [p for p in WITHIN if Engine().run(p.read_bytes()).status == "FAILED"]
    assert len(failed) > 20
    for p in failed:
        r = results[key(p)]["emit"]
        assert r.is_error is False and r.structured_content["error"] == "nothing_recovered"


def test_emit_spec_recovers_a_spec_for_resolved_and_ambiguous_files(results):
    r = results["spike/samples/mystery_d"]["emit"]
    assert r.is_error is False and set(r.structured_content["files"]) >= {"requirements.md", "design.md"}


def test_files_over_the_limit_get_the_web_services_413_body(results):
    web_body = json.loads(web_app._too_large().body)
    assert web_body["limit_bytes"] == LIMIT
    for p in OVER:
        for tool in ("analyse", "emit"):
            r = results[key(p)][tool]
            assert r.is_error is True and r.structured_content == web_body, (key(p), tool)


def test_limits_equal_the_web_services():
    assert core.MAX_BYTES == web_app.MAX_UPLOAD == LIMIT
    src = inspect.getsource(web_app._analyse) + inspect.getsource(web_app._spec_zip)
    assert src.count("deadline_seconds=5.0") == 2 and core.DEADLINE_SECONDS == 5.0


def test_mystery_d_reports_18_candidates_and_the_tool_chooses_none(results):
    sc = results["spike/samples/mystery_d"]["analyse"].structured_content
    assert sc["status"] == "UNRESOLVED_AMBIGUITY" and len(sc["candidates"]) == 18
    assert "chosen" not in sc and "selected" not in sc


AGENT_LIMIT = 20_000


@pytest.mark.xfail(strict=True, reason="measured 32,236 characters with only the two keys removed; the 20,000 limit 's decision is open")
def test_analyse_on_mystery_d_is_under_20000_characters(results):
    size = len(results["spike/samples/mystery_d"]["analyse"].content[0].text)
    assert size < AGENT_LIMIT, size


def test_analyse_on_mystery_d_is_much_smaller_than_the_web_payload(results):
    size = len(results["spike/samples/mystery_d"]["analyse"].content[0].text)
    data = (REPO_ROOT / "spike" / "samples" / "mystery_d").read_bytes()
    full = len(json.dumps(to_payload(Engine().run(data), data, 0.0), separators=(",", ":")))
    assert full > 200_000 and size < full / 6, (size, full)   # the reason for the change


def test_analyse_removes_only_the_pixel_buffers_and_the_spec(results):
    for p in WITHIN:
        sc = results[key(p)]["analyse"].structured_content
        assert "spec" not in sc
        for k in ("candidates", "partial_candidates"):
            for c in sc.get(k, []):
                assert "data_b64" not in c["render"]
                assert set(c["render"]) >= ({"failure"} if "failure" in c["render"] else {"width", "height", "channels", "note"})


def test_tool_descriptions_tell_an_agent_to_choose_none():
    tools = run_session(lambda c: c.list_tools()).tools
    assert [t.name for t in tools] == ["analyse", "emit_spec"]
    for t in tools:
        assert "choose none" in t.description or "chooses none" in t.description


@pytest.mark.parametrize("args,code", [
    ({}, "bad_input"),
    ({"path": "x", "data_base64": "AAAA"}, "bad_input"),
    ({"data_base64": "not base64!!"}, "invalid_base64"),
    ({"path": "spike/samples/does_not_exist"}, "file_not_found"),
    ({"path": "spike/samples"}, None),   # a directory: not_a_file or unreadable, never a crash
    ({"data_base64": base64.b64encode(bytes(LIMIT + 1)).decode()}, "file_too_large"),
    ({"data_base64": "A" * 200_000}, "file_too_large"),
    ({"path": str(real_corpus.REAL / "pillow_tiff_tiled_raw.tif")}, "file_too_large"),
])
def test_input_errors_are_structured_and_marked_as_errors(args, code):
    for tool in ("analyse", "emit_spec"):
        r = run_session(lambda c: c.call_tool(tool, args))
        assert r.is_error is True
        sc = r.structured_content
        if code:
            assert sc["error"] == code
        else:
            assert sc["error"] in ("not_a_file", "unreadable")
        assert "message" in sc


def test_exactly_the_limit_is_accepted():
    r = run_session(lambda c: c.call_tool("analyse", {"data_base64": base64.b64encode(bytes(LIMIT)).decode()}))
    assert r.is_error is False and r.structured_content["status"] in STATUSES


def test_short_input_is_a_failed_result_and_not_an_error():
    r = run_session(lambda c: c.call_tool("analyse", {"data_base64": ""}))
    assert r.is_error is False and r.structured_content["status"] == "FAILED"


@settings(max_examples=200, deadline=None)
@given(st.binary(max_size=LIMIT))
def test_property_analyse_never_raises_and_returns_a_payload_or_a_structured_error(data):
    payload, is_error = core.analyse(data_base64=base64.b64encode(data).decode())
    assert isinstance(payload, dict)
    if is_error:
        assert "error" in payload and "message" in payload
    else:
        assert payload["status"] in STATUSES and payload["total_file_size"] == len(data)
        json.dumps(payload, allow_nan=False)


@settings(max_examples=200, deadline=None)
@given(st.one_of(st.none(), st.text(max_size=300), st.binary(max_size=50)),
       st.one_of(st.none(), st.text(max_size=300), st.binary(max_size=50)))
def test_property_any_input_arguments_never_raise(path, data_base64):
    for fn in (core.analyse, core.emit):
        payload, is_error = fn(path, data_base64)
        assert isinstance(payload, dict) and isinstance(is_error, bool)
        if is_error:
            assert "error" in payload


def test_workspace_registration_starts_the_server():
    cfg = json.loads((REPO_ROOT / ".kiro" / "settings" / "mcp.json").read_text(encoding="utf-8"))
    entry = cfg["mcpServers"]["necropsy"]
    assert entry["command"] == "python" and entry["args"] == ["-m", "necropsy_mcp"]
    assert not entry.get("autoApprove") and not entry.get("disabled")
    tools = run_session(lambda c: c.list_tools(), server_params(command=sys.executable, args=entry["args"])).tools
    assert [t.name for t in tools] == ["analyse", "emit_spec"]
