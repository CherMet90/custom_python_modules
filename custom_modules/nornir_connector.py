# custom_modules/nornir_connector.py
from __future__ import annotations
import os

from typing import Dict, Any, Optional, List
from nornir import InitNornir
from nornir.core import Nornir
from nornir_netmiko.tasks import netmiko_send_command

from custom_modules.log import logger
from custom_modules.errors import Error
from custom_modules.tasks.dispatcher import dynamic_send_command


class NornirConnector:
    """
    Обертка над InitNornir.
    Позволяет инициализировать Nornir из Python-словаря,
    не требуя YAML-файлов.
    """

    def __init__(
        self,
        hosts_dict: Dict[str, Dict[str, Any]],
        *,
        num_workers: int = 10,
        log_level: str = "INFO",
        inventory_plugin: str = "DictInventory",
        connect_timeout: int = 30,
        command_timeout: int = 60,
    ) -> None:
        """Инициализация NornirConnector с заданными параметрами."""
        if not hosts_dict:
            raise Error("Nornir inventory is empty – nothing to connect")

        # Регистрируем плагин DictInventory
        try:
            from nornir.core.plugins.inventory import InventoryPluginRegister
            from nornir_salt.plugins.inventory import DictInventory
            InventoryPluginRegister.register("DictInventory", DictInventory)
        except ImportError as e:
            raise Error(f"Failed to import DictInventory plugin. Install 'nornir-salt': {e}")

        # Добавляем дефолтные настройки соединения ко всем хостам
        enriched_hosts = {}
        for hostname, host_data in hosts_dict.items():
            enriched_host = host_data.copy()
            # Устанавливаем дефолты, если не заданы
            enriched_host.setdefault("data", {}).update({
                "connect_timeout": connect_timeout,
                "command_timeout": command_timeout,
            })

            # Обрабатываем connection_options для Netmiko (fast_cli, session_log и др.)
            if "connection_options" in host_data:
                conn_opts = host_data["connection_options"]
                if isinstance(conn_opts, dict) and "netmiko" in conn_opts:
                    # Убеждаемся, что connection_options корректно структурированы
                    netmiko_opts = conn_opts["netmiko"]
                    if isinstance(netmiko_opts, dict):
                        # Дополнительная проверка extras
                        extras = netmiko_opts.get("extras", {})
                        if isinstance(extras, dict):
                            logger.debug(f"Host {hostname}: applying Netmiko connection options with {len(extras)} extras")
                        else:
                            logger.warning(f"Host {hostname}: extras in netmiko options is not a dict")
                        # connection_options уже скопированы через host_data.copy()
                    else:
                        logger.warning(f"Host {hostname}: invalid netmiko connection_options format, ignoring")
                else:
                    logger.warning(f"Host {hostname}: invalid connection_options format, ignoring")

            enriched_hosts[hostname] = enriched_host

        # Конфигурация Nornir
        nornir_settings = {
            "runner": {
                "plugin": "threaded", 
                "options": {"num_workers": num_workers}
            },
            "inventory": {
                "plugin": "DictInventory",
                "options": {
                    "hosts": enriched_hosts,
                    "groups": {},
                    "defaults": {},
                },
            },
            "logging": {
                "enabled": True,
                "level": log_level,
                "to_console": False,
                "log_file": "nornir.log",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        }

        try:
            self._nornir = InitNornir(**nornir_settings)
            logger.info(
                f"Nornir initialized with {len(enriched_hosts)} hosts, "
                f"{num_workers} workers ({inventory_plugin})"
            )
        except Exception as e:
            raise Error(f"Failed to initialize Nornir: {e}")

    @staticmethod
    def _get_netmiko_opts(host_obj):
        """
        Безопасное извлечение netmiko connection_options из host объекта.

        Args:
            host_obj: Nornir host object

        Returns:
            ConnectionOptions object или None если не найден
        """
        try:
            conn_opts = getattr(host_obj, 'connection_options', None)
            if not conn_opts:
                return None
            return conn_opts["netmiko"]
        except (KeyError, TypeError, AttributeError):
            return None

    def run_commands(
        self, 
        command: str, 
        hosts: Optional[List[str]] = None,
        **netmiko_kwargs
    ) -> Dict[str, Dict[str, Any]]:
        """
        Выполняет команду на указанных хостах через универсальный dispatcher.

        Dispatcher автоматически определяет необходимость:
        - pre/post команд (hooks)
        - авто-пагинации (pagination)
        - обычного выполнения команды
        """

        # Фильтруем хосты, если указаны
        nr = self._nornir
        if hosts:
            available_hosts = set(nr.inventory.hosts.keys())
            requested_hosts = set(hosts)
            valid_hosts = requested_hosts & available_hosts
            missing_hosts = requested_hosts - available_hosts

            if missing_hosts:
                logger.warning(f"Hosts not found in inventory: {missing_hosts}")

            if not valid_hosts:
                logger.error(f"No valid hosts found for command execution. Skipping command '{command}'.")
                return {command: {}}

            logger.debug(f"Found {len(valid_hosts)} valid hosts: {sorted(list(valid_hosts))}")

            nr = nr.filter(filter_func=lambda host: host.name in valid_hosts)

            # Проверяем результат фильтрации
            filtered_count = len(nr.inventory.hosts)
            logger.debug(f"After filtering: {filtered_count} hosts remaining")

            if filtered_count == 0:
                logger.error(f"Filter resulted in 0 hosts. This shouldn't happen if valid_hosts was not empty.")
                return {command: {}}

        # Выполняем команду через универсальный dispatcher
        logger.info(f"Executing command '{command}' on {len(nr.inventory.hosts)} hosts using dynamic dispatcher")

        try:
            # ОДИН вызов .run() для ВСЕХ хостов
            result = nr.run(
                task=dynamic_send_command,
                command=command,
                **netmiko_kwargs
            )

            # Преобразуем результаты в удобный формат
            formatted_results = {}
            for hostname, task_result in result.items():
                if task_result.failed:
                    error_msg = str(task_result.exception) if task_result.exception else "Unknown error"
                    formatted_results[hostname] = f"ERROR: {error_msg}"
                    logger.error(f"Command failed on {hostname}: {error_msg}")
                else:
                    formatted_results[hostname] = task_result.result
                    logger.debug(f"Command succeeded on {hostname}")

            logger.info(f"Command execution completed. Success: {len([r for r in formatted_results.values() if not str(r).startswith('ERROR:')])}, Failed: {len([r for r in formatted_results.values() if str(r).startswith('ERROR:')])}")

            return {command: formatted_results}

        except Exception as e:
            logger.error(f"Failed to execute command '{command}': {str(e)}")
            raise Error(f"Command execution failed: {e}")

    def close_connections(self) -> None:
        """Закрывает все активные подключения."""
        try:
            self._nornir.close_connections()
            logger.info("All Nornir connections closed")
        except Exception as e:
            logger.warning(f"Error closing connections: {str(e)}")

    def get_inventory_summary(self) -> Dict[str, Any]:
        """Возвращает сводку по текущему инвентарю."""
        hosts = self._nornir.inventory.hosts
        platforms = {}
        sites = {}

        for hostname, host_obj in hosts.items():
            platform = getattr(host_obj, 'platform', 'unknown')
            site = getattr(host_obj, 'data', {}).get('site', 'unknown')

            platforms[platform] = platforms.get(platform, 0) + 1
            sites[site] = sites.get(site, 0) + 1

        return {
            "status": "initialized",
            "total_hosts": len(hosts),
            "platforms": platforms,
            "sites": sites,
            "hosts": list(hosts.keys())
        }

    def get_session_logs_info(self) -> Dict[str, Any]:
        """
        Возвращает информацию о файлах session_log для анализа проблем подключения.

        Returns:
            Dict с информацией о session log файлах для каждого хоста
        """
        session_info = {}

        for hostname, host_obj in self._nornir.inventory.hosts.items():
            netmiko_opts = self._get_netmiko_opts(host_obj)
            if netmiko_opts:
                extras = getattr(netmiko_opts, 'extras', {})
                if isinstance(extras, dict) and 'session_log' in extras:
                    log_path = extras['session_log']
                    session_info[hostname] = {
                        'log_file': log_path,
                        'exists': os.path.exists(log_path),
                        'size': os.path.getsize(log_path) if os.path.exists(log_path) else 0
                    }

        return session_info

    def __del__(self):
        """Автоматическая очистка при уничтожении объекта."""
        self.close_connections()