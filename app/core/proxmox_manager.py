import proxmoxer
from typing import List, Any

class ProxmoxManager:
    def __init__(self):
        self.proxmox = None
    
    def connect(self, host: str, user: str, password: str = None, 
                token_name: str = None, token_value: str = None) -> bool:
        try:
            if token_name and token_value:
                self.proxmox = proxmoxer.ProxmoxAPI(host, user=user, token_name=token_name, token_value=token_value, verify_ssl=False)
            else:
                self.proxmox = proxmoxer.ProxmoxAPI(host, user=user, password=password, verify_ssl=False)
            self.proxmox.version.get()
            return True
        except Exception as e:
            print(f"Ошибка подключения к Proxmox: {e}")
            return False

    def get_nodes(self) -> List[str]:
        try:
            nodes = self.proxmox.nodes.get()
            return [node['node'] for node in nodes]
        except Exception as e:
            print(f"Ошибка получения списка нод: {e}")
            return []

    def get_vm_node(self, vmid: int) -> str:
        try:
            for node in self.get_nodes():
                vms = self.proxmox.nodes(node).qemu.get()
                for vm in vms:
                    if int(vm.get('vmid', -1)) == vmid:
                        return node
            return ""
        except Exception as e:
            print(f"Ошибка определения ноды ВМ {vmid}: {e}")
            return ""

    def list_bridges(self, node: str) -> list[str]:
        try:
            nets = self.proxmox.nodes(node).network.get()
            return [n['iface'] for n in nets if n.get('type') == 'bridge']
        except Exception as e:
            print(f"Ошибка получения сетей на ноде {node}: {e}")
            return []

    def ensure_bridge(self, node: str, bridge_name: str) -> bool:
        try:
            if bridge_name == 'vmbr0':
                return True
            existing = self.list_bridges(node)
            if bridge_name in existing:
                return True
            self.proxmox.nodes(node).network.post(type='bridge', iface=bridge_name, autostart=1)
            try:
                self.proxmox.nodes(node).network.reload.post()
            except Exception:
                pass
            return True
        except Exception as e:
            print(f"Ошибка создания bridge {bridge_name} на ноде {node}: {e}")
            return False

    def next_free_bridge_name(self, node: str, start_from: int = 1000) -> str:
        try:
            existing = set(self.list_bridges(node))
            n = max(1000, start_from)
            while True:
                candidate = f"vmbr{n}"
                if candidate not in existing:
                    return candidate
                n += 1
        except Exception:
            return f"vmbr{max(1000, start_from)}"

    def get_next_vmid(self) -> int:
        """Получить следующий доступный VMID из кластера"""
        try:
            return int(self.proxmox.cluster.nextid.get())
        except Exception as e:
            print(f"Ошибка получения следующего VMID: {e}")
            return 1000

    def check_vmid_unique(self, vmid: int) -> bool:
        """Проверить уникальность VMID во всём кластере"""
        try:
            for node in self.get_nodes():
                vms = self.proxmox.nodes(node).qemu.get()
                for vm in vms:
                    if int(vm.get('vmid', -1)) == int(vmid):
                        return False
            return True
        except Exception as e:
            print(f"Ошибка проверки уникальности VMID: {e}")
            return False

    def clone_vm(self, template_node: str, template_vmid: int, 
                 target_node: str, new_vmid: int, name: str, pool: str | None) -> bool:
        try:
            clone_params = {'newid': new_vmid, 'name': name, 'target': target_node, 'full': 0}
            if pool:
                clone_params['pool'] = pool
            task = self.proxmox.nodes(template_node).qemu(template_vmid).clone.post(**clone_params)
            return self._wait_for_task(task, template_node)
        except Exception as e:
            print(f"Ошибка клонирования ВМ: {e}")
            return False

    def _wait_for_task(self, task, node: str, timeout: int = 300) -> bool:
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

    def ensure_vm_in_pool(self, pool: str, vmid: int) -> bool:
        try:
            try:
                self.proxmox.pools(pool).post(vms=str(vmid))
                return True
            except Exception as e:
                try:
                    self.proxmox.pools(pool).post(vmid=str(vmid))
                    return True
                except Exception:
                    if 'not implemented' in str(e).lower():
                        return True
                    return False
        except Exception as e:
            print(f"Ошибка при добавлении ВМ {vmid} в пул {pool}: {e}")
            return False

    def delete_vm(self, node: str, vmid: int) -> bool:
        try:
            try:
                self.proxmox.nodes(node).qemu(vmid).status.stop.post()
            except Exception:
                pass
            try:
                self.proxmox.nodes(node).qemu(vmid).delete()
            except Exception as e:
                if 'does not exist' in str(e).lower():
                    return True
                raise
            return True
        except Exception as e:
            print(f"Ошибка удаления ВМ {vmid} на ноде {node}: {e}")
            return False

    def bridge_in_use(self, node: str, bridge_name: str) -> bool:
        try:
            vms = self.proxmox.nodes(node).qemu.get()
            for vm in vms:
                vmid = int(vm.get('vmid', -1))
                if vmid < 0:
                    continue
                cfg = self.proxmox.nodes(node).qemu(vmid).config.get()
                for key, val in cfg.items():
                    if isinstance(val, str) and key.startswith('net') and f"bridge={bridge_name}" in val:
                        return True
            return False
        except Exception:
            return True

    def delete_bridge(self, node: str, bridge_name: str) -> bool:
        try:
            if bridge_name == 'vmbr0':
                return False
            self.proxmox.nodes(node).network(bridge_name).delete()
            try:
                self.proxmox.nodes(node).network.reload.post()
            except Exception:
                pass
            return True
        except Exception as e:
            print(f"Ошибка удаления bridge {bridge_name} на ноде {node}: {e}")
            return False

