# GPT D&D Campaign Runtime — Project Overview

## 1. Назначение проекта

Этот проект — отдельная, облегчённая D&D-игра поверх ChatGPT Work.

Он **не заменяет** основной проект `ai-dnd-master` и не является его урезанной реализацией.

Цель:

> Дать возможность уже сейчас играть в долгую D&D-кампанию через ChatGPT, используя минимальную файловую дисциплину для сохранения состояния, истории и continuity между чатами.

Основной принцип:

```text
Chat = интерфейс текущей игровой сессии
Files = долговременная память кампании
GPT = Dungeon Master + rules adjudicator + state writer
```

Это сознательно менее строгая архитектура, чем у `ai-dnd-master`.

---

## 2. Чем этот проект отличается от `ai-dnd-master`

### Основной `ai-dnd-master`

Цель:

```text
correctness by architecture
```

Там:

```text
Player / AI DM
→ Command
→ Validation
→ Rule Engine
→ Result
→ Events
→ State update
→ Persistence
→ Narration
```

AI не является authoritative источником игровой истины.

### GPT D&D Campaign Runtime

Цель:

```text
maximum playable quality
with minimum engineering
```

Здесь:

```text
Player
→ AI DM interpretation
→ rules adjudication
→ dice / randomness
→ outcome
→ save update
→ narration
```

AI здесь **может напрямую изменять текущее игровое состояние**.

Это было бы запрещено в основном проекте, но здесь является сознательным компромиссом.

---

## 3. Что заимствуем из основного проекта

Из `ai-dnd-master` переносится не код, а несколько дисциплинирующих принципов:

1. Чат не является долговременным хранилищем состояния.
2. Должен существовать один явный источник текущей истины.
3. Текущая истина и история должны быть разделены.
4. Правила кампании должны быть отделены от текущего состояния.
5. Случайность не должна подстраиваться под желаемый сюжетный результат.
6. Игровой факт должен быть определён до его художественного описания.
7. Секретный факт, текущий факт и будущий план DM — разные категории данных.
8. Новый чат должен уметь продолжить игру без пересказа всей истории вручную.

Не переносим:

- Commands;
- Events на каждое действие;
- Event Store;
- Rule Engine;
- Application Layer;
- State Owners;
- сериализаторы;
- repository abstractions;
- формальные Definition-модели;
- схемы событий;
- replay;
- database;
- тестируемую доменную механику.

Если новая GPT-игра начинает требовать всё перечисленное выше, значит она незаметно превращается во второй `ai-dnd-master`, чего следует избегать.

---

# 4. Целевая среда запуска

Базовая среда:

```text
ChatGPT Project
+
Default memory
+
Project Instructions
+
ChatGPT Work
+
локальная папка кампании
```

## Важные ограничения

### 4.1 Project-only memory не использовать

Для проекта, в котором планируется использовать Work, нельзя рассчитывать на `project-only memory`.

Поэтому:

```text
Project memory = convenience only
Files = authoritative game memory
```

Память ChatGPT не может устанавливать или изменять игровой факт.

Если память модели и локальные файлы расходятся, побеждают локальные файлы.

### 4.2 Desktop Work — основной игровой клиент v1

Полноценная authoritative игра предполагается через desktop Work с доступом к локальной папке кампании.

Web/mobile пока не должны считаться authoritative игровыми клиентами, если они не имеют доступа к той же локальной файловой области.

Не добавлять облачную синхронизацию, GitHub, Google Drive или БД только ради mobile-доступа на первом этапе.

### 4.3 `AGENTS.md` не имеет специальной магии имени

Имя `AGENTS.md` используется как наша собственная конвенция.

Project Instructions должны явно указывать AI:

```text
Перед началом или продолжением игры прочитай AGENTS.md
в локальной папке кампании и следуй ему.
```

Нельзя рассчитывать, что Work автоматически распознаёт имя файла как специальное.

---

