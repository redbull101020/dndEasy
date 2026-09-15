# Контракт `CAMPAIGN.md` v3

Формат/порядок разделов зафиксирован текущим шаблоном и полным validator. `Campaign ID` — 32 lowercase hex из доверенного CSPRNG; pristine template хранит `not-set` и revision 0. Первое утверждённое изменение вместе с save устанавливает обе revisions в 1; дальнейшее изменение campaign увеличивает configuration revision ровно на 1 и одновременно увеличивает save revision на 1. `Updated at` — timezone-aware ISO 8601.

До `await-lore` должны быть утверждены edition/source, boundaries, число героев, стартовый уровень, методы характеристик/HP и допустимые character sources. `Baseline reference access` = `local: references/<file>` с SHA-256, `remote: https://...` с `remote-unpinned` либо `model-knowledge-only (degraded)` с `not-applicable`; remote URL проверяется как публичный HTTPS. Доступность и содержание источника ИИ проверяет отдельно; validator не доказывает, что remote страница была фактически прочитана.

Перед `ready` все пользовательские поля должны быть утверждены, `not-set` не остаётся. `none` и `not-applicable` допустимы только по явному решению. `Narrative Direction` содержит моральный тон, юмор, NPC dialogue, прочие предпочтения, без отдельной настройки голоса. Неочевидные варианты и defaults объясняются в `SETUP_GUIDE.md`. Настройки кампании не переписываются автоматически при создании следующего приключения.
