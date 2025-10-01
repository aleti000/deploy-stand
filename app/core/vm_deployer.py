from typing import List, Any
from app.core.proxmox_manager import ProxmoxManager
from app.core.user_manager import UserManager
import random
import hashlib
from app.utils.console import warn, success, title, emphasize

class VMDeployer:
    def __init__(self, proxmox_manager: ProxmoxManager):
        self.proxmox = proxmox_manager
        self.user_manager = UserManager(proxmox_manager)
        self.alias_to_vmbr: dict[str, str] = {}
    
    def _allocate_vmbr_for_alias_and_pool(self, node: str, alias: str, pool: str) -> str:
        if alias == 'vmbr0':
            return 'vmbr0'
        key = f"{node}:{pool}:{alias}"
        if key in self.alias_to_vmbr:
            return self.alias_to_vmbr[key]
        vmbr = self.proxmox.next_free_bridge_name(node, start_from=1000)
        self.alias_to_vmbr[key] = vmbr
        return vmbr
    
    def deploy_configuration(self, users: List[str], config: dict[str, Any], 
                           node_selection: str = None, target_node: str = None) -> dict[str, str]:
        results = {}
        nodes = self.proxmox.get_nodes()
        if not nodes:
            print("Не удалось получить список нод!")
            return {}
        node_index = 0
        for user in users:
            title(f"\n--- Развертывание для пользователя: {emphasize(user)} ---")
            created_user, password = self.user_manager.create_user_and_pool(user)
            if not created_user:
                print(f"Ошибка создания пользователя {user}")
                continue
            results[user] = password
            user_node = self._select_node_for_user(nodes, node_selection, target_node)
            if not user_node:
                print(f"Не удалось выбрать ноду для пользователя {user}")
                continue
            if node_selection == 'balanced' and len(nodes) > 1:
                user_node = nodes[node_index % len(nodes)]
                node_index += 1
            pool_name = user.split('@')[0]
            self._create_user_vms(config, user_node, pool_name)
        banner = "!" * 78
        print(f"\n{banner}")
        warn("ВНИМАНИЕ: После создания сетевых адаптеров необходимо вручную перезагрузить сеть на управляемых нодах.")
        warn("Рекомендуется выполнить на каждой ноде: systemctl restart networking")
        print(f"{banner}\n")
        return results
    
    def _select_node_for_user(self, nodes: List[str], selection: str, target_node: str) -> str:
        if len(nodes) == 1:
            return nodes[0]
        if selection == "specific" and target_node:
            return target_node
        elif selection == "balanced":
            return random.choice(nodes)
        else:
            return None
    
    def _create_user_vms(self, config: dict[str, Any], target_node: str, pool: str):
        for machine_config in config.get('machines', []):
            device_type = machine_config.get('device_type', 'linux')
            new_vmid = self.proxmox.get_next_vmid()
            while not self.proxmox.check_vmid_unique(new_vmid):
                new_vmid += 1
            clone_ok = self.proxmox.clone_vm(
                template_node=machine_config['template_node'],
                template_vmid=machine_config['template_vmid'],
                target_node=target_node,
                new_vmid=new_vmid,
                name=machine_config['name'],
                pool=pool
            )
            if clone_ok:
                success(f"Успешно создана ВМ {emphasize(machine_config['name'])} (VMID: {emphasize(str(new_vmid))})")
                self._configure_network(new_vmid, target_node, machine_config['networks'], pool, device_type)
                self.proxmox.ensure_vm_in_pool(pool, new_vmid)
            else:
                print(f"Ошибка создания ВМ {machine_config['name']}")
    
    def _configure_network(self, vmid: int, node: str, networks: List[dict], pool: str, device_type: str = 'linux'):
        next_index_offset = 0
        mgmt_created = False
        if device_type == 'ecorouter':
            try:
                mgmt_net_id = 'net0'
                mgmt_vmbr = 'vmbr0'
                mac = self._generate_ecorouter_mac()
                value = f'model=vmxnet3,bridge={mgmt_vmbr},macaddr={mac},link_down=1'
                self.proxmox.proxmox.nodes(node).qemu(vmid).config.post(**{mgmt_net_id: value})
                success(f"  Создан управляющий адаптер {emphasize(mgmt_net_id)} (ecorouter) на bridge {emphasize(mgmt_vmbr)}")
                mgmt_created = True
            except Exception as e:
                print(f"  Ошибка создания управляющего адаптера net0: {e}")
            next_index_offset = 1
        for idx, network in enumerate(networks):
            try:
                i = idx + next_index_offset
                net_id = f"net{i}"
                alias = network['bridge']
                vmbr = self._allocate_vmbr_for_alias_and_pool(node, alias, pool)
                self.proxmox.ensure_bridge(node, vmbr)
                if device_type == 'ecorouter':
                    mac = self._generate_ecorouter_mac()
                    value = f'model=vmxnet3,bridge={vmbr},macaddr={mac}'
                else:
                    value = f'model=virtio,bridge={vmbr},firewall=1'
                config_params = { f'{net_id}': value }
                self.proxmox.proxmox.nodes(node).qemu(vmid).config.post(**config_params)
                success(f"  Настроен сетевой адаптер {emphasize(net_id)} на bridge {emphasize(vmbr)}")
            except Exception as e:
                print(f"  Ошибка настройки сетевого адаптера {i}: {e}")
        if device_type == 'ecorouter' and not mgmt_created:
            try:
                mgmt_net_id = 'net0'
                mgmt_vmbr = 'vmbr0'
                mac = self._generate_ecorouter_mac()
                value = f'model=vmxnet3,bridge={mgmt_vmbr},macaddr={mac},link_down=1'
                self.proxmox.proxmox.nodes(node).qemu(vmid).config.post(**{mgmt_net_id: value})
                success(f"  Повторно создан управляющий адаптер {emphasize(mgmt_net_id)} (ecorouter) на bridge {emphasize(mgmt_vmbr)}")
            except Exception as e:
                print(f"  Не удалось создать управляющий адаптер net0 повторно: {e}")
    
    def _generate_ecorouter_mac(self) -> str:
        import random
        tail = [random.randint(0x00, 0xFF) for _ in range(2)]
        return '1C:87:76:40:{:02X}:{:02X}'.format(tail[0], tail[1])