# 5. Минимальная структура проекта

Целевая структура v1:

```text
dnd-campaign/
│
├── AGENTS.md
├── CAMPAIGN.md
├── SAVE.md
│
├── journal/
│   ├── 0001.md
│   ├── 0002.md
│   └── ...
│
├── references/
│   └── ...
│
└── backups/
    └── ...
```

Дополнительно, только если capability-test покажет, что это реально удобно и поддерживается:

```text
tools/
└── dice.py
```

На первом этапе `tools/` не является обязательной частью архитектуры.

---

# 6. Источники истины

## 6.1 `AGENTS.md`

Отвечает на вопрос:

> Как AI должен вести игру?

Это operational contract AI Dungeon Master.

Он определяет:

- startup protocol;
- порядок чтения файлов;
- взаимодействие с игроком;
- правила adjudication;
- правила использования D&D rules;
- когда нужен бросок;
- как определять DC;
- как работать с advantage/disadvantage;
- как вести combat;
- как обновлять SAVE;
- как вести journal;
- как работать с DM secrets;
- как сохранять player agency;
- как вести NPC;
- как обрабатывать ошибки;
- как работать при сомнении в правилах;
- как продолжать игру в новом чате;
- какие данные AI имеет право считать authoritative.

`AGENTS.md` не должен хранить настройки конкретной кампании.

---

## 6.2 `CAMPAIGN.md`

Отвечает на вопрос:

> Какую именно кампанию мы играем?

Содержит относительно стабильную конфигурацию:

- rules edition;
- baseline rules source;
- дополнительные разрешённые источники правил;
- setting;
- tone;
- difficulty;
- character death policy;
- leveling method;
- roll visibility;
- narration style;
- combat presentation;
- house rules;
- persistent rulings;
- player preferences;
- content boundaries;
- character creation assumptions.

Пример:

```text
Rules edition: D&D 5th Edition — 2014 rules
Baseline reference: SRD 5.1
Leveling: milestone
Character death: possible
Plot armor: none
Narration: medium detail
Combat: tactical but not excessively verbose
```

---

## 6.3 `SAVE.md`

Отвечает на вопрос:

> Что истинно сейчас?

Это **единственный authoritative snapshot текущей игры**.

Он содержит:

- состояние персонажа;
- HP;
- AC;
- ресурсы;
- spell slots;
- conditions;
- exhaustion;
- inventory;
- деньги;
- consumables;
- текущую локацию;
- current scene;
- game time;
- active combat;
- active quests;
- важные NPC;
- важные мировые flags;
- текущие последствия;
- DM-only secret facts;
- clocks;
- NPC intentions;
- future plans, которые ещё не произошли.

`SAVE.md` важнее:

- Project Memory;
- предыдущих чатов;
- journal;
- воспоминаний AI;
- старых backup-файлов.

При конфликте:

```text
SAVE.md wins
```

---

## 6.4 `journal/`

Отвечает на вопрос:

> Что важного произошло раньше?

Это cold storage истории кампании.

Журнал **не является источником текущего состояния**.

Он нужен для:

- recap;
- поиска старых сюжетных фактов;
- истории NPC;
- воспоминаний;
- долгосрочного continuity;
- поиска ответа на вопросы вроде:
  - когда мы впервые встретили NPC;
  - кто предал группу;
  - когда был найден артефакт;
  - какое решение было принято несколько сессий назад.

Не нужно писать журнал после каждого броска.

Новый чат не обязан читать журнал при запуске.

---

## 6.5 `references/`

Содержит предоставленные игровые материалы и справочники.

Базовое направление:

```text
D&D 5th Edition — 2014 rules
Baseline reference: SRD 5.1
```

Важно:

> SRD 5.1 — не вся D&D 5e 2014.

Если кампания использует материалы за пределами SRD, игрок может предоставить дополнительные rule/reference sources.

AI не обязан читать весь reference corpus каждый ход.

