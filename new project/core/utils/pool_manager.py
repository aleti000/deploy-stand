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

    def create_pool(self, poolid: str, comment: str = "") -> bool:
        """
        Создать пул

        Args:
            poolid: ID пула
            comment: Комментарий к пулу

        Returns:
            True если создание успешно или пул уже существует
        """
        try:
            # Сначала проверить существует ли пул
            if self.pool_exists(poolid):
                logger.info(f"Пул {poolid} уже существует")
                return True

            self.proxmox.api.pools.post(poolid=poolid, comment=comment)
            logger.info(f"Пул {poolid} создан")
            return True

        except Exception as e:
            logger.error(f"Ошибка создания пула {poolid}: {e}")
            # Если ошибка из-за того что пул уже существует - считаем успехом
            if "already exists" in str(e) or "duplicate" in str(e).lower():
                logger.info(f"Пул {poolid} уже существует (обработано как успех)")
                return True
            return False

    def pool_exists(self, poolid: str) -> bool:
        """
        Проверить существует ли пул

        Args:
            poolid: ID пула

        Returns:
            True если пул существует
        """
        try:
            pools = self.proxmox.api.pools.get()
            return any(pool.get('poolid') == poolid for pool in pools)
        except Exception as e:
            logger.error(f"Ошибка проверки существования пула {poolid}: {e}")
            return False

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



    def set_pool_permissions(self, userid: str, poolid: str, permissions: List[str]) -> bool:
        """
        Установить права пользователя на пул

        Args:
            userid: ID пользователя
            poolid: ID пула
            permissions: Список прав для установки

        Returns:
            True если права установлены успешно
        """
        try:
            for permission in permissions:
                # Используем PUT /access/acl для установки ACL прав
                self.proxmox.api.access.acl.put(
                    users=userid,
                    path=f"/pool/{poolid}",
                    roles=permission,
                    propagate=1  # Применить права к дочерним объектам
                )

            logger.info(f"Права пользователя {userid} на пул {poolid} установлены")
            return True

        except Exception as e:
            logger.error(f"Ошибка установки прав пользователя {userid}: {e}")
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

    def delete_pool(self, pool_name: str) -> bool:
        """
        Удалить пул

        Args:
            pool_name: Имя пула для удаления

        Returns:
            True если удаление успешно
        """
        try:
            self.proxmox.api.pools(pool_name).delete()
            logger.info(f"✅ Пул {pool_name} удален")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления пула {pool_name}: {e}")
            return False

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
