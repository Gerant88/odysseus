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

#### Scratchpad
- New **Scratchpad** panel under Tools — type anything, AI triages and routes it to the right artifact
- Categories: note, idea, reminder, task, event, grocery list, project/feature/build
- Simple entries (note/task/event/grocery) are created immediately in the background
- Project entries generate a full proposal document (Summary, Architecture, Implementation Plan, Open Questions, Estimated Effort)
- Proposal cards show **Approve & Execute** (spawns a PM agent) and **Open Chat** (opens a new session with proposal as context)
- Notification dot on sidebar badge when a proposal is waiting for review
- Toggleable in Settings > Appearance
- Full backend: `POST/GET /api/scratchpad`, `/approve`, `/open-chat`, `/delete`
- Pipeline is async — panel polls at 2s intervals for status updates

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
