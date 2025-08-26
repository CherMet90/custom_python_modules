# custom_modules/tasks/dispatcher.py
# ──────────────────────────────────────────────────────────────────────────────
"""
Универсальный dispatcher «всё-в-одном».

Поддерживает:
1.  Произвольные pre/post-команды (exec-mode и config-mode) ─ блок `hooks`
2.  Автоматическую пагинацию ─ блок `pagination`
3.  Обычный send_command, если ничего из выше перечисленного не задано.

Блоки в inventory (обычно приходят из platform_parsers.yaml → platform_config):

data:
  platform_config:
    hooks:
      pre_exec:  ["terminal length 0"]
      pre_cfg:   ["conf t", "no logging console", "end"]
      post_cfg:  ["conf t", "logging console", "end"]
      post_exec: ["wr mem"]         # пример
    pagination:
      prompt_pattern: "--More--"
      response: " "
      max_pages: 250
"""
# ──────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from typing import Iterable, Sequence, List

from nornir.core.task import Task, Result
from nornir_netmiko.tasks import netmiko_send_command, netmiko_send_config

from .auto_paging import auto_paging_fast
from custom_modules.log import logger


# ──────────────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ──────────────────────────────────────────────────────────────────────────────
def _to_list(obj: str | Iterable[str] | None) -> List[str]:
    """Преобразует вход (None|str|Iterable[str]) в список строк."""
    if obj is None:
        return []
    return [obj] if isinstance(obj, str) else list(obj)


def _run_exec(task: Task, commands: Sequence[str], name: str) -> None:
    if not commands:
        return
    logger.debug(f"{task.host.name}: exec {commands}")
    task.run(
        task=netmiko_send_command,
        command_string="\n".join(commands),
        name=name,
    )


def _run_cfg(task: Task, commands: Sequence[str], name: str) -> None:
    if not commands:
        return
    logger.debug(f"{task.host.name}: cfg  {commands}")
    task.run(
        task=netmiko_send_config,
        config_commands=list(commands),
        name=name,
    )


# ──────────────────────────────────────────────────────────────────────────────
# ОСНОВНОЙ DISPATCHER
# ──────────────────────────────────────────────────────────────────────────────
def dynamic_send_command(
    task: Task,
    command: str,
    **kwargs,
) -> Result:
    """
    Выполняет команду с учётом:
    • hooks.pre_exec / hooks.pre_cfg
    • hooks.post_cfg / hooks.post_exec
    • pagination

    Если блоков hooks/pagination нет – ведёт себя как обычный
    netmiko_send_command.
    """
    host_data = task.host.data or {}
    pcfg = host_data.get("platform_config", {})

    hooks = pcfg.get("hooks", {})
    pg    = pcfg.get("pagination")

    # Пре-/пост-команды
    pre_exec  = _to_list(hooks.get("pre_exec"))
    pre_cfg   = _to_list(hooks.get("pre_cfg"))
    post_cfg  = _to_list(hooks.get("post_cfg"))
    post_exec = _to_list(hooks.get("post_exec"))

    use_paging = pg is not None

    try:
        # ─── PRE ────────────────────────────────────────────────
        _run_exec(task, pre_exec,  "pre_exec")
        _run_cfg(task,  pre_cfg,   "pre_cfg")

        # ─── MAIN ───────────────────────────────────────────────
        if use_paging:
            result = auto_paging_fast(
                task=task,
                command=command,
                prompt_pattern=pg.get("prompt_pattern", r"--More--"),
                response=pg.get("response", " "),
                idle_timeout=pg.get("idle_timeout", 3.0),
                max_total=pg.get("max_total", 60.0),
                max_pages=pg.get("max_pages", 200),
                **kwargs,
            )
        else:
            result = netmiko_send_command(
                task=task,
                command_string=command,
                **kwargs,
            )

    finally:
        # ─── POST (выполняется всегда) ─────────────────────────
        _run_cfg(task,  post_cfg,  "post_cfg")
        _run_exec(task, post_exec, "post_exec")

    # Если hooks не использовались и не было пагинации,
    # task.run вернет Result. В остальных случаях auto_paging_fast
    # или netmiko_send_command уже вернули Result.
    if isinstance(result, Result):
        return result

    # safety-net (не должно случаться)
    return Result(host=task.host, failed=True, result="No result from command")