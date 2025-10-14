#!/usr/bin/env python3
"""
Вспомогательные утилиты для нового проекта
Минимальный набор необходимых функций
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
                        time.sleep(2)
                        continue
                    else:
                        logger.error(f"Задача {task_id} завершилась со статусом: {status}")
                        return False

                except Exception as e:
                    if 'no such task' in str(e).lower():
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
