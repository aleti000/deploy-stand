import random
import string
from typing import Tuple, List

class UserManager:
    def __init__(self, proxmox_manager):
        self.proxmox = proxmox_manager
    
    def create_user_and_pool(self, username: str) -> Tuple[bool, str]:
        """Создание пользователя и пула с правами PVEVMAdmin"""
        try:
            # Генерация пароля формата {00000-99999}
            password = self._generate_password()
            
            # Создание пользователя
            user_params = {
                'userid': username,
                'password': password
            }
            self.proxmox.proxmox.access.users.post(**user_params)
            
            # Создание пула (имя без @pve)
            pool_name = username.split('@')[0]
            pool_params = {
                'poolid': pool_name
            }
            self.proxmox.proxmox.pools.post(**pool_params)
            
            # Назначение прав на пул
            acl_params = {
                'path': f'/pool/{pool_name}',
                'roles': 'PVEVMAdmin',
                'users': username
            }
            self.proxmox.proxmox.access.acl.put(**acl_params)
            
            return True, password
            
        except Exception as e:
            print(f"Ошибка создания пользователя/пула: {e}")
            return False, ""
    
    def _generate_password(self) -> str:
        """Генерация пароля формата {00000-99999}"""
        random_part = ''.join(random.choices(string.digits, k=8))
        return f"{{{random_part}}}"
    
    def delete_user_resources(self, username: str) -> bool:
        """Удаление пользователя, пула и связанных ВМ"""
        try:
            pool_name = username.split('@')[0]
            
            # Удаление пула (автоматически удаляет связанные ВМ)
            self.proxmox.proxmox.pools(pool_name).delete()
            
            # Удаление пользователя
            self.proxmox.proxmox.access.users(username).delete()
            
            return True
            
        except Exception as e:
            print(f"Ошибка удаления ресурсов пользователя: {e}")
            return False
    
    def get_user_vms(self, username: str) -> List[dict]:
        """Получение списка ВМ пользователя"""
        try:
            pool_name = username.split('@')[0]
            pool_info = self.proxmox.proxmox.pools(pool_name).get()
            return pool_info.get('members', [])
        except Exception as e:
            print(f"Ошибка получения ВМ пользователя: {e}")
            return []