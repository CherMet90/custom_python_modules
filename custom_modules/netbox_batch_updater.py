from collections import defaultdict
from itertools import islice
from typing import Dict, Tuple, Any, List

from custom_modules.log import logger
from custom_modules.interface_normalizer import InterfaceNormalizer
from custom_modules.netbox_connector import NetboxDevice


class NetboxBatchUpdater:
    """
    Очередь и пакетное обновление интерфейсов NetBox.
    Используется как контекст-менеджер:
        with NetboxBatchUpdater(batch_size=200) as upd:
            upd.queue(...)
            upd.flush()
    """
    def __init__(self, batch_size: int = 200, overwrite_existing: bool = False):
        self.nb = NetboxDevice.netbox_connection        # готовый pynetbox.api
        self.batch_size = batch_size
        self.overwrite_existing = overwrite_existing

        self._device_cache: Dict[str, Dict[str, Any]] = {}
        self._pending: Dict[Tuple[int, int], str] = {}  # (dev_id, if_id) -> descr
        self.stats = defaultdict(int)

    # ---------- Context ----------
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # автоматически отправляем, если забыли вызвать flush()
        try:
            self.flush()
        except Exception as e:
            logger.error(f"BatchUpdater flush error in __exit__: {e}")

    # ---------- Public ----------
    def queue(self, device_name: str, if_name: str, new_descr: str):
        """
        Ставит изменение в очередь. Никаких HTTP-вызовов, кроме возможного
        единичного bulk-GET всех интерфейсов устройства.
        """
        if not device_name or not if_name:
            logger.warning(f"Invalid parameters: device_name='{device_name}', if_name='{if_name}'")
            self.stats['failed'] += 1
            return

        iface = self._get_interface(device_name, if_name)
        if not iface:
            self.stats['not_found'] += 1
            return

        # overwrite check
        if not self.overwrite_existing and (iface.description or '').strip():
            self.stats['skipped'] += 1
            return

        # no change
        if iface.description == new_descr:
            self.stats['unchanged'] += 1
            return

        key = (iface.device.id, iface.id)
        self._pending[key] = new_descr

    def flush(self):
        """Отправить queued изменения пачками используя стандартный bulk update."""
        if not self._pending:
            return

        logger.debug(f"Flushing {len(self._pending)} pending updates in batches of {self.batch_size}")

        iterator = iter(self._pending.items())
        batch_num = 0

        while True:
            chunk = list(islice(iterator, self.batch_size))
            if not chunk:
                break

            batch_num += 1
            payload = [
                {'id': if_id, 'description': desc}
                for (_dev_id, if_id), desc in chunk
            ]

            try:
                logger.debug(f"Batch {batch_num}: updating {len(chunk)} interfaces")

                # Используем стандартный bulk update без query параметров
                self.nb.dcim.interfaces.update(payload)

                self.stats['updated'] += len(chunk)
                logger.debug(f"Batch {batch_num}: successfully updated {len(chunk)} interfaces")

            except Exception as e:
                logger.error(f"Batch {batch_num}: bulk update failed for {len(chunk)} interfaces: {e}")
                self.stats['failed'] += len(chunk)

        self._pending.clear()
        logger.info(f"NetBox bulk-update completed: {dict(self.stats)}")

    # ---------- Helpers ----------
    def _get_interface(self, dev_name: str, if_name: str):
        # Получаем/кэшируем интерфейсы устройства
        cache = self._device_cache.get(dev_name)
        if cache is None:
            dev = self.nb.dcim.devices.get(name=dev_name)
            if not dev:
                logger.warning(f"Device {dev_name} not found in NetBox")
                self._device_cache[dev_name] = {}
                return None
            interfaces = self.nb.dcim.interfaces.filter(device_id=dev.id, limit=0)
            cache = {i.name: i for i in interfaces}
            self._device_cache[dev_name] = cache

        # нормализация имени — повторяем логику InterfaceNormalizer
        variants = InterfaceNormalizer.normalize_interface(if_name, to_long=True)
        variants.extend(InterfaceNormalizer.normalize_interface(if_name, to_long=False))
        variants = list(dict.fromkeys(variants))        # unique & ordered

        for v in variants:
            iface = cache.get(v)
            if iface:
                return iface
        return None