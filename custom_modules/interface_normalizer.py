import re
from typing import Dict, List, Tuple
from custom_modules.log import logger

class InterfaceNormalizer:
    """
    Класс для нормализации названий интерфейсов между различными форматами.
    """

    # Mapping коротких названий в полные
    INTERFACE_MAPPINGS = {
        # Cisco patterns
        r'^Po(\d+)$': r'Port-channel\1',
        r'^Gi(\d+/\d+/\d+)$': r'GigabitEthernet\1',
        r'^Gi(\d+/\d+)$': r'GigabitEthernet\1', 
        r'^Gi(\d+)$': r'GigabitEthernet\1',
        r'^Te(\d+/\d+/\d+)$': r'TenGigabitEthernet\1',
        r'^Te(\d+/\d+)$': r'TenGigabitEthernet\1',
        r'^Te(\d+)$': r'TenGigabitEthernet\1',
        r'^Fa(\d+/\d+)$': r'FastEthernet\1',
        r'^Fa(\d+)$': r'FastEthernet\1',
        r'^Et(\d+/\d+/\d+)$': r'Ethernet\1',
        r'^Et(\d+/\d+)$': r'Ethernet\1',
        r'^Et(\d+)$': r'Ethernet\1',
        r'^Vl(\d+)$': r'Vlan\1',
        r'^Lo(\d+)$': r'Loopback\1',

        # HP/Aruba patterns  
        r'^(\d+)$': r'Port\1',
        r'^Trk(\d+)$': r'Trunk\1',

        # Juniper patterns
        r'^ge-(\d+/\d+/\d+)$': r'GigabitEthernet\1',
        r'^xe-(\d+/\d+/\d+)$': r'TenGigabitEthernet\1',

        # Generic patterns
        r'^(\d+/\d+/\d+)$': r'Ethernet\1',
        r'^(\d+/\d+)$': r'Ethernet\1',
    }

    # Обратный mapping (полные в короткие)
    REVERSE_MAPPINGS = {
        r'^Port-channel(\d+)$': r'Po\1',
        r'^GigabitEthernet(\d+/\d+/\d+)$': r'Gi\1',
        r'^GigabitEthernet(\d+/\d+)$': r'Gi\1',
        r'^GigabitEthernet(\d+)$': r'Gi\1',
        r'^TenGigabitEthernet(\d+/\d+/\d+)$': r'Te\1',
        r'^TenGigabitEthernet(\d+/\d+)$': r'Te\1',
        r'^TenGigabitEthernet(\d+)$': r'Te\1',
        r'^FastEthernet(\d+/\d+)$': r'Fa\1',
        r'^FastEthernet(\d+)$': r'Fa\1',
        r'^Ethernet(\d+/\d+/\d+)$': r'Et\1',
        r'^Ethernet(\d+/\d+)$': r'Et\1',
        r'^Ethernet(\d+)$': r'Et\1',
        r'^Vlan(\d+)$': r'Vl\1',
        r'^Loopback(\d+)$': r'Lo\1',
    }

    @classmethod
    def normalize_interface(cls, interface_name: str, to_long: bool = True) -> List[str]:
        """
        Нормализует название интерфейса, возвращая список возможных вариантов.

        Args:
            interface_name: Исходное название интерфейса
            to_long: True для преобразования в длинный формат, False для короткого

        Returns:
            List[str]: Список возможных вариантов названия интерфейса
        """
        variants = [interface_name]  # Всегда включаем исходное название

        mappings = cls.INTERFACE_MAPPINGS if to_long else cls.REVERSE_MAPPINGS

        for pattern, replacement in mappings.items():
            match = re.match(pattern, interface_name, re.IGNORECASE)
            if match:
                try:
                    normalized = re.sub(pattern, replacement, interface_name, flags=re.IGNORECASE)
                    if normalized != interface_name and normalized not in variants:
                        variants.append(normalized)
                except re.error as e:
                    logger.warning(f"Regex error in interface normalization: {e}")
                    continue

        return variants

    @classmethod
    def find_matching_interface(cls, short_name: str, available_interfaces: List[str]) -> str:
        """
        Находит соответствующий интерфейс в списке доступных.

        Args:
            short_name: Короткое название из MAC-таблицы
            available_interfaces: Список интерфейсов из NetBox

        Returns:
            str: Найденный интерфейс или исходное короткое название
        """
        # Сначала точное совпадение
        if short_name in available_interfaces:
            return short_name

        # Генерируем варианты длинных названий
        long_variants = cls.normalize_interface(short_name, to_long=True)

        for variant in long_variants:
            if variant in available_interfaces:
                logger.debug(f"Interface mapping: {short_name} -> {variant}")
                return variant

        # Если не нашли, попробуем обратное преобразование
        # (на случай если в MAC-таблице длинное название, а в NetBox короткое)
        short_variants = cls.normalize_interface(short_name, to_long=False)

        for variant in short_variants:
            if variant in available_interfaces:
                logger.debug(f"Interface mapping: {short_name} -> {variant}")
                return variant

        # Если ничего не нашли, возвращаем исходное название
        logger.debug(f"No interface mapping found for: {short_name}")
        return short_name