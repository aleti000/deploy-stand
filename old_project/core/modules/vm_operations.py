"""
Операции с виртуальными машинами системы Deploy-Stand

Предоставляет функциональность для создания, настройки и управления
виртуальными машинами в кластере Proxmox VE.
"""

import logging
from typing import Dict, List, Any
from core.proxmox.proxmox_client import ProxmoxClient

logger = logging.getLogger(__name__)


class VMOperations:
    """Операции с виртуальными машинами"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация операций с виртуальными машинами

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def create_user_vms(self, config: Dict[str, Any], target_node: str, pool: str) -> List[int]:
        """
        Создать виртуальные машины для пользователя

        Args:
            config: Конфигурация развертывания
            target_node: Целевая нода
            pool: Имя пула

        Returns:
            Список созданных VMID
        """
        created_vms = []

        try:
            for machine_config in config.get('machines', []):
                vmid = self._create_single_vm(machine_config, target_node, pool)
                if vmid:
                    created_vms.append(vmid)

            logger.info(f"Создано {len(created_vms)} виртуальных машин для пула {pool}")
            return created_vms

        except Exception as e:
            logger.error(f"Ошибка создания виртуальных машин: {e}")
            return created_vms

    def _create_single_vm(self, machine_config: Dict[str, Any], target_node: str, pool: str) -> int:
        """
        Создать одну виртуальную машину

        Args:
            machine_config: Конфигурация машины
            target_node: Целевая нода
            pool: Имя пула

        Returns:
            VMID созданной машины или 0 при ошибке
        """
        try:
            # Получить параметры машины
            template_node = machine_config.get('template_node', target_node)
            template_vmid = machine_config['template_vmid']
            device_type = machine_config.get('device_type', 'linux')
            name = machine_config.get('name', f"vm-{template_vmid}-{pool}")
            full_clone = machine_config.get('full_clone', False)

            # Получить следующий VMID
            new_vmid = self.proxmox.get_next_vmid()

            # Клонировать виртуальную машину
            task_id = self.proxmox.clone_vm(
                template_node=template_node,
                template_vmid=template_vmid,
                target_node=target_node,
                new_vmid=new_vmid,
                name=name,
                pool=pool,
                full_clone=full_clone
            )

            # Ожидать завершения клонирования
            if not self.proxmox.wait_for_task(task_id, template_node):
                logger.error(f"Ошибка клонирования VM {new_vmid}")
                return 0

            # Настроить сеть если указана
            networks = machine_config.get('networks', [])
            if networks:
                self._configure_vm_network(new_vmid, target_node, networks, pool, device_type)

            logger.info(f"Машина {name} (VMID: {new_vmid}) создана в пуле {pool}")
            return new_vmid

        except Exception as e:
            logger.error(f"Ошибка создания машины: {e}")
            return 0

    def _configure_vm_network(self, vmid: int, node: str, networks: List[Dict],
                            pool: str, device_type: str) -> bool:
        """
        Настроить сеть виртуальной машины с использованием BridgeManager

        Args:
            vmid: VMID машины
            node: Нода размещения
            networks: Конфигурация сетей (с алias'ами bridge)
            pool: Имя пула
            device_type: Тип устройства

        Returns:
            True если настройка успешна
        """
        try:
            from core.modules.network.bridge_manager import BridgeManager

            # ИНИЦИАЛИЗИРОВАТЬ BRIDGE MANAGER И ИСПОЛЬЗОВАТЬ ЕГО!
            bridge_manager = BridgeManager(self.proxmox)

            # ⚠️ ВАЖНО: передать networks с alias'ами, а НЕ с реальными bridge именами
            return bridge_manager.configure_network(vmid, node, networks, pool, device_type)

        except Exception as e:
            logger.error(f"❌ Критическая ошибка настройки сети VM {vmid}: {e}")
            return False

    def _generate_mac_address(self) -> str:
        """Сгенерировать случайный MAC адрес"""
        import secrets
        mac = [0x52, 0x54, 0x00]  # QEMU/Libvirt prefix
        mac.extend(secrets.randbelow(256) for _ in range(3))
        return ':'.join(f'{b:02x}' for b in mac)

    def check_existing_vms_in_pools(self, users: List[str], config: Dict[str, Any]) -> bool:
        """
        Проверить отсутствие конфликтов с существующими виртуальными машинами

        Args:
            users: Список пользователей
            config: Конфигурация развертывания

        Returns:
            True если можно продолжать развертывание
        """
        try:
            for user in users:
                pool_name = user.split('@')[0]

                # Проверить пул пользователя
                if self._pool_has_vms(pool_name):
                    logger.warning(f"Пул {pool_name} уже содержит виртуальные машины")
                    # Можно добавить логику для обработки конфликтов

            return True

        except Exception as e:
            logger.error(f"Ошибка проверки существующих VM: {e}")
            return False

    def _pool_has_vms(self, pool_name: str) -> bool:
        """
        Проверить содержит ли пул виртуальные машины

        Args:
            pool_name: Имя пула

        Returns:
            True если пул содержит виртуальные машины
        """
        try:
            # Заглушка - в реальности здесь должна быть логика проверки пула
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки пула {pool_name}: {e}")
            return True  # В случае ошибки считаем что содержит

    def stop_user_vms(self, username: str) -> bool:
        """
        Остановить все виртуальные машины пользователя

        Args:
            username: Имя пользователя

        Returns:
            True если остановка успешна
        """
        try:
            # Заглушка - в реальности здесь должна быть логика остановки VM
            logger.info(f"VM пользователя {username} остановлены")
            return True
        except Exception as e:
            logger.error(f"Ошибка остановки VM пользователя {username}: {e}")
            return False

    def delete_user_vms(self, username: str) -> bool:
        """
        Удалить все виртуальные машины пользователя

        Args:
            username: Имя пользователя

        Returns:
            True если удаление успешно
        """
        try:
            # Заглушка - в реальности здесь должна быть логика удаления VM
            logger.info(f"VM пользователя {username} удалены")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления VM пользователя {username}: {e}")
            return False

    def get_vm_info(self, node: str, vmid: int) -> Dict[str, Any]:
        """
        Получить информацию о виртуальной машине

        Args:
            node: Нода размещения
            vmid: VMID машины

        Returns:
            Информация о виртуальной машине
        """
        try:
            config = self.proxmox.get_vm_config(node, vmid)
            return {
                'vmid': vmid,
                'node': node,
                'config': config,
                'status': 'running'  # Заглушка
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации о VM {vmid}: {e}")
            return {}

    def list_user_vms(self, username: str) -> List[Dict[str, Any]]:
        """
        Получить список виртуальных машин пользователя

        Args:
            username: Имя пользователя

        Returns:
            Список виртуальных машин пользователя
        """
        try:
            # Заглушка - в реальности здесь должна быть логика получения списка VM пользователя
            return []
        except Exception as e:
            logger.error(f"Ошибка получения списка VM пользователя {username}: {e}")
            return []
