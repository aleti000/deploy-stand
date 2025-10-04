import proxmoxer
from typing import List
from app.utils.logger import logger

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
            logger.error(f"Ошибка подключения к Proxmox: {e}")
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
        """Найти общее хранилище между двумя нодами для полного клонирования"""
        try:
            source_storages = set(self.get_storages(source_node))
            target_storages = set(self.get_storages(target_node))

            print(f"🔍 Поиск общего хранилища между нодами {source_node} и {target_node}")

            # Найти пересечение хранилищ (общие хранилища)
            common = source_storages.intersection(target_storages)

            if common:
                # Предпочитаем shared хранилища для клонирования между нодами
                for storage in common:
                    storage_info = self.get_storage_info(source_node, storage)
                    if storage_info and storage_info.get('shared') == 1:
                        content_types = storage_info.get('content', '').split(',')
                        if 'images' in content_types:
                            print(f"   ✅ Выбрано shared хранилище '{storage}' для клонирования между нодами")
                            return storage

                # Fallback: используем любое общее хранилище кроме local-lvm
                for storage in common:
                    if storage != 'local-lvm':
                        storage_info = self.get_storage_info(source_node, storage)
                        if storage_info:
                            content_types = storage_info.get('content', '').split(',')
                            if 'images' in content_types:
                                print(f"   ⚠️ Используем не-shared хранилище '{storage}' для клонирования между нодами")
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
            # Если клонирование между разными нодами - используем миграцию для подготовки локального шаблона
            if template_node != target_node:
                print(f"🔄 Создаем {'полный' if full_clone else 'linked'} клон с использованием миграции между нодами {template_node} -> {target_node}")
                # Генерируем уникальный VMID для промежуточного шаблона
                template_vmid_for_migration = self.get_next_vmid()
                while not self.check_vmid_unique(template_vmid_for_migration):
                    template_vmid_for_migration += 1
                return self._create_local_template_via_migration(template_node, template_vmid, target_node, template_vmid_for_migration, name, pool)
            else:
                # Для клонирования на той же ноде используем обычный метод
                clone_params = {'newid': new_vmid, 'name': name, 'target': target_node, 'full': 1 if full_clone else 0}
                if pool:
                    clone_params['pool'] = pool

                print(f"🔄 Создаем {'полный' if full_clone else 'linked'} клон на той же ноде '{target_node}'")
                try:
                    task = self.proxmox.nodes(template_node).qemu(template_vmid).clone.post(**clone_params)
                    return self._wait_for_task(task, template_node)
                except Exception as e:
                    print(f"❌ Ошибка клонирования ВМ: {e}")
                    return False
        except Exception as e:
            print(f"Ошибка клонирования ВМ: {e}")
            return False



    def _create_local_template_via_migration(self, template_node: str, template_vmid: int,
                                           target_node: str, new_vmid: int, name: str, pool: str | None) -> bool:
        """Создать локальный шаблон на целевой ноде с использованием миграции"""
        try:
            # Шаг 1: Создать полный клон на ноде где расположен шаблон
            print(f"📋 Шаг 1: Создаем полный клон на ноде '{template_node}'...")
            template_name = f"template-{template_vmid}-{target_node}"

            # Создаем полный клон на той же ноде сначала
            clone_params = {
                'newid': new_vmid,
                'name': template_name,
                'target': template_node,  # Создаем на той же ноде сначала
                'full': 1  # Полный клон
            }

            print(f"   Создаем полную копию VMID {template_vmid} на ноде '{template_node}'")
            try:
                task = self.proxmox.nodes(template_node).qemu(template_vmid).clone.post(**clone_params)
                if not self._wait_for_task(task, template_node):
                    print("❌ Ошибка создания полной копии на исходной ноде")
                    return False
                print(f"✅ Полный клон создан на ноде '{template_node}' с VMID {new_vmid}")
            except Exception as e:
                print(f"❌ Ошибка создания полного клона: {e}")
                return False

            # Шаг 2: Преобразовать ВМ в шаблон
            print(f"📋 Шаг 2: Преобразовываем ВМ {new_vmid} в шаблон...")
            try:
                self.proxmox.nodes(template_node).qemu(new_vmid).template.post()
                print(f"✅ ВМ преобразована в шаблон на ноде '{template_node}'")
            except Exception as e:
                print(f"⚠️  Не удалось преобразовать ВМ в шаблон: {e}")
                print("💡 Продолжаем с миграцией...")

            # Шаг 3: Выполнить миграцию шаблона на нужную ноду
            print(f"📋 Шаг 3: Выполняем миграцию шаблона на ноду '{target_node}'...")
            try:
                migration_params = {
                    'target': target_node,
                    'online': 1  # Онлайн миграция
                }

                print(f"   Миграция шаблона VMID {new_vmid} с '{template_node}' на '{target_node}'...")
                task = self.proxmox.nodes(template_node).qemu(new_vmid).migrate.post(**migration_params)

                if not self._wait_for_task(task, template_node):
                    print("❌ Ошибка миграции шаблона")
                    # Попробуем очистить неудачно мигрированный шаблон
                    try:
                        self.delete_vm(template_node, new_vmid)
                    except Exception:
                        pass
                    return False

                print(f"✅ Миграция успешно завершена на ноду '{target_node}'")

            except Exception as e:
                print(f"❌ Ошибка миграции: {e}")
                # Попробуем очистить неудачно мигрированный шаблон
                try:
                    self.delete_vm(template_node, new_vmid)
                except Exception:
                    pass
                return False

            # Шаг 4: Вернуть информацию о новом шаблоне
            print(f"📋 Локальный шаблон готов: VMID {new_vmid} на ноде '{target_node}'")
            print(f"💡 Шаблон создан с помощью миграции с ноды '{template_node}' и размещен локально на ноде '{target_node}'")
            print(f"💡 Последовательность: полный клон → шаблон → миграция")

            return True

        except Exception as e:
            print(f"Ошибка создания локального шаблона через миграцию: {e}")
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
            except Exception as e:
                if 'does not exist' in str(e).lower():
                    return True

            import time
            try:
                self.proxmox.nodes(node).qemu(vmid).delete()

                # Ждем немного чтобы Proxmox обновил состояние
                time.sleep(3)

                # Проверяем, действительно ли ВМ удалена (множественные проверки)
                for check_attempt in range(3):
                    try:
                        self.proxmox.nodes(node).qemu(vmid).status.get()
                        time.sleep(1)
                        if check_attempt == 2:  # Последняя попытка
                            return False
                    except Exception:
                        return True

            except Exception as e:
                if 'does not exist' in str(e).lower():
                    return True
                return False

        except Exception as e:
            return False

    def force_delete_vm(self, node: str, vmid: int) -> bool:
        """Принудительное удаление ВМ с дополнительными проверками"""
        try:
            import time

            print(f"🗑️ Удаляется ВМ {vmid}")

            # Попытка 1: Стандартное удаление
            if self.delete_vm(node, vmid):
                print(f"✅ ВМ {vmid} успешно удалена")
                return True

            print(f"   ⚠️ Стандартное удаление не удалось, пробуем альтернативные методы")

            # Попытка 2: Удалить без остановки сначала
            try:
                self.proxmox.nodes(node).qemu(vmid).delete()
                time.sleep(3)

                # Проверяем удаление
                try:
                    self.proxmox.nodes(node).qemu(vmid).status.get()
                    print(f"❌ ВМ {vmid} все еще существует после альтернативного удаления")
                except Exception:
                    print(f"✅ ВМ {vmid} успешно удалена альтернативным методом")
                    return True
            except Exception as e:
                print(f"❌ Альтернативное удаление также не удалось: {e}")

            # Попытка 3: Проверить, существует ли ВМ вообще
            try:
                vm_info = self.proxmox.nodes(node).qemu(vmid).status.get()

                # Попробовать уничтожить (destroy) перед удалением
                try:
                    self.proxmox.nodes(node).qemu(vmid).status.destroy.post()
                    time.sleep(2)
                except Exception:
                    pass

                # Теперь попробовать удалить
                self.proxmox.nodes(node).qemu(vmid).delete()
                time.sleep(3)

                # Финальная проверка
                try:
                    self.proxmox.nodes(node).qemu(vmid).status.get()
                    print(f"❌ ВМ {vmid} все еще существует после принудительного удаления")
                    return False
                except Exception:
                    print(f"✅ ВМ {vmid} успешно удалена принудительным методом")
                    return True

            except Exception:
                print(f"✅ ВМ {vmid} не существует - уже удалена")
                return True

        except Exception as e:
            print(f"❌ Критическая ошибка принудительного удаления ВМ {vmid}: {e}")
            return False

    def bridge_in_use(self, node: str, bridge_name: str) -> bool:
        """Проверить, используется ли bridge виртуальными машинами"""
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
        """Удалить неиспользуемый bridge"""
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

    def get_bridges_in_use(self, node: str) -> List[str]:
        """Получить список всех используемых bridge на ноде"""
        try:
            vms = self.proxmox.nodes(node).qemu.get()
            used_bridges = set()

            for vm in vms:
                vmid = int(vm.get('vmid', -1))
                if vmid < 0:
                    continue
                cfg = self.proxmox.nodes(node).qemu(vmid).config.get()
                for key, val in cfg.items():
                    if isinstance(val, str) and key.startswith('net'):
                        for part in val.split(','):
                            if part.startswith('bridge='):
                                bridge = part.split('=', 1)[1]
                                used_bridges.add(bridge)

            return list(used_bridges)
        except Exception as e:
            print(f"Ошибка получения используемых bridge на ноде {node}: {e}")
            return []

    def get_templates(self, node: str) -> List[dict]:
        """Получить список шаблонов на ноде"""
        try:
            vms = self.proxmox.nodes(node).qemu.get()
            templates = []

            for vm in vms:
                vmid = int(vm.get('vmid', -1))
                if vmid < 0:
                    continue

                # Проверяем, является ли VM шаблоном
                try:
                    config = self.proxmox.nodes(node).qemu(vmid).config.get()
                    template = config.get('template', 0)

                    if template == 1:  # Это шаблон
                        vm_name = config.get('name', f'VM-{vmid}')
                        templates.append({
                            'vmid': vmid,
                            'name': vm_name,
                            'node': node
                        })
                except Exception as e:
                    # Игнорируем ошибки получения конфигурации для отдельных VM
                    continue

            return templates
        except Exception as e:
            print(f"Ошибка получения шаблонов на ноде {node}: {e}")
            return []

    def force_delete_pool(self, pool: str) -> bool:
        """Принудительное удаление пула с повторными попытками"""
        try:
            import time

            # Многократная попытка удаления пула
            for attempt in range(3):
                try:
                    self.proxmox.pools(pool).delete()

                    # Проверяем, действительно ли пул удален
                    time.sleep(1)
                    try:
                        self.proxmox.pools(pool).get()
                        if attempt == 2:  # Последняя попытка
                            return False
                    except Exception:
                        return True

                except Exception as e:
                    if 'not empty' in str(e).lower():
                        # Очистка членов пула перед следующей попыткой
                        try:
                            pool_info = self.proxmox.pools(pool).get()
                            members = pool_info.get('members', [])
                            for member in members:
                                if member.get('type') == 'qemu':
                                    vmid = int(member['vmid'])
                                    self.proxmox.pools(pool).delete(vms=str(vmid))
                        except Exception:
                            pass
                    elif attempt == 2:  # Последняя попытка
                        return False

                time.sleep(2)

            return True
        except Exception as e:
            print(f"❌ Критическая ошибка принудительного удаления пула {pool}: {e}")
            return False