Reference material используется при необходимости.

---

## 6.6 `backups/`

Recovery-only область.

Backup:

- не authoritative;
- не читается в обычной игре;
- не используется для определения текущего состояния;
- нужен только для восстановления после повреждения или ошибочного редактирования `SAVE.md`.

---

# 7. Почему текущий State — Markdown, а не JSON

Для первой версии выбран `SAVE.md`, а не `STATE.json`.

Причины:

1. Игра обслуживается LLM, а не формальной программой.
2. Markdown проще читать и вручную проверять.
3. Markdown менее хрупок при редактировании AI.
4. Нет необходимости вводить JSON Schema.
5. Не требуется формальная сериализация.
6. Уменьшается риск превратить проект в mini-engine.

При необходимости формального machine-readable state это решение можно пересмотреть позднее.

---

# 8. Предлагаемая структура `SAVE.md`

Точная схема ещё не зафиксирована.

Базовый каркас:

```markdown
# Save

## Metadata

## Player Character

### Identity
### Abilities
### Combat
### Resources
### Conditions
### Inventory
### Features
### Spells

## Current Scene

### Location
### Situation
### Visible Entities
### Immediate Dangers
### Recent Context

## Active Combat

## Active Quests

## Active World State

## DM Private State

### Secret Facts
### Clocks
### NPC Intentions
### Plans
```

---

# 9. Важное разделение типов фактов

Внутри save необходимо различать:

## FACT

Уже истинно в мире.

Пример:

```text
Северные ворота разрушены.
```

## SECRET FACT

Уже истинно, но неизвестно игроку.

Пример:

```text
Барон является членом культа.
```

## PLAN

Возможное будущее.

Пример:

```text
Если игрок не вмешается до полуночи,
барон прикажет перевезти пленника.
```

`PLAN` не является произошедшим событием.

AI не имеет права задним числом считать план уже реализованным только потому, что он записан в save.

---

# 10. Почему пока нет отдельных файлов персонажа, мира и NPC

Пока не используем:

```text
CHARACTER.md
WORLD.md
NPCS.md
QUESTS.md
INVENTORY.md
```

Причина — distributed state.

Например, действие:

> Я выпиваю зелье и ухожу из комнаты.

может затронуть:

- HP;
- inventory;
- location;
- world state.

При разбиении на несколько authoritative файлов AI пришлось бы синхронно редактировать несколько источников истины.

На v1 безопаснее:

```text
один SAVE.md = один текущий snapshot
```

Разделять его следует только после появления фактической проблемы размера или стоимости чтения.

---

# 11. Возможная будущая проблема размера SAVE

Если кампания станет очень большой, `SAVE.md` может начать разрастаться:

```text
10 KB
→ 100 KB
→ 500 KB
→ ...
```

В таком случае можно будет вынести cold world data в отдельные файлы, например:

```text
WORLD.md
```

Но это **отложенное решение**.

Не проектировать split заранее без реального evidence.

---

# 12. `journal/` вместо одного `JOURNAL.md`

Решено не использовать один бесконечно растущий файл.

Вместо этого:

```text
journal/
├── 0001.md
├── 0002.md
├── 0003.md
└── ...
```

Каждая запись — короткий checkpoint законченного значимого эпизода.

Пример:

```markdown
# Checkpoint 0017

Game time: 14 Eleasis, evening

## Events

- Entered Blackgate Keep through the eastern culvert.
- Captain Merrow was killed.
- Obtained the cellar key.
- Learned that Elric is being transferred tomorrow.

## Character consequences

- Spent one 2nd-level spell slot.
- Acquired 37 gp.
```

Не нужно дублировать текущее HP, если это просто текущее состояние.

Текущие значения принадлежат `SAVE.md`.

---

# 13. Когда писать journal

Журнал обновляется на естественных checkpoint'ах:

