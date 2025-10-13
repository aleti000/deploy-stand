#!/usr/bin/env python3
"""
Менеджер виртуальных машин
Отвечает за операции с виртуальными машинами: создание, клонирование, удаление, управление состоянием
"""

import logging
from typing import Dict, List, Any, Optional
from .proxmox_client import ProxmoxClient

logger = logging.getLogger(__name__)


class VMManager:
    """Менеджер виртуальных машин для всех операций с VM"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация менеджера VM

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def clone_vm(self, template_node: str, template_vmid: int, target_node: str,
                 new_vmid: int, name: str, pool: str = None, full_clone: bool = False) -> str:
        """
        Клонировать виртуальную машину через VMManager
        Функция реализации клонирования в VMManager

        Args:
            template_node: Нода с шаблоном
            template_vmid: VMID шаблона
            target_node: Целевая нода
            new_vmid: Новый VMID
            name: Имя новой VM
            pool: Имя пула (опционально)
            full_clone: Полное клонирование (True) или linked clone (False)

        Returns:
            Task ID операции клонирования
        """
        try:
            # Клонирование напрямую через Proxmox API в VMManager
            clone_params = {
                'newid': new_vmid,
                'name': name,
                'target': target_node,
                'full': 1 if full_clone else 0
            }

            if pool:
                clone_params['pool'] = pool

            # Использование API напрямую
            task = self.proxmox.api.nodes(template_node).qemu(template_vmid).clone.post(**clone_params)
            task_id = task if isinstance(task, str) else str(task)

            logger.info(f"Запущено клонирование VM {template_vmid} -> {new_vmid} ({name}) в VMManager")
            return task_id
        except Exception as e:
            logger.error(f"Ошибка клонирования VM {template_vmid} -> {new_vmid} в VMManager: {e}")
            raise

    def delete_vm(self, node: str, vmid: int) -> bool:
        """
        Удалить виртуальную машину

        Args:
            node: Нода размещения VM
            vmid: VMID машины для удаления

        Returns:
            True если удаление успешно
        """
        try:
            success = self.proxmox.delete_vm(node, vmid)
            if success:
                logger.info(f"VM {vmid} удалена с ноды {node}")
            else:
                logger.error(f"Не удалось удалить VM {vmid} с ноды {node}")
            return success
        except Exception as e:
            logger.error(f"Ошибка удаления VM {vmid} на ноде {node}: {e}")
            return False

    def start_vm(self, node: str, vmid: int) -> bool:
        """
        Запустить виртуальную машину

        Args:
            node: Нода размещения VM
            vmid: VMID машины

        Returns:
            True если запуск успешен
        """
        try:
            success = self.proxmox.start_vm(node, vmid)
            if success:
                logger.info(f"VM {vmid} запущена на ноде {node}")
            else:
                logger.error(f"Не удалось запустить VM {vmid} на ноде {node}")
            return success
        except Exception as e:
            logger.error(f"Ошибка запуска VM {vmid} на ноде {node}: {e}")
            return False

    def stop_vm(self, node: str, vmid: int) -> bool:
        """
        Остановить виртуальную машину

        Args:
            node: Нода размещения VM
            vmid: VMID машины

        Returns:
            True если остановка успешна
        """
        try:
            success = self.proxmox.stop_vm(node, vmid)
            if success:
                logger.info(f"VM {vmid} остановлена на ноде {node}")
            else:
                logger.error(f"Не удалось остановить VM {vmid} на ноде {node}")
            return success
        except Exception as e:
            logger.error(f"Ошибка остановки VM {vmid} на ноде {node}: {e}")
            return False

    def get_vm_info(self, node: str, vmid: int) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о виртуальной машине

        Args:
            node: Нода размещения VM
            vmid: VMID машины

        Returns:
            Информация о VM или None если не найдена
        """
        try:
            vm_info = self.proxmox.get_vm_info(node, vmid)
            return vm_info
        except Exception as e:
            logger.error(f"Ошибка получения информации о VM {vmid} на ноде {node}: {e}")
            return None

    def list_user_vms(self, pool: str) -> List[Dict[str, Any]]:
        """
        Получить список VM пользователя по пулу

        Args:
            pool: Имя пула пользователя

        Returns:
            Список VM в пуле
        """
        try:
            vms = self.proxmox.get_pool_vms(pool)
            logger.debug(f"Найдено {len(vms)} VM в пуле {pool}")
            return vms
        except Exception as e:
            logger.error(f"Ошибка получения списка VM в пуле {pool}: {e}")
            return []

    def check_vmid_available(self, vmid: int) -> bool:
        """
        Проверить доступность VMID

        Args:
            vmid: VMID для проверки

        Returns:
            True если VMID свободен
        """
        try:
            vm_info = self.get_vm_info("any", vmid)  # Проверяем везде
            return vm_info is None
        except Exception:
            return True  # В случае ошибки считаем доступным

    def get_vm_status(self, node: str, vmid: int) -> str:
        """
        Получить статус виртуальной машины

        Args:
            node: Нода размещения VM
            vmid: VMID машины

        Returns:
            Статус VM ('running', 'stopped', etc.) или 'unknown'
        """
        try:
            vm_info = self.get_vm_info(node, vmid)
            if vm_info:
                return vm_info.get('status', 'unknown')
            return 'not_found'
        except Exception as e:
            logger.error(f"Ошибка получения статуса VM {vmid} на ноде {node}: {e}")
            return 'unknown'

    def get_next_vmid(self) -> int:
        """
        Получить следующий доступный VMID

        Returns:
            Доступный VMID
        """
        try:
            # Используем API Proxmox для получения следующего ID
            nextid_response = self.proxmox.api.cluster.nextid.get()
            next_vmid = int(nextid_response)
            logger.debug(f"Получен следующий VMID: {next_vmid}")
            return next_vmid
        except Exception as e:
            logger.warning(f"Ошибка получения следующего VMID через API: {e}")
            # Fallback: найти максимальный VMID + 1
            return self._find_max_vmid() + 1

    def _find_max_vmid(self) -> int:
        """
        Найти максимальный VMID в кластере

        Returns:
            Максимальный VMID или 100 если не найден
        """
        try:
            resources = self.proxmox.api.cluster.resources.get(type='vm')
            if resources:
                vmids = [int(r.get('vmid', 0)) for r in resources]
                return max(vmids) if vmids else 100
            return 100
        except Exception:
            return 100

    def get_vm_status(self, node: str, vmid: int) -> str:
        """
        Получить статус виртуальной машины

        Args:
            node: Нода размещения VM
            vmid: VMID машины

        Returns:
            Статус VM ('running', 'stopped', etc.) или 'unknown'
        """
        try:
            vm_info = self.get_vm_info(node, vmid)
            if vm_info:
                return vm_info.get('status', 'unknown')
            return 'not_found'
        except Exception as e:
            logger.error(f"Ошибка получения статуса VM {vmid} на ноде {node}: {e}")
            return 'unknown'
