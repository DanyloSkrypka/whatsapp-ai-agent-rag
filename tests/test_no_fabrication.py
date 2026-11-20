"""Out-of-scope questions: honest hand-over, no invented answer. Same in Claude mode."""
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.core.db import DB
from app.main import build_agent

from conftest import MANAGER, Chat, make_settings


@pytest.mark.parametrize("q,lang,phrase", [
    ("Do you help with visa applications?", "en", "I'll pass your question to a manager"),
    ("Helfen Sie bei der Wohnungssuche?", "de", "Ich gebe Ihre Frage an eine Mitarbeiterin weiter"),
    ("Есть ли у вас общежитие?", "ru", "Передам ваш вопрос менеджеру"),
])
def test_out_of_scope_hands_over(chat, q, lang, phrase):
    out = chat.say(q)
    assert out.meta["kind"] == "handoff"
    assert phrase in out.text
    assert "📄" not in out.text and "€" not in out.text  # no source, no prices: nothing made up
    alerts = chat.alerts()
    assert len(alerts) == 1 and alerts[0].meta["kind"] == "alert_question"
    assert q in alerts[0].text
    assert chat.agent.db.handoffs()[0]["question"] == q


def test_answer_quotes_document_with_source(chat):
    out = chat.say("How much is the C1 course?")
    assert out.meta["kind"] == "ai"
    assert "€690" in out.text
    assert "📄 Source: prices_en.md" in out.text


def test_answer_in_users_language_uses_german_twin(chat):
    out = chat.say("Bis wann kann ich kostenlos stornieren?")
    assert "14 Tage" in out.text and "Quelle: terms_de.pdf · §3" in out.text


def test_russian_uses_russian_price_list(chat):
    out = chat.say("Сколько стоит курс C1?")
    assert "690 €" in out.text and "Источник: prices_ru.md" in out.text


def test_russian_question_on_pdf_terms(chat):
    out = chat.say("За сколько дней до начала курса можно отменить бесплатно?")
    assert "14 дней" in out.text and "terms_ru.pdf · §3" in out.text


def test_missing_translation_is_quoted_with_note(chat):
    from app.rag.index import Hit
    ans = chat.agent.answerer
    en_only = next(c for c in ans.by_key["price-c1"].values() if c.lang == "en")
    saved = ans.by_key["price-c1"]
    ans.by_key["price-c1"] = {"en": en_only}  # pretend the RU price list has no C1 line
    try:
        out = ans.answer("Сколько стоит C1?", "ru", [Hit(en_only, 0.99)])
    finally:
        ans.by_key["price-c1"] = saved
    assert "на английском" in out.text and "€690" in out.text


# ---------------- Claude mode (API mocked) ----------------
class FakeClaude:
    def __init__(self, reply="", stop="end_turn", fail=False):
        self.reply, self.stop, self.fail, self.calls = reply, stop, fail, []
        self.messages = self
        self.beta = SimpleNamespace(messages=self)

    def create(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise RuntimeError("network down")
        return SimpleNamespace(stop_reason=self.stop, content=[SimpleNamespace(type="text", text=self.reply)])


def claude_agent(tmp_path, index, fake):
    s = make_settings(tmp_path)
    return build_agent(s, DB(s.db_path), index=index, claude_client=fake)


def test_claude_no_answer_means_handoff(tmp_path, index):
    fake = FakeClaude("NO_ANSWER")
    c = Chat(claude_agent(tmp_path, index, fake))
    out = c.say("Can my employer pay for the course?")
    assert len(fake.calls) == 1          # the documents matched, so Claude was asked...
    assert out.meta["kind"] == "handoff"  # ...but it said the sources don't answer -> hand-over


def test_claude_not_called_below_threshold(tmp_path, index):
    fake = FakeClaude("Sure, we have yoga on Fridays!")  # would be a fabrication
    c = Chat(claude_agent(tmp_path, index, fake))
    out = c.say("Do you offer yoga classes?")
    assert out.meta["kind"] == "handoff" and fake.calls == []
    assert "yoga on Fridays" not in out.text


def test_claude_answer_uses_only_retrieved_sources(tmp_path, index):
    fake = FakeClaude("A private lesson costs €55.\n📄 Source: prices_en.md · Private lessons")
    c = Chat(claude_agent(tmp_path, index, fake))
    out = c.say("How much is a private lesson?")
    assert out.meta["kind"] == "ai" and out.meta["mode"] == "claude"
    system = fake.calls[0]["system"]
    assert "ONLY" in system and "NO_ANSWER" in system and "€55 per 45-minute lesson" in system
    assert fake.calls[0]["model"] == Settings().claude_model


def test_claude_refusal_is_handoff(tmp_path, index):
    c = Chat(claude_agent(tmp_path, index, FakeClaude("", stop="refusal")))
    assert c.say("How much is a private lesson?").meta["kind"] == "handoff"


def test_claude_error_falls_back_to_template(tmp_path, index):
    c = Chat(claude_agent(tmp_path, index, FakeClaude(fail=True)))
    out = c.say("How much is a private lesson?")
    assert out.meta["kind"] == "ai" and out.meta["mode"] == "template" and "€55" in out.text
