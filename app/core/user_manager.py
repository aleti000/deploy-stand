import random
import string
from typing import Tuple, List

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
            print(f"Ошибка создания пользователя/пула: {e}")
            return False, ""
    
    def _generate_password(self) -> str:
        random_part = ''.join(random.choices(string.digits, k=8))
        return f"{{{random_part}}}"
    
    def delete_user_resources(self, username: str) -> bool:
        try:
            pool_name = username.split('@')[0]
            try:
                pool_info = self.proxmox.proxmox.pools(pool_name).get()
                members = pool_info.get('members', [])
            except Exception:
                members = []
            bridges_to_check: list[tuple[str, str]] = []
            for member in members:
                if member.get('type') == 'qemu':
                    vmid = int(member['vmid'])
                    node = member.get('node') or self.proxmox.get_vm_node(vmid)
                    if node:
                        try:
                            cfg = self.proxmox.proxmox.nodes(node).qemu(vmid).config.get()
                            for key, val in cfg.items():
                                if key.startswith('net') and isinstance(val, str):
                                    for p in val.split(','):
                                        if p.startswith('bridge='):
                                            br = p.split('=', 1)[1]
                                            if br != 'vmbr0':
                                                bridges_to_check.append((node, br))
                        except Exception:
                            pass
                        self.proxmox.delete_vm(node, vmid)
            try:
                self.proxmox.proxmox.pools(pool_name).delete()
            except Exception:
                pass
            seen = set()
            for node, br in bridges_to_check:
                key = f"{node}:{br}"
                if key in seen:
                    continue
                seen.add(key)
                try:
                    if not self.proxmox.bridge_in_use(node, br):
                        self.proxmox.delete_bridge(node, br)
                except Exception:
                    pass
            try:
                self.proxmox.proxmox.access.users(username).delete()
            except Exception:
                pass
            return True
        except Exception as e:
            print(f"Ошибка удаления ресурсов пользователя: {e}")
            return False

