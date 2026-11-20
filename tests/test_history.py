"""Dialog history: every turn is stored, the manager sees it, follow-ups use it."""
from conftest import MANAGER, Chat


def test_history_is_stored_in_order(chat):
    chat.say("How much is the C1 course?")
    chat.say("Do you help with visa applications?")
    c = chat.agent.db.client(chat.key)
    h = chat.agent.db.history(c["id"])
    assert [m["role"] for m in h] == ["user", "bot", "user", "bot"]
    assert h[0]["text"] == "How much is the C1 course?"
    assert h[1]["meta"]["kind"] == "ai" and h[1]["meta"]["sources"] == ["prices_en.md:price-c1"]
    assert h[3]["meta"]["kind"] == "handoff"


def test_manager_reply_reaches_client_and_history(agent):
    client = Chat(agent)
    client.say("Do you help with visa applications?")
    cid = agent.db.client(client.key)["id"]
    mgr = Chat(agent, user=MANAGER.split(":")[1])
    mgr.say(f"#{cid} Yes, we can recommend a partner agency.")
    to_client = [o for k, o in mgr.last_all if k == client.key]
    assert to_client and "recommend a partner agency" in to_client[0].text
    assert agent.db.history(cid)[-1]["role"] == "manager"
    out = mgr.say(f"/history {cid}")
    assert "visa applications" in out.text and "partner agency" in out.text


def test_handoff_alert_contains_recent_history(chat):
    chat.say("How much is the C1 course?")
    chat.say("Can I bring my dog to class?")
    alert = chat.alerts()[0].text
    assert "client #" in alert and "C1 course" in alert and "dog" in alert


def test_short_follow_up_uses_previous_question(chat):
    chat.say("How much is the evening course?")
    out = chat.say("and online?")
    assert out.meta["kind"] == "ai" and ("Zoom" in out.text)


def test_disclosure_only_in_first_reply(chat):
    first = chat.say("How much is the C1 course?")
    second = chat.say("When does the next intensive course start?")
    assert "I'm the AI assistant" in first.text and "AI assistant" not in second.text


def test_unknown_client_number_for_manager(agent):
    assert "No client #99" in Chat(agent, user=MANAGER.split(":")[1]).say("#99 hello").text


def test_history_api(wa):
    import json
    from conftest import sign, wa_text
    body = json.dumps(wa_text("4915700000042", "How much is the C1 course?")).encode()
    wa.post("/webhook/whatsapp", content=body, headers={"X-Hub-Signature-256": sign(body)})
    h = wa.get("/api/history/1").json()
    assert h["client"]["user_key"] == "whatsapp:4915700000042" and len(h["messages"]) == 2


def test_new_question_does_not_inherit_previous_topic(chat):
    chat.say("Bis wann kann ich kostenlos stornieren?")
    assert chat.say("Вы помогаете с визой?").meta["kind"] == "handoff"


def test_every_out_of_scope_question_right_after_an_answer_is_handed_over(agent):
    """The stress set again, but each question comes after an answered one in the same chat."""
    import json
    from pathlib import Path
    rows = [json.loads(x) for x in (Path(__file__).parent / "data/stress_out_of_scope.jsonl").read_text().splitlines()]
    warmup = {"en": "How much is the evening course?", "de": "Bis wann kann ich kostenlos stornieren?",
              "ru": "Сколько стоит курс C1?"}
    bad = []
    for i, r in enumerate(rows):
        c = Chat(agent, user=f"49170{i:05d}")
        assert c.say(warmup[r["lang"]]).meta["kind"] == "ai"
        if c.say(r["q"]).meta["kind"] != "handoff":
            bad.append(r["q"])
    assert bad == []
