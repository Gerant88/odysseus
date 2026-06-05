"""
routes/scratchpad_routes.py

Scratchpad — intelligent free-form inbox.

POST /api/scratchpad          submit text → async triage + artifact creation
GET  /api/scratchpad          list entries
GET  /api/scratchpad/{id}     get single entry (frontend polls for status)
POST /api/scratchpad/{id}/approve    approve project proposal → spawn PM agent
POST /api/scratchpad/{id}/open-chat  create pre-loaded session → return session_id
DELETE /api/scratchpad/{id}   delete entry
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.database import SessionLocal, ScratchpadEntry, Document, ScheduledTask
from src.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ScratchpadSubmit(BaseModel):
    text: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _owner(request: Request) -> str:
    return get_current_user(request) or "admin"


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _entry_dict(e: ScratchpadEntry) -> dict:
    return {
        "id": e.id,
        "raw_text": e.raw_text,
        "category": e.category,
        "triage_json": e.triage_json,
        "status": e.status,
        "error_msg": e.error_msg,
        "artifact_type": e.artifact_type,
        "artifact_id": e.artifact_id,
        "proposal_doc_id": e.proposal_doc_id,
        "spinoff_session_id": e.spinoff_session_id,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _update_entry(db, entry_id: str, **kwargs):
    e = db.query(ScratchpadEntry).filter(ScratchpadEntry.id == entry_id).first()
    if not e:
        return
    for k, v in kwargs.items():
        setattr(e, k, v)
    e.updated_at = _utcnow()
    db.commit()


def _resolve_llm(owner: str):
    """Return (url, model, headers) for the owner — same fallback as skills import."""
    from src.endpoint_resolver import resolve_endpoint
    from core.database import SessionLocal, Session as DBSession

    url, model, headers = resolve_endpoint("default", owner=owner)
    _non_gen = ("safety", "embedding", "moderation", "classify")
    if not model or any(h in (model or "").lower() for h in _non_gen):
        try:
            db = SessionLocal()
            sessions = (
                db.query(DBSession)
                .filter(DBSession.owner == owner)
                .order_by(DBSession.last_accessed.desc())
                .limit(5)
                .all()
            )
            db.close()
            for s in sessions:
                if s.model and not any(h in s.model.lower() for h in _non_gen):
                    model = s.model
                    break
        except Exception:
            pass
    return url, model, headers


def _parse_json_response(raw: str) -> Optional[dict]:
    """Strip fences and parse JSON; return None on failure."""
    raw = raw.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\n?```$", "", raw, flags=re.MULTILINE)
    # Some models wrap in <think>…</think> — strip
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # Find first { … } block
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        raw = m.group(0)
    try:
        return json.loads(raw)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Background pipeline
# ---------------------------------------------------------------------------

async def _run_pipeline(entry_id: str, text: str, owner: str, session_manager, task_scheduler):
    """Triage + artifact creation — runs as a background asyncio task."""
    from src.llm_core import llm_call_async
    from src.tool_implementations import do_manage_notes, do_manage_tasks, do_manage_calendar

    db = SessionLocal()
    try:
        # ── 1. Triage ────────────────────────────────────────────────────────
        ep_url, ep_model, ep_headers = _resolve_llm(owner)
        if not ep_url or not ep_model:
            _update_entry(db, entry_id, status="error",
                          error_msg="No model configured. Set a Default model in Settings.")
            return

        from datetime import datetime as _dt_now
        _today = _dt_now.now().strftime("%Y-%m-%d %H:%M")

        triage_system = (
            f"Today is {_today}.\n\n"
            "You are a triage assistant. Given free-form text, determine what kind of "
            "thing it is and extract structured data.\n\n"
            "Respond ONLY with a JSON object — no preamble, no markdown fences.\n\n"
            "JSON schema:\n"
            '{"category": "note|idea|reminder|task|event|grocery_list|project",\n'
            ' "title": "<60 chars — short descriptive title>",\n'
            ' "summary": "<one sentence>",\n'
            ' "extracted": {\n'
            '   "due": "<ISO-8601 datetime or null — use the current year unless user specifies otherwise>",\n'
            '   "items": ["list", "of", "items"] or null,\n'
            '   "description": "<fuller text or null>"\n'
            " }}\n\n"
            "Category rules:\n"
            "- note: general observation, journal entry, reference info\n"
            "- idea: creative or inventive thought\n"
            "- reminder: something to remember at a specific time\n"
            "- task: concrete to-do, actionable item without a specific calendar time\n"
            "- event: something with a specific date/time/location\n"
            "- grocery_list: a shopping list\n"
            "- project: implies building, designing, developing, implementing, or shipping "
            "a product, feature, system, or plan\n\n"
            "Be decisive. If ambiguous, prefer the simpler category (task over project)."
        )

        try:
            raw = await llm_call_async(
                ep_url, ep_model,
                [{"role": "system", "content": triage_system},
                 {"role": "user", "content": text}],
                max_tokens=512,
                headers=ep_headers,
            )
        except Exception as e:
            _update_entry(db, entry_id, status="error", error_msg=f"Triage LLM failed: {e}")
            return

        triage = _parse_json_response(raw)
        if not triage:
            _update_entry(db, entry_id, status="error",
                          error_msg="Could not parse triage response. Try again.")
            return

        category = triage.get("category", "note")
        title = triage.get("title") or text[:60]
        summary = triage.get("summary") or text[:200]
        extracted = triage.get("extracted") or {}
        due = extracted.get("due")
        items = extracted.get("items")
        description = extracted.get("description") or summary

        _update_entry(db, entry_id,
                      category=category,
                      triage_json=json.dumps(triage),
                      status="creating")

        # ── 2. Artifact routing ───────────────────────────────────────────────
        artifact_type = None
        artifact_id = None

        if category in ("note", "idea", "grocery_list"):
            args = {"action": "add", "title": title,
                    "content": description,
                    "note_type": "checklist" if items else "note"}
            if items:
                args["items"] = [{"text": i, "done": False} for i in items]
            try:
                result = await do_manage_notes(json.dumps(args), owner=owner)
                note_id = (result or {}).get("note", {}).get("id")
                artifact_type, artifact_id = "note", note_id
            except Exception as e:
                logger.warning(f"scratchpad: do_manage_notes failed: {e}")

        elif category in ("task", "reminder"):
            args = {"action": "create", "name": title,
                    "prompt": description,
                    "task_type": "llm",
                    "schedule": "once"}
            if due:
                args["scheduled_date"] = due
            try:
                result = await do_manage_tasks(json.dumps(args), owner=owner)
                task_id = (result or {}).get("task", {}).get("id")
                artifact_type, artifact_id = "task", task_id
            except Exception as e:
                logger.warning(f"scratchpad: do_manage_tasks failed: {e}")

        elif category == "event":
            args = {"action": "create_event", "summary": title,
                    "description": description}
            if due:
                args["dtstart"] = due
            try:
                result = await do_manage_calendar(json.dumps(args), owner=owner)
                if result and result.get("exit_code", 0) != 0:
                    logger.warning(f"scratchpad: do_manage_calendar returned error: {result.get('error')}")
                ev_id = (result or {}).get("event_id") or (result or {}).get("id")
                artifact_type, artifact_id = "event", ev_id
            except Exception as e:
                logger.warning(f"scratchpad: do_manage_calendar failed: {e}")

        elif category == "project":
            await _run_project_proposal(
                db, entry_id, title, summary, text, owner,
                ep_url, ep_model, ep_headers, session_manager, task_scheduler
            )
            return  # status managed inside

        # ── 3. Wrap up ────────────────────────────────────────────────────────
        _update_entry(db, entry_id,
                      status="done",
                      artifact_type=artifact_type,
                      artifact_id=artifact_id)

        if task_scheduler:
            task_scheduler.add_notification(
                f"Scratchpad: {title}", "completed",
                task_id=entry_id, owner=owner,
                body=f"Created {artifact_type or category}: {title}"
            )

    except Exception as e:
        logger.exception(f"scratchpad pipeline error for {entry_id}")
        _update_entry(db, entry_id, status="error", error_msg=str(e))
    finally:
        db.close()


async def _run_project_proposal(
    db, entry_id: str, title: str, summary: str, original_text: str,
    owner: str, ep_url: str, ep_model: str, ep_headers,
    session_manager, task_scheduler
):
    """Generate a proposal document for project-category entries."""
    from src.llm_core import llm_call_async

    proposal_system = (
        "You are a senior software architect. Given a project idea, produce a structured "
        "proposal document in Markdown.\n\n"
        "The document must include these sections:\n"
        "# {title}\n\n"
        "## Summary\n"
        "One paragraph describing the goal.\n\n"
        "## Architecture\n"
        "High-level system design: components, data flows, key technology choices.\n\n"
        "## Implementation Plan\n"
        "Numbered phases or milestones with concrete deliverables.\n\n"
        "## Open Questions / Research Needed\n"
        "Bullet list of unknowns to resolve before starting.\n\n"
        "## Estimated Effort\n"
        "T-shirt sizing (S/M/L/XL) with reasoning.\n\n"
        "Be specific. Avoid filler. Aim for 400-800 words. "
        "Output only the Markdown document — no preamble."
    )

    try:
        proposal_md = await llm_call_async(
            ep_url, ep_model,
            [{"role": "system", "content": proposal_system},
             {"role": "user", "content": f"Project idea:\n\n{original_text}"}],
            max_tokens=2000,
            headers=ep_headers,
        )
    except Exception as e:
        _update_entry(db, entry_id, status="error",
                      error_msg=f"Proposal generation failed: {e}")
        return

    # Strip accidental fences
    proposal_md = re.sub(r"^```[a-z]*\n?", "", proposal_md.strip(), flags=re.MULTILINE)
    proposal_md = re.sub(r"\n?```$", "", proposal_md.strip(), flags=re.MULTILINE)

    # Store as a Document
    now = _utcnow()
    doc = Document(
        id=str(uuid.uuid4()),
        owner=owner,
        title=f"Proposal: {title}",
        language="markdown",
        current_content=proposal_md,
        version_count=1,
        is_active=False,
        archived=False,
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    _update_entry(db, entry_id,
                  status="awaiting_approval",
                  artifact_type="document",
                  artifact_id=doc.id,
                  proposal_doc_id=doc.id)

    if task_scheduler:
        task_scheduler.add_notification(
            f"Scratchpad: {title}", "proposal_ready",
            task_id=entry_id, owner=owner,
            body=f"Project proposal ready for review: {title}"
        )


# ---------------------------------------------------------------------------
# Route factory
# ---------------------------------------------------------------------------

def setup_scratchpad_routes(session_manager, task_scheduler) -> APIRouter:
    router = APIRouter(tags=["scratchpad"])

    @router.post("/api/scratchpad")
    async def submit_scratchpad(request: Request, body: ScratchpadSubmit):
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        owner = _owner(request)
        entry_id = str(uuid.uuid4())
        now = _utcnow()
        db = SessionLocal()
        try:
            entry = ScratchpadEntry(
                id=entry_id, owner=owner, raw_text=text,
                status="triaging", created_at=now, updated_at=now,
            )
            db.add(entry)
            db.commit()
        finally:
            db.close()
        asyncio.create_task(
            _run_pipeline(entry_id, text, owner, session_manager, task_scheduler)
        )
        return {"id": entry_id, "status": "triaging",
                "created_at": now.isoformat()}

    @router.get("/api/scratchpad")
    async def list_scratchpad(request: Request, limit: int = 50, offset: int = 0):
        owner = _owner(request)
        db = SessionLocal()
        try:
            q = (db.query(ScratchpadEntry)
                   .filter(ScratchpadEntry.owner == owner)
                   .order_by(ScratchpadEntry.created_at.desc())
                   .offset(offset).limit(limit).all())
            total = (db.query(ScratchpadEntry)
                       .filter(ScratchpadEntry.owner == owner).count())
            return {"entries": [_entry_dict(e) for e in q], "total": total}
        finally:
            db.close()

    @router.get("/api/scratchpad/{entry_id}")
    async def get_scratchpad_entry(request: Request, entry_id: str):
        owner = _owner(request)
        db = SessionLocal()
        try:
            e = db.query(ScratchpadEntry).filter(
                ScratchpadEntry.id == entry_id,
                ScratchpadEntry.owner == owner,
            ).first()
            if not e:
                raise HTTPException(status_code=404, detail="Entry not found")
            return _entry_dict(e)
        finally:
            db.close()

    @router.post("/api/scratchpad/{entry_id}/approve")
    async def approve_proposal(request: Request, entry_id: str):
        owner = _owner(request)
        db = SessionLocal()
        try:
            entry = db.query(ScratchpadEntry).filter(
                ScratchpadEntry.id == entry_id,
                ScratchpadEntry.owner == owner,
            ).first()
            if not entry:
                raise HTTPException(status_code=404, detail="Entry not found")
            if not entry.proposal_doc_id:
                raise HTTPException(status_code=400, detail="No proposal document on this entry")

            doc = db.query(Document).filter(Document.id == entry.proposal_doc_id).first()
            proposal_md = doc.current_content if doc else ""
            title = doc.title if doc else "Project"

            triage = json.loads(entry.triage_json) if entry.triage_json else {}
            task_title = triage.get("title") or title

            now = _utcnow()
            pm_task = ScheduledTask(
                id=str(uuid.uuid4()),
                owner=owner,
                name=f"PM: {task_title}",
                task_type="llm",
                schedule="once",
                status="active",
                prompt=(
                    "You are a project manager executing an approved proposal. "
                    "Use all available tools to implement the plan step by step. "
                    "Break the work into subtasks, use manage_notes to track progress, "
                    "and create any files, code, or documents the plan requires.\n\n"
                    f"=== APPROVED PROPOSAL ===\n\n{proposal_md}"
                ),
                created_at=now,
                updated_at=now,
            )
            db.add(pm_task)
            entry.status = "approved"
            entry.updated_at = now
            db.commit()
        finally:
            db.close()

        # Trigger immediately
        try:
            await task_scheduler.run_task_now(pm_task.id)
        except Exception as e:
            logger.warning(f"scratchpad approve: run_task_now failed: {e}")

        return {"ok": True, "task_id": pm_task.id, "status": "spawned"}

    @router.post("/api/scratchpad/{entry_id}/open-chat")
    async def open_chat(request: Request, entry_id: str):
        owner = _owner(request)
        db = SessionLocal()
        try:
            entry = db.query(ScratchpadEntry).filter(
                ScratchpadEntry.id == entry_id,
                ScratchpadEntry.owner == owner,
            ).first()
            if not entry:
                raise HTTPException(status_code=404, detail="Entry not found")

            doc = None
            if entry.proposal_doc_id:
                doc = db.query(Document).filter(Document.id == entry.proposal_doc_id).first()

            proposal_md = doc.current_content if doc else entry.raw_text
            triage = json.loads(entry.triage_json) if entry.triage_json else {}
            title = triage.get("title") or "Scratchpad Project"
        finally:
            db.close()

        ep_url, ep_model, ep_headers = _resolve_llm(owner)
        if not ep_url or not ep_model:
            raise HTTPException(status_code=400,
                                detail="No model configured. Set a Default model in Settings.")

        new_sid = str(uuid.uuid4())
        sess = session_manager.create_session(
            session_id=new_sid,
            name=f"Project: {title}",
            endpoint_url=ep_url,
            model=ep_model,
            owner=owner,
        )
        from core.models import ChatMessage
        sess.add_message(ChatMessage(
            role="system",
            content=(
                "The following is an approved project proposal. Use it as context "
                "to answer the user's follow-up questions, suggest improvements, "
                "or continue planning.\n\n"
                f"=== PROPOSAL ===\n\n{proposal_md}"
            ),
            metadata={"scratchpad_entry_id": entry_id},
        ))
        session_manager.save_sessions()

        # Update entry with the spinoff session id
        db = SessionLocal()
        try:
            e = db.query(ScratchpadEntry).filter(ScratchpadEntry.id == entry_id).first()
            if e:
                e.spinoff_session_id = new_sid
                e.updated_at = _utcnow()
                db.commit()
        finally:
            db.close()

        return {"ok": True, "session_id": new_sid}

    @router.delete("/api/scratchpad/{entry_id}")
    async def delete_scratchpad_entry(request: Request, entry_id: str):
        owner = _owner(request)
        db = SessionLocal()
        try:
            e = db.query(ScratchpadEntry).filter(
                ScratchpadEntry.id == entry_id,
                ScratchpadEntry.owner == owner,
            ).first()
            if not e:
                raise HTTPException(status_code=404, detail="Entry not found")
            db.delete(e)
            db.commit()
        finally:
            db.close()
        return {"ok": True}

    return router
