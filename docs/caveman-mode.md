# Caveman Mode

Caveman mode is a built-in chat toggle that instructs the AI to respond in compressed, terse prose — cutting output tokens by ~65–75% while keeping full technical accuracy.

Inspired by the [caveman skill](https://github.com/JuliusBrussee/caveman).

## How to use

Click the **rock icon** (🪨) in the chat toolbar — it sits to the right of the Shell Access button. The icon highlights when active. Click again to turn it off.

The toggle persists per chat session and is saved across page reloads (same as the Web Search and Shell Access toggles).

## What it does

When active, a system prompt is prepended to every request instructing the model to:

- Drop articles (a/an/the), filler words, pleasantries, and hedging
- Use fragments — short synonyms, direct patterns
- Keep all technical terms exact
- Leave code blocks completely unchanged
- Quote error strings verbatim

**Pattern:** `[thing] [action] [reason]. [next step].`

| Normal | Caveman |
|---|---|
| "Sure! I'd be happy to help. The issue you're experiencing is likely caused by..." | "Bug in auth middleware. Token expiry check wrong. Fix:" |

## Implementation

The feature is built into the core chat pipeline — not a stored skill — so it's always available and can't be accidentally deleted.

| File | Change |
|---|---|
| `static/index.html` | Rock outline SVG button `#caveman-toggle-btn` + hidden checkbox `#caveman-toggle` |
| `static/app.js` | `setupToggle` wiring, toast label, splash description, collapsible/reset list |
| `static/js/chat.js` | Appends `caveman_mode=true` to the FormData payload when toggle is on |
| `routes/chat_routes.py` | Reads `caveman_mode` from form data, passes it to `build_chat_context` |
| `routes/chat_helpers.py` | Threads `caveman_mode` through to `build_context_preface` |
| `src/chat_processor.py` | Injects `CAVEMAN_SYSTEM_PROMPT` as a system message when `caveman_mode=True` |

## Caveat

Caveman mode is intentionally disabled for:
- Security warnings
- Irreversible action confirmations
- Any step where compression would create technical ambiguity

The model is instructed to resume caveman prose after the clear portion is done.
