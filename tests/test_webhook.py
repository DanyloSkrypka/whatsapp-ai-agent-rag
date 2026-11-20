"""WhatsApp Cloud API webhook: verification, X-Hub-Signature-256, payloads sent to graph.facebook.com."""
import json

from conftest import MANAGER, sign, wa_text


def test_verify_handshake(wa):
    r = wa.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "42"})
    assert r.status_code == 200 and r.text == "42"
    r = wa.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "42"})
    assert r.status_code == 403


def test_valid_signature_processes_and_replies(wa):
    body = json.dumps(wa_text("4915700000042", "How much is the C1 course?")).encode()
    r = wa.post("/webhook/whatsapp", content=body, headers={"X-Hub-Signature-256": sign(body), "content-type": "application/json"})
    assert r.status_code == 200
    assert len(wa.sent) == 1
    msg = wa.sent[0]
    assert msg["url"] == "https://graph.facebook.com/v23.0/123456/messages"
    assert msg["auth"] == "Bearer test-token"
    assert msg["json"]["to"] == "4915700000042" and msg["json"]["type"] == "text"
    assert "€690" in msg["json"]["text"]["body"] and "AI assistant" in msg["json"]["text"]["body"]


def test_bad_or_missing_signature_rejected(wa):
    body = json.dumps(wa_text("4915700000042", "hi")).encode()
    assert wa.post("/webhook/whatsapp", content=body, headers={"X-Hub-Signature-256": sign(body, "other")}).status_code == 401
    assert wa.post("/webhook/whatsapp", content=body).status_code == 401
    tampered = body.replace(b"hi", b"ho")
    assert wa.post("/webhook/whatsapp", content=tampered, headers={"X-Hub-Signature-256": sign(body)}).status_code == 401
    assert wa.sent == []


def test_status_updates_are_ignored(wa):
    body = json.dumps({"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.X", "status": "read"}]}}]}]}).encode()
    assert wa.post("/webhook/whatsapp", content=body, headers={"X-Hub-Signature-256": sign(body)}).status_code == 200
    assert wa.sent == []


def test_manager_alert_uses_template_outside_24h_window(wa):
    body = json.dumps(wa_text("4915700000042", "Do you help with visa applications?")).encode()
    wa.post("/webhook/whatsapp", content=body, headers={"X-Hub-Signature-256": sign(body)})
    to_manager = [m["json"] for m in wa.sent if m["json"]["to"] == MANAGER.split(":")[1]]
    assert len(to_manager) == 1
    assert to_manager[0]["type"] == "template" and to_manager[0]["template"]["name"] == "manager_alert"


def test_greeting_buttons_are_interactive(wa):
    body = json.dumps(wa_text("4915700000043", "Hallo")).encode()
    wa.post("/webhook/whatsapp", content=body, headers={"X-Hub-Signature-256": sign(body)})
    p = wa.sent[0]["json"]
    assert p["type"] == "interactive" and p["interactive"]["type"] == "button"
    assert all(len(b["reply"]["title"]) <= 20 for b in p["interactive"]["action"]["buttons"])
    assert "KI-Assistent" in p["interactive"]["body"]["text"]


def test_health(wa):
    h = wa.get("/health").json()
    assert h["ok"] and h["retriever"] == "embeddings + reranker" and h["answers"] == "template"
