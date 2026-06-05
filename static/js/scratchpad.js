/**
 * scratchpad.js — Intelligent free-form inbox.
 *
 * Exported API:
 *   openPanel()            open the side panel
 *   closePanel()           close it
 *   togglePanel()          open if closed, close if open
 *   hasPendingProposals()  true if any entry is awaiting_approval
 */

const API = window.location.origin;
let _open = false;
let _entries = [];
let _pollTimer = null;
let _pollingIds = new Set();

// ---------------------------------------------------------------------------
// Panel lifecycle
// ---------------------------------------------------------------------------

export function togglePanel() {
  _open ? closePanel() : openPanel();
}

export async function openPanel() {
  if (_open) return;
  _open = true;
  _buildPanel();
  document.getElementById('tool-scratchpad-btn')?.classList.add('active');
  await _loadEntries();
  _maybeStartPolling();
}

export function closePanel() {
  if (!_open) return;
  _open = false;
  _stopPolling();
  const backdrop = document.getElementById('scratchpad-pane-backdrop');
  if (backdrop) {
    const pane = document.getElementById('scratchpad-pane');
    if (pane) pane.classList.add('notes-pane-leaving');
    setTimeout(() => backdrop.remove(), 180);
  }
  document.getElementById('tool-scratchpad-btn')?.classList.remove('active');
}

export function hasPendingProposals() {
  return _entries.some(e => e.status === 'awaiting_approval');
}

// ---------------------------------------------------------------------------
// Panel HTML
// ---------------------------------------------------------------------------

function _buildPanel() {
  if (document.getElementById('scratchpad-pane')) return;

  // Pane — sized smaller than Notes since it's a quick-entry tool
  const pane = document.createElement('div');
  pane.id = 'scratchpad-pane';
  pane.className = 'notes-pane';
  pane.style.cssText = 'width:min(480px,92vw);height:auto;max-height:min(70vh,600px);';
  pane.innerHTML = `
    <div class="notes-mobile-grabber" aria-hidden="true"></div>
    <div class="notes-pane-header">
      <h4 class="notes-pane-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
          style="vertical-align:-2.5px;margin-right:6px;">
          <rect x="3" y="3" width="18" height="18" rx="2"/>
          <line x1="3" y1="9" x2="21" y2="9"/>
          <line x1="9" y1="21" x2="9" y2="9"/>
        </svg>Scratchpad
      </h4>
      <span style="flex:1"></span>
      <button id="scratchpad-minimize-btn" class="modal-minimize-btn" title="Close" aria-label="Close scratchpad">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="3.4" stroke-linecap="round" aria-hidden="true">
          <line x1="6" y1="18" x2="18" y2="18"/>
        </svg>
      </button>
    </div>

    <div style="padding:10px 14px 6px;">
      <textarea id="scratchpad-textarea"
        placeholder="Type anything — a note, idea, task, event, grocery list, or project idea… (Ctrl+Enter to send)"
        rows="3"
        style="width:100%;box-sizing:border-box;resize:vertical;font-size:0.88em;
               background:var(--input-bg,rgba(255,255,255,0.05));
               border:1px solid rgba(255,255,255,0.1);border-radius:6px;
               color:inherit;padding:8px 10px;outline:none;font-family:inherit;"></textarea>
      <div style="display:flex;justify-content:flex-end;margin-top:6px;">
        <button id="scratchpad-submit-btn" class="memory-toolbar-btn">Submit</button>
      </div>
    </div>

    <div id="scratchpad-entries-list" style="overflow-y:auto;max-height:320px;padding:4px 0 8px;"></div>
  `;

  // Backdrop — same pattern as Notes, centres the pane
  const backdrop = document.createElement('div');
  backdrop.className = 'notes-pane-backdrop';
  backdrop.id = 'scratchpad-pane-backdrop';
  backdrop.addEventListener('click', e => { if (e.target === backdrop) closePanel(); });
  backdrop.appendChild(pane);
  document.body.appendChild(backdrop);

  document.getElementById('scratchpad-minimize-btn').addEventListener('click', closePanel);
  document.getElementById('scratchpad-submit-btn').addEventListener('click', _onSubmit);
  document.getElementById('scratchpad-textarea').addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      _onSubmit();
    }
  });
}

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

async function _loadEntries() {
  try {
    const r = await fetch(`${API}/api/scratchpad?limit=50`, { credentials: 'same-origin' });
    if (!r.ok) return;
    const d = await r.json();
    _entries = d.entries || [];
    _renderEntries();
  } catch (e) {
    console.warn('scratchpad: load failed', e);
  }
}

