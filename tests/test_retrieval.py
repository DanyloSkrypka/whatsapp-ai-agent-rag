"""Search finds the right document and section, in EN / DE / RU, from Markdown and PDF."""
import pytest

from app.rag.index import BM25Index, rewrite_query


def test_loader_reads_all_documents(chunks):
    docs = {c.doc for c in chunks}
    assert docs == {"faq_en.md", "faq_de.md", "faq_ru.md", "prices_en.md", "prices_de.md", "prices_ru.md",
                    "terms_en.pdf", "terms_de.pdf", "terms_ru.pdf"}
    pdf = [c for c in chunks if c.doc == "terms_de.pdf"]
    assert [c.key for c in pdf] == [f"terms-{i}" for i in range(1, 9)]
    assert "14 Tage" in next(c.text for c in pdf if c.key == "terms-3")


def test_twins_share_keys(chunks):
    keys_en = {c.key for c in chunks if c.lang == "en"}
    keys_de = {c.key for c in chunks if c.lang == "de"}
    keys_ru = {c.key for c in chunks if c.lang == "ru"}
    assert keys_en == keys_de  # every EN section has a German twin
    assert keys_ru == keys_en  # ...and a Russian one


@pytest.mark.parametrize("q,lang,doc_prefix,key", [
    ("How much does a private lesson cost?", "en", "prices", "price-private"),
    ("When does the next evening course start?", "en", "faq", "start-dates"),
    ("Can I cancel for free before the course starts?", "en", "terms", "terms-3"),
    ("Was kostet der Abendkurs?", "de", "prices", "price-evening"),
    ("Bis wann kann ich kostenlos stornieren?", "de", "terms", "terms-3"),
    ("Sind Sie ein telc-Prüfungszentrum?", "de", "faq", "exam-centre"),
    ("Сколько стоит подготовка к экзамену telc?", "ru", "prices", "price-exam-prep"),
    ("Можно ли перенести индивидуальное занятие?", "ru", "terms", "terms-4"),
    ("Где находится школа?", "ru", "faq", "location"),
])
def test_finds_right_document(index, q, lang, doc_prefix, key):
    hits = index.search(q, lang=lang)
    assert hits[0].chunk.key == key, [(h.chunk.key, round(h.score, 3)) for h in hits]
    assert hits[0].chunk.doc.startswith(doc_prefix)
    assert hits[0].score >= index.default_min_score


@pytest.mark.parametrize("q,lang", [
    ("Do you offer yoga classes?", "en"),
    ("Haben Sie eine Kantine?", "de"),
    ("Есть ли у вас курсы вождения?", "ru"),
])
def test_out_of_scope_scores_low(index, q, lang):
    assert index.search(q, lang=lang)[0].score < index.default_min_score


def test_rewrite_you_means_the_business():
    assert rewrite_query("Where are you located?", "en") == "Where are the school located?"
    assert rewrite_query("Haben Sie eine Kantine?", "de") == "Haben die Schule eine Kantine?"
    assert rewrite_query("Где вы находитесь?", "ru") == "Где школа находитесь?"


def test_short_sentences_are_glued():
    from app.rag.index import _sentences
    assert _sentences("Yes. Evening courses are online via Zoom. Intensive courses are on site only.") == [
        "Yes. Evening courses are online via Zoom.", "Intensive courses are on site only."]


def test_stress_out_of_scope_set_has_no_false_answers():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
    from run_eval import run
    s = run("stress", write=False, quiet=True)["summary"]
    assert s["questions"] == 30 and s["fabrications"] == 0


def test_bm25_fallback_works_without_models(chunks):
    bm = BM25Index(chunks)
    assert bm.search("private lesson price")[0].chunk.key == "price-private"
    assert bm.search("Einzelunterricht Preis")[0].chunk.key == "price-private"
