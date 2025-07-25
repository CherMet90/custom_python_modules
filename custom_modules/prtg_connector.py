import os
import requests
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
import urllib3

from custom_modules.log import logger
from custom_modules.errors import Error

@dataclass
class DeviceConfig:
    """Dataclass для хранения конфигурации устройства."""
    act: str
    ip_device: str
    community: str
    site_slug: str
    role: str
    vm: str
    snmp: str
    model_oid: str
    status: str

class PRTGConnector:
    def __init__(self, prtg_url: str = None, api_token: str = None):
        """
        Инициализирует коннектор для работы с PRTG API.

        Args:
            prtg_url: URL сервера PRTG (если не указан, берется из PRTG_URL)
            api_token: API токен (если не указан, берется из PRTG_API_TOKEN)
        """
        load_dotenv()
        self.prtg_url = prtg_url or os.getenv("PRTG_URL")
        self.api_token = api_token or os.getenv("PRTG_API_TOKEN")
        if not self.prtg_url or not self.api_token:
            raise ValueError("PRTG_URL and PRTG_API_TOKEN must be provided.")
        
        # Преобразуем строковое значение из env в boolean
        verify_ssl_str = os.getenv("PRTG_VERIFY_SSL", "true").lower()
        self.verify_ssl = verify_ssl_str in ("true", "1", "yes", "on")
        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.warning("SSL verification is disabled for PRTG connection")

    def get_devices(self, tag_mapping: Dict, defaults: Dict, 
                    import_tag: str = None, exclude_tag: str = None) -> List[Dict]:
        """
        Получает и обрабатывает устройства из PRTG.

        :param tag_mapping: Словарь маппинга тегов на свойства устройств
        :param defaults: Словарь значений по умолчанию
        :param import_tag: Тег для импорта устройств (если None, берется из переменных окружения)
        :param exclude_tag: Тег для исключения устройств (если None, берется из переменных окружения)
        :return: Список обработанных устройств
        """
        # Получаем теги из аргументов или переменных окружения
        import_tag = import_tag or os.getenv("PRTG_IMPORT_TAG")
        exclude_tag = exclude_tag or os.getenv("PRTG_EXCLUDE_TAG")

        if not import_tag:
            raise ValueError("import_tag must be provided either as argument or PRTG_IMPORT_TAG environment variable")

        try:
            response = requests.get(
                f"{self.prtg_url}/api/table.json",
                params={
                    'content': 'devices',
                    'columns': 'objid,device,host,tags,status',
                    'apitoken': self.api_token
                },
                verify=self.verify_ssl
            )
            response.raise_for_status()
            devices_data = response.json().get('devices', [])
            logger.info(f"Retrieved {len(devices_data)} devices from PRTG.")

            processed_devices = []
            excluded_count = 0
            
            for device in devices_data:
                device_tags = self._parse_tags(device.get('tags', ''))

                # Проверяем наличие тегов обработки
                if import_tag not in device_tags:
                    continue
                if exclude_tag and exclude_tag in device_tags:
                    excluded_count += 1
                    logger.debug(f"Device {device.get('device', 'Unknown')} excluded by {exclude_tag} tag")
                    continue

                config_data = defaults.copy()                                   # Применяем дефолты
                self._apply_tag_mapping(device_tags, config_data, tag_mapping)  # Обрабатываем теги PRTG
                # Информация об устройстве по данным PRTG
                config_data.update({
                    'ip_device': device.get('host', ''),
                    'status': str(device.get('status_raw', 0))
                })
                device_config = DeviceConfig(**config_data)
                processed_devices.append(asdict(device_config))

            logger.info(f"Processed {len(processed_devices)} devices with {import_tag} tag.")
            if excluded_count > 0:
                logger.info(f"Excluded {excluded_count} devices with {exclude_tag} tag.")

            return processed_devices

        except requests.RequestException as e:
            raise Error(f"Failed to connect to PRTG API: {e}")
        except Exception as e:
            raise Error(f"Error processing PRTG devices: {e}")

    def _apply_tag_mapping(self, device_tags: List[str], config_data: Dict, tag_mapping: Dict) -> None:
        """Применяет маппинг тегов к конфигурации устройства."""
        for prop, mappings in tag_mapping.items():
            for tag in device_tags:
                if tag in mappings:
                    config_data[prop] = mappings[tag]
                    break

    def _parse_tags(self, tags_string: str) -> List[str]:
        """Парсит строку тегов в список."""
        if not tags_string:
            return []
        return [tag.strip().lower() for tag in tags_string.split() if tag.strip()]
