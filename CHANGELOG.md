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
- New **Scratchpad** quick-entry panel — accessible via pencil icon directly below **New Chat** in the sidebar
- Type anything freely; AI triages and routes it to the right artifact automatically
- Categories: `note`, `idea`, `reminder`, `task`, `event`, `grocery_list`, `project`
- Simple entries (note/task/event/grocery) are created immediately in the appropriate section (Notes, Tasks, Calendar)
- Project entries trigger a full proposal document including: Summary, Market Research, Competitors & Alternatives, Architecture, Implementation Plan, Open Questions, and an **Honest Recommendation** (Go/Pause/Stop verdict)
- Proposal is saved to **Library → Documents** and can be opened directly in the document editor via **View Proposal**
- Notification dot on the Scratchpad sidebar icon when a proposal is waiting for review
- Toggleable in Settings > Appearance
- Auto-delete fuse: processed entries show a red line that fills toward a trash icon over 60 seconds, then auto-removes only the scratchpad record (the created artifact is unaffected)
- Pipeline is async with real-time status updates (wave spinner matches the app's loading style)
- Retry logic: up to 2 automatic retries on transient API errors, with counter shown in the spinner label

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

### Fixed

#### Scratchpad — Pipeline Reliability
- Triage LLM prompt now includes today's date so relative dates like "June 7 at 10am" or "this Sunday" resolve to the correct year
- Replaced greedy regex JSON parser with a brace-depth scanner — handles reasoning models that append commentary after the closing `}` without breaking parse
- Spinner stays visible across poll re-renders (was disappearing on each 2s poll cycle due to detached DOM elements)
- Error state shows `⚠ Could not identify — <reason>` instead of generic `⚠ Error`

#### Scratchpad — UI
- Window centred on screen and sized compactly (480px) matching Notes/Calendar modal style
- Close button is a proper × using the app's `modal-minimize-btn` class
- Submit button centred below textarea; Ctrl+Enter hint moved below Submit in small faded text
- Window draggable by header (uses shared `makeWindowDraggable` from `windowDrag.js`)
- Pencil icon in both sidebar entry and popup header, coloured with `var(--accent)` to match the New Chat icon across all themes
- Scratchpad moved to top of sidebar, directly below New Chat, for faster access

---

## Fork base

Forked from [`pewdiepie-archdaemon/odysseus`](https://github.com/pewdiepie-archdaemon/odysseus) at commit `7ddc5ea`.
