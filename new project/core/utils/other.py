#!/usr/bin/env python3
"""
Вспомогательные утилиты
Содержит общие функции, которые не подошли в другие специализированные менеджеры
"""

import logging
from typing import Dict, List, Any, Optional
from .proxmox_client import ProxmoxClient

logger = logging.getLogger(__name__)


class OtherUtils:
    """Класс с вспомогательными функциями"""

    def __init__(self, proxmox_client: Optional[ProxmoxClient] = None):
        """
        Инициализация утилит

        Args:
            proxmox_client: Клиент Proxmox (опционально)
        """
        self.proxmox = proxmox_client

    
    def wait_for_task_completion(self, task_id: str, node: str, timeout: int = 300) -> bool:
        """
        Ожидать завершения задачи Proxmox

        Args:
            task_id: ID задачи
            node: Нода выполнения задачи
            timeout: Таймаут в секундах

        Returns:
            True если задача завершилась успешно
        """
        if not self.proxmox:
            logger.error("Proxmox client не инициализирован")
            return False

        try:
            import time
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    task_status = self.proxmox.api.nodes(node).tasks(task_id).status.get()
                    status = task_status.get('status')

                    if status == 'stopped':
                        exitstatus = task_status.get('exitstatus', 'OK')
                        logger.info(f"Задача {task_id} завершена со статусом: {exitstatus}")
                        return exitstatus == 'OK'
                    elif status == 'running':
                        time.sleep(2)  # Проверка каждые 2 секунды
                        continue
                    else:
                        logger.error(f"Задача {task_id} завершилась со статусом: {status}")
                        return False

                except Exception as e:
                    if 'no such task' in str(e).lower():
                        # Задача могла завершиться и быть удалена
                        logger.info(f"Задача {task_id} исчезла после выполнения (предполагаем успех)")
                        return True
                    else:
                        logger.error(f"Ошибка проверки статуса задачи {task_id}: {e}")
                        time.sleep(2)

            logger.warning(f"Таймаут ожидания задачи {task_id}")
            return False

        except Exception as e:
            logger.error(f"Ошибка ожидания завершения задачи {task_id}: {e}")
            return False





    def estimate_deployment_time(self, config: Dict[str, Any], users_count: int) -> float:
        """
        Оценить время развертывания в секундах

        Args:
            config: Конфигурация развертывания
            users_count: Количество пользователей

        Returns:
            Оценка времени в секундах
        """
        try:
            machines_count = len(config.get('machines', []))

            # Базовое время на пользователя: 30 сек
            base_time_per_user = 30.0

            # Дополнительное время на каждую машину: 10 сек
            time_per_machine = 10.0

            # Общее время
            total_time = users_count * (base_time_per_user + machines_count * time_per_machine)

            # Добавляем 20% на непредвиденные задержки
            total_time *= 1.2

            return total_time

        except Exception:
            return 300.0  # 5 минут по умолчанию

    def format_deployment_progress(self, current: int, total: int, operation: str = "") -> str:
        """
        Форматировать прогресс развертывания

        Args:
            current: Текущий шаг
            total: Общее количество шагов
            operation: Текущая операция

        Returns:
            Форматированная строка прогресса
        """
        try:
            percentage = int((current / total) * 100) if total > 0 else 0
            progress_bar = f"[{'=' * (percentage // 5)}{' ' * (20 - percentage // 5)}]"

            if operation:
                return f"{progress_bar} {percentage}% - {operation}"
            else:
                return f"{progress_bar} {percentage}% ({current}/{total})"

        except Exception:
            return f"[{current}/{total}]"
