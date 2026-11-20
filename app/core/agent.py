"""The conversation brain: messenger-agnostic, no network calls except the optional Claude answerer.

handle(Incoming) -> list of (user_key, Out). One incoming message can produce replies to the client
and alerts to managers (hot lead, unanswered question).
"""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Optional

from ..rag.answer import Answer
from ..rag.index import BaseIndex, Hit
from . import leads as L
from .db import DB, now_iso
from .lang import detect, t
from .models import Button, Incoming, Out, Template

GREETING = re.compile(r"^\W*(hi|hello|hey|good (morning|afternoon|evening)|hallo|moin|servus|guten (tag|morgen|abend)|"
                      r"привет|здравствуйте|добрый (день|вечер)|доброе утро)\W*$", re.I)
THANKS = re.compile(r"^\W*(thanks?( you)?|thx|danke( schön| sehr)?|vielen dank|спасибо|благодарю)\W*$", re.I)
QUESTION = re.compile(r"\?|^\s*(how|what|when|where|which|who|why|is|are|do|does|can|could|wie|was|wann|wo|welche|"
                      r"gibt|kann|ist|sind|haben|как|что|когда|где|сколько|можно|есть|какой|какая|какие)\b", re.I)

FOLLOW_UP = re.compile(r"^\s*(and|also|what about|how about|und|auch|was ist mit|а|и|а если|а как|ещё)\b.{0,30}$", re.I)

BUTTONS = {
    "en": [("q:start", "📅 Start dates"), ("q:test", "🧪 Level test"), ("lead:start", "✍️ Sign up")],
    "de": [("q:start", "📅 Kurstermine"), ("q:test", "🧪 Einstufungstest"), ("lead:start", "✍️ Anmelden")],
    "ru": [("q:start", "📅 Даты старта"), ("q:test", "🧪 Тест уровня"), ("lead:start", "✍️ Записаться")],
}
CANNED = {
    "q:start": {"en": "When do new courses start?", "de": "Wann beginnen neue Kurse?", "ru": "Когда начинаются новые курсы?"},
    "q:test": {"en": "How do I find out my level?", "de": "Wie finde ich mein Niveau heraus?", "ru": "Как узнать мой уровень?"},
}


