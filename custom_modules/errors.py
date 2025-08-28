# custom_modules/errors.py
from custom_modules.color_printer import print_red, print_yellow
from custom_modules.error_aggregator import ErrorAggregator
from custom_modules.log import logger

AGG = ErrorAggregator()  # Singleton

# --- Helper-функция для уведомлений ---
def _notify_deprecated(old_api: str, new_api: str):
    """Формирует и логирует предупреждение об устаревшем API."""
    msg = (
        f"{old_api} is deprecated and will be removed in version 2.0. "
        f"Use {new_api} instead."
    )
    logger.warning("DEPRECATED: %s", msg)

# --- Класс Error ---
class Error(Exception):
    """Базовый класс для критических ошибок."""
    category = "critical"
    _error_messages = []  # Устаревшее хранилище для совместимости

    def __init__(self, message, ip=None):
        super().__init__(message)
        print_red(f"CriticalError: {message}")
        if ip is not None:
            self.store_error(ip, message)

    @classmethod
    def store_error(cls, ip, message):
        AGG.add(cls.category, ip, str(message))
        cls._error_messages.append({ip: str(message)})  # Дублирование для совместимости

    @classmethod
    @property
    def error_messages(cls):
        """
        DEPRECATED! Используйте ErrorAggregator()._errors['critical'].
        Оставлено для обратной совместимости. Будет удалено в версии 2.0.
        """
        _notify_deprecated(
            "Error.error_messages",
            "ErrorAggregator()._errors['critical']"
        )
        return [{ip: msg} for ip, msg in AGG._errors.get(cls.category, {}).items()]

# --- Класс NonCriticalError ---
class NonCriticalError(Error):
    """Класс для некритических (warning) ошибок."""
    category = "non_critical"
    _error_messages = []  # Устаревшее хранилище для совместимости

    def __init__(self, message, ip=None, calling_function=None):
        if calling_function:
            message = f"{calling_function} failed: {message}"
        Exception.__init__(self, message)
        print_yellow(f"NonCriticalError: {message}")
        if ip is not None:
            self.store_error(ip, message)

    # store_error наследуется от Error и корректно использует cls.category

    @classmethod
    @property
    def error_messages(cls):
        """
        DEPRECATED! Используйте ErrorAggregator()._errors['non_critical'].
        Оставлено для обратной совместимости. Будет удалено в версии 2.0.
        """
        _notify_deprecated(
            "NonCriticalError.error_messages",
            "ErrorAggregator()._errors['non_critical']"
        )
        return [{ip: msg} for ip, msg in AGG._errors.get(cls.category, {}).items()]