- закончилась важная сцена;
- закончился combat;
- long rest;
- major discovery;
- major quest change;
- завершение крупного эпизода;
- завершение игровой сессии / чата;
- по явной команде игрока.

Не вести journal на каждый ход.

---

# 14. Когда обновлять SAVE

## Обязательно сразу

При механически или сюжетно значимом изменении:

- HP;
- temporary HP;
- spell slots;
- conditions;
- exhaustion;
- consumables;
- ammunition, если она отслеживается;
- inventory;
- деньги;
- active effects;
- game time;
- location;
- combat state;
- initiative;
- quest progress;
- NPC death/disappearance;
- важное отношение;
- мировой flag;
- раскрытый факт;
- level up.

Пример:

```text
Attack
→ Damage 7
→ HP 21 → 14
→ SAVE.md обновляется до следующего игрового действия
```

## Можно не обновлять

Если состояние не изменилось.

Пример:

> Как выглядит статуя?

Если игрок только получил описание, save write не нужен.

---

# 15. Action Resolution Protocol

Базовый цикл одного значимого действия:

```text
Player intent
        ↓
Read relevant current state
        ↓
Determine applicable rule
        ↓
Determine whether a roll is required
        ↓
Determine modifiers / DC / advantage state
        ↓
Roll if required
        ↓
Resolve outcome
        ↓
Update SAVE.md
        ↓
Narrate outcome
```

Критический принцип:

> Сначала определить игровой факт, затем писать художественное описание.

Запрещён подход:

```text
придумать красивый результат
→ подобрать под него механику
```

---

# 16. Броски и случайность

AI не должен подкручивать результат ради сюжета.

Правильный порядок:

```text
определить проверку
→ определить DC
→ определить модификатор
→ определить advantage/disadvantage
→ только потом получить случайный результат
```

Запрещено:

```text
сюжету нужен успех
→ значит выпало 18
```

или:

```text
бой слишком лёгкий
→ у монстра внезапно появилось дополнительное HP
```

---

# 17. `dice.py` пока не является обязательной зависимостью

Ранее планировался:

```text
tools/dice.py
```

Work Preflight завершён 2026-09-07. Обычные команды `python`, `python3` и
`py -3` недоступны, но штатный механизм Workspace Dependencies обнаружил и
успешно запустил встроенный Python 3.12.14. Через стандартный модуль `secrets`
подтверждён алгоритмически честный local random source.

Пока в `AGENTS.md` должен существовать абстрактный:

```text
Random Source
```

До этапа 6 действует следующий порядок:

1. использовать встроенный Python, обнаруживая его штатным механизмом среды;
2. получать случайность через `secrets.randbelow()` только после определения
   типа броска, модификаторов, DC и advantage/disadvantage;
3. если встроенный runtime недоступен, остановить бросок и явно сообщить об
   отсутствии подтверждённого random source.

Отдельный `tools/dice.py` остаётся необязательным удобством. Решение о нём будет
принято на этапе 6 после проверки полного игрового workflow; сам факт наличия
Python не доказывает, что дополнительный файл улучшит надёжность v1.

---

# 18. Когда бросок не нужен

AI не должен бросать d20 на каждое действие.

Правило:

```text
нет значимой неопределённости
→ нет проверки
```

Пример:

> Я открываю незапертую дверь.

Обычно проверки нет.

Но:

> Я пытаюсь бесшумно открыть проржавевшую дверь, пока рядом спит стражник.

Проверка может потребоваться.

---

# 19. Player Agency

AI управляет:

```text
NPC
monsters
environment
consequences
world
```

Игрок управляет:

```text
PC intentions
PC decisions
PC dialogue
```

AI не должен принимать содержательные решения за персонажа игрока.

Плохо:

> Ты бросаешься вперёд и хватаешь дверь.

если игрок этого не говорил.

Хорошо:

> Дверь начинает закрываться. Что ты делаешь?

---

# 20. Не превращать игру в меню

По умолчанию не давать:

