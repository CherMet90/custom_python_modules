from collections import defaultdict
import json
import atexit
import os
from pathlib import Path
from prettytable import PrettyTable
from custom_modules.log import logger

class ErrorAggregator:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.reset()
            atexit.register(cls._instance.render)  # Auto-render on exit
        return cls._instance

    def reset(self):
        self._errors = defaultdict(dict)
        self._stats = defaultdict(int)
        self._already_rendered = False

    def add(self, category: str, ip: str, message: str):
        self._errors[category][ip] = message

    def inc(self, metric: str, delta: int = 1):
        self._stats[metric] += delta

    def render(self):
        if self._already_rendered or os.getenv('DISABLE_ERROR_AGGREGATOR'):
            return
        self._already_rendered = True
        self._pretty_print()
        self._dump_json()

    def _truncate_message(self, message: str, max_length: int = 200) -> str:
        """Обрезает длинные сообщения для читаемого вывода в таблице."""
        if len(message) > max_length:
            return message[:max_length] + "... [truncated]"
        return message

    def _pretty_print(self):
        # [Implementation as in proposal]
        tbl = PrettyTable(["Metric", "Value"])
        for k, v in self._stats.items():
            tbl.add_row([k, v])
        logger.info("\n===== WORKFLOW SUMMARY =====\n%s", tbl)

        for cat, data in self._errors.items():
            if not data:
                continue
            col_name = f"{cat.title()} Error"
            subtbl = PrettyTable(["Device", col_name])
            subtbl.align["Device"] = "l"
            subtbl.align[f"{cat.title()} Error"] = "l"
            subtbl.max_width = 75
            subtbl.valign[f"{cat.title()} Error"] = "t"

            for ip, msg in data.items():
                truncated_msg = self._truncate_message(msg)
                subtbl.add_row([ip, truncated_msg])

                # Логируем полное сообщение только если оно было обрезано
                if len(msg) > 200:
                    logger.debug(f"Full {cat} error for {ip}: {msg}")

            log_method = logger.error if cat == "critical" else logger.warning
            log_method("\n%s ERRORS:\n%s", cat.upper(), subtbl)

    def _dump_json(self):
        summary = {"stats": dict(self._stats), "errors": dict(self._errors)}
        Path("error_summary.json").write_text(json.dumps(summary, indent=2))