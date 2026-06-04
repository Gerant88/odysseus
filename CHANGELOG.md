# Changelog

All notable changes to this fork of [Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) are documented here.

---

## [Unreleased]

### Added

#### Caveman Mode
- New toggle button in the chat toolbar (boulder icon, beside Shell Access) that activates compressed AI responses
- When active, injects the [Caveman skill](https://github.com/JuliusBrussee/caveman) system prompt — cuts output tokens ~65–75% while preserving full technical accuracy
- Follows the same toggle pattern as Web Search and Shell Access (per-mode persistence, toast notification, first-use splash card)
- Full documentation in [`docs/caveman-mode.md`](docs/caveman-mode.md)

#### GitHub Skill Import
- New "Import from GitHub" input in Brain → Add → Add Skill panel
- Paste any GitHub repo URL to import skills automatically — no manual copy-paste needed
- Four-stage import strategy:
  1. Specific `skills/<name>` subfolder if the URL points to one
  2. Root `SKILL.md` at the repo level
  3. Discovers all `skills/<name>/SKILL.md` entries via GitHub API and imports them all in one shot (e.g. `obra/superpowers` → 14 skills)
  4. Falls back to fetching the README and asking the active LLM to synthesise a `SKILL.md` for repos with no skill files
- Handles YAML block scalars (`description: >` multiline) via PyYAML pre-processing
- Uses most-recently-used chat session model as fallback when the configured default is a non-generative model

---

## Fork base

Forked from [`pewdiepie-archdaemon/odysseus`](https://github.com/pewdiepie-archdaemon/odysseus) at commit `7ddc5ea`.
