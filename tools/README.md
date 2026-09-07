# Dice Tool

`dice.py` получает честные локальные броски через стандартный модуль Python
`secrets` и выводит результат в JSON без внешних зависимостей.

Примеры после обнаружения доступного Python runtime:

```text
<python> tools/dice.py 1d20+5
<python> tools/dice.py 1d20+5 --mode advantage
<python> tools/dice.py 2d6+3
```

Поля `rolls` содержат все исходные значения, `kept` — применённые значения,
`total` — итог с модификатором. Advantage/disadvantage разрешены только для
`1d20`.

Путь к Python нельзя закреплять в campaign-файлах: runtime должен обнаруживать
встроенный интерпретатор штатным механизмом текущей среды.
