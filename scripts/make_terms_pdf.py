"""Generate the demo company's terms and conditions as real PDF files (kb/terms_en.pdf, kb/terms_de.pdf, kb/terms_ru.pdf).

The bot reads the PDFs with pypdf like any client document; this script only exists so the
demo data can be rebuilt. Run:  .venv/bin/python scripts/make_terms_pdf.py
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

KB = Path(__file__).resolve().parent.parent / "kb"

EN = ("Nordlicht Language School: Terms and Conditions (2027)", [
    ("§1 Registration", "Registration is binding once you sign the registration form or confirm it in writing "
     "(e-mail or WhatsApp). Your seat is reserved after the registration fee and the first payment are received."),
    ("§2 Payment", "The course fee is due 7 days before the course starts. Courses over €400 can be paid in up to "
     "3 monthly instalments by SEPA direct debit at no extra cost. If a payment is late, we may refuse access to "
     "classes until it is paid."),
    ("§3 Cancellation by the student", "You can cancel free of charge up to 14 days before the course starts. From "
     "13 to 3 days before the start we keep 30 % of the course fee. Later than that, or after the course has "
     "started, the full fee is due. You may name a replacement participant at any time at no cost."),
    ("§4 Missed lessons", "Missed group lessons cannot be refunded or made up. Private lessons can be cancelled or "
     "moved free of charge up to 24 hours before the lesson; later cancellations are charged in full."),
    ("§5 Minimum group size", "A group course runs with at least 5 participants. If a course does not reach this "
     "number, we offer another date or a shorter course with fewer participants, or refund the full fee."),
    ("§6 Changing courses", "You can switch to another level or course time within the first week of a course at "
     "no cost, if there is a free seat. Later changes cost €20."),
    ("§7 Refunds", "Refunds are paid by bank transfer within 14 days to the account the payment came from."),
    ("§8 Data protection", "We store your contact details and course data only to run your course and keep invoices "
     "for 10 years as required by German tax law. WhatsApp chats with our assistant are deleted after 90 days. "
     "Details: privacy notice at the office and on our website."),
])
DE = ("Nordlicht Sprachschule: Allgemeine Geschäftsbedingungen (2027)", [
    ("§1 Anmeldung", "Die Anmeldung ist verbindlich, sobald Sie das Anmeldeformular unterschreiben oder schriftlich "
     "bestätigen (E-Mail oder WhatsApp). Ihr Platz ist reserviert, wenn Anmeldegebühr und erste Zahlung eingegangen sind."),
    ("§2 Zahlung", "Die Kursgebühr ist 7 Tage vor Kursbeginn fällig. Kurse über 400 € können ohne Aufpreis in bis zu "
     "3 Monatsraten per SEPA-Lastschrift bezahlt werden. Bei Zahlungsverzug können wir die Teilnahme bis zur Zahlung verweigern."),
    ("§3 Rücktritt durch Teilnehmende", "Bis 14 Tage vor Kursbeginn können Sie kostenlos zurücktreten. Vom 13. bis "
     "3. Tag vor Beginn behalten wir 30 % der Kursgebühr ein. Danach oder nach Kursbeginn ist die volle Gebühr fällig. "
     "Eine Ersatzperson können Sie jederzeit kostenlos benennen."),
    ("§4 Versäumter Unterricht", "Versäumte Gruppenstunden werden weder erstattet noch nachgeholt. Einzelstunden "
     "können bis 24 Stunden vorher kostenlos abgesagt oder verschoben werden; spätere Absagen werden voll berechnet."),
    ("§5 Mindestteilnehmerzahl", "Ein Gruppenkurs findet ab 5 Teilnehmenden statt. Wird diese Zahl nicht erreicht, "
     "bieten wir einen anderen Termin oder einen kürzeren Kurs mit weniger Teilnehmenden an oder erstatten die volle Gebühr."),
    ("§6 Kurswechsel", "In der ersten Kurswoche können Sie kostenlos in ein anderes Niveau oder eine andere Kurszeit "
     "wechseln, wenn ein Platz frei ist. Spätere Wechsel kosten 20 €."),
    ("§7 Erstattungen", "Erstattungen überweisen wir innerhalb von 14 Tagen auf das Konto, von dem die Zahlung kam."),
    ("§8 Datenschutz", "Wir speichern Ihre Kontaktdaten und Kursdaten nur zur Durchführung des Kurses und bewahren "
     "Rechnungen 10 Jahre auf, wie es das deutsche Steuerrecht verlangt. WhatsApp-Chats mit unserem Assistenten werden "
     "nach 90 Tagen gelöscht. Details: Datenschutzhinweise im Büro und auf unserer Website."),
])
RU = ("Языковая школа Nordlicht: условия обучения (2027)", [
    ("§1 Запись", "Запись становится обязательной, когда вы подписываете регистрационную форму или подтверждаете её "
     "письменно (e-mail или WhatsApp). Место закрепляется за вами после оплаты регистрационного взноса и первого платежа."),
    ("§2 Оплата", "Оплата курса — за 7 дней до начала. Курсы дороже 400 € можно оплатить без доплаты частями, до 3 "
     "ежемесячных платежей через SEPA-списание. При просрочке оплаты мы можем не допускать к занятиям до её поступления."),
    ("§3 Отказ от курса", "Отказаться бесплатно можно не позднее чем за 14 дней до начала курса. С 13-го по 3-й день до "
     "начала мы удерживаем 30 % стоимости. Позже или после начала курса оплачивается полная стоимость. Вместо себя "
     "можно бесплатно прислать другого участника в любое время."),
    ("§4 Пропущенные занятия", "Пропущенные групповые занятия не возвращаются и не переносятся. Индивидуальное занятие "
     "можно бесплатно отменить или перенести не позднее чем за 24 часа; при более поздней отмене оно оплачивается полностью."),
    ("§5 Минимальный размер группы", "Групповой курс проводится, если в нём не меньше 5 участников. Если группа не "
     "набралась, мы предлагаем другую дату или более короткий курс с меньшим числом участников либо возвращаем всю сумму."),
    ("§6 Смена курса", "В первую неделю курса можно бесплатно перейти на другой уровень или в другое время, если есть "
     "свободное место. Позже смена стоит 20 €."),
    ("§7 Возврат денег", "Деньги возвращаем банковским переводом в течение 14 дней на счёт, с которого пришла оплата."),
    ("§8 Защита данных", "Мы храним ваши контакты и данные о курсе только для проведения обучения, а счета — 10 лет, как "
     "требует налоговое право Германии. Переписка с нашим ассистентом в WhatsApp удаляется через 90 дней. "
     "Подробности — в памятке о защите данных в офисе и на сайте."),
])


def font() -> str:
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(p).exists():
            pdfmetrics.registerFont(TTFont("Body", p))
            return "Body"
    return "Helvetica"


def build(path: Path, title: str, sections) -> None:
    f = font()
    h1 = ParagraphStyle("h1", fontName=f, fontSize=16, leading=20, spaceAfter=10)
    h2 = ParagraphStyle("h2", fontName=f, fontSize=12, leading=16, spaceBefore=8, spaceAfter=3)
    body = ParagraphStyle("b", fontName=f, fontSize=10.5, leading=14.5)
    story = [Paragraph(title, h1), Paragraph("Nordlicht · Beispielstraße 12 · 20095 Hamburg", body), Spacer(1, 6 * mm)]
    for head, text in sections:
        story += [Paragraph(head, h2), Paragraph(text, body)]
    SimpleDocTemplate(str(path), pagesize=A4, title=title, author="Nordlicht (demo company)",
                      leftMargin=22 * mm, rightMargin=22 * mm).build(story)
    print("wrote", path)


if __name__ == "__main__":
    build(KB / "terms_en.pdf", *EN)
    build(KB / "terms_de.pdf", *DE)
    build(KB / "terms_ru.pdf", *RU)
