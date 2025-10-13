"""
Менеджер пользователей и пулов

Предоставляет централизованное управление пользователями, пулами и правами доступа
для всех стратегий развертывания виртуальных машин.
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
from core.proxmox.proxmox_client import ProxmoxClient
from core.modules.common.deployment_utils import DeploymentUtils

logger = logging.getLogger(__name__)


class UserManager:
    """Менеджер пользователей и пулов"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация менеджера пользователей

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client
        self.utils = DeploymentUtils()

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
                password = self.utils.generate_password()

            # Создание пользователя
            if not self.proxmox.create_user(user, password):
                logger.error(f"Не удалось создать пользователя {user}")
                return False, ""

            logger.info(f"✅ Пользователь {user} создан")

            # Создание пула
            pool_name = self.utils.extract_pool_name(user)
            if not self.proxmox.create_pool(pool_name, f"Pool for {user}"):
                logger.error(f"Не удалось создать пул {pool_name} для пользователя {user}")
                # Удалить созданного пользователя при неудаче создания пула
                self._cleanup_user(user)
                return False, ""

            logger.info(f"✅ Пул {pool_name} создан для пользователя {user}")

            # Установка прав пользователя на пул
            permissions = ["PVEVMAdmin"]
            if not self.proxmox.set_pool_permissions(user, pool_name, permissions):
                logger.error(f"Не удалось установить права для пользователя {user} на пул {pool_name}")
                # Очистить созданные ресурсы при неудаче установки прав
                self._cleanup_user_and_pool(user, pool_name)
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
            pool_name = self.utils.extract_pool_name(user)

            # Удалить виртуальные машины пользователя
            if not self._delete_user_vms(user):
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

    def check_user_exists(self, user: str) -> bool:
        """
        Проверить существование пользователя

        Args:
            user: Имя пользователя для проверки

        Returns:
            True если пользователь существует
        """
        try:
            # Попытаться получить информацию о пользователе
            users = self.proxmox.api.access.users.get()
            return any(u.get('userid') == user for u in users)
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

    def get_user_pools(self, user: str) -> List[str]:
        """
        Получить список пулов пользователя

        Args:
            user: Имя пользователя

        Returns:
            Список пулов пользователя
        """
        try:
            pool_name = self.utils.extract_pool_name(user)
            pools = self.proxmox.api.pools.get()
            return [p.get('poolid') for p in pools if p.get('poolid') == pool_name]
        except Exception as e:
            logger.error(f"Ошибка получения пулов пользователя {user}: {e}")
            return []

    def delete_user_resources_batch(self, users: List[str]) -> Dict[str, List[str]]:
        """
        Пакетное удаление ресурсов пользователей

        Args:
            users: Список пользователей для удаления

        Returns:
            Словарь с результатами {successful: [], failed: [], skipped: []}
        """
        results = {
            'successful': [],
            'failed': [],
            'skipped': []
        }

        for user in users:
            try:
                if self.delete_user_and_pool(user):
                    results['successful'].append(user)
                else:
                    results['failed'].append(user)
            except Exception as e:
                logger.error(f"Ошибка удаления ресурсов пользователя {user}: {e}")
                results['failed'].append(user)

        logger.info(f"Пакетное удаление завершено: успешных {len(results['successful'])}, "
                   f"неудачных {len(results['failed'])}, пропущено {len(results['skipped'])}")

        return results

    def _delete_user_vms(self, user: str) -> bool:
        """
        Удалить все виртуальные машины пользователя

        Args:
            user: Имя пользователя

        Returns:
            True если все VM удалены успешно
        """
        try:
            pool_name = self.utils.extract_pool_name(user)
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
                        if self.proxmox.delete_vm(node, vmid):
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
            pool_name = self.utils.extract_pool_name(user)
            pool_vms = self.proxmox.get_pool_vms(pool_name)
            return len(pool_vms)
        except Exception as e:
            logger.error(f"Ошибка получения количества VM пользователя {user}: {e}")
            return 0

    def list_user_resources(self, user: str) -> Dict[str, Any]:
        """
        Получить все ресурсы пользователя

        Args:
            user: Имя пользователя

        Returns:
            Словарь с ресурсами пользователя
        """
        try:
            pool_name = self.utils.extract_pool_name(user)
            pool_vms = self.proxmox.get_pool_vms(pool_name)

            resources = {
                'user': user,
                'pool': pool_name,
                'vm_count': len(pool_vms),
                'vms': []
            }

            for vm in pool_vms:
                vm_info = {
                    'vmid': vm.get('vmid'),
                    'name': vm.get('name'),
                    'node': vm.get('node'),
                    'status': vm.get('status')
                }
                resources['vms'].append(vm_info)

            return resources

        except Exception as e:
            logger.error(f"Ошибка получения ресурсов пользователя {user}: {e}")
            return {
                'user': user,
                'pool': pool_name,
                'vm_count': 0,
                'vms': [],
                'error': str(e)
            }
