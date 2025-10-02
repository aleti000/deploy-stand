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

    def get_storages(self, node: str) -> List[str]:
        """Получить список доступных хранилищ на ноде"""
        try:
            storages = self.proxmox.nodes(node).storage.get()
            return [storage['storage'] for storage in storages if storage.get('enabled') == 1]
        except Exception as e:
            print(f"Ошибка получения хранилищ на ноде {node}: {e}")
            return []

    def find_common_storage(self, source_node: str, target_node: str) -> str:
        """Найти общее хранилище между двумя нодами"""
        try:
            source_storages = set(self.get_storages(source_node))
            target_storages = set(self.get_storages(target_node))

            print(f"🔍 Поиск общего хранилища между нодами {source_node} и {target_node}")
            print(f"   Хранилища источника: {sorted(source_storages)}")
            print(f"   Хранилища цели: {sorted(target_storages)}")

            # Шаг 1: Найти пересечение хранилищ (общие хранилища)
            common = source_storages.intersection(target_storages)
            print(f"   Общие хранилища: {sorted(common) if common else 'не найдены'}")

            if common:
                # Предпочитаем shared хранилища для клонирования между нодами
                for storage in common:
                    storage_info = self.get_storage_info(source_node, storage)
                    if storage_info:
                        content_types = storage_info.get('content', '').split(',')
                        is_shared = storage_info.get('shared') == 1
                        storage_type = storage_info.get('type', '')

                        print(f"   Проверка хранилища '{storage}': shared={is_shared}, type={storage_type}, content={content_types}")

                        # Предпочитаем shared storage для межнодового клонирования
                        if 'images' in content_types and is_shared:
                            print(f"   ✅ Выбрано shared хранилище '{storage}' для клонирования между нодами")
                            return storage

                # Если нет shared хранилищ, используем любые общие хранилища кроме local-lvm для локальных шаблонов
                for storage in common:
                    if storage == 'local-lvm':
                        continue

                    storage_info = self.get_storage_info(source_node, storage)
                    if storage_info:
                        content_types = storage_info.get('content', '').split(',')
                        if 'images' in content_types:
                            print(f"   ⚠️ Используем не-shared хранилище '{storage}' для клонирования между нодами")
                            return storage

            # Шаг 2: Если нет общих хранилищ, попробуем найти shared storage на любой ноде
            all_shared_storages = set()
            for storage in source_storages:
                storage_info = self.get_storage_info(source_node, storage)
                if storage_info and storage_info.get('shared') == 1:
                    all_shared_storages.add(storage)

            for storage in target_storages:
                storage_info = self.get_storage_info(target_node, storage)
                if storage_info and storage_info.get('shared') == 1:
                    all_shared_storages.add(storage)

            if all_shared_storages:
                for storage in all_shared_storages:
                    storage_info = self.get_storage_info(source_node, storage)
                    if storage_info:
                        content_types = storage_info.get('content', '').split(',')
                        if 'images' in content_types:
                            print(f"   ✅ Найдено shared хранилище '{storage}' доступное для клонирования")
                            return storage

            print(f"❌ Подходящее хранилище не найдено")
            return ""
        except Exception as e:
            print(f"Ошибка поиска общего хранилища между {source_node} и {target_node}: {e}")
            return ""

    def get_storage_info(self, node: str, storage: str) -> dict:
        """Получить информацию о хранилище"""
        try:
            storages = self.proxmox.nodes(node).storage.get()
            for s in storages:
                if s['storage'] == storage:
                    return s
            return {}
        except Exception:
            return {}

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
                 target_node: str, new_vmid: int, name: str, pool: str | None, full_clone: bool = False) -> bool:
        try:
            clone_params = {'newid': new_vmid, 'name': name, 'target': target_node, 'full': 1 if full_clone else 0}

            # Если клонирование происходит между разными нодами
            if template_node != target_node:
                if full_clone:
                    # Для полного клонирования ищем общее хранилище
                    common_storage = self.find_common_storage(template_node, target_node)
                    if common_storage:
                        clone_params['storage'] = common_storage
                        print(f"🔄 Используется общее хранилище '{common_storage}' для полного клонирования между нодами {template_node} -> {target_node}")
                    else:
                        print(f"⚠️  Внимание: Не найдено общее хранилище между нодами {template_node} и {target_node}")
                        print("   Полное клонирование может завершиться неудачей. Рекомендуется настроить общее хранилище.")
                        return False
                else:
                    # Для linked clone между разными нодами используем автоматическое создание локального шаблона
                    print(f"🔄 Автоматически создаем локальный шаблон на ноде '{target_node}' для linked clone...")
                    return self._create_local_template_for_linked_clone(template_node, template_vmid, target_node, new_vmid, name, pool)
            else:
                # Для клонирования на той же ноде
                if not full_clone:
                    # Для linked clone на той же ноде используем local-lvm
                    target_storages = self.get_storages(target_node)
                    if 'local-lvm' in target_storages:
                        clone_params['storage'] = 'local-lvm'
                        print(f"🔄 Используется local-lvm для linked clone на ноде '{target_node}'")
                    else:
                        print(f"⚠️  local-lvm не найден на ноде '{target_node}', используем хранилище по умолчанию")

            if pool:
                clone_params['pool'] = pool

            task = self.proxmox.nodes(template_node).qemu(template_vmid).clone.post(**clone_params)
            return self._wait_for_task(task, template_node)
        except Exception as e:
            print(f"Ошибка клонирования ВМ: {e}")
            return False

    def _create_local_template_for_linked_clone(self, template_node: str, template_vmid: int,
                                               target_node: str, new_vmid: int, name: str, pool: str | None) -> bool:
        """Создать локальный шаблон на целевой ноде для linked clone"""
        try:
            # Шаг 1: Найти общее хранилище для полного клонирования
            common_storage = self.find_common_storage(template_node, target_node)
            if not common_storage:
                print(f"❌ Не найдено общее хранилище между нодами {template_node} и {target_node}")
                print("💡 Рекомендация: Настройте общее хранилище между нодами в Proxmox.")
                return False

            # Шаг 2: Создать полную копию на целевую ноду
            template_name = f"template-{template_vmid}-{target_node}"
            clone_params = {
                'newid': new_vmid,
                'name': template_name,
                'target': target_node,
                'full': 1,
                'storage': common_storage
            }

            if pool:
                clone_params['pool'] = pool

            print(f"📋 Создаем полную копию шаблона VMID {template_vmid} на ноде '{target_node}'...")
            print(f"   Используемое хранилище: {common_storage}")
            try:
                task = self.proxmox.nodes(template_node).qemu(template_vmid).clone.post(**clone_params)
            except Exception as e:
                error_msg = str(e)
                if "can't clone to non-shared storage" in error_msg:
                    print(f"❌ Ошибка создания локального шаблона: {error_msg}")
                    print(f"💡 Проблема: Хранилище '{common_storage}' не является общим между нодами")
                    print(f"💡 Решения:")
                    print(f"   1. Настройте общее хранилище (NFS, Ceph, etc.) между нодами {template_node} и {target_node}")
                    print(f"   2. Используйте полное клонирование вместо linked clone")
                    print(f"   3. Разместите шаблоны на одной ноде")
                else:
                    print(f"❌ Ошибка создания полной копии для локального шаблона: {error_msg}")
                return False

            if not self._wait_for_task(task, template_node):
                print("❌ Ошибка создания полной копии для локального шаблона")
                return False

            # Шаг 3: Преобразовать скопированную ВМ в шаблон
            print(f"🔄 Преобразовываем ВМ {new_vmid} в шаблон...")
            try:
                self.proxmox.nodes(target_node).qemu(new_vmid).template.post()
                print(f"✅ Шаблон успешно создан на ноде '{target_node}' с VMID {new_vmid}")
            except Exception as e:
                print(f"⚠️  ВМ создана, но не удалось преобразовать в шаблон: {e}")
                print("💡 Можно преобразовать в шаблон вручную в веб-интерфейсе Proxmox")

            # Шаг 4: Вернуть информацию о новом шаблоне
            print(f"📋 Локальный шаблон готов: VMID {new_vmid} на ноде '{target_node}'")
            print(f"💡 Обновите конфигурацию развертывания: template_vmid={new_vmid}, template_node={target_node}")

            return True

        except Exception as e:
            print(f"Ошибка создания локального шаблона: {e}")
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
