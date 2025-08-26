import re
import time
from nornir.core.task import Task, Result
from custom_modules.log import logger

def auto_paging_fast(
    task: Task,
    command: str,
    prompt_pattern: str = r"--More--",
    response: str = " ",
    idle_timeout: float = 3.0,
    max_total: float = 60.0,
    sleep_step: float = 0.2,
    max_pages: int = 200,
    **netmiko_kwargs,
) -> Result:
    """
    Быстрая версия auto-paging с idle timeout вместо общего таймаута.
    Завершается сразу после получения всех данных.
    """
    try:
        conn = task.host.get_connection("netmiko", task.nornir.config)
        conn.read_channel()  # Очищаем буфер

        logger.debug(f"Sending command to {task.host.name}: {command}")
        conn.write_channel(command + "\n")

        full_output = ""
        pages_processed = 0
        start_time = time.time()
        last_data_time = start_time

        while True:
            # Читаем данные из канала
            partial_output = conn.read_channel()

            if partial_output:
                full_output += partial_output
                last_data_time = time.time()  # Сбрасываем idle таймер
                logger.debug(f"Received data from {task.host.name} (len={len(partial_output)})")

                # Проверка на пагинацию
                if re.search(prompt_pattern, full_output):
                    logger.debug(f"Pagination prompt found on {task.host.name}")
                    full_output = re.sub(prompt_pattern, "", full_output)
                    conn.write_channel(response)
                    pages_processed += 1
                    if pages_processed >= max_pages:
                        raise RuntimeError(f"Pagination overflow: {max_pages} pages")
                    continue

                # Проверка на финальный промпт
                tail_lines = "\n".join(full_output.splitlines()[-2:])
                if re.search(conn.base_prompt, tail_lines):
                    logger.debug(f"Base prompt found on {task.host.name}")
                    break

            # Проверка таймаутов
            current_time = time.time()
            idle_time = current_time - last_data_time
            total_time = current_time - start_time

            if idle_time > idle_timeout:
                logger.debug(f"Idle timeout ({idle_timeout}s) reached on {task.host.name}")
                break

            if total_time > max_total:
                raise TimeoutError(f"Maximum total time ({max_total}s) exceeded")

            time.sleep(sleep_step)

        # Очистка от финального промпта
        full_output = re.sub(conn.base_prompt + r".*$", "", full_output, flags=re.MULTILINE).strip()

        logger.info(f"Auto-paging completed on {task.host.name}: {pages_processed} pages, {len(full_output)} bytes")
        return Result(host=task.host, result=full_output)

    except Exception as e:
        logger.error(f"Auto-paging failed on {task.host.name}: {e}")
        return Result(host=task.host, failed=True, exception=e, 
                     result=locals().get("full_output", ""))