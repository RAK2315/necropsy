"""The NECROPSY Power (necropsy-mcp spec, Requirement 6).

Checks the package against the Agent Plugins and Agent Skills formats Kiro documents, and that the
server starts from the Power's own mcp.json in a copy of the Power with the repository off the path.

Not covered, and not coverable from outside Kiro: Kiro's installer and Kiro calling the tool.
"""
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator
from mcp import Client, StdioServerParameters

from tests.conftest import REPO_ROOT
from tools import build_power

POWER = REPO_ROOT / "powers" / "necropsy"
SCHEMAS = REPO_ROOT / "tests" / "support" / "agent_plugins"   # copies of agent-plugins.org/schemas/1.0.0/*.json


def load(name):
    return json.loads((POWER / name).read_text(encoding="utf-8"))


def schema(name):
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def test_plugin_json_validates_against_the_agent_plugins_schema():
    manifest = load("plugin.json")
    Draft202012Validator(schema("plugin.schema.json")).validate(manifest)
    assert manifest["name"] == "necropsy" and manifest["author"]["name"] and manifest["description"]
    assert manifest["keywords"], "keywords trigger activation"


def test_mcp_json_validates_against_the_agent_plugins_schema():
    cfg = load("mcp.json")
    Draft202012Validator(schema("mcp.schema.json")).validate(cfg)
    entry = cfg["mcpServers"]["necropsy"]
    assert entry["type"] == "stdio" and entry["command"] == "python"
    assert entry["args"] == ["-m", "necropsy_mcp"] and entry["cwd"] == "${PLUGIN_ROOT}"


def test_the_schemas_reject_a_bad_manifest_and_a_bad_mcp_config():
    # Teeth: the validators are not accepting everything.
    with pytest.raises(Exception):
        Draft202012Validator(schema("plugin.schema.json")).validate({"name": "Bad Name"})
    with pytest.raises(Exception):
        Draft202012Validator(schema("mcp.schema.json")).validate(
            {"$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
             "mcpServers": {"x": {"type": "stdio", "command": "python", "cwd": "../escape"}}})


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text.replace("\r\n", "\n"), re.S)
    assert m, "SKILL.md must start with YAML frontmatter"
    fields = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        fields[k.strip()] = v.strip()
    return fields


def test_skill_satisfies_the_agent_skills_frontmatter_rules():
    skills = sorted((POWER / "skills").iterdir())
    assert [s.name for s in skills] == ["unknown-file"]
    text = (skills[0] / "SKILL.md").read_text(encoding="utf-8")
    fm = frontmatter(text)
    assert set(fm) == {"name", "description"}
    assert fm["name"] == skills[0].name
    assert len(fm["name"]) <= 64 and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fm["name"])
    assert 0 < len(fm["description"]) <= 1024
    assert len(text.splitlines()) < 500


def test_skill_tells_an_agent_to_call_analyse_first_report_every_candidate_and_pick_none():
    body = (POWER / "skills" / "unknown-file" / "SKILL.md").read_text(encoding="utf-8")
    for needle in ("Call `analyse` first", "**every** candidate", "Do not pick one", "UNRESOLVED_AMBIGUITY",
                   "FAILED", "Stop.", "Never choose between candidates"):
        assert needle in body, needle


def test_the_bundle_matches_the_source():
    assert build_power.differences() == []


def test_the_bundle_check_catches_a_changed_file(tmp_path, monkeypatch):
    copy = tmp_path / "necropsy"
    shutil.copytree(POWER, copy)
    (copy / "necropsy_mcp" / "core.py").write_text("tampered\n", encoding="utf-8")
    monkeypatch.setattr(build_power, "POWER", copy)
    assert "differs necropsy_mcp/core.py" in build_power.differences()


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    """The Power copied elsewhere, as an install does."""
    dest = tmp_path_factory.mktemp("installed") / "necropsy"
    shutil.copytree(POWER, dest, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


def launch_params(root):
    entry = load("mcp.json")["mcpServers"]["necropsy"]
    command = shutil.which(entry["command"]) or sys.executable
    cwd = entry["cwd"].replace("${PLUGIN_ROOT}", str(root))
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PLUGIN_ROOT"] = str(root)
    return StdioServerParameters(command=command, args=entry["args"], cwd=cwd, env=env)


def test_the_installed_copy_imports_its_own_code_and_not_the_repository(installed):
    entry = load("mcp.json")["mcpServers"]["necropsy"]
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    out = subprocess.run(
        [shutil.which(entry["command"]) or sys.executable, "-c",
         "import necropsy, necropsy_mcp, web.serialise as w; print(necropsy.__file__); print(necropsy_mcp.__file__); print(w.__file__)"],
        cwd=str(installed), env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    for line in out.stdout.split():
        assert os.path.commonpath([os.path.realpath(line), str(installed.resolve())]) == str(installed.resolve()), line


def test_the_tool_is_callable_from_the_powers_own_mcp_json(installed):
    async def go():
        async with Client(launch_params(installed)) as c:
            tools = await c.list_tools()
            r = await c.call_tool("analyse", {"path": str(REPO_ROOT / "spike" / "samples" / "mystery_d")})
            return [t.name for t in tools.tools], r
    names, r = asyncio.run(go())
    assert names == ["analyse", "emit_spec"]
    assert r.is_error is False
    sc = r.structured_content
    assert sc["status"] == "UNRESOLVED_AMBIGUITY" and len(sc["candidates"]) == 18
