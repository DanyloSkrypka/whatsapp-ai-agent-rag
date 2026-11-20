"""Language detection (EN / DE / RU) and every fixed text the agent sends."""
from __future__ import annotations

import re
from typing import Optional

_CYR = re.compile(r"[а-яё]", re.I)
_DE_CHARS = re.compile(r"[äöüß]", re.I)
_DE = set("""ich du sie wir ihr ist sind bin habe haben hat kann können möchte will wie was wann wo warum gibt es
der die das den dem des ein eine einen und oder nicht kein keine mein meine ihr ihre mit für bei zum zur auch noch
bitte danke hallo guten tag kurs kurse preis kostet kosten anmelden anmeldung termin geöffnet gruppe stunde
übernimmt bekomme passiert teilnehmer niveau wechseln woche fällig""".split())
_EN = set("""i you we they is are am have has can could would will how what when where why there the a an and or
not no my your our with for at to of in on please thanks hello hi course courses price cost costs sign book
lesson level group get does do much""".split())


def detect(text: str, previous: Optional[str] = None) -> str:
    """Guess the language of one message. Very short messages (a name, "600 €") keep the previous language."""
    t = (text or "").strip()
    if not t:
        return previous or "en"
    if len(_CYR.findall(t)) >= 2:
        return "ru"
    words = re.findall(r"[a-zäöüß']+", t.lower())
    de = sum(w in _DE for w in words) + 2 * bool(_DE_CHARS.search(t))
    en = sum(w in _EN for w in words)
    if de == en:  # nothing to decide on: keep the conversation language
        return previous or ("de" if de else "en")
    return "de" if de > en else "en"


T = {
    "disclosure": {
        "en": "Hi! I'm the AI assistant of {company} 🤖 I answer from the school's official documents, and a manager takes over when needed.",
        "de": "Hallo! Ich bin der KI-Assistent der {company} 🤖 Ich antworte aus den offiziellen Unterlagen der Schule, bei Bedarf übernimmt eine Mitarbeiterin.",
        "ru": "Здравствуйте! Я ИИ-ассистент школы {company} 🤖 Отвечаю по официальным документам школы, а если нужно, подключаю менеджера.",
    },
    "how_help": {
        "en": "How can I help? Ask me about courses, prices, start dates or our terms.",
        "de": "Wie kann ich helfen? Fragen Sie mich nach Kursen, Preisen, Terminen oder unseren AGB.",
        "ru": "Чем помочь? Спросите про курсы, цены, даты старта или условия.",
    },
    "thanks": {
        "en": "You're welcome! Write any time.",
        "de": "Gern geschehen! Schreiben Sie jederzeit.",
        "ru": "Пожалуйста! Пишите в любое время.",
    },
    "source": {"en": "Source", "de": "Quelle", "ru": "Источник"},
    "quote_other_lang": {
        "en": "Here is what our document says:",
        "de": "Das steht in unserem Dokument (auf Englisch):",
        "ru": "Вот что сказано в нашем документе (на английском):",
    },
    "handoff": {
        "en": "I couldn't find this in our documents, and I don't want to guess. I'll pass your question to a manager, who will reply here in this chat.",
        "de": "Dazu steht nichts in unseren Unterlagen, und raten möchte ich nicht. Ich gebe Ihre Frage an eine Mitarbeiterin weiter, sie antwortet hier im Chat.",
        "ru": "В документах школы ответа на это нет, а гадать я не буду. Передам ваш вопрос менеджеру, он ответит здесь, в этом чате.",
    },
    "ask_name": {
        "en": "Great, let's get you started! What's your name?",
        "de": "Sehr gern! Wie heißen Sie?",
        "ru": "Отлично, давайте оформим! Как вас зовут?",
    },
    "ask_task": {
        "en": "Nice to meet you, {name}! Which course do you need and what for? (e.g. B1 for work, start in January)",
        "de": "Freut mich, {name}! Welchen Kurs suchen Sie und wofür? (z. B. B1 für den Job, Start im Januar)",
        "ru": "Приятно познакомиться, {name}! Какой курс нужен и для чего? (например, B1 для работы, старт в январе)",
    },
    "ask_budget": {
        "en": "Got it. What budget do you have in mind for the course?",
        "de": "Verstanden. Welches Budget haben Sie für den Kurs eingeplant?",
        "ru": "Понял. На какой бюджет за курс вы рассчитываете?",
    },
    "lead_done": {
        "en": "Thank you, {name}! I've passed your request to our manager. They'll contact you here on WhatsApp today.",
        "de": "Danke, {name}! Ich habe Ihre Anfrage an unsere Mitarbeiterin weitergegeben. Sie meldet sich heute hier per WhatsApp.",
        "ru": "Спасибо, {name}! Я передал вашу заявку менеджеру. Он свяжется с вами здесь, в WhatsApp, сегодня.",
    },
    "lead_saved": {
        "en": "Thank you, {name}! I've saved your request, and a manager will get back to you with options.",
        "de": "Danke, {name}! Ich habe Ihre Anfrage gespeichert, eine Mitarbeiterin meldet sich mit passenden Angeboten.",
        "ru": "Спасибо, {name}! Я сохранил заявку, менеджер вернётся к вам с вариантами.",
    },
    "manager_prefix": {"en": "Manager", "de": "Mitarbeiterin", "ru": "Менеджер"},
}


def t(key: str, lang: str, **kw) -> str:
    s = T[key].get(lang) or T[key]["en"]
    return s.format(**kw) if kw else s
