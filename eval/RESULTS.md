# Evaluation: 40 questions

Retriever: **embeddings + reranker**, hand-over threshold 0.27 (picked on the separate dev set). Answers: template mode (no API key), so every answer is a quote from a document.

- **Accuracy: 37/40 = 92.5 %**
- Answerable questions: 27/30 correct (3 handed over to a manager, 0 wrong source)
- Out-of-scope questions: 10/10 handed over, **0 fabrications**
- Language detected correctly: 40/40

| # | Lang | Question | Expected | Bot | Score | Result |
|---|---|---|---|---|---|---|
| 1 | en | How much does the evening German course cost? | price-evening | price-evening | 1.0 | ✅ |
| 2 | en | Where exactly are you located? | location | location | 0.979 | ✅ |
| 3 | en | Can I cancel my course and get my money back? | terms-3, terms-7 | terms-3 | 0.611 | ✅ |
| 4 | en | Is there a free test to check my level? | placement-test | placement-test | 0.999 | ✅ |
| 5 | en | Do you have Business English? | price-english, languages-levels | price-english | 0.564 | ✅ |
| 6 | en | When does the next intensive course begin? | start-dates | start-dates | 1.0 | ✅ |
| 7 | en | Can I pay in instalments? | terms-2, payment-methods | payment-methods | 0.99 | ✅ |
| 8 | en | What's the price for one private lesson? | price-private | price-private | 1.0 | ✅ |
| 9 | en | Is the exam fee included in the telc preparation course? | price-exam-prep | price-exam-prep | 0.997 | ✅ |
| 10 | en | I missed a group lesson, can I make it up later? | terms-4 | terms-4 | 1.0 | ✅ |
| 11 | en | Are books included in the price? | books | books | 0.991 | ✅ |
| 12 | de | Was kostet der Intensivkurs Deutsch? | price-intensive | price-intensive | 1.0 | ✅ |
| 13 | de | Wie lange ist das Büro samstags geöffnet? | hours | hours | 0.997 | ✅ |
| 14 | de | Gibt es Rabatt für Studenten? | price-discounts | price-discounts | 0.903 | ✅ |
| 15 | de | Kann ich online am Abendkurs teilnehmen? | online, price-evening | online | 1.0 | ✅ |
| 16 | de | Wie viele Leute sind in einer Gruppe? | class-size | class-size | 1.0 | ✅ |
| 17 | de | Übernimmt das Jobcenter die Kosten mit Bildungsgutschein? | invoice-employer | invoice-employer | 0.966 | ✅ |
| 18 | de | Was passiert, wenn sich nicht genug Teilnehmer anmelden? | terms-5, class-size | hand-over | 0.25 | ❌ handed over |
| 19 | de | Kann ich in der ersten Woche das Niveau wechseln? | terms-6 | terms-6 | 1.0 | ✅ |
| 20 | de | Bekomme ich am Ende ein Zertifikat? | certificate | hand-over | 0.212 | ❌ handed over |
| 21 | de | Wann ist die Kursgebühr fällig? | terms-2 | terms-2 | 0.998 | ✅ |
| 22 | ru | Сколько стоит курс C1? | price-c1 | price-c1 | 1.0 | ✅ |
| 23 | ru | Можно ли прийти на пробный урок бесплатно? | trial-lesson | trial-lesson | 1.0 | ✅ |
| 24 | ru | Вы принимаете наличные? | payment-methods | hand-over | 0.058 | ❌ handed over |
| 25 | ru | Есть ли у вас интеграционный курс и сколько он стоит? | integration, price-integration | integration | 1.0 | ✅ |
| 26 | ru | Можно ли у вас сдать экзамен telc? | exam-centre | exam-centre | 1.0 | ✅ |
| 27 | ru | Какой у вас регистрационный взнос? | price-registration | price-registration | 0.349 | ✅ |
| 28 | ru | Как долго вы храните мою переписку в WhatsApp? | terms-8 | terms-8 | 0.991 | ✅ |
| 29 | ru | Где вы находитесь и есть ли парковка? | location | location | 0.995 | ✅ |
| 30 | ru | За сколько дней до начала курса можно отменить бесплатно? | terms-3 | terms-3 | 1.0 | ✅ |
| 31 | en | Do you help with visa applications? | *(not in docs)* | hand-over | 0.014 | ✅ |
| 32 | en | Is there a cafeteria in the building? | *(not in docs)* | hand-over | 0.003 | ✅ |
| 33 | en | Can I bring my dog to class? | *(not in docs)* | hand-over | 0.04 | ✅ |
| 34 | en | What's the Wi-Fi password? | *(not in docs)* | hand-over | 0.007 | ✅ |
| 35 | de | Organisieren Sie Ausflüge am Wochenende? | *(not in docs)* | hand-over | 0.037 | ✅ |
| 36 | de | Helfen Sie bei der Wohnungssuche in Hamburg? | *(not in docs)* | hand-over | 0.081 | ✅ |
| 37 | de | Gibt es Sommercamps für Kinder? | *(not in docs)* | hand-over | 0.042 | ✅ |
| 38 | ru | Вы помогаете найти работу после курса? | *(not in docs)* | hand-over | 0.015 | ✅ |
| 39 | ru | Есть ли у вас общежитие для студентов? | *(not in docs)* | hand-over | 0.033 | ✅ |
| 40 | ru | Как зовут преподавателя группы B1? | *(not in docs)* | hand-over | 0.021 | ✅ |

Re-run: `.venv/bin/python eval/run_eval.py`
