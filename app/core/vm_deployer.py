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
        self.local_templates: dict[str, int] = {}  # Кэш для локальных шаблонов: ключ "оригинальный_vmid:target_node"
    
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
        # Загружаем существующие локальные шаблоны из конфигурации
        self.load_local_templates_from_config()

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

        # Вывод результатов развертывания
        if results:
            print("🎯 РЕЗУЛЬТАТЫ РАЗВЕРТЫВАНИЯ:")
            print("=" * 50)
            for user, password in results.items():
                print(f"👤 Пользователь: {emphasize(user)}")
                print(f"🔑 Пароль: {emphasize(password)}")
                print("-" * 30)
            print("=" * 50)
            print("⚠️  СОХРАНИТЕ ЭТУ ИНФОРМАЦИЮ! Пароли больше не будут отображаться.")
        else:
            print("❌ Развертывание не удалось или не было создано пользователей.")

        # Вывод информации о локальных шаблонах
        if self.local_templates:
            print("\n📋 СОЗДАННЫЕ ЛОКАЛЬНЫЕ ШАБЛОНЫ:")
            print("=" * 60)
            for template_key, template_vmid in self.local_templates.items():
                original_vmid, target_node = template_key.split(':')
                print(f"🔗 Шаблон VMID {template_vmid} на ноде '{target_node}' (из оригинала {original_vmid})")
            print("=" * 60)
            print("💡 Эти шаблоны будут автоматически использоваться для будущих развертываний linked clone")

            # Сохраняем локальные шаблоны в конфигурацию для будущих развертываний
            self.save_local_templates_to_config()

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

            # Определяем ноду шаблона
            template_node = machine_config.get('template_node', target_node)
            original_template_vmid = machine_config['template_vmid']

            # Проверяем, есть ли локальный шаблон для linked clone
            local_template_key = f"{original_template_vmid}:{target_node}"
            if not machine_config.get('full_clone', False) and template_node != target_node:
                if local_template_key in self.local_templates:
                    # Используем существующий локальный шаблон
                    actual_template_vmid = self.local_templates[local_template_key]
                    actual_template_node = target_node
                    print(f"📋 Используем локальный шаблон VMID {actual_template_vmid} на ноде '{actual_template_node}' для linked clone")
                else:
                    # Создаем локальный шаблон автоматически
                    print(f"📋 Автоматическое создание локального шаблона для linked clone...")
                    temp_vmid = self.proxmox.get_next_vmid()
                    while not self.proxmox.check_vmid_unique(temp_vmid):
                        temp_vmid += 1

                    template_create_ok = self.proxmox.clone_vm(
                        template_node=template_node,
                        template_vmid=original_template_vmid,
                        target_node=target_node,
                        new_vmid=temp_vmid,
                        name=f"template-{original_template_vmid}-{target_node}",
                        pool=pool,
                        full_clone=False  # Это вызовет автоматическое создание локального шаблона
                    )

                    if template_create_ok:
                        # Сохраняем информацию о локальном шаблоне
                        self.local_templates[local_template_key] = temp_vmid
                        actual_template_vmid = temp_vmid
                        actual_template_node = target_node
                        print(f"✅ Локальный шаблон создан и готов к использованию")
                    else:
                        print(f"❌ Не удалось создать локальный шаблон для linked clone")
                        print(f"🔄 Попытка использования полного клонирования как запасного варианта...")
                        # Fallback to full clone
                        actual_template_vmid = original_template_vmid
                        actual_template_node = template_node
                        # Устанавливаем флаг полного клонирования для этой ВМ
                        machine_config['full_clone'] = True
                        print(f"✅ Используем полное клонирование для ВМ {machine_config['name']}")
            else:
                # Используем оригинальную логику для full clone или когда ноды совпадают
                actual_template_vmid = original_template_vmid
                actual_template_node = template_node

            print(f"📋 Клонирование шаблона VMID {actual_template_vmid} с ноды '{actual_template_node}' на ноду '{target_node}'")

            clone_ok = self.proxmox.clone_vm(
                template_node=actual_template_node,
                template_vmid=actual_template_vmid,
                target_node=target_node,
                new_vmid=new_vmid,
                name=machine_config['name'],
                pool=pool,
                full_clone=machine_config.get('full_clone', False)
            )

            if clone_ok:
                success(f"Успешно создана ВМ {emphasize(machine_config['name'])} (VMID: {emphasize(str(new_vmid))})")
                self._configure_network(new_vmid, target_node, machine_config['networks'], pool, device_type)
                self.proxmox.ensure_vm_in_pool(pool, new_vmid)
            else:
                print(f"❌ Ошибка создания ВМ {emphasize(machine_config['name'])}")
                if actual_template_node != target_node:
                    print(f"💡 Рекомендация: Проверьте локальный шаблон VMID {actual_template_vmid} на ноде '{actual_template_node}'")
                    print("   Или настройте общее хранилище между нодами в Proxmox.")
                else:
                    print("💡 Проверьте, что шаблон доступен и не поврежден.")
    
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

    def save_local_templates_to_config(self, config_path: str = "data/deployment_config.yml") -> bool:
        """Сохранить информацию о локальных шаблонах в конфигурационный файл"""
        try:
            import yaml
            import os

            # Загружаем существующий конфиг
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
            else:
                config = {}

            # Добавляем или обновляем информацию о локальных шаблонах
            if 'local_templates' not in config:
                config['local_templates'] = {}

            for template_key, template_vmid in self.local_templates.items():
                original_vmid, target_node = template_key.split(':')
                config['local_templates'][template_key] = {
                    'vmid': template_vmid,
                    'node': target_node,
                    'original_vmid': original_vmid
                }

            # Сохраняем обновленный конфиг
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, indent=2)

            print(f"✅ Информация о локальных шаблонах сохранена в {config_path}")
            return True

        except Exception as e:
            print(f"❌ Ошибка сохранения локальных шаблонов в конфиг: {e}")
            return False

    def load_local_templates_from_config(self, config_path: str = "data/deployment_config.yml") -> bool:
        """Загрузить информацию о локальных шаблонах из конфигурационного файла"""
        try:
            import yaml
            import os

            if not os.path.exists(config_path):
                return False

            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}

            local_templates_info = config.get('local_templates', {})

            # Загружаем информацию о локальных шаблонах
            for template_key, template_info in local_templates_info.items():
                if isinstance(template_info, dict):
                    vmid = template_info.get('vmid')
                    if vmid:
                        self.local_templates[template_key] = vmid
                else:
                    # Обратная совместимость со старым форматом
                    self.local_templates[template_key] = template_info

            if self.local_templates:
                print(f"✅ Загружено {len(self.local_templates)} локальных шаблонов из конфигурации")
                for template_key, template_vmid in self.local_templates.items():
                    original_vmid, target_node = template_key.split(':')
                    print(f"   - Шаблон VMID {template_vmid} на ноде '{target_node}' (из оригинала {original_vmid})")

            return True

        except Exception as e:
            print(f"❌ Ошибка загрузки локальных шаблонов из конфига: {e}")
            return False

    def cleanup_local_template(self, original_vmid: int, target_node: str) -> bool:
        """Удалить локальный шаблон"""
        try:
            template_key = f"{original_vmid}:{target_node}"

            if template_key not in self.local_templates:
                print(f"❌ Локальный шаблон для VMID {original_vmid} на ноде '{target_node}' не найден")
                return False

            template_vmid = self.local_templates[template_key]

            # Удаляем шаблон через Proxmox API
            if self.proxmox.delete_vm(target_node, template_vmid):
                # Удаляем из кэша
                del self.local_templates[template_key]
                print(f"✅ Локальный шаблон VMID {template_vmid} удален с ноды '{target_node}'")
                return True
            else:
                print(f"❌ Не удалось удалить локальный шаблон VMID {template_vmid}")
                return False

        except Exception as e:
            print(f"❌ Ошибка удаления локального шаблона: {e}")
            return False
