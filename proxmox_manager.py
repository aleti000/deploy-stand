import proxmoxer
from typing import List, Any
import os

class ProxmoxManager:
    def __init__(self):
        self.proxmox = None
    
    def connect(self, host: str, user: str, password: str = None, 
                token_name: str = None, token_value: str = None) -> bool:
        """Подключение к Proxmox с аутентификацией по токену или паролю"""
        try:
            if token_name and token_value:
                # Аутентификация по токену :cite[1]:cite[6]:cite[9]
                self.proxmox = proxmoxer.ProxmoxAPI(
                    host,
                    user=user,
                    token_name=token_name,
                    token_value=token_value,
                    verify_ssl=False
                )
            else:
                # Аутентификация по паролю :cite[1]
                self.proxmox = proxmoxer.ProxmoxAPI(
                    host,
                    user=user,
                    password=password,
                    verify_ssl=False
                )
            
            # Проверка подключения
            self.proxmox.version.get()
            print("Успешное подключение к Proxmox!")
            return True
            
        except Exception as e:
            print(f"Ошибка подключения к Proxmox: {e}")
            return False
    
    def get_nodes(self) -> List[str]:
        """Получение списка нод в кластере"""
        try:
            nodes = self.proxmox.nodes.get()
            return [node['node'] for node in nodes]
        except Exception as e:
            print(f"Ошибка получения списка нод: {e}")
            return []
    
    def get_next_vmid(self) -> int:
        """Получение следующего доступного VMID"""
        try:
            return self.proxmox.cluster.nextid.get()
        except Exception as e:
            print(f"Ошибка получения следующего VMID: {e}")
            return 100  # fallback
    
    def check_vmid_unique(self, vmid: int) -> bool:
        """Проверка уникальности VMID в пределах кластера :cite[3]:cite[7]"""
        try:
            # Получаем все ВМ со всех нод
            nodes = self.get_nodes()
            for node in nodes:
                vms = self.proxmox.nodes(node).qemu.get()
                for vm in vms:
                    if vm['vmid'] == vmid:
                        return False
            return True
        except Exception as e:
            print(f"Ошибка проверки уникальности VMID: {e}")
            return False
    
    def clone_vm(self, template_node: str, template_vmid: int, 
                target_node: str, new_vmid: int, name: str, 
                pool: str = None) -> bool:
        """Клонирование ВМ из шаблона"""
        try:
            clone_params = {
                'newid': new_vmid,
                'name': name,
                'target': target_node,
                'full': 1  # Полный клон :cite[2]
            }
            
            if pool:
                clone_params['pool'] = pool
            
            task = self.proxmox.nodes(template_node).qemu(template_vmid).clone.post(**clone_params)
            
            # Ожидание завершения задачи
            return self._wait_for_task(task, template_node)
            
        except Exception as e:
            print(f"Ошибка клонирования ВМ: {e}")
            return False
    
    def _wait_for_task(self, task, node: str, timeout: int = 300) -> bool:
        """Ожидание завершения задачи"""
        import time
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                status = self.proxmox.nodes(node).tasks(task).status.get()
                if status['status'] == 'stopped':
                    return status['exitstatus'] == 'OK'
                time.sleep(2)
            except Exception as e:
                print(f"Ошибка проверки статуса задачи: {e}")
                return False
        
        print("Таймаут ожидания задачи")
        return False