async function _onSubmit() {
  const ta = document.getElementById('scratchpad-textarea');
  const btn = document.getElementById('scratchpad-submit-btn');
  const text = ta?.value.trim();
  if (!text) return;
  ta.value = '';
  ta.disabled = true;
  if (btn) btn.disabled = true;
  try {
    const r = await fetch(`${API}/api/scratchpad`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ text }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
    _entries.unshift(data);
    _renderEntries();
    _pollingIds.add(data.id);
    _maybeStartPolling();
  } catch (e) {
    console.warn('scratchpad submit error', e);
    if (window.uiModule?.showError) window.uiModule.showError('Submit failed: ' + e.message);
  } finally {
    if (ta) ta.disabled = false;
    if (btn) btn.disabled = false;
    ta?.focus();
  }
}

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------

function _maybeStartPolling() {
  const inFlight = _entries.filter(e => e.status === 'triaging' || e.status === 'creating');
  inFlight.forEach(e => _pollingIds.add(e.id));
  if (_pollingIds.size === 0 || _pollTimer) return;
  _pollTimer = setInterval(_pollInFlight, 2000);
}

function _stopPolling() {
  if (_pollTimer) clearInterval(_pollTimer);
  _pollTimer = null;
  _pollingIds.clear();
}

async function _pollInFlight() {
  if (_pollingIds.size === 0) {
    _stopPolling();
    return;
  }
  const done = new Set();
  await Promise.all([..._pollingIds].map(async id => {
    try {
      const r = await fetch(`${API}/api/scratchpad/${id}`, { credentials: 'same-origin' });
      if (!r.ok) { done.add(id); return; }
      const fresh = await r.json();
      const idx = _entries.findIndex(e => e.id === id);
      if (idx !== -1) _entries[idx] = fresh;
      else _entries.unshift(fresh);
      if (!['triaging', 'creating'].includes(fresh.status)) done.add(id);
    } catch (_) { done.add(id); }
  }));
  done.forEach(id => _pollingIds.delete(id));
  _renderEntries();
  _updateNotifDot();
  if (_pollingIds.size === 0) _stopPolling();
}

