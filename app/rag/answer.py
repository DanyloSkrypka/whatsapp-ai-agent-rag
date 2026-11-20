"""Turn retrieved chunks into a reply, or refuse and hand over.

Two answerers share one contract: `answer(question, lang, hits, history) -> Answer`.
* TemplateAnswerer (no API key): quotes the best chunk word for word, in the client's language when the
  document exists in it, and names the source. It cannot invent anything.
* ClaudeAnswerer (ANTHROPIC_API_KEY set): Claude phrases the reply in the client's language, using only
  the retrieved sources, and must answer NO_ANSWER when they don't cover the question.
The retrieval threshold runs first in both modes: a weak match never reaches the answerer.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from ..core.lang import t
from .index import Hit
from .loader import Chunk

log = logging.getLogger("rag")


@dataclass
class Answer:
    answered: bool
    text: str = ""
    sources: list[str] = field(default_factory=list)   # chunk ids actually used
    keys: list[str] = field(default_factory=list)      # language-independent keys (for eval)
    mode: str = "template"


def twins(chunks: list[Chunk]) -> dict[str, dict[str, Chunk]]:
    out: dict[str, dict[str, Chunk]] = {}
    for c in chunks:
        out.setdefault(c.key, {}).setdefault(c.lang, c)
    return out


class TemplateAnswerer:
    mode = "template"

    def __init__(self, chunks: list[Chunk]):
        self.by_key = twins(chunks)

    def pick(self, hit: Hit, lang: str) -> Chunk:
        versions = self.by_key.get(hit.chunk.key, {})
        return versions.get(lang) or versions.get("en") or hit.chunk

    def answer(self, question: str, lang: str, hits: list[Hit], history: Optional[list[dict]] = None) -> Answer:
        if not hits:
            return Answer(False, mode=self.mode)
        c = self.pick(hits[0], lang)
        body = c.text if c.lang == lang else f"{t('quote_other_lang', lang)}\n“{c.text}”"
        text = f"{body}\n\n📄 {t('source', lang)}: {c.source}"
        return Answer(True, text, [c.id], [c.key], self.mode)


SYSTEM = """You are the WhatsApp assistant of {company}. You answer customers' questions using ONLY the
numbered sources below, which come from the company's own documents.

Rules:
- Reply in {lang_name}, in 1-4 short sentences, friendly and plain. No markdown headings or tables.
- Use only facts that are written in the sources. Do not add prices, dates, services or promises that are not there.
- If the sources do not answer the question, reply with exactly NO_ANSWER and nothing else.
- End with one line: "📄 {source_word}: " followed by the file and section of the source(s) you used, e.g. "prices.md · Private lessons".

Sources:
{sources}"""

LANG_NAMES = {"en": "English", "de": "German", "ru": "Russian"}


class ClaudeAnswerer:
    mode = "claude"
    # models that accept the server-side refusal fallback
    FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-fable-5-2"}

    def __init__(self, chunks: list[Chunk], api_key: str, model: str, company: str, client=None):
        self.template = TemplateAnswerer(chunks)
        self.model = model
        self.company = company
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
        self.client = client

    def _prompt(self, lang: str, hits: list[Hit]) -> str:
        parts = []
        for i, h in enumerate(hits, 1):
            c = self.template.pick(h, lang)
            parts.append(f"[{i}] {c.source}\n{c.text}")
        return SYSTEM.format(company=self.company, lang_name=LANG_NAMES.get(lang, "English"),
                             source_word=t("source", lang), sources="\n\n".join(parts))

    def answer(self, question: str, lang: str, hits: list[Hit], history: Optional[list[dict]] = None) -> Answer:
        if not hits:
            return Answer(False, mode=self.mode)
        msgs = []
        for m in (history or [])[-6:]:
            role = "user" if m["role"] == "user" else "assistant"
            if msgs and msgs[-1]["role"] == role:
                msgs[-1]["content"] += "\n" + m["text"]
            else:
                msgs.append({"role": role, "content": m["text"]})
        if msgs and msgs[0]["role"] == "assistant":
            msgs.pop(0)
        if msgs and msgs[-1]["role"] == "user":
            msgs[-1]["content"] += "\n" + question
        else:
            msgs.append({"role": "user", "content": question})
        kwargs = dict(model=self.model, max_tokens=2048, system=self._prompt(lang, hits), messages=msgs,
                      output_config={"effort": "low"})
        try:
            if self.model in self.FALLBACK_MODELS:
                resp = self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                        fallbacks="default", **kwargs)
            else:
                resp = self.client.messages.create(**kwargs)
        except Exception as e:  # network, rate limit, bad key: never leave the client without a reply
            log.warning("Claude call failed (%s), using template answer", e)
            return self.template.answer(question, lang, hits, history)
        if getattr(resp, "stop_reason", None) == "refusal":
            return Answer(False, mode=self.mode)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if not text or re.fullmatch(r"\W*NO_ANSWER\W*", text) or text.startswith("NO_ANSWER"):
            return Answer(False, mode=self.mode)
        used = [h for h in hits if self.template.pick(h, lang).title in text] or hits[:1]
        return Answer(True, text, [self.template.pick(h, lang).id for h in used],
                      [h.chunk.key for h in used], self.mode)