class Agent:
    def __init__(self, db: DB, index: BaseIndex, answerer, company, managers: list[str],
                 min_score: Optional[float] = None, hot_budget: int = 250, alert_template: str = "manager_alert"):
        self.db = db
        self.index = index
        self.answerer = answerer
        # company name per language: {"en": "...", "de": "..."} or one string for all
        self.company = company if isinstance(company, dict) else {"en": company}
        self.managers = list(managers)
        self.min_score = min_score or index.default_min_score
        self.hot_budget = hot_budget
        self.alert_template = alert_template

    # ------------------------------------------------------------------ entry
    def handle(self, inc: Incoming) -> list[tuple[str, Out]]:
        if inc.user_key in self.managers:
            return self._manager(inc)
        c = self.db.client(inc.user_key, inc.name)
        st = c["state"]
        text = (inc.text or "").strip()
        if inc.payload in CANNED:
            text = CANNED[inc.payload].get(c.get("lang") or "en")
        elif inc.payload == "lead:start":
            text = {"de": "Ich möchte mich anmelden", "ru": "Хочу записаться"}.get(c.get("lang"), "I'd like to sign up")
        lang = detect(text, c.get("lang"))
        c["lang"], c["last_in"] = lang, now_iso()
        self.db.add_message(c["id"], "user", text, {"payload": inc.payload} if inc.payload else None)

        out: list[tuple[str, Out]] = []
        if not text:  # image, voice note, sticker...
            reply = Out({"en": "I can read text messages only. Please type your question.",
                         "de": "Ich kann nur Textnachrichten lesen. Bitte schreiben Sie Ihre Frage.",
                         "ru": "Я понимаю только текст. Пожалуйста, напишите вопрос."}[lang], meta={"kind": "system"})
        elif GREETING.match(text):
            reply = Out(t("how_help", lang), [Button(i, ttl) for i, ttl in BUTTONS[lang]], meta={"kind": "system"})
        elif THANKS.match(text):
            reply = Out(t("thanks", lang), meta={"kind": "system"})
        else:
            reply, extra = self._converse(c, text, lang)
            out += extra
        if not st.get("disclosed"):  # EU AI Act art. 50: say it's an AI in the first reply
            reply.text = f"{t('disclosure', lang, company=self.company.get(lang) or self.company['en'])}\n\n{reply.text}"
            reply.meta["disclosure"] = True
            st["disclosed"] = True
        self.db.add_message(c["id"], "bot", reply.text, {k: v for k, v in reply.meta.items() if k != "hits"})
        self.db.save_client(c)
        return [(inc.user_key, reply)] + out

    # ------------------------------------------------------------------ client side
    def _converse(self, c: dict, text: str, lang: str) -> tuple[Out, list]:
        st = c["state"]
        ls = L.LeadState(**st.get("lead", {}))
        alerts: list = []
        if not ls.active and not ls.done and L.has_intent(text):
            ls.active = True
        if ls.active:
            learned = ls.absorb(text)
            is_q = bool(QUESTION.search(text)) and not learned
            answer_out = None
            if is_q or (L.has_intent(text) and "?" in text):
                answer_out, alerts = self._rag(c, text, lang, quiet_handoff=False)
            nxt = ls.missing()
            if nxt:
                ls.awaiting = nxt
                ask = t(f"ask_{nxt}", lang, name=ls.name or "")
                st["lead"] = asdict(ls)
                if answer_out:
                    answer_out.text += "\n\n" + ask
                    return answer_out, alerts
                return Out(ask, meta={"kind": "lead", "lead": asdict(ls)}), alerts
            # all three fields known -> score and pass on
            status = L.score(ls, self.hot_budget)
            lead_id = self.db.add_lead(c["id"], ls.name, ls.task, ls.budget, ls.budget_eur, status, lang)
            ls.active, ls.done, ls.awaiting = False, True, None
            st["lead"] = asdict(ls)
            lead = {"id": lead_id, "client": c["id"], "name": ls.name, "task": ls.task, "budget": ls.budget,
                    "status": status, "lang": lang}
            if status == "hot":
                alerts += self._alert(c, self._lead_text(lead), f"Hot lead #{c['id']}: {ls.name}, budget {ls.budget}",
                                      {"kind": "alert_lead", "lead": lead})
            reply = Out(t("lead_done" if status == "hot" else "lead_saved", lang, name=ls.name),
                        meta={"kind": "lead_done", "lead": lead})
            if answer_out:
                reply.text = answer_out.text + "\n\n" + reply.text
            return reply, alerts
        reply, alerts = self._rag(c, text, lang)
        return reply, alerts

    def _search(self, c: dict, text: str) -> list[Hit]:
        hits = self.index.search(text, lang=c.get("lang"))
        # explicit follow-up ("and online?", "und am Abend?", "а онлайн?") -> also try with the previous question.
        # Only fragments: a full new question must never inherit the previous topic.
        if FOLLOW_UP.match(text) or len(text.split()) <= 2:
            prev = [m["text"] for m in self.db.history(c["id"], 6) if m["role"] == "user"][:-1]
            if prev:
                alt = self.index.search(prev[-1] + " " + text, lang=c.get("lang"))
                if alt and hits and alt[0].score > hits[0].score + 0.02:
                    hits = alt
        return hits

    def _rag(self, c: dict, text: str, lang: str, quiet_handoff: bool = False) -> tuple[Out, list]:
        hits = self._search(c, text)
        top = hits[0].score if hits else 0.0
        hit_meta = [{"source": h.chunk.source, "key": h.chunk.key, "score": round(h.score, 3)} for h in hits[:3]]
        ans = Answer(False)
        if hits and top >= self.min_score:
            ans = self.answerer.answer(text, lang, [h for h in hits if h.score >= self.min_score - 0.04][:4],
                                       self.db.history(c["id"], 8)[:-1])
        if ans.answered:
            return Out(ans.text, meta={"kind": "ai", "sources": ans.sources, "keys": ans.keys, "mode": ans.mode,
                                       "hits": hit_meta, "threshold": self.min_score}), []
        # honest hand-over: no guessing
        hid = self.db.add_handoff(c["id"], text, top)
        alerts = self._alert(c, self._handoff_text(c, text, lang), f"Question from client #{c['id']} needs an answer",
                             {"kind": "alert_question", "client": c["id"], "question": text, "handoff": hid})
        return Out(t("handoff", lang), meta={"kind": "handoff", "hits": hit_meta, "threshold": self.min_score,
                                             "best_score": round(top, 3)}), alerts

    # ------------------------------------------------------------------ manager side
    def _alert(self, c: dict, text: str, one_line: str, meta: dict) -> list[tuple[str, Out]]:
        tpl = Template(self.alert_template, "en", [one_line])  # used only if the manager's 24 h window is closed
        return [(m, Out(text, template=tpl, meta=dict(meta))) for m in self.managers]

    def _who(self, c: dict) -> str:
        ch, _, uid = c["user_key"].partition(":")
        parts = [c.get("profile_name") or ""] + ([f"+{uid}"] if ch == "whatsapp" else [])
        return " · ".join(p for p in parts if p) or uid

    def _tail(self, cid: int, n: int = 4) -> str:
        """Last n messages before the current question, without the AI-disclosure greeting."""
        rows = self.db.history(cid, n + 1)[:-1] if n else []
        icon = {"user": "👤", "bot": "🤖", "manager": "🧑‍💼"}
        out = []
        for m in rows:
            text = m["text"]
            if m["meta"].get("disclosure") and "\n\n" in text:
                text = text.split("\n\n", 1)[1]
            text = text.split("\n\n📄")[0].replace("\n", " ")
            out.append(f"{icon[m['role']]} {text[:80]}{'…' if len(text) > 80 else ''}")
        return "\n".join(out)

    def _lead_text(self, lead: dict) -> str:
        return (f"🔥 Hot lead · client #{lead['client']}\n"
                f"Name: {lead['name']}\nTask: {lead['task']}\nBudget: {lead['budget']}\n"
                f"Language: {lead['lang'].upper()}\n\nReply to the client: #{lead['client']} your text")

    def _handoff_text(self, c: dict, question: str, lang: str) -> str:
        tail = self._tail(c["id"], 2)
        return (f"❓ No answer in the documents · client #{c['id']} ({lang.upper()}, {self._who(c)})\n"
                f"“{question}”\n" + (f"\nEarlier:\n{tail}\n" if tail else "") +
                f"\nReply to the client: #{c['id']} your text")

    def _manager(self, inc: Incoming) -> list[tuple[str, Out]]:
        text = (inc.text or "").strip()
        me = inc.user_key
        m = re.match(r"^#(\d+)\s+(.+)$", text, re.S)
        if m:
            c = self.db.client_by_id(int(m.group(1)))
            if not c:
                return [(me, Out(f"No client #{m.group(1)}.", meta={"kind": "system"}))]
            body = m.group(2).strip()
            lang = c.get("lang") or "en"
            self.db.add_message(c["id"], "manager", body)
            return [(c["user_key"], Out(f"🧑‍💼 {t('manager_prefix', lang)}: {body}", meta={"kind": "manager"})),
                    (me, Out(f"✓ Sent to client #{c['id']}", meta={"kind": "system"}))]
        m = re.match(r"^/history\s+#?(\d+)$", text)
        if m:
            c = self.db.client_by_id(int(m.group(1)))
            if not c:
                return [(me, Out(f"No client #{m.group(1)}.", meta={"kind": "system"}))]
            rows = self.db.history(c["id"], 12)
            icon = {"user": "👤", "bot": "🤖", "manager": "🧑‍💼"}
            body = "\n".join(f"{icon[r['role']]} {r['text'][:120]}" for r in rows) or "(empty)"
            return [(me, Out(f"History of client #{c['id']}:\n{body}", meta={"kind": "system"}))]
        if text == "/leads":
            rows = self.db.leads()
            body = "\n".join(f"#{r['client_id']} {r['status'].upper()} · {r['name']} · {r['task'][:40]} · {r['budget']}"
                             for r in rows[-10:]) or "No leads yet."
            return [(me, Out(body, meta={"kind": "system"}))]
        return [(me, Out("Manager commands:\n#<client> <text>: reply to a client\n/history <client>\n/leads",
                         meta={"kind": "system"}))]
