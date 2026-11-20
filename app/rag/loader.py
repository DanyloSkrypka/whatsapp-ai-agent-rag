"""Load company documents (Markdown FAQ / price list, PDF terms) into small, self-contained chunks.

Every chunk has a language-independent `key`. The same answer in two languages (faq_en / faq_de,
terms_en.pdf / terms_de.pdf) shares the key, so the bot can quote the version in the user's language.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class Chunk:
    key: str        # e.g. "price-evening", "terms-3" (same for EN/DE twins)
    doc: str        # file name, e.g. "prices.md"
    lang: str       # en | de
    title: str      # question / section heading
    text: str       # answer body, quoted as is in template mode

    @property
    def id(self) -> str:
        return f"{self.doc}:{self.key}"

    @property
    def source(self) -> str:
        """Short citation shown to the client."""
        return f"{self.doc} · {self.title}"


_ID = re.compile(r"<!--\s*id:\s*([\w-]+)\s*-->")
_LANG = re.compile(r"_(en|de|ru)\.\w+$")


def _lang_of(path: Path, default: str = "en") -> str:
    m = _LANG.search(path.name)
    return m.group(1) if m else default


def load_markdown(path: Path) -> list[Chunk]:
    """`## Heading <!-- id: key -->` starts a chunk; the paragraph(s) below are its text."""
    chunks, cur, body = [], None, []
    lang = _lang_of(path)

    def flush():
        if cur and body:
            chunks.append(Chunk(cur[0], path.name, lang, cur[1], " ".join(body).strip()))

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            flush()
            m = _ID.search(line)
            title = _ID.sub("", line[3:]).strip()
            key = m.group(1) if m else re.sub(r"\W+", "-", title.lower()).strip("-")
            cur, body = (key, title), []
        elif cur and line.strip():
            body.append(line.strip())
    flush()
    return chunks


_PARA = re.compile(r"^§\s?(\d+)\s+(.+)$")


def load_pdf(path: Path) -> list[Chunk]:
    """Terms and conditions: one chunk per numbered clause (§1, §2, ...)."""
    text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    chunks, cur, body = [], None, []
    lang = _lang_of(path)

    def flush():
        if cur and body:
            chunks.append(Chunk(f"terms-{cur[0]}", path.name, lang, f"§{cur[0]} {cur[1]}", " ".join(body).strip()))

    for line in text.splitlines():
        m = _PARA.match(line.strip())
        if m:
            flush()
            cur, body = (m.group(1), m.group(2).strip()), []
        elif cur and line.strip():
            body.append(line.strip())
    flush()
    return chunks


def load_kb(folder: str | Path) -> list[Chunk]:
    out: list[Chunk] = []
    for p in sorted(Path(folder).iterdir()):
        if p.suffix == ".md":
            out += load_markdown(p)
        elif p.suffix == ".pdf":
            out += load_pdf(p)
    return out
