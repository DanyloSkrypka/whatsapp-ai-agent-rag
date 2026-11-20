"""FastAPI app: WhatsApp Cloud API webhook, local emulator API, health and history endpoints.

Run:  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8092
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .adapters.emulator import EmulatorAdapter
from .adapters.whatsapp import WhatsAppAdapter
from .config import ROOT, Settings
from .core.agent import Agent
from .core.db import DB
from .core.models import Incoming
from .rag.answer import ClaudeAnswerer, TemplateAnswerer
from .rag.index import make_index
from .rag.loader import load_kb

log = logging.getLogger("whatsapp-ai-agent")


def build_agent(settings: Settings, db: DB, index=None, claude_client=None) -> Agent:
    chunks = load_kb(settings.kb_dir)
    index = index or make_index(chunks, settings.retriever, settings.embed_model, settings.db_path,
                               settings.rerank_model)
    if settings.anthropic_api_key or claude_client is not None:
        answerer = ClaudeAnswerer(chunks, settings.anthropic_api_key, settings.claude_model, settings.company,
                                  client=claude_client)
    else:
        answerer = TemplateAnswerer(chunks)
    managers = list(settings.managers)
    if settings.demo_mode and "emulator:manager" not in managers:
        managers.append("emulator:manager")
    return Agent(db, index, answerer, {"en": settings.company, "de": settings.company_de or settings.company,
                                       "ru": settings.company}, managers, settings.min_score or None,
                 settings.hot_budget, settings.wa_alert_template)


def create_app(settings: Optional[Settings] = None, wa_client=None, index=None, claude_client=None) -> FastAPI:
    settings = settings or Settings()
    db = DB(settings.db_path)
    agent = build_agent(settings, db, index, claude_client)
    adapters = {
        "whatsapp": WhatsAppAdapter(settings.wa_token, settings.wa_phone_number_id, settings.wa_app_secret,
                                    settings.wa_api_version, client=wa_client),
        "emulator": EmulatorAdapter(),
    }

    async def deliver(user_key: str, outs) -> None:
        channel, _, uid = user_key.partition(":")
        ad = adapters.get(channel)
        if not ad:
            return
        row = db._x("SELECT last_in FROM clients WHERE user_key=?", (user_key,)).fetchone()
        last_in = row["last_in"] if row else None
        try:
            await ad.send(uid, outs, last_in)
        except Exception as e:  # never crash the webhook because one send failed
            log.warning("send to %s failed: %s", user_key, e)

    async def process(inc: Incoming) -> list:
        replies = agent.handle(inc)
        for key, out in replies:
            await deliver(key, [out])
        return replies

    app = FastAPI(title="WhatsApp AI agent (RAG)")
    app.state.agent = agent
    app.state.db = db
    app.state.adapters = adapters

    @app.get("/health")
    async def health():
        return {"ok": True, "retriever": agent.index.name, "answers": agent.answerer.mode,
                "chunks": len(agent.index.chunks), "threshold": agent.min_score}

    # ---------------- WhatsApp Cloud API ----------------
    @app.get("/webhook/whatsapp")
    async def wa_verify(request: Request):
        q = request.query_params
        if q.get("hub.mode") == "subscribe" and settings.wa_verify_token and \
                q.get("hub.verify_token") == settings.wa_verify_token:
            return PlainTextResponse(q.get("hub.challenge", ""))
        raise HTTPException(403, "verification failed")

    @app.post("/webhook/whatsapp")
    async def wa_webhook(request: Request):
        raw = await request.body()
        ad = adapters["whatsapp"]
        if not ad.verify_signature(raw, {k.lower(): v for k, v in request.headers.items()}):
            raise HTTPException(401, "bad signature")
        for inc in ad.parse(await request.json()):
            await process(inc)
        return {"ok": True}

    # ---------------- Emulator (local demo only) ----------------
    if settings.demo_mode:
        emu: EmulatorAdapter = adapters["emulator"]

        @app.get("/")
        async def root():
            return RedirectResponse("/demo/")

        @app.post("/api/emu/send")
        async def emu_send(request: Request):
            inc = emu.parse(await request.json())[0]
            await process(inc)
            return {"messages": emu.drain(inc.user_id)}

        @app.get("/api/emu/poll")
        async def emu_poll(user: str):
            return {"messages": emu.drain(user)}

        @app.get("/api/emu/state")
        async def emu_state():
            return {"leads": db.leads(), "handoffs": db.handoffs()}

        @app.get("/api/history/{client_id}")
        async def history(client_id: int):
            c = db.client_by_id(client_id)
            if not c:
                raise HTTPException(404, "no such client")
            return {"client": {k: c[k] for k in ("id", "user_key", "lang")}, "messages": db.history(client_id, 200)}

        app.mount("/demo", StaticFiles(directory=str(ROOT / "demo"), html=True), name="demo")

    return app


_app = None


def __getattr__(name: str):
    """`uvicorn app.main:app` builds the app on first access, so importing this module (tests) stays cheap."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
