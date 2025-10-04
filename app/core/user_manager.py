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
        try:
            pool_name = username.split('@')[0]

            # Получить информацию о пуле и его членах
            try:
                pool_info = self.proxmox.proxmox.pools(pool_name).get()
                members = pool_info.get('members', [])
            except Exception:
                members = []

            # Собрать VM для удаления
            vm_nodes = {}
            for member in members:
                if member.get('type') == 'qemu':
                    vmid = int(member['vmid'])
                    node = member.get('node') or self.proxmox.get_vm_node(vmid)
                    if node:
                        vm_nodes[vmid] = node

            # Удалить все VM пользователя
            for vmid, node in vm_nodes.items():
                if not self.proxmox.force_delete_vm(node, vmid):
                    logger.error(f"Критическая ошибка: не удалось удалить VM {vmid} на ноде {node}")

            # Удалить пул и пользователя
            try:
                self.proxmox.force_delete_pool(pool_name)
            except Exception as e:
                logger.error(f"Ошибка удаления пула {pool_name}: {e}")

            try:
                self.proxmox.proxmox.access.users(username).delete()
            except Exception as e:
                logger.error(f"Ошибка удаления пользователя {username}: {e}")

            return True
        except Exception as e:
            logger.error(f"Ошибка удаления ресурсов пользователя: {e}")
            return False
