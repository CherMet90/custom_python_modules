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

    def _pretty_print(self):
        # [Implementation as in proposal]
        tbl = PrettyTable(["Metric", "Value"])
        for k, v in self._stats.items():
            tbl.add_row([k, v])
        logger.info("\n===== WORKFLOW SUMMARY =====\n%s", tbl)

        for cat, data in self._errors.items():
            if not data:
                continue
            subtbl = PrettyTable(["Device", f"{cat.title()} Error"])
            for ip, msg in data.items():
                subtbl.add_row([ip, msg])
            logger.warning("\n%s ERRORS:\n%s", cat.upper(), subtbl)

    def _dump_json(self):
        summary = {"stats": dict(self._stats), "errors": dict(self._errors)}
        Path("error_summary.json").write_text(json.dumps(summary, indent=2))