"""Lead qualification: name, task, budget -> hot lead to the manager."""
import pytest

from app.core import leads as L

from conftest import MANAGER


@pytest.mark.parametrize("text,awaiting,name", [
    ("My name is anna", False, "Anna"),
    ("Ich heiße Jonas", False, "Jonas"),
    ("Меня зовут Олег", False, "Олег"),
    ("Anna Schmidt", True, "Anna Schmidt"),
    ("Anna", False, None),             # a bare word is a name only when we asked for it
    ("I am interested", False, None),
    ("How much is it?", True, None),
])
def test_extract_name(text, awaiting, name):
    assert L.extract_name(text, awaiting) == name


@pytest.mark.parametrize("text,awaiting,eur", [
    ("around 600 €", False, 600),
    ("€1.200", False, 1200),
    ("1,5k euro", False, 1000),
    ("до 500 евро", False, 500),
    ("maybe 400", True, 400),
    ("400", False, None),              # a bare number counts only as an answer to the budget question
    ("не знаю", True, "unknown"),
])
def test_extract_budget(text, awaiting, eur):
    r = L.extract_budget(text, awaiting)
    if eur is None:
        assert r is None
    elif eur == "unknown":
        assert r and r[1] is None
    else:
        assert r and r[1] == eur


def test_intent_detection():
    for t in ("I'd like to sign up", "Can I book the B1 course?", "Ich möchte mich anmelden", "Хочу записаться на курс"):
        assert L.has_intent(t), t
    for t in ("How much is the C1 course?", "Wann ist die Kursgebühr fällig?", "Сколько стоит курс?"):
        assert not L.has_intent(t), t


def test_hot_lead_flow_alerts_manager(chat):
    assert "What's your name" in chat.say("I'd like to sign up").text
    assert "Which course" in chat.say("Anna").text
    assert "budget" in chat.say("B1 evening course for work, from January").text
    out = chat.say("around 600 €")
    assert out.meta["kind"] == "lead_done" and "Anna" in out.text
    alerts = chat.alerts()
    assert len(alerts) == 1 and alerts[0].meta["kind"] == "alert_lead"
    assert "Hot lead" in alerts[0].text and "Budget: around 600 €" in alerts[0].text
    lead = chat.agent.db.leads()[0]
    assert (lead["name"], lead["budget_eur"], lead["status"]) == ("Anna", 600, "hot")


def test_intent_with_course_fills_task_immediately(chat):
    chat.say("I'd like to sign up for the B1 evening course")
    chat.say("My name is Tom")
    chat.say("700 euro")
    lead = chat.agent.db.leads()[0]
    assert lead["task"] == "B1 evening course" and lead["name"] == "Tom"


@pytest.mark.parametrize("text,task", [
    ("I'd like to sign up for the B1 evening course", "B1 evening course"),
    ("Ich möchte mich für den Intensivkurs B2 anmelden", "Intensivkurs B2"),
    ("Хочу записаться на вечерний курс B1", "Вечерний курс B1"),
    ("B1 for work, start in January", "B1 for work, start in January"),
])
def test_clean_task(text, task):
    assert L.clean_task(text) == task


def test_low_budget_is_warm_and_not_pushed(chat):
    chat.say("Хочу записаться")
    chat.say("Олег")
    chat.say("индивидуальные уроки английского")
    out = chat.say("100 евро")
    assert out.meta["kind"] == "lead_done" and "сохранил" in out.text
    assert chat.alerts() == []
    assert chat.agent.db.leads()[0]["status"] == "warm"


def test_question_during_qualification_is_answered_then_reasked(chat):
    chat.say("Ich möchte mich anmelden")
    chat.say("Lisa")
    out = chat.say("Gibt es den Abendkurs auch online?")
    assert "Zoom" in out.text and "Welchen Kurs" in out.text
    chat.say("B2 Abendkurs online")
    chat.say("500 €")
    assert chat.agent.db.leads()[0]["name"] == "Lisa"


def test_sign_up_button_starts_qualification(chat):
    chat.say("hi")
    assert "name" in chat.say(payload="lead:start").text