```text
1. Идти налево
2. Открыть дверь
3. Вернуться
```

если игрок не попросил варианты.

Предпочтительный стиль:

> Коридор раздваивается. Слева слышна вода, справа виден слабый свет. Что ты делаешь?

Опции допустимы, если игрок прямо спрашивает:

> Какие у меня здесь очевидные варианты?

---

# 21. Правила и спорные случаи

Предлагаемый приоритет:

```text
CAMPAIGN.md explicit house rule / persistent ruling
        ↓
provided campaign reference material
        ↓
SRD 5.1
        ↓
well-established 2014 D&D 5e rule
        ↓
temporary DM ruling
```

Если уверенность низкая, AI не должен уверенно придумывать официальный rule.

Допустимо временное решение:

> Точного подтверждения сейчас не нахожу. Для продолжения сцены применяю временное решение X.

Постоянным house rule оно становится только после явного согласования с игроком.

---

# 22. Открытые и скрытые броски

Базовая рекомендуемая политика:

## Открытые

Большинство бросков PC:

```text
Attack: 12 + 6 = 18 — hit
Damage: 7
```

## Скрытые

Те, где число само раскрывает секрет:

- enemy stealth;
- NPC deception;
- некоторые perception/insight ситуации;
- random encounter checks;
- другие секретные DM rolls.

Конкретная политика задаётся в `CAMPAIGN.md`.

---

# 23. Project Instructions

Project Instructions должны быть короткими.

Они не должны дублировать `AGENTS.md`.

Предварительный смысл:

```text
Ты ведёшь D&D-кампанию через локальную папку кампании.

Перед игровым действием следуй AGENTS.md.

SAVE.md — единственный authoritative источник текущего состояния.
Не используй память, предыдущие чаты или journal как замену SAVE.md.

CAMPAIGN.md определяет правила и настройки кампании.

При открытии нового игрового чата сначала загрузи:
AGENTS.md
CAMPAIGN.md
SAVE.md
```

Полная инструкция будет спроектирована позднее.

---

# 24. Новый чат

Игрок должен иметь возможность открыть новый Work-чат в том же проекте и написать:

> Продолжить игру.

Startup protocol:

```text
1. Read AGENTS.md
2. Read CAMPAIGN.md
3. Read SAVE.md
4. Do not read journal unless needed
5. Continue exactly from Current Scene
```

Новый чат не должен требовать ручного пересказа старой переписки.

---

# 25. ChatGPT memory

Память ChatGPT может помогать повествованию, но никогда не является источником игрового факта.

Правило:

```text
memory may help narration
memory can never establish or override a game fact
```

Если AI «помнит», что NPC мёртв, но `SAVE.md` говорит, что он жив:

```text
SAVE.md wins
```

---

# 26. Backup policy

`SAVE.md` — критический файл, поэтому нужен recovery mechanism.

Пример:

```text
backups/
├── save_0001.md
├── save_0002.md
└── ...
```

Backup создаётся:

- по явной команде;
- перед крупной сессией;
- после крупного сюжетного checkpoint;
- перед потенциально рискованным массовым обновлением save.

Backup не является вторым источником истины.

AI не должен сравнивать его с текущим save при обычной игре.

---

# 27. Ошибка сохранения

Если AI определил игровой результат, который должен изменить state, но не смог записать `SAVE.md`, он не должен молча продолжать.

Принцип:

```text
failed persistence
→ explicitly report
→ do not pretend the turn is safely saved
```

При необходимости восстановить консистентность перед следующим значимым действием.

---

# 28. Возможные meta-команды

Это не DSL и не обязательный интерфейс.

Игрок может всегда говорить естественным языком.

Для удобства можно позже поддержать:

```text
/status
/sheet
/inventory
/recap
/save
/rules <question>
/ooc <message>
/checkpoint
```

Примеры:

```text
/status
```

Показывает актуальные HP/resources/conditions.

```text
/rules sneak attack
```

