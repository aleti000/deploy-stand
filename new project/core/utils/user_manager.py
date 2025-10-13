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

    def create_user_and_pool(self, user: str, password: str = None) -> Tuple[bool, str]:
        """
        Создать пользователя и пул

        Args:
            user: Имя пользователя в формате user@pve
            password: Пароль пользователя (генерируется автоматически если не указан)

        Returns:
            Кортеж (успех, пароль_пользователя)
        """
        try:
            # Генерация пароля если не указан
            if password is None:
                password = self._generate_password()

            # Создание пользователя
            if not self._create_user_impl(user, password):
                logger.error(f"Не удалось создать пользователя {user}")
                return False, ""

            logger.info(f"✅ Пользователь {user} создан")

            # Создание пула
            pool_name = self._extract_pool_name(user)
            if not self._create_pool_impl(pool_name, f"Pool for {user}"):
                logger.error(f"Не удалось создать пул {pool_name} для пользователя {user}")
                # Удалить созданного пользователя при неудаче создания пула
                self._delete_user_impl(user)
                return False, ""

            logger.info(f"✅ Пул {pool_name} создан для пользователя {user}")

            # Установка прав пользователя на пул
            permissions = ["PVEVMAdmin"]
            if not self._set_pool_permissions_impl(user, pool_name, permissions):
                logger.error(f"Не удалось установить права для пользователя {user} на пул {pool_name}")
                # Очистить созданные ресурсы при неудаче установки прав
                self._delete_user_and_pool_impl(user, pool_name)
                return False, ""

            logger.info(f"✅ Права пользователя {user} на пул {pool_name} установлены")
            return True, password

        except Exception as e:
            logger.error(f"Ошибка создания пользователя и пула для {user}: {e}")
            return False, ""

    def delete_user_and_pool(self, user: str) -> bool:
        """
        Удалить пользователя и его пул

        Args:
            user: Имя пользователя для удаления

        Returns:
            True если удаление успешно
        """
        try:
            pool_name = self._extract_pool_name(user)

            # Удалить виртуальные машины пользователя
            if not self.delete_user_vms(user):
                logger.warning(f"Не удалось удалить все VM пользователя {user}")

            # Удалить пул
            if not self.proxmox.delete_pool(pool_name):
                logger.warning(f"Не удалось удалить пул {pool_name}")

            # Удалить пользователя
            if not self.proxmox.delete_user(user):
                logger.error(f"Не удалось удалить пользователя {user}")
                return False

            logger.info(f"✅ Пользователь {user} и пул {pool_name} удалены")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления пользователя {user}: {e}")
            return False

    def check_user_exists(self, user: str) -> bool:
        """
        Проверить существование пользователя

        Args:
            user: Имя пользователя для проверки

        Returns:
            True если пользователь существует
        """
        try:
            # Попытаться получить информацию о пользователе через access API
            if hasattr(self.proxmox, 'api') and hasattr(self.proxmox.api, 'access'):
                users = self.proxmox.api.access.users.get()
                return any(u.get('userid') == user for u in users)
            else:
                # Fallback для обратной совместимости
                logger.warning(f"ProxmoxClient не имеет access API, пользователь {user} считается существующим")
                return True
        except Exception as e:
            logger.error(f"Ошибка проверки существования пользователя {user}: {e}")
            return False

    def check_pool_exists(self, pool_name: str) -> bool:
        """
        Проверить существование пула

        Args:
            pool_name: Имя пула для проверки

        Returns:
            True если пул существует
        """
        try:
            pools = self.proxmox.api.pools.get()
            return any(p.get('poolid') == pool_name for p in pools)
        except Exception as e:
            logger.error(f"Ошибка проверки существования пула {pool_name}: {e}")
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

    def _cleanup_user(self, user: str) -> None:
        """Очистить пользователя"""
        try:
            logger.info(f"Начинается очистка пользователя {user}")
            # Здесь можно добавить дополнительную логику очистки
            # Например, удаление из внешних систем учета
        except Exception as e:
            logger.error(f"Ошибка очистки пользователя {user}: {e}")

    def _cleanup_user_and_pool(self, user: str, pool: str) -> None:
        """Очистить пользователя и пул"""
        try:
            logger.info(f"Начинается очистка пользователя {user} и пула {pool}")
            # Здесь можно добавить дополнительную логику очистки
            # Например, удаление из внешних систем учета
        except Exception as e:
            logger.error(f"Ошибка очистки пользователя и пула: {e}")

    def _create_user_impl(self, user: str, password: str) -> bool:
        """
        Реализация создания пользователя в UserManager
        """
        try:
            # Сначала проверить существует ли пользователь - реализовать в UserManager
            if self._check_user_exists_impl(user):
                logger.info(f"Пользователь {user} уже существует")
                return True

            # Создать пользователя через API напрямую
            user_params = {
                'userid': user,
                'password': password,
                'comment': f'User {user}'
            }

            self.proxmox.api.access.users.post(**user_params)
            logger.info(f"Пользователь {user} создан через UserManager")
            return True

        except Exception as e:
            logger.error(f"Ошибка создания пользователя {user} в UserManager: {e}")
            # Если ошибка из-за того что пользователь уже существует - считаем успехом
            if "already exists" in str(e) or "duplicate" in str(e).lower():
                logger.info(f"Пользователь {user} уже существует (обработано как успех)")
                return True
            return False

    def _delete_user_impl(self, user: str) -> bool:
        """
        Реализация удаления пользователя в UserManager
        """
        try:
            if not self.proxmox.check_user_exists(user):
                logger.info(f"Пользователь {user} не существует")
                return True

            self.proxmox.api.access.users(user).delete()
            logger.info(f"Пользователь {user} удален через UserManager")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления пользователя {user} в UserManager: {e}")
            return False

    def _create_pool_impl(self, pool_name: str, comment: str = "") -> bool:
        """
        Реализация создания пула в UserManager
        """
        try:
            # Сначала проверить существует ли пул
            pools = self.proxmox.api.pools.get()
            if any(p.get('poolid') == pool_name for p in pools):
                logger.info(f"Пул {pool_name} уже существует")
                return True

            self.proxmox.api.pools.post(poolid=pool_name, comment=comment)
            logger.info(f"Пул {pool_name} создан через UserManager")
            return True

        except Exception as e:
            logger.error(f"Ошибка создания пула {pool_name} в UserManager: {e}")
            # Если ошибка из-за того что пул уже существует - считаем успехом
            if "already exists" in str(e) or "duplicate" in str(e).lower():
                logger.info(f"Пул {pool_name} уже существует (обработано как успех)")
                return True
            return False

    def _delete_pool_impl(self, pool_name: str) -> bool:
        """
        Реализация удаления пула в UserManager
        """
        try:
            pools = self.proxmox.api.pools.get()
            if not any(p.get('poolid') == pool_name for p in pools):
                logger.info(f"Пул {pool_name} не существует")
                return True

            self.proxmox.api.pools(pool_name).delete()
            logger.info(f"Пул {pool_name} удален через UserManager")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления пула {pool_name} в UserManager: {e}")
            return False

    def _set_pool_permissions_impl(self, user: str, pool_name: str, permissions: List[str]) -> bool:
        """
        Реализация установки прав пользователя на пул в UserManager
        """
        try:
            for permission in permissions:
                # Используем PUT /access/acl для установки ACL прав
                self.proxmox.api.access.acl.put(
                    users=user,
                    path=f"/pool/{pool_name}",
                    roles=permission,
                    propagate=1  # Применить права к дочерним объектам
                )

            logger.info(f"Права пользователя {user} на пул {pool_name} установлены через UserManager")
            return True

        except Exception as e:
            logger.error(f"Ошибка установки прав пользователя {user} на пул {pool_name} в UserManager: {e}")
            return False

    def _delete_user_and_pool_impl(self, user: str, pool_name: str) -> None:
        """
        Реализация очистки пользователя и пула в UserManager при ошибке
        """
        try:
            logger.info(f"Начинается очистка пользователя {user} и пула {pool_name} после ошибки")
            # Сначала попробовать удалить пул
            self._delete_pool_impl(pool_name)
            # Потом пользователя
            self._delete_user_impl(user)
        except Exception as e:
            logger.error(f"Ошибка очистки пользователя и пула после ошибки: {e}")

    def _check_user_exists_impl(self, user: str) -> bool:
        """
        Проверка существования пользователя в UserManager
        """
        try:
            users = self.proxmox.api.access.users.get()
            return any(u.get('userid') == user for u in users)
        except Exception as e:
            logger.error(f"Ошибка проверки существования пользователя {user} в UserManager: {e}")
            return False
