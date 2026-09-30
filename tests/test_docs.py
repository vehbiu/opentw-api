"""Keeps the documentation and the source honest."""
import re
import subprocess
from pathlib import Path

import pytest
import yaml

import server

ROOT = Path(__file__).resolve().parent.parent


def routes():
    """Every route server.py defines, written the way the README writes it: {name} per parameter.

    Only server.py's own: sanic-ext adds its /docs OpenAPI routes, which are not ours to document.
    """
    for route in server.app.router.routes:
        if getattr(route.handler, "__module__", None) != server.__name__:
            continue
        path = "/" + route.path.lstrip("/")
        if path != "/":
            yield re.sub(r"<(\w+)(?::\w+)?>", r"{\1}", path)


def test_routes_are_found():
    assert len(set(routes())) >= 7


@pytest.mark.parametrize("route", sorted(set(routes())))
def test_every_route_is_documented_in_the_readme(route):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # A documented route is the path, followed by the end of the line or a query string.
    assert re.search(re.escape(route) + r"(?:$|[?\[\s])", readme, re.M), (
        f"{route} is not documented in README.md"
    )


def source_files():
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py", "*.md", "*.yml", "*.ini", "*.txt"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.split()
    return tracked or [str(p.relative_to(ROOT)) for p in ROOT.rglob("*.py") if ".venv" not in p.parts]


# Everything below a space except tab, newline and carriage return.
CONTROL = re.compile("[" + "".join(chr(c) for c in range(32) if c not in (9, 10, 13)) + "]")


def test_no_control_characters_in_source():
    # A regex's \b once arrived in this repo as a literal backspace, and matched nothing.
    offenders = []
    for name in source_files():
        text = (ROOT / name).read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.split("\n"), 1):
            if CONTROL.search(line):
                offenders.append(f"{name}:{number}: {line.strip()!r}")
    assert not offenders, "control characters found:\n" + "\n".join(offenders)


AGENT_DOCS = [
    "AGENTS.md",
    ".github/copilot-instructions.md",
    "docs/agents/testing.md",
    "docs/agents/trackwrestling.md",
    "docs/agents/open-agent-format.md",
    "skills/add-endpoint/SKILL.md",
    "skills/fix-trackwrestling-change/SKILL.md",
]


@pytest.mark.parametrize("doc", AGENT_DOCS)
def test_agent_docs_link_to_files_that_exist(doc):
    text = (ROOT / doc).read_text(encoding="utf-8")
    base = (ROOT / doc).parent
    for target in re.findall(r"\]\(([^)#]+?)\)", text):
        if "://" not in target:
            assert (base / target).exists(), f"{doc} links to missing {target}"
    for path in re.findall(r"`((?:tests|parsers|utils|models|docs|skills)/[\w./-]+\.(?:py|md))`", text):
        assert (ROOT / path).exists(), f"{doc} mentions missing {path}"


# ─── Open Agent Format (https://openagentformat.com/) ────────────────────────
#
# AGENTS.md is an OAF v0.8.0 manifest. These keep it valid, and keep the .claude/skills/
# discovery pointers in step with the canonical skills/ they point to.

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, f"{path.relative_to(ROOT)} has no YAML frontmatter"
    return yaml.safe_load(match.group(1))


def test_agents_md_is_a_valid_oaf_manifest():
    meta = frontmatter(ROOT / "AGENTS.md")

    for field in ("name", "vendorKey", "agentKey", "version", "slug", "description", "author", "license", "tags"):
        assert meta.get(field), f"AGENTS.md frontmatter is missing required OAF field '{field}'"

    assert 1 <= len(meta["name"]) <= 100
    assert KEBAB.match(meta["vendorKey"]) and KEBAB.match(meta["agentKey"])
    assert meta["slug"] == f"{meta['vendorKey']}/{meta['agentKey']}"
    assert SEMVER.match(meta["version"])
    assert 50 <= len(meta["description"]) <= 500, f"description is {len(meta['description'])} characters"
    assert isinstance(meta["tags"], list) and meta["tags"]

    body = (ROOT / "AGENTS.md").read_text(encoding="utf-8").split("\n---\n", 1)[1]
    assert body.lstrip().startswith("#"), "OAF structured format: the body starts with a heading"


def declared_skills():
    return [s["name"] for s in frontmatter(ROOT / "AGENTS.md").get("skills", [])]


def test_every_skill_directory_is_declared():
    on_disk = sorted(p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md"))
    assert on_disk == sorted(declared_skills())


@pytest.mark.parametrize("name", declared_skills())
def test_skill_is_valid_and_its_discovery_pointer_matches(name):
    declared = next(s for s in frontmatter(ROOT / "AGENTS.md")["skills"] if s["name"] == name)
    assert declared["source"] == "local"
    assert SEMVER.match(declared["version"])

    canonical = ROOT / "skills" / name / "SKILL.md"
    pointer = ROOT / ".claude" / "skills" / name / "SKILL.md"
    assert canonical.exists(), f"skills/{name}/SKILL.md is missing"
    assert pointer.exists(), f".claude/skills/{name}/SKILL.md is missing (Claude Code, Copilot and OpenCode look there)"

    skill = frontmatter(canonical)
    # AgentSkills rules: lowercase with single hyphens, at most 64 characters, same as the directory.
    # Tools silently skip a skill that breaks them.
    assert skill["name"] == name and KEBAB.match(name) and len(name) <= 64
    assert skill.get("description")
    assert skill.get("metadata", {}).get("version") == declared["version"]

    shim = frontmatter(pointer)
    assert (shim["name"], shim["description"]) == (skill["name"], skill["description"])
    assert f"skills/{name}/SKILL.md" in pointer.read_text(encoding="utf-8")


def test_claude_md_imports_agents_md():
    assert "@AGENTS.md" in (ROOT / "CLAUDE.md").read_text(encoding="utf-8").split()
