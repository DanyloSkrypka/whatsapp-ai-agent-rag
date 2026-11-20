"""Settings come only from environment variables (.env). Nothing secret lives in the code."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent


def _list(name: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: _env("DB_PATH", str(ROOT / "data" / "agent.db")))
    kb_dir: str = field(default_factory=lambda: _env("KB_DIR", str(ROOT / "kb")))
    company: str = field(default_factory=lambda: _env("COMPANY_NAME", "Nordlicht Language School"))
    company_de: str = field(default_factory=lambda: _env("COMPANY_NAME_DE", "Nordlicht Sprachschule"))

    # Retrieval: "auto" = embeddings + reranker if sentence-transformers is installed, else BM25
    retriever: str = field(default_factory=lambda: _env("RETRIEVER", "auto"))
    embed_model: str = field(default_factory=lambda: _env("EMBED_MODEL", "intfloat/multilingual-e5-small"))
    rerank_model: str = field(default_factory=lambda: _env("RERANK_MODEL", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"))
    min_score: float = field(default_factory=lambda: float(_env("MIN_SCORE", "0")))  # 0 = backend default

    # Answers: Claude if a key is set, otherwise quotes from the documents
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    claude_model: str = field(default_factory=lambda: _env("CLAUDE_MODEL", "claude-opus-5-5"))

    # Managers get hot leads and unanswered questions: "<channel>:<id>", e.g. "whatsapp:4915112345678"
    managers: list[str] = field(default_factory=lambda: _list("MANAGER_IDS"))
    hot_budget: int = field(default_factory=lambda: int(_env("HOT_LEAD_MIN_BUDGET", "250")))

    # WhatsApp Cloud API (official, graph.facebook.com)
    wa_token: str = field(default_factory=lambda: _env("WA_ACCESS_TOKEN"))
    wa_phone_number_id: str = field(default_factory=lambda: _env("WA_PHONE_NUMBER_ID"))
    wa_verify_token: str = field(default_factory=lambda: _env("WA_VERIFY_TOKEN"))
    wa_app_secret: str = field(default_factory=lambda: _env("WA_APP_SECRET"))
    wa_api_version: str = field(default_factory=lambda: _env("WA_API_VERSION", "v23.0"))
    wa_alert_template: str = field(default_factory=lambda: _env("WA_ALERT_TEMPLATE", "manager_alert"))

    demo_mode: bool = field(default_factory=lambda: _env("DEMO_MODE", "1") == "1")
