from prettytable import PrettyTable

from custom_modules.errors import Error, NonCriticalError
from custom_modules.log import logger


def _pretty_table(data: dict, header: str) -> PrettyTable:
    """Возвращает отформатированную таблицу по словарю {device: message}."""
    tbl = PrettyTable(["Device", header])
    tbl.align["Device"] = "l"
    tbl.align[header] = "l"
    tbl.max_width = 75
    tbl.valign[header] = "t"
    for ip, msg in data.items():
        tbl.add_row([ip, msg])
    return tbl

def print_errors():
    logger.info('The work is completed')

    # кортежи: (список-хранилище, заголовок столбца, метод логгера)
    groups = [
        (NonCriticalError.error_messages, "Non-Critical Error", logger.warning),
        (Error.error_messages,        "Critical Error",     logger.error),
    ]

    for storage, column_header, log_method in groups:
        if not storage:
            continue                               # ничего выводить
        flat = {k: v for d in storage for k, v in d.items()}
        log_method("\n%s", _pretty_table(flat, column_header))