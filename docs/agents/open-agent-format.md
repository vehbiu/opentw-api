# Open Agent Format in this repository

The agent instructions here follow the **Open Agent Format (OAF)**, v0.8.0 (January 2026),
<https://openagentformat.com/> (spec source: <https://github.com/jeffrschneider/OpenAgentFormat>,
CC0).

**If you are an AI agent, you may not know OAF.** It is recent. What matters:

- OAF describes an agent as **a directory whose manifest is `AGENTS.md`**. It builds on the
  AGENTS.md convention (<https://agents.md/>) and the AgentSkills.io skill format
  (<https://agentskills.io/>).
- `AGENTS.md` starts with **YAML frontmatter**, which is metadata:
  - identity: `name`, `vendorKey`, `agentKey`, `version` (semver), `slug` = `vendorKey/agentKey`
  - metadata: `description` (50-500 characters), `author`, `license` (SPDX), `tags`
  - optionally, composition such as `skills`

  **The instructions you follow are the Markdown body**, not the frontmatter.
- The body uses OAF's recommended headings:
  - Agent Purpose, Core Responsibilities, Capabilities
  - Behavioral Guidelines (Do / Don't), Tool Usage Patterns, Delegation Strategy
  - Limitations & Boundaries, Examples, Version History, Support
- **Local skills** are declared in the frontmatter with `source: "local"` and defined in
  `skills/<name>/SKILL.md`. Each has frontmatter with `name` (lowercase, hyphens, matching the
  directory), `description` (what it does and when to use it), and optionally `license` and
  `metadata`.

## How this maps onto each tool

No harness reads OAF natively yet, so the repository maps it onto what each tool does read.

| | Instructions | Skills |
| --- | --- | --- |
| Claude Code | `CLAUDE.md`, which imports `AGENTS.md` with `@AGENTS.md` (Claude Code reads `AGENTS.md` itself only as a fallback when there is no `CLAUDE.md`, from v2.1.277) | `.claude/skills/` |
| GitHub Copilot (VS Code, CLI) | `AGENTS.md`, `.github/copilot-instructions.md`, and `.github/instructions/*.instructions.md` for `applyTo` paths | `.claude/skills/` (also `.github/skills/`, `.agents/skills/`) |
| OpenCode | `AGENTS.md` | `.claude/skills/` (also `.opencode/skills/`, `.agents/skills/`) |

`.claude/skills/` is the one skills directory that all four read. So each skill has two files:

- `skills/<name>/SKILL.md`: the **canonical** skill, in the OAF location. Edit this one.
- `.claude/skills/<name>/SKILL.md`: a **discovery pointer** with the *same* `name` and
  `description`, whose body says to read the canonical file.

`tests/test_docs.py` fails if the two drift apart, if a skill is declared in `AGENTS.md` but
missing, or if the OAF frontmatter is invalid.

## Changing the agent definition

- Edit `AGENTS.md` only. `CLAUDE.md` and `.github/copilot-instructions.md` point to it. The
  scoped `.github/instructions/*.instructions.md` files are short Copilot-only reminders; keep
  them consistent with `AGENTS.md`.
- **Adding a skill:**
  1. Create `skills/<name>/SKILL.md`.
  2. Create the matching pointer in `.claude/skills/<name>/SKILL.md`.
  3. Declare it under `skills:` in the `AGENTS.md` frontmatter.
  4. Add it to the Operational Skills table.
- Bump `version` in the `AGENTS.md` frontmatter for meaningful changes to the instructions, and
  add a line to its Version History section. (OAF also allows keeping older copies in
  `versions/`; this repository does not.)
- OAF's optional `tests/` directory means agent test scenarios. In this repository `tests/` is
  the project's pytest suite. The two are unrelated.
