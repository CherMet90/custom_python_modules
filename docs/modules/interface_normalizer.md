# README: Модуль interface_normalizer.py

## Обзор

Модуль `interface_normalizer.py` предоставляет класс `InterfaceNormalizer` для нормализации названий сетевых интерфейсов. Он решает проблему несоответствия форматов названий интерфейсов между различными системами (например, короткие названия в MAC-таблицах, такие как `Po1`, и длинные в инвентарных системах, такие как `Port-channel1`).

Модуль поддерживает популярные паттерны для устройств Cisco, HP/Aruba, Juniper и общие форматы. Он генерирует варианты названий и может искать совпадения в списках интерфейсов.

**Версия:** 1.0 (интегрируется в custom_modules v1.4.0+)

**Зависимости:** Python 3.12+, re (стандартная библиотека), custom_modules.log (для логирования)

## Использование

Импортируйте класс и используйте его методы.

### Основные методы

1. **normalize_interface(interface_name: str, to_long: bool = True) -> List[str]**
   - Генерирует список возможных вариантов названий интерфейса.
   - `to_long=True`: Преобразует в длинный формат (например, `Po1` -> `Port-channel1`).
   - `to_long=False`: Преобразует в короткий формат (например, `Port-channel1` -> `Po1`).
   - Возвращает список, всегда включая исходное название.

2. **find_matching_interface(short_name: str, available_interfaces: List[str]) -> str**
   - Ищет совпадение для заданного названия в списке доступных интерфейсов.
   - Генерирует варианты (длинные и короткие) и возвращает первое совпадение.
   - Если ничего не найдено, возвращает исходное название.

### Примеры

```python
from custom_modules.interface_normalizer import InterfaceNormalizer

# Пример нормализации в длинный формат
variants = InterfaceNormalizer.normalize_interface("Po1", to_long=True)
print(variants)  # ['Po1', 'Port-channel1']

# Пример нормализации в короткий формат
variants = InterfaceNormalizer.normalize_interface("GigabitEthernet1/0/24", to_long=False)
print(variants)  # ['GigabitEthernet1/0/24', 'Gi1/0/24']

# Пример поиска совпадения
available = ["Port-channel1", "GigabitEthernet1/0/1", "Vlan100"]
match = InterfaceNormalizer.find_matching_interface("Po1", available)
print(match)  # 'Port-channel1'

# Если совпадения нет
match = InterfaceNormalizer.find_matching_interface("Unknown", available)
print(match)  # 'Unknown'
```

### Поддерживаемые паттерны

Модуль использует регулярные выражения для mapping. Текущие паттерны:

- **Длинный формат (INTERFACE_MAPPINGS):**
  - `Po(\d+)` -> `Port-channel\1`
  - `Gi(\d+/\d+/\d+)` -> `GigabitEthernet\1`
  - И другие для Te, Fa, Et, Vl, Lo, Trk и т.д.

- **Короткий формат (REVERSE_MAPPINGS):**
  - `Port-channel(\d+)` -> `Po\1`
  - `GigabitEthernet(\d+/\d+/\d+)` -> `Gi\1`
  - И аналогичные.

### Известные ограничения

- Работает только с текстовыми паттернами; не учитывает специфические конфигурации устройств.
- Игнорирует регистр (case-insensitive).
- Если несколько совпадений, возвращает первое найденное.