Временно останавливает повествование и обсуждает правило.

```text
/ooc Сделай сцену менее мрачной.
```

Это meta-настройка, а не действие персонажа.

---

# 29. Что намеренно отложено

Не добавлять без фактической необходимости:

- database;
- Event Store;
- JSONL events;
- replay;
- formal state schema;
- отдельный файл каждого NPC;
- отдельный файл каждой локации;
- separate inventory engine;
- separate quest engine;
- character renderer;
- world simulator;
- embeddings/vector DB;
- Discord;
- VTT;
- облачную инфраструктуру;
- rules engine;
- testing framework;
- git-based autosave;
- production dependencies.

---

# 30. Preflight перед проектированием финальной версии

Перед финальной фиксацией файлов и инструкций нужно один раз проверить реальные возможности desktop Work.

Минимальный acceptance test:

```text
1. Work открывает выбранную campaign folder.

2. Work читает существующий test.md.

3. Work изменяет существующий test.md.

4. Work создаёт новый .md файл.

5. Проверить, может ли Work выполнять Python / random operation.

6. Открыть новый Work-чат в том же Project и проверить,
   что он снова может работать с этой папкой.
```

Особенно важен пункт 5.

Архитектура случайности не должна зависеть от `dice.py`, пока выполнение Python не подтверждено.

---

# 31. Порядок дальнейшей разработки

## Этап 0 — Work Preflight

Проверить реальные capabilities.

Результат:

- подтверждение file read/write;
- подтверждение file create;
- подтверждение поведения нового чата;
- решение по random source;
- решение, нужен ли `dice.py`.

---

## Этап 1 — `SAVE.md` Contract

Спроектировать точный минимальный формат.

Нужно определить:

- обязательные секции;
- что считается current state;
- что такое secret fact;
- что такое plan;
- что не хранится в save;
- какие поля должны обновляться сразу;
- как записывается combat;
- как записываются spell/resources;
- как хранить NPC/world facts;
- как хранить current scene;
- насколько подробно хранить character sheet.

---

## Этап 2 — `AGENTS.md`

Написать полноценный AI DM operational contract:

```text
startup
→ intent
→ rule
→ roll
→ outcome
→ save
→ narration
→ journal checkpoint
```

Отдельно определить:

- player agency;
- combat;
- secrets;
- NPC behavior;
- world continuity;
- rule disputes;
- save failures;
- recovery;
- chat transition;
- use of memory;
- use of references.

---

## Этап 3 — `CAMPAIGN.md`

Зафиксировать:

- edition;
- rules sources;
- house rules;
- persistent rulings;
- tone;
- difficulty;
- death policy;
- narration;
- combat style;
- roll visibility;
- player preferences;
- content boundaries.

---

## Этап 4 — journal format

Определить:

- когда создаётся checkpoint;
- naming scheme;
- минимальный формат;
- что запрещено дублировать;
- когда AI должен искать journal.

---

## Этап 5 — Project Instructions

Сделать короткую bootloader-инструкцию, указывающую на локальные файлы.

---

## Этап 6 — Randomness

По результатам preflight:

### Вариант A

Использовать встроенный доступный Work tool.

### Вариант B

Использовать минимальный dependency-free `tools/dice.py`.

### Вариант C

Согласовать другой fallback.

---

## Этап 7 — Acceptance Test готового продукта

Прогнать искусственную мини-кампанию:

```text
character creation
→ exploration
→ skill check
→ NPC dialogue
→ combat
→ damage
→ healing
→ spell slot use
→ inventory change
→ quest progress
→ long rest
→ rule dispute
→ checkpoint
→ close chat
→ new chat
→ continue campaign
```

Проверить:

- continuity;
- player agency;
- корректность save;
- отсутствие зависимости от старого chat context;
- корректное использование journal;
- отсутствие silent state drift;
- пригодность к реальной игре.

---

# 32. Критерий успеха v1

Проект считается готовым к использованию, если:

