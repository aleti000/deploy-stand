#!/usr/bin/env python3
"""
Менеджер пользователей и пулов
Отвечает за создание, удаление, управление пользователями и их пулами
"""

import logging
from typing import Dict, List, Any, Tuple, Optional
from .proxmox_client import ProxmoxClient

logger = logging.getLogger(__name__)


class UserManager:
    """Менеджер пользователей и пулов для всех операций с пользователями"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация менеджера пользователей

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def create_user(self, userid: str, password: str, groups: List[str] = None) -> bool:
        """
        Создать пользователя

        Args:
            userid: ID пользователя (например, "student1@pve")
            password: Пароль пользователя
            groups: Список групп для пользователя

        Returns:
            True если создание успешно или пользователь уже существует
        """
        try:
            # Сначала проверить существует ли пользователь
            if self.user_exists(userid):
                logger.info(f"Пользователь {userid} уже существует")
                return True

            user_params = {
                'userid': userid,
                'password': password
            }

            if groups:
                user_params['groups'] = ','.join(groups)

            self.proxmox.api.access.users.post(**user_params)
            logger.info(f"Пользователь {userid} создан")
            return True

        except Exception as e:
            logger.error(f"Ошибка создания пользователя {userid}: {e}")
            # Если ошибка из-за того что пользователь уже существует - считаем успехом
            if "already exists" in str(e) or "duplicate" in str(e).lower():
                logger.info(f"Пользователь {userid} уже существует (обработано как успех)")
                return True
            return False

    def user_exists(self, userid: str) -> bool:
        """
        Проверить существует ли пользователь

        Args:
            userid: ID пользователя

        Returns:
            True если пользователь существует
        """
        try:
            users = self.proxmox.api.access.users.get()
            return any(user.get('userid') == userid for user in users)
        except Exception as e:
            logger.error(f"Ошибка проверки существования пользователя {userid}: {e}")
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

    def grant_vm_permissions(self, user: str, node: str, vmid: int) -> bool:
        """
        Выдать права пользователю на конкретную виртуальную машину

        Args:
            user: Имя пользователя (например, "student1@pve")
            node: Нода размещения VM
            vmid: VMID машины

        Returns:
            True если права выданы успешно
        """
        try:
            # Установить права PVEVMUser на конкретную VM
            permissions = ["PVEVMUser"]

            for permission in permissions:
                self.proxmox.api.access.acl.put(
                    users=user,
                    path=f"/vms/{vmid}",
                    roles=permission,
                    propagate=0  # Не распространять на дочерние объекты
                )

            logger.info(f"✅ Права PVEVMUser выданы пользователю {user} на VM {vmid} на ноде {node}")
            return True

        except Exception as e:
            logger.error(f"Ошибка выдачи прав пользователю {user} на VM {vmid}: {e}")
            return False

    def get_user_pools(self, user: str) -> List[str]:
        """
        Получить список пулов пользователя

        Args:
            user: Имя пользователя

        Returns:
            Список пулов пользователя
        """
        try:
            pool_name = self._extract_pool_name(user)
            pools = self.proxmox.api.pools.get()
            return [p.get('poolid') for p in pools if p.get('poolid') == pool_name]
        except Exception as e:
            logger.error(f"Ошибка получения пулов пользователя {user}: {e}")
            return []

    def delete_user_vms(self, user: str) -> bool:
        """
        Удалить все виртуальные машины пользователя

        Args:
            user: Имя пользователя

        Returns:
            True если все VM удалены успешно
        """
        from .vm_manager import VMManager

        try:
            vm_manager = VMManager(self.proxmox)
            pool_name = self._extract_pool_name(user)
            pool_vms = self.proxmox.get_pool_vms(pool_name)

            if not pool_vms:
                logger.info(f"У пользователя {user} нет виртуальных машин для удаления")
                return True

            success_count = 0
            for vm_info in pool_vms:
                try:
                    vmid = vm_info.get('vmid')
                    node = vm_info.get('node')

                    if vmid and node:
                        if vm_manager.delete_vm(node, vmid):
                            success_count += 1
                            logger.info(f"VM {vmid} пользователя {user} удалена")
                        else:
                            logger.error(f"Не удалось удалить VM {vmid} пользователя {user}")
                except Exception as e:
                    logger.error(f"Ошибка удаления VM пользователя {user}: {e}")

            logger.info(f"Удалено VM пользователя {user}: {success_count}/{len(pool_vms)}")
            return success_count == len(pool_vms)

        except Exception as e:
            logger.error(f"Ошибка удаления VM пользователя {user}: {e}")
            return False

    def validate_user_permissions(self, user: str, required_permissions: List[str] = None) -> bool:
        """
        Проверить права пользователя

        Args:
            user: Имя пользователя для проверки
            required_permissions: Требуемые права

        Returns:
            True если пользователь имеет необходимые права
        """
        if required_permissions is None:
            required_permissions = ["PVEVMUser"]

        try:
            # Получить права пользователя
            acls = self.proxmox.api.access.acl.get()

            user_acls = [acl for acl in acls if acl.get('users') == user]

            for permission in required_permissions:
                if not any(permission in acl.get('roles', []) for acl in user_acls):
                    logger.warning(f"Пользователь {user} не имеет права {permission}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Ошибка проверки прав пользователя {user}: {e}")
            return False

    def get_user_vm_count(self, user: str) -> int:
        """
        Получить количество виртуальных машин пользователя

        Args:
            user: Имя пользователя

        Returns:
            Количество VM пользователя
        """
        try:
            pool_name = self._extract_pool_name(user)
            pool_vms = self.proxmox.get_pool_vms(pool_name)
            return len(pool_vms)
        except Exception as e:
            logger.error(f"Ошибка получения количества VM пользователя {user}: {e}")
            return 0



    def build_user_name(self, pool: str, domain: str = "pve") -> str:
        """
        Построить полное имя пользователя из пула

        Args:
            pool: Имя пула
            domain: Домен (по умолчанию 'pve')

        Returns:
            Полное имя пользователя pool@pve
        """
        return f"{pool}@{domain}"

    def extract_user_name(self, user: str) -> str:
        """
        Извлечь имя пользователя без домена

        Args:
            user: Полное имя пользователя user@pve

        Returns:
            Имя пользователя без домена
        """
        # Извлекаем часть до @ для имени пользователя
        if '@' in user:
            return user.split('@')[0]
        return user

    def _extract_pool_name(self, user: str) -> str:
        """
        Извлечь имя пула из имени пользователя

        Args:
            user: Имя пользователя

        Returns:
            Имя пула
        """
        # Используем PoolManager для извлечения имени пула
        from .pool_manager import PoolManager
        pool_manager = PoolManager(None)
        return pool_manager.extract_pool_name(user)

    def _generate_password(self) -> str:
        """
        Сгенерировать случайный пароль для пользователя

        Returns:
            Случайный пароль
        """
        import secrets
        import string

        # Генерация пароля: 12 символов - буквы, цифры, спецсимволы
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(secrets.choice(alphabet) for _ in range(12))
        return password
