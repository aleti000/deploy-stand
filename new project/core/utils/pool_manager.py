#!/usr/bin/env python3
"""
Менеджер пулов
Отвечает за создание, удаление, управление пулами и правами доступа к ним
"""

import logging
from typing import Dict, List, Any, Optional
from .proxmox_client import ProxmoxClient

# Импорт для совместимости
try:
    from .validator import ConfigValidator
    from .logger import Logger
except ImportError:
    # Fallback для обратной совместимости
    ConfigValidator = None
    Logger = None

logger = logging.getLogger(__name__)


class PoolManager:
    """Менеджер пулов для всех операций с пулами Proxmox"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация менеджера пулов

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def extract_pool_name(self, user: str) -> str:
        """
        Извлечь имя пула из имени пользователя

        Args:
            user: Имя пользователя в формате user@pve

        Returns:
            Имя пула (часть до @)
        """
        if '@' in user:
            return user.split('@')[0]
        return user

    def create_pool(self, pool_name: str, comment: str = "") -> bool:
        """
        Создать пул

        Args:
            pool_name: Имя пула
            comment: Комментарий к пулу

        Returns:
            True если пул создан успешно
        """
        try:
            success = self.proxmox.create_pool(pool_name, comment)
            if success:
                logger.info(f"✅ Пул {pool_name} создан")
            else:
                logger.error(f"Не удалось создать пул {pool_name}")
            return success
        except Exception as e:
            logger.error(f"Ошибка создания пула {pool_name}: {e}")
            return False

    def delete_pool(self, pool_name: str) -> bool:
        """
        Удалить пул

        Args:
            pool_name: Имя пула для удаления

        Returns:
            True если пул удален успешно
        """
        return self._delete_pool_impl(pool_name)

    def get_pool_info(self, pool_name: str) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о пуле

        Args:
            pool_name: Имя пула

        Returns:
            Информация о пуле или None если пул не найден
        """
        try:
            pools = self.proxmox.api.pools.get()
            for pool in pools:
                if pool.get('poolid') == pool_name:
                    return pool
            return None
        except Exception as e:
            logger.error(f"Ошибка получения информации о пуле {pool_name}: {e}")
            return None

    def list_pools(self) -> List[str]:
        """
        Получить список всех пулов

        Returns:
            Список имен пулов
        """
        try:
            pools = self.proxmox.api.pools.get()
            return [pool.get('poolid') for pool in pools if pool.get('poolid')]
        except Exception as e:
            logger.error(f"Ошибка получения списка пулов: {e}")
            return []

    def check_pool_exists(self, pool_name: str) -> bool:
        """
        Проверить существование пула

        Args:
            pool_name: Имя пула для проверки

        Returns:
            True если пул существует
        """
        try:
            return self.get_pool_info(pool_name) is not None
        except Exception:
            return False

    def set_pool_permissions(self, user: str, pool_name: str, permissions: List[str]) -> bool:
        """
        Установить права пользователя на пул

        Args:
            user: Имя пользователя
            pool_name: Имя пула
            permissions: Список прав для установки

        Returns:
            True если права установлены успешно
        """
        try:
            success = self.proxmox.set_pool_permissions(user, pool_name, permissions)
            if success:
                logger.info(f"✅ Права пользователя {user} на пул {pool_name} установлены: {permissions}")
            else:
                logger.error(f"Не удалось установить права пользователя {user} на пул {pool_name}")
            return success
        except Exception as e:
            logger.error(f"Ошибка установки прав пользователя {user} на пул {pool_name}: {e}")
            return False

    def revoke_pool_permissions(self, user: str, pool_name: str) -> bool:
        """
        Отозвать все права пользователя на пул

        Args:
            user: Имя пользователя
            pool_name: Имя пула

        Returns:
            True если права отозваны успешно
        """
        try:
            # Используем API для удаления ACL записей
            self.proxmox.api.access.acl.delete(
                users=user,
                path=f"/pool/{pool_name}"
            )
            logger.info(f"✅ Права пользователя {user} на пул {pool_name} отозваны")
            return True
        except Exception as e:
            logger.error(f"Ошибка отзыва прав пользователя {user} на пул {pool_name}: {e}")
            return False

    def get_pool_permissions(self, pool_name: str) -> Dict[str, List[str]]:
        """
        Получить права доступа к пулу

        Args:
            pool_name: Имя пула

        Returns:
            Словарь {user: [permissions]}
        """
        try:
            acls = self.proxmox.api.access.acl.get()

            pool_acls = {}
            for acl in acls:
                path = acl.get('path', '')
                if path == f"/pool/{pool_name}":
                    users = acl.get('users', '')
                    roles = acl.get('roles', [])
                    if users and roles:
                        pool_acls[users] = roles

            return pool_acls

        except Exception as e:
            logger.error(f"Ошибка получения прав доступа к пулу {pool_name}: {e}")
            return {}

    def get_pool_vms(self, pool_name: str) -> List[Dict[str, Any]]:
        """
        Получить список VM в пуле через PoolManager

        Args:
            pool_name: Имя пула

        Returns:
            Список VM в пуле
        """
        try:
            # Используем API напрямую через PoolManager
            pool_vms = self.proxmox.api.pools(pool_name).get()
            return pool_vms.get('members', [])
        except Exception as e:
            logger.error(f"Ошибка получения списка VM в пуле {pool_name} через PoolManager: {e}")
            return []

    def get_pool_resources(self, pool_name: str) -> List[Dict[str, Any]]:
        """
        Получить все ресурсы пула (VM, storage, etc.)

        Args:
            pool_name: Имя пула

        Returns:
            Список ресурсов пула
        """
        try:
            return self.proxmox.api.pools(pool_name).get()
        except Exception as e:
            logger.error(f"Ошибка получения ресурсов пула {pool_name}: {e}")
            return []

    def add_vm_to_pool(self, vmid: int, pool_name: str) -> bool:
        """
        Добавить VM в пул

        Args:
            vmid: VMID машины
            pool_name: Имя пула

        Returns:
            True если VM добавлена в пул успешно
        """
        try:
            # Используем API для изменения пула VM
            self.proxmox.api.pools(pool_name).put(vms=[vmid])
            logger.info(f"✅ VM {vmid} добавлена в пул {pool_name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления VM {vmid} в пул {pool_name}: {e}")
            return False

    def remove_vm_from_pool(self, vmid: int, pool_name: str) -> bool:
        """
        Удалить VM из пула

        Args:
            vmid: VMID машины
            pool_name: Имя пула

        Returns:
            True если VM удалена из пула успешно
        """
        try:
            # Получить текущий список VM в пуле
            current_vms = self.get_pool_vms(pool_name)
            current_vmids = [vm.get('vmid') for vm in current_vms if vm.get('vmid') != vmid]

            # Обновить пул без этой VM
            self.proxmox.api.pools(pool_name).put(vms=current_vmids)
            logger.info(f"✅ VM {vmid} удалена из пула {pool_name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления VM {vmid} из пула {pool_name}: {e}")
            return False

    def get_pool_statistics(self, pool_name: str) -> Dict[str, Any]:
        """
        Получить статистику пула

        Args:
            pool_name: Имя пула

        Returns:
            Статистика пула
        """
        try:
            pool_vms = self.get_pool_vms(pool_name)
            pool_info = self.get_pool_info(pool_name)

            stats = {
                'pool_name': pool_name,
                'vm_count': len(pool_vms),
                'total_vms': len(pool_vms),
                'exists': pool_info is not None,
                'comment': pool_info.get('comment', '') if pool_info else '',
                'permissions': self.get_pool_permissions(pool_name),
                'vms': []
            }

            # Дополнительная информация о VM
            for vm in pool_vms:
                vm_stats = {
                    'vmid': vm.get('vmid'),
                    'name': vm.get('name'),
                    'node': vm.get('node'),
                    'status': vm.get('status')
                }
                stats['vms'].append(vm_stats)

            return stats

        except Exception as e:
            logger.error(f"Ошибка получения статистики пула {pool_name}: {e}")
            return {
                'pool_name': pool_name,
                'error': str(e)
            }

    def _delete_pool_impl(self, pool_name: str) -> bool:
        """
        Реализация удаления пула в PoolManager
        """
        try:
            pools = self.proxmox.api.pools.get()
            if not any(p.get('poolid') == pool_name for p in pools):
                logger.info(f"Пул {pool_name} не существует")
                return True

            self.proxmox.api.pools(pool_name).delete()
            logger.info(f"Пул {pool_name} удален через PoolManager")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления пула {pool_name} в PoolManager: {e}")
            return False
