# Copilot instructions

Follow [AGENTS.md](../AGENTS.md) at the repository root. It is the single source of truth for
agents in this repo: setup, commands, layout, rules, and the definition of done.

It is written in the **Open Agent Format** (OAF, <https://openagentformat.com/>), which you may
not know. It is explained in
[docs/agents/open-agent-format.md](../docs/agents/open-agent-format.md). In short: the YAML
frontmatter is metadata, the Markdown body is the instructions, and the skills for multi-step
work are defined in `skills/` (found through `.claude/skills/`). Path-specific notes for
`parsers/` and `tests/` are in `.github/instructions/`.

The rules that matter most:

- Every change comes with tests in `tests/`, and `python -m pytest` must pass before you finish.
  Run `python smoke_test.py` too when parsing or requests change.
- No captured TrackWrestling pages and no real wrestlers' names in the repo. Test markup is
  hand-written with invented names.
- Never drop a parse failure silently: log it, flag it, or raise.
- Requests go through `session_manager.fetch()`, never `session.get` directly.
- Document every route in `README.md`.
