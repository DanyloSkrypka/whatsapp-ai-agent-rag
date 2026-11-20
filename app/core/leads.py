"""Lead qualification: notice buying intent, then collect name, task and budget, then score the lead.

Rules, not an LLM: they are predictable, testable and free. Questions asked in the middle of the
qualification are still answered from the documents (the agent handles that), so the client never
feels stuck in a form.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

FIELDS = ("name", "task", "budget")

INTENT = re.compile(
    r"\b(sign(ing)? ?up|enrol+|register|book(ing)?|join|reserve|i want to (start|take|do)|i'?d like to (start|take|join|book))\b"
    r"|\b(anmelden|anmeldung|buchen|einschreiben|reservieren|teilnehmen möchte|ich möchte (den|einen|am) )"
    r"|(записат|запиши|хочу (на|пойти|начать|курс|запис)|оформ|забронир)",
    re.I)

COURSE_WORDS = re.compile(
    r"\b(a1|a2|b1|b2|c1|intensive?|intensiv\w*|evening|abend\w*|private|einzel\w*|telc|goethe|integration\w*|"
    r"business|english|englisch|german|deutsch|exam|prüfung)\b|интенсив|вечерн|индивидуал|экзамен|английск|немецк|интеграц",
    re.I)

_NAME_PATTERNS = [
    re.compile(r"\b(?:my name is|i am|i'm|this is|call me)\s+([A-Z][\w'-]{1,30})", re.I),
    re.compile(r"\b(?:ich heiße|ich heisse|mein name ist|ich bin)\s+([A-ZÄÖÜ][\w'-]{1,30})", re.I),
    re.compile(r"(?:меня зовут|моё имя|мое имя|я\s+—|это)\s+([А-ЯЁA-Z][\w'-]{1,30})", re.I),
]
_NOT_NAMES = set("""interested looking new here from a an the not just also very ready student
interessiert neu hier aus nicht student студент""".split())

_MONEY = re.compile(r"(?:€|eur\s*|euro\s*)\s*(\d[\d.,\s]{0,8}\d|\d)|(\d[\d.,\s]{0,8}\d|\d)\s*(?:€|eur\b|euro|евро|k\b|тыс)", re.I)
_NUMBER = re.compile(r"\d[\d.,\s]{0,8}\d|\d")
_NO_BUDGET = re.compile(r"\b(no idea|not sure|don't know|keine ahnung|weiß nicht|egal|flexible|flexibel)\b|не знаю|без разницы|любой", re.I)


def has_intent(text: str) -> bool:
    return bool(INTENT.search(text or ""))


def extract_name(text: str, awaiting: bool) -> Optional[str]:
    t = (text or "").strip()
    for p in _NAME_PATTERNS:
        m = p.search(t)
        if m and m.group(1).lower() not in _NOT_NAMES:
            return m.group(1).capitalize()
    if awaiting:
        # a bare reply like "Anna" or "Anna Schmidt" when we just asked for the name
        words = re.findall(r"[^\W\d_][\w'-]*", t)
        if 1 <= len(words) <= 3 and not _NUMBER.search(t) and "?" not in t:
            return " ".join(w.capitalize() for w in words[:2])
    return None


def _to_int(s: str) -> Optional[int]:
    s = s.replace(" ", "")
    s = re.sub(r"[.,](\d{3})\b", r"\1", s)        # 1.200 / 1,200 -> 1200
    s = s.split(",")[0].split(".")[0]
    return int(s) if s.isdigit() else None


def extract_budget(text: str, awaiting: bool) -> Optional[tuple[str, Optional[int]]]:
    """-> (raw text, euros) ; euros None means "client doesn't know"."""
    t = (text or "").strip()
    m = _MONEY.search(t)
    if m:
        v = _to_int(m.group(1) or m.group(2))
        if v is not None:
            if re.search(r"\d\s*(k\b|тыс)", t, re.I):
                v *= 1000
            return t[:60], v
    if awaiting:
        if _NO_BUDGET.search(t):
            return t[:60], None
        n = _NUMBER.search(t)
        if n:
            v = _to_int(n.group(0))
            if v is not None and v >= 20:
                return t[:60], v
    return None


_TASK_PREFIX = re.compile(
    r"^\s*(hi|hello|hallo)?[,!.\s]*(i'?d like to|i want to|i would like to|can i|could i)?\s*"
    r"(sign ?up|enrol+|register|book|join|reserve|start)\s*(for|in|on)?\s*(a|the)?\s+"
    r"|^\s*ich möchte (mich )?(für )?(den |einen |am )?"
    r"|^\s*(я )?хочу (записаться )?(на )?", re.I)


def clean_task(t: str) -> str:
    """'I'd like to sign up for the B1 evening course' -> 'B1 evening course'."""
    out = _TASK_PREFIX.sub("", t).strip(" .!")
    out = re.sub(r"\s+(anmelden|buchen)$", "", out, flags=re.I)
    return (out[:1].upper() + out[1:])[:140] if len(out) >= 2 else t[:140]


def extract_task(text: str, awaiting: bool) -> Optional[str]:
    t = (text or "").strip()
    if awaiting and len(t) >= 2 and "?" not in t:
        return clean_task(t)
    if COURSE_WORDS.search(t) and has_intent(t):
        return clean_task(t)
    return None


@dataclass
class LeadState:
    active: bool = False
    name: Optional[str] = None
    task: Optional[str] = None
    budget: Optional[str] = None
    budget_eur: Optional[int] = None
    awaiting: Optional[str] = None
    done: bool = False
    extra: dict = field(default_factory=dict)

    def missing(self) -> Optional[str]:
        for f in FIELDS:
            if getattr(self, f) is None:
                return f
        return None

    def absorb(self, text: str) -> bool:
        """Fill whatever fields this message contains. Returns True if anything new was learned."""
        learned = False
        if self.name is None:
            n = extract_name(text, self.awaiting == "name")
            if n:
                self.name, learned = n, True
        if self.budget is None:
            b = extract_budget(text, self.awaiting == "budget")
            if b:
                self.budget, self.budget_eur = b
                learned = True
        if self.task is None and not (learned and self.awaiting in ("name", "budget")):
            k = extract_task(text, self.awaiting == "task")
            if k:
                self.task, learned = k, True
        return learned


def score(state: LeadState, hot_budget: int) -> str:
    """hot = all three fields and a budget that covers a real course; warm = everything else."""
    if state.missing():
        return "cold"
    if state.budget_eur is not None and state.budget_eur >= hot_budget:
        return "hot"
    return "warm"
