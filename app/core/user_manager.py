import random
import string
from typing import Tuple
from app.utils.logger import logger

class UserManager:
    def __init__(self, proxmox_manager):
        self.proxmox = proxmox_manager

    def create_user_and_pool(self, username: str) -> Tuple[bool, str]:
        try:
            password = self._generate_password()
            try:
                self.proxmox.proxmox.access.users(username).get()
                user_exists = True
            except Exception:
                user_exists = False
            if not user_exists:
                self.proxmox.proxmox.access.users.post(userid=username, password=password, enable=1)
            pool_name = username.split('@')[0]
            try:
                self.proxmox.proxmox.pools.post(poolid=pool_name)
            except Exception:
                pass
            acl_params = {'path': f'/pool/{pool_name}', 'roles': 'PVEVMAdmin', 'users': username}
            self.proxmox.proxmox.access.acl.put(**acl_params)
            return True, password
        except Exception as e:
            logger.error(f"Ошибка создания пользователя/пула: {e}")
            return False, ""

    def _generate_password(self) -> str:
        """Генерирует случайный пароль для пользователя (8 цифр)"""
        random_part = ''.join(random.choices(string.digits, k=8))
        return random_part

    def delete_user_resources(self, username: str) -> bool:
        """Удалить ресурсы пользователя с полной проверкой зависимостей"""
        try:
            logger.info(f"🗑️ Начинаем удаление ресурсов пользователя: {username}")
            pool_name = username.split('@')[0]

            # Шаг 1: Проверить наличие пользователя
            logger.debug(f"🔍 Проверяем наличие пользователя {username}")
            user_exists = self._check_user_exists(username)

            if not user_exists:
                logger.warning(f"⚠️ Пользователь {username} не существует - пропускаем")
                return True

            # Шаг 2: Проверить наличие пула
            logger.debug(f"🔍 Проверяем наличие пула {pool_name}")
            pool_exists = self._check_pool_exists(pool_name)

            if not pool_exists:
                # Пула нет - просто удаляем пользователя
                logger.info(f"📋 Пул {pool_name} не найден - удаляем только пользователя")
                self._delete_user_only(username)
                return True

            # Шаг 3: Проверить наличие VMs в пуле
            logger.debug(f"🔍 Проверяем наличие VMs в пуле {pool_name}")
            pool_vms = self._get_pool_vms(pool_name)

            if not pool_vms:
                # VMs нет - удаляем пул и пользователя
                logger.info(f"📋 VMs в пуле {pool_name} не найдены - удаляем пул и пользователя")
                self._delete_pool_and_user(pool_name, username)
                return True

            # Шаг 4: Проверить сетевые bridge, используемые VMs
            logger.debug(f"🔍 Проверяем сетевые bridge для VMs в пуле {pool_name}")
            bridge_usage = self._check_vm_bridges_usage(pool_vms)

            if not bridge_usage:
                # Нет специальных bridge - удаляем VMs, пул, пользователя
                logger.info(f"📋 Специальные bridge не найдены - удаляем VMs, пул, пользователя")
                self._delete_vms_pool_user(pool_vms, pool_name, username)
                return True

            # Шаг 5: Удалить bridge, VMs, пул, пользователя
            logger.info(f"📋 Найдены специальные bridge - удаляем bridge, VMs, пул, пользователя")
            self._delete_bridges_vms_pool_user(bridge_usage, pool_vms, pool_name, username)
            return True

        except Exception as e:
            logger.error(f"❌ Критическая ошибка удаления ресурсов пользователя {username}: {e}")
            return False

    def delete_user_resources_batch(self, usernames: list) -> dict:
        """Удалить ресурсы списка пользователей с оптимизацией для отсутствующих пользователей"""
        logger.info(f"🗑️ Начинаем пакетное удаление ресурсов {len(usernames)} пользователей")
        results = {
            'successful': [],
            'failed': [],
            'skipped': []  # Пользователи не найденные в системе
        }

        for username in usernames:
            try:
                logger.debug(f"📋 Обрабатываем пользователя: {username}")

                # Быстрая проверка существования пользователя
                user_exists = self._check_user_exists(username)

                if not user_exists:
                    logger.debug(f"⚠️ Пользователь {username} не существует - пропускаем дополнительные проверки")
                    results['skipped'].append(username)
                    continue

                # Если пользователь существует, выполняем полную очистку
                if self.delete_user_resources(username):
                    results['successful'].append(username)
                    logger.success(f"✅ Ресурсы пользователя {username} успешно удалены")
                else:
                    results['failed'].append(username)
                    logger.error(f"❌ Ошибка удаления ресурсов пользователя {username}")

            except Exception as e:
                logger.error(f"❌ Критическая ошибка обработки пользователя {username}: {e}")
                results['failed'].append(username)

        # Вывод итогов только если есть успешные удаления или ошибки
        if results['successful'] or results['failed']:
            logger.info(f"📊 Итоги пакетного удаления:")
            if results['successful']:
                logger.info(f"   ✅ Успешно: {len(results['successful'])} пользователей")
            if results['failed']:
                logger.info(f"   ❌ Ошибки: {len(results['failed'])} пользователей")
            if results['skipped']:
                logger.info(f"   ⏭️ Пропущено: {len(results['skipped'])} пользователей")

            if results['failed']:
                logger.warning(f"⚠️ Не удалось удалить ресурсы: {', '.join(results['failed'])}")

        return results

    def _check_user_exists(self, username: str) -> bool:
        """Проверить существование пользователя"""
        try:
            self.proxmox.proxmox.access.users(username).get()
            return True
        except Exception:
            return False

    def _check_pool_exists(self, pool_name: str) -> bool:
        """Проверить существование пула"""
        try:
            self.proxmox.proxmox.pools(pool_name).get()
            return True
        except Exception:
            return False

    def _get_pool_vms(self, pool_name: str) -> dict:
        """Получить VMs в пуле с информацией о нодах"""
        try:
            pool_info = self.proxmox.proxmox.pools(pool_name).get()
            members = pool_info.get('members', [])
            vm_nodes = {}

            for member in members:
                if member.get('type') == 'qemu':
                    vmid = int(member['vmid'])
                    node = member.get('node') or self.proxmox.get_vm_node(vmid)
                    if node:
                        vm_nodes[vmid] = node

            return vm_nodes
        except Exception as e:
            logger.error(f"Ошибка получения VMs из пула {pool_name}: {e}")
            return {}

    def _check_vm_bridges_usage(self, vm_nodes: dict) -> dict:
        """Проверить использование специальных bridge VMs"""
        bridge_usage = {}

        for vmid, node in vm_nodes.items():
            try:
                # Получить конфигурацию VM
                vm_config = self.proxmox.proxmox.nodes(node).qemu(vmid).config.get()

                # Проверить каждый сетевой интерфейс
                for key, value in vm_config.items():
                    if key.startswith('net') and isinstance(value, str):
                        # Разбор строки конфигурации сети
                        parts = value.split(',')
                        for part in parts:
                            if part.startswith('bridge=') and not part.startswith('bridge=vmbr0'):
                                bridge_name = part.split('=', 1)[1]
                                if bridge_name not in bridge_usage:
                                    bridge_usage[bridge_name] = []
                                bridge_usage[bridge_name].append((vmid, node))

            except Exception as e:
                logger.warning(f"Не удалось получить конфигурацию VM {vmid} на ноде {node}: {e}")

        return bridge_usage

    def _delete_user_only(self, username: str) -> bool:
        """Удалить только пользователя"""
        try:
            logger.info(f"🗑️ Удаляем пользователя {username}")
            self.proxmox.proxmox.access.users(username).delete()
            logger.success(f"✅ Пользователь {username} удален")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка удаления пользователя {username}: {e}")
            return False

    def _delete_pool_and_user(self, pool_name: str, username: str) -> bool:
        """Удалить пул и пользователя"""
        try:
            logger.info(f"🗑️ Удаляем пул {pool_name} и пользователя {username}")

            # Удаляем пул
            if not self.proxmox.force_delete_pool(pool_name):
                logger.error(f"❌ Не удалось удалить пул {pool_name}")

            # Удаляем пользователя
            try:
                self.proxmox.proxmox.access.users(username).delete()
                logger.success(f"✅ Пул {pool_name} и пользователь {username} удалены")
                return True
            except Exception as e:
                logger.error(f"❌ Ошибка удаления пользователя {username}: {e}")
                return False

        except Exception as e:
            logger.error(f"❌ Ошибка удаления пула и пользователя: {e}")
            return False

    def _delete_vms_pool_user(self, vm_nodes: dict, pool_name: str, username: str) -> bool:
        """Удалить VMs, пул и пользователя"""
        try:
            logger.info(f"🗑️ Удаляем VMs, пул {pool_name} и пользователя {username}")

            # Удаляем все VMs
            for vmid, node in vm_nodes.items():
                logger.debug(f"   Удаляем VM {vmid} на ноде {node}")
                if not self.proxmox.force_delete_vm(node, vmid):
                    logger.error(f"❌ Критическая ошибка: не удалось удалить VM {vmid} на ноде {node}")

            # Проверяем, что все VMs удалены
            remaining_vms = self._get_pool_vms(pool_name)
            if remaining_vms:
                logger.error(f"❌ Не все VMs удалены из пула {pool_name}: {list(remaining_vms.keys())}")
                return False

            # Удаляем пул и пользователя
            return self._delete_pool_and_user(pool_name, username)

        except Exception as e:
            logger.error(f"❌ Ошибка удаления VMs, пула и пользователя: {e}")
            return False

    def _delete_bridges_vms_pool_user(self, bridge_usage: dict, vm_nodes: dict, pool_name: str, username: str) -> bool:
        """Удалить bridge, VMs, пул и пользователя"""
        try:
            logger.info(f"🗑️ Удаляем bridge, VMs, пул {pool_name} и пользователя {username}")

            # Удаляем все VMs сначала
            for vmid, node in vm_nodes.items():
                logger.debug(f"   Удаляем VM {vmid} на ноде {node}")
                if not self.proxmox.force_delete_vm(node, vmid):
                    logger.error(f"❌ Критическая ошибка: не удалось удалить VM {vmid} на ноде {node}")

            # Проверяем, что все VMs удалены
            remaining_vms = self._get_pool_vms(pool_name)
            if remaining_vms:
                logger.error(f"❌ Не все VMs удалены из пула {pool_name}: {list(remaining_vms.keys())}")
                return False

            # Удаляем неиспользуемые bridge
            for bridge_name in bridge_usage.keys():
                # Проверяем, используется ли bridge другими VMs
                for node in self.proxmox.get_nodes():
                    if not self.proxmox.bridge_in_use(node, bridge_name):
                        logger.debug(f"   Удаляем неиспользуемый bridge {bridge_name} на ноде {node}")
                        self.proxmox.delete_bridge(node, bridge_name)

            # Удаляем пул и пользователя
            return self._delete_pool_and_user(pool_name, username)

        except Exception as e:
            logger.error(f"❌ Ошибка удаления bridge, VMs, пула и пользователя: {e}")
            return False
