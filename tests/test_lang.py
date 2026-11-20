"""EN / DE / RU: detection, AI disclosure (EU AI Act art. 50), replies in the user's language."""
import pytest

from app.core.lang import detect

from conftest import Chat


@pytest.mark.parametrize("text,lang", [
    ("How much is the course?", "en"), ("Was kostet der Kurs?", "de"), ("Сколько стоит курс?", "ru"),
    ("Gibt es Rabatt für Studenten?", "de"), ("Is there parking?", "en"), ("Übernimmt das Jobcenter die Kosten?", "de"),
])
def test_detect(text, lang):
    assert detect(text) == lang


def test_short_message_keeps_previous_language():
    assert detect("Anna", "de") == "de" and detect("600 €", "ru") == "ru"


@pytest.mark.parametrize("text,phrase", [
    ("Hello", "I'm the AI assistant"), ("Hallo", "Ich bin der KI-Assistent der Nordlicht Sprachschule"),
    ("Привет", "Я ИИ-ассистент"),
])
def test_ai_disclosure_in_each_language(agent, text, phrase):
    out = Chat(agent, user="49" + str(abs(hash(text)) % 10**9)).say(text)
    assert phrase in out.text and out.meta.get("disclosure")


def test_non_text_message_gets_polite_reply(chat):
    assert "text messages only" in chat.say("").text
