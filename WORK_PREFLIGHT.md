# ChatGPT Work Preflight

## Purpose

This test verifies the capabilities required by the campaign runtime in the
actual target client: a **local ChatGPT Work task** attached to this project
folder.

Results obtained in Codex do not automatically count as ChatGPT Work results.

## Current Codex baseline

Verified on 2026-09-07 in the current local Codex task:

| Capability | Result | Evidence |
|---|---|---|
| Read an existing project file | PASS | Read `GPT_DND_CAMPAIGN_RUNTIME_OVERVIEW.md` |
| Create a Markdown file | PASS | Created `WORK_PREFLIGHT.md` |
| Read the created file | PASS | Read `WORK_PREFLIGHT.md` back successfully |
| Modify an existing Markdown file | PASS | Reviewed, corrected, and reread `WORK_PREFLIGHT.md` |
| Run `python` from `PATH` | FAIL | The `python` command was not found |
| Run bundled Python explicitly | PASS | Python 3.12.14 executed successfully |
| Use an algorithmically uniform local random source | PASS | `secrets.randbelow()` produced test dice rolls |
| Continue from the same folder in a new ChatGPT Work chat | NOT TESTED | Requires a separate local Work chat |

The bundled Python path is an implementation detail of the desktop runtime and
must not be treated as a stable campaign dependency until it is verified in
ChatGPT Work.

## Exact prompt for ChatGPT Work

Run the prompt below in a **local ChatGPT Work task** whose primary folder is
this project folder. Run it once in the first chat, then open a genuinely new
local Work chat in the same project and run the same prompt again.

```text
Проведи двухфазный preflight локальной папки для GPT D&D Campaign Runtime.

Работай только внутри текущей папки проекта. Не изменяй
GPT_DND_CAMPAIGN_RUNTIME_OVERVIEW.md и не создавай пока AGENTS.md, CAMPAIGN.md,
SAVE.md, journal, references, backups или tools/dice.py. Не устанавливай
программы и зависимости.

Используй файлы WORK_PREFLIGHT_STATE.md и WORK_PREFLIGHT_RESULT.md.

Сначала определи фазу:

- Если WORK_PREFLIGHT_STATE.md отсутствует, выполни ФАЗУ A.
- Если он существует и содержит status: awaiting-new-chat, выполни ФАЗУ B.
- При любом другом состоянии ничего не перезаписывай; объясни проблему.

ФАЗА A — первый локальный Work-чат:

1. Определи абсолютный путь текущей рабочей папки штатным способом среды и
   проверь, что GPT_DND_CAMPAIGN_RUNTIME_OVERVIEW.md находится именно в ней.
   Запиши путь и способ его определения; не выводи путь из текста prompt.
2. Прочитай GPT_DND_CAMPAIGN_RUNTIME_OVERVIEW.md непосредственно с диска.
   Извлеки из него название проекта и полный текст выделенной формулировки из
   раздела «Главный архитектурный принцип проекта». Также получи размер файла и
   SHA-256 штатными средствами среды. Это проверяемые свидетельства чтения.
3. Создай WORK_PREFLIGHT_STATE.md. Запиши в него:
   - status: phase-a-running;
   - continuity-token длиной не менее 16 символов;
   - continuity-token-method — точный способ создания token;
   - created-at — дату и время в ISO 8601 с часовым поясом;
   - project-root — определённый абсолютный путь;
   - название проекта, извлечённое из обзорного документа.
   Token нужен только как маркер переноса состояния. Если надёжный генератор
   случайности ещё не подтверждён, используй уникальную комбинацию UTC-времени
   и SHA-256 обзорного файла и не называй её случайной.
4. Прочитай созданный файл обратно, затем измени status на
   awaiting-new-chat и добавь строку phase-a-write-verified: true. Снова прочитай
   файл, проверь обе записи и получи SHA-256 этого файла. Это проверка
   create/read/write. Не показывай continuity-token в ответе пользователю: он
   должен попасть во вторую фазу через файл, а не через текст чата.
5. Проверь локальное выполнение Python без установки зависимостей:
   - последовательно проверь уже доступные команды `python --version`,
     `python3 --version` и `py -3 --version`, останавливаясь после успеха;
   - если они отсутствуют, можно использовать штатный механизм среды для
     обнаружения уже доступного встроенного Python;
   - нельзя угадывать путь, устанавливать Python или менять конфигурацию;
   - точно запиши все попытки, использованный исполняемый файл и версию либо
     проверяемую причину FAIL.
6. Если Python доступен, сгенерируй через стандартный модуль `secrets` десять
   результатов d20 формулой `secrets.randbelow(20) + 1`. Не используй заранее
   выбранные числа и не перебрасывай результаты. Проверь только то, что каждый
   результат является целым числом от 1 до 20; десять результатов не являются
   статистическим доказательством качества генератора. Если Python недоступен,
   проверь другой реально доступный системный или computation-инструмент
   случайности и точно назови алгоритм/API. Если надёжного инструмента нет,
   поставь FAIL; не имитируй случайность моделью.
7. Создай WORK_PREFLIGHT_RESULT.md. Запиши определённый project-root, название и
   главный принцип проекта, размер и SHA-256 обзорного файла, SHA-256 state-файла
   после записи, точные результаты проверки Python и неизменённую
   последовательность десяти d20. Добавь таблицу PASS/FAIL для: правильной
   рабочей папки, чтения существующего файла, создания файла, чтения созданного
   файла, изменения файла, повторного чтения, Python и надёжного random source.
   Для new-chat continuity поставь PENDING.
8. Заверши ответ просьбой открыть новый локальный Work-чат в этом же локальном
   проекте и снова отправить этот же prompt. Не раскрывай continuity-token.
   Не выполняй ФАЗУ B в текущем чате.

ФАЗА B — только новый локальный Work-чат:

1. Не используй пересказ пользователя, старый чат или память проекта и не проси
   continuity-token. Сначала самостоятельно определи абсолютный путь текущей
   рабочей папки, затем прочитай
   WORK_PREFLIGHT_STATE.md и WORK_PREFLIGHT_RESULT.md непосредственно с диска.
2. Проверь, что status равен awaiting-new-chat, continuity-token существует, а
   phase-a-write-verified равен true. Проверь совпадение project-root с текущей
   папкой. До любых изменений повторно вычисли SHA-256 обзорного файла и
   WORK_PREFLIGHT_STATE.md и сопоставь их с записанными результатами фазы A.
   Если state-файл не удалось прочитать с диска, это FAIL, даже если какие-либо
   значения доступны из памяти.
3. Измени status на complete и добавь phase-b-read-verified: true и
   phase-b-verified-at с текущими датой и временем в ISO 8601 с часовым поясом.
4. В WORK_PREFLIGHT_RESULT.md замени new-chat continuity: PENDING на PASS и
   укажи путь прочитанного state-файла и проверенный continuity-token в
   замаскированном виде: первые 4 и последние 4 символа. Если файлы недоступны,
   project-root не совпадает или данные не совпадают, поставь FAIL и ничего не
   выдумывай.
5. Покажи итоговую таблицу и явно ответь:
   - пригоден ли local ChatGPT Work для authoritative campaign runtime;
   - какой random source следует выбрать для v1;
   - нужен ли tools/dice.py;
   - какие ограничения остались.
```

## Acceptance rule

Stage 0 is complete only after Phase B has updated
`WORK_PREFLIGHT_RESULT.md`. Until then, the Work-specific capabilities and the
new-chat continuity requirement remain unverified.