function _updateNotifDot() {
  const dot = document.getElementById('scratchpad-notif-dot');
  if (dot) dot.style.display = hasPendingProposals() ? '' : 'none';
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

const CATEGORY_LABELS = {
  note: '📝 Note', idea: '💡 Idea', reminder: '🔔 Reminder',
  task: '✅ Task', event: '📅 Event', grocery_list: '🛒 Grocery',
  project: '🚀 Project',
};

function _renderEntries() {
  const list = document.getElementById('scratchpad-entries-list');
  if (!list) return;
  if (_entries.length === 0) {
    list.innerHTML = `<div style="padding:20px 16px;opacity:0.4;font-size:0.85em;text-align:center;">
      No entries yet. Type something above.
    </div>`;
    return;
  }
  list.innerHTML = _entries.map(_cardHTML).join('');
  // Bind delete buttons
  list.querySelectorAll('[data-delete-id]').forEach(btn => {
    btn.addEventListener('click', () => _deleteEntry(btn.dataset.deleteId));
  });
  // Bind proposal actions
  list.querySelectorAll('[data-approve-id]').forEach(btn => {
    btn.addEventListener('click', () => _approveEntry(btn.dataset.approveId));
  });
  list.querySelectorAll('[data-openchat-id]').forEach(btn => {
    btn.addEventListener('click', () => _openChat(btn.dataset.openchatId));
  });
}

function _cardHTML(e) {
  const catLabel = CATEGORY_LABELS[e.category] || e.category || '…';
  const preview = (e.raw_text || '').slice(0, 120) + (e.raw_text?.length > 120 ? '…' : '');
  const ts = e.created_at ? new Date(e.created_at).toLocaleString([], { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' }) : '';

  let statusEl = '';
  if (e.status === 'triaging' || e.status === 'creating') {
    statusEl = `<span class="scratchpad-status-spinner" style="opacity:0.6;font-size:0.8em;">
      ⟳ ${e.status === 'triaging' ? 'Triaging…' : 'Creating…'}</span>`;
  } else if (e.status === 'done') {
    statusEl = `<span style="opacity:0.5;font-size:0.8em;">✓ ${catLabel}</span>`;
  } else if (e.status === 'awaiting_approval') {
    statusEl = `<span style="color:var(--accent,#e05c5c);font-size:0.8em;">● Proposal ready</span>`;
  } else if (e.status === 'approved') {
    statusEl = `<span style="opacity:0.5;font-size:0.8em;">✓ Approved — agent running</span>`;
  } else if (e.status === 'error') {
    statusEl = `<span style="color:#e05c5c;font-size:0.8em;" title="${e.error_msg || ''}">⚠ Error</span>`;
  } else {
    statusEl = `<span style="opacity:0.4;font-size:0.8em;">${e.status}</span>`;
  }

  const proposalCard = e.status === 'awaiting_approval' ? `
    <div style="margin-top:8px;padding:10px;background:rgba(224,92,92,0.08);
                border:1px solid rgba(224,92,92,0.25);border-radius:6px;">
      <div style="font-size:0.82em;opacity:0.8;margin-bottom:8px;">
        📄 Proposal generated — review and choose an action:
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <button data-approve-id="${e.id}"
          class="memory-toolbar-btn"
          style="font-size:0.82em;padding:4px 10px;">
          ✓ Approve &amp; Execute
        </button>
        <button data-openchat-id="${e.id}"
          class="memory-toolbar-btn"
          style="font-size:0.82em;padding:4px 10px;opacity:0.8;">
          💬 Open Chat
        </button>
      </div>
    </div>` : '';

  const spinnerAnim = e.status === 'triaging' || e.status === 'creating'
    ? `<style>@keyframes sp-spin{to{transform:rotate(360deg)}}.scratchpad-status-spinner{display:inline-block;animation:sp-spin 1.2s linear infinite;}</style>`
    : '';

  return `
    <div class="scratchpad-entry-card" style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.05);">
      ${spinnerAnim}
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
        <div style="flex:1;min-width:0;">
          <div style="font-size:0.82em;opacity:0.45;margin-bottom:3px;">${ts}</div>
          <div style="font-size:0.88em;line-height:1.4;word-break:break-word;">${_esc(preview)}</div>
          <div style="margin-top:5px;">${statusEl}</div>
          ${proposalCard}
        </div>
        <button data-delete-id="${e.id}" title="Delete"
          style="flex-shrink:0;background:none;border:none;cursor:pointer;opacity:0.3;
                 padding:2px 4px;color:inherit;" onmouseenter="this.style.opacity=0.8"
          onmouseleave="this.style.opacity=0.3">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/>
            <line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    </div>`;
}

function _esc(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function _deleteEntry(id) {
  try {
    await fetch(`${API}/api/scratchpad/${id}`, { method: 'DELETE', credentials: 'same-origin' });
    _entries = _entries.filter(e => e.id !== id);
    _pollingIds.delete(id);
    _renderEntries();
    _updateNotifDot();
  } catch (e) {
    console.warn('scratchpad delete failed', e);
  }
}

async function _approveEntry(id) {
  const btn = document.querySelector(`[data-approve-id="${id}"]`);
  if (btn) { btn.disabled = true; btn.textContent = 'Starting…'; }
  try {
    const r = await fetch(`${API}/api/scratchpad/${id}/approve`, {
      method: 'POST', credentials: 'same-origin',
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
    const idx = _entries.findIndex(e => e.id === id);
    if (idx !== -1) _entries[idx].status = 'approved';
    _renderEntries();
    _updateNotifDot();
    if (window.uiModule?.showToast) window.uiModule.showToast('Agent spawned — check Tasks for progress');
  } catch (e) {
    if (window.uiModule?.showError) window.uiModule.showError('Approve failed: ' + e.message);
    if (btn) { btn.disabled = false; btn.textContent = '✓ Approve & Execute'; }
  }
}

async function _openChat(id) {
  const btn = document.querySelector(`[data-openchat-id="${id}"]`);
  if (btn) { btn.disabled = true; btn.textContent = 'Opening…'; }
  try {
    const r = await fetch(`${API}/api/scratchpad/${id}/open-chat`, {
      method: 'POST', credentials: 'same-origin',
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
    closePanel();
    // Navigate to the new session — use the global loadSession if available
    if (window.loadSession) {
      window.loadSession(d.session_id);
    } else {
      // Fallback: reload with session hash
      window.location.hash = d.session_id;
      window.location.reload();
    }
  } catch (e) {
    if (window.uiModule?.showError) window.uiModule.showError('Open Chat failed: ' + e.message);
    if (btn) { btn.disabled = false; btn.textContent = '💬 Open Chat'; }
  }
}
