from typing import List, Any
from proxmox_manager import ProxmoxManager
from user_manager import UserManager
import random

class VMDeployer:
    def __init__(self, proxmox_manager: ProxmoxManager):
        self.proxmox = proxmox_manager
        self.user_manager = UserManager(proxmox_manager)
    
    def deploy_configuration(self, users: List[str], config: dict[str, Any], 
                           node_selection: str = None, target_node: str = None) -> dict[str, str]:
        """Развертывание конфигурации для списка пользователей"""
        results = {}
        nodes = self.proxmox.get_nodes()
        
        if not nodes:
            print("Не удалось получить список нод!")
            return {}
        
        for user in users:
            print(f"\n--- Развертывание для пользователя: {user} ---")
            
            # Создание пользователя и пула
            success, password = self.user_manager.create_user_and_pool(user)
            if not success:
                print(f"Ошибка создания пользователя {user}")
                continue
            
            results[user] = password
            
            # Определение целевой ноды для пользователя
            user_node = self._select_node_for_user(nodes, node_selection, target_node)
            if not user_node:
                print(f"Не удалось выбрать ноду для пользователя {user}")
                continue
            
            # Создание ВМ для пользователя
            pool_name = user.split('@')[0]
            self._create_user_vms(config, user_node, pool_name)
        
        return results
    
    def _select_node_for_user(self, nodes: List[str], selection: str, target_node: str) -> str:
        """Выбор ноды для размещения ВМ пользователя"""
        if len(nodes) == 1:
            return nodes[0]
        
        if selection == "specific" and target_node:
            return target_node
        elif selection == "balanced":
            # Простая реализация балансировки - случайный выбор
            return random.choice(nodes)
        else:
            return None
    
    def _create_user_vms(self, config: dict[str, Any], target_node: str, pool: str):
        """Создание ВМ пользователя согласно конфигурации"""
        for machine_config in config.get('machines', []):
            # Генерация уникального VMID для кластера :cite[3]:cite[7]
            new_vmid = self.proxmox.get_next_vmid()
            
            while not self.proxmox.check_vmid_unique(new_vmid):
                new_vmid += 1
            
            # Клонирование ВМ
            success = self.proxmox.clone_vm(
                template_node=machine_config['template_node'],
                template_vmid=machine_config['template_vmid'],
                target_node=target_node,
                new_vmid=new_vmid,
                name=machine_config['name'],
                pool=pool
            )
            
            if success:
                print(f"Успешно создана ВМ {machine_config['name']} (VMID: {new_vmid})")
                # Настройка сетевых адаптеров
                self._configure_network(new_vmid, target_node, machine_config['networks'])
            else:
                print(f"Ошибка создания ВМ {machine_config['name']}")
    
    def _configure_network(self, vmid: int, node: str, networks: List[dict]):
        """Настройка сетевых адаптеров ВМ"""
        for i, network in enumerate(networks):
            try:
                # Proxmox использует net0, net1, net2 и т.д.
                net_id = f"net{i}"
                bridge = network['bridge']
                
                # Базовая настройка сети - можно расширить дополнительными параметрами
                config_params = {
                    f'{net_id}': f'bridge={bridge},firewall=1'
                }
                
                self.proxmox.proxmox.nodes(node).qemu(vmid).config.post(**config_params)
                print(f"  Настроен сетевой адаптер {net_id} на bridge {bridge}")
                
            except Exception as e:
                print(f"  Ошибка настройки сетевого адаптера {i}: {e}")