1. Игрок может начать кампанию без ручного управления файлами.
2. AI сохраняет значимые изменения состояния.
3. Новый чат продолжает игру только по локальным файлам.
4. История старых приключений доступна без чтения всей переписки.
5. Ошибка памяти AI не может молча переписать текущий state.
6. Игровой процесс остаётся естественным, без DSL и лишнего bookkeeping.
7. Не требуется полноценный Rule Engine.
8. Структура остаётся достаточно простой, чтобы сам AI мог устойчиво её обслуживать.
9. Кампания переживает смену чатов.
10. Игрок может просто играть, а не администрировать систему.

---

# 33. Главный архитектурный принцип проекта

Финальная формулировка:

> **Мы не пытаемся сделать GPT безошибочным Rule Engine. Мы даём GPT-DM минимальную файловую дисциплину, которая защищает наиболее важные вещи: текущее состояние, ресурсы, мир, continuity и переход между чатами.**

Именно поэтому проект должен оставаться значительно проще `ai-dnd-master`.

---

# 34. Статус решений

## Зафиксировано как текущее направление

- отдельный проект от `ai-dnd-master`;
- ChatGPT Work как игровой runtime;
- локальная папка как долговременное хранилище;
- `SAVE.md` как единственный authoritative current state;
- `AGENTS.md` как operational DM contract;
- `CAMPAIGN.md` как конфигурация кампании;
- `journal/` как cold historical storage;
- `references/` как rule/reference material;
- `backups/` как recovery-only storage;
- Markdown вместо JSON на v1;
- Project Memory не authoritative;
- никакого Event Store;
- никакого Rule Engine;
- никакого распределённого authoritative state на первом этапе;
- новый чат должен продолжать игру без ручного пересказа;
- контракт `SAVE.md` v1 зафиксирован в `SAVE_CONTRACT.md`;
- начальный `SAVE.md` существует в однозначном состоянии `setup-required`;
- `CAMPAIGN.md` и его контракт v1 зафиксированы без выдуманных настроек;
- operational DM contract реализован в `AGENTS.md`;
- формат journal checkpoint зафиксирован в `JOURNAL_CONTRACT.md`;
- Project Instructions подготовлены в `PROJECT_INSTRUCTIONS.md`;
- backup и recovery policy зафиксированы в `BACKUP_CONTRACT.md`;
- dependency-free `tools/dice.py` выбран как основной wrapper над
  `secrets.randbelow()`.

## Подтверждено Work Preflight 2026-09-07

- local desktop Work читает, создаёт и изменяет файлы выбранной папки;
- новый local Work-чат получает доступ к той же папке и продолжает состояние
  через файлы без передачи continuity-token в тексте чата;
- встроенный Python 3.12.14 доступен через Workspace Dependencies, хотя команды
  Python из `PATH` отсутствуют;
- `secrets.randbelow()` доступен как надёжный random source для v1.

## Требует дальнейшего проектирования

- настройки и персонаж конкретной кампании через Setup protocol;
- фактический прогон сквозных сценариев из `ACCEPTANCE_TEST.md`;
- исправления, обнаруженные этим прогоном.

## Отложено

- split `SAVE.md` на несколько файлов;
- JSON state;
- schemas;
- отдельные NPC/location files;
- cloud sync;
- mobile-authoritative gameplay;
- formal deterministic rules;
- event log;
- replay;
- database;
- VTT/Discord/infrastructure.

---

# 35. Следующий этап разработки

Этапы 0–6 реализованы. Сквозной план проверки находится в
`ACCEPTANCE_TEST.md`.

Следующий шаг:

> **Этап 7 — Acceptance Test готового продукта**

Нужно подключить текст `PROJECT_INSTRUCTIONS.md` к локальному ChatGPT Project и
прогнать тест в отдельной копии папки. После исправления найденных дефектов
можно запускать Setup protocol уже для настоящей кампании.
