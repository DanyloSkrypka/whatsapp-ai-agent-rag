import hashlib
import hmac
import json
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.core.db import DB  # noqa: E402
from app.core.models import Incoming  # noqa: E402
from app.main import build_agent, create_app  # noqa: E402
from app.rag.index import make_index  # noqa: E402
from app.rag.loader import load_kb  # noqa: E402

APP_SECRET = "test-app-secret"
MANAGER = "whatsapp:4915100000001"


@pytest.fixture(scope="session")
def chunks():
    return load_kb(ROOT / "kb")


@pytest.fixture(scope="session")
def index(chunks, tmp_path_factory):
    """The real local retriever (e5-small + multilingual reranker), loaded once per test run."""
    return make_index(chunks, "auto", cache_db=str(tmp_path_factory.mktemp("idx") / "vec.db"))


def make_settings(tmp_path, **kw) -> Settings:
    s = Settings()
    s.db_path = str(tmp_path / "agent.db")
    s.anthropic_api_key = ""
    s.managers = [MANAGER]
    s.demo_mode = True
    s.wa_app_secret = APP_SECRET
    s.wa_verify_token = "verify-me"
    s.wa_token = "test-token"
    s.wa_phone_number_id = "123456"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


@pytest.fixture
def agent(tmp_path, index):
    s = make_settings(tmp_path)
    return build_agent(s, DB(s.db_path), index=index)


class Chat:
    """Tiny helper: talk to the agent as one client."""

    def __init__(self, agent, user="4915700000042", channel="whatsapp", name=None):
        self.agent, self.user, self.channel, self.name = agent, user, channel, name

    @property
    def key(self):
        return f"{self.channel}:{self.user}"

    def say(self, text=None, payload=None):
        replies = self.agent.handle(Incoming(self.channel, self.user, text=text, payload=payload, name=self.name))
        self.last_all = replies
        mine = [o for k, o in replies if k == self.key]
        return mine[0] if mine else None

    def alerts(self):
        return [o for k, o in self.last_all if k == MANAGER]


@pytest.fixture
def chat(agent):
    return Chat(agent)


def sign(body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def wa_text(frm: str, text: str, name: str = "Anna") -> dict:
    return {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
        "messaging_product": "whatsapp", "metadata": {"phone_number_id": "123456"},
        "contacts": [{"wa_id": frm, "profile": {"name": name}}],
        "messages": [{"from": frm, "id": "wamid.X", "timestamp": "1763600000", "type": "text", "text": {"body": text}}]}}]}]}


@pytest.fixture
def wa(tmp_path, index):
    """FastAPI test client + list of payloads the bot posted to graph.facebook.com (HTTP mocked)."""
    from fastapi.testclient import TestClient

    sent = []

    def handler(request: httpx.Request):
        sent.append({"url": str(request.url), "auth": request.headers.get("authorization"),
                     "json": json.loads(request.content)})
        return httpx.Response(200, json={"messages": [{"id": "wamid.OUT"}]})

    app = create_app(make_settings(tmp_path), wa_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                     index=index)
    with TestClient(app) as c:
        c.sent = sent
        yield c
