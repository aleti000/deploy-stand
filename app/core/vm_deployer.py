from typing import List, Dict, Any
from app.core.proxmox_manager import ProxmoxManager
from app.core.user_manager import UserManager
from app.core.template_manager import TemplateManager
import random
from app.utils.logger import logger

class VMDeployer:
    def __init__(self, proxmox_manager: ProxmoxManager):
        self.proxmox = proxmox_manager
        self.user_manager = UserManager(proxmox_manager)
        self.template_manager = TemplateManager(proxmox_manager)
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
        logger.info("🚀 Начинаем развертывание...")

        # Подготовка шаблонов
        templates_prepared = self._prepare_all_templates(config, node_selection, target_node)
        if not templates_prepared:
            logger.error("Ошибка подготовки шаблонов")
            return {}

        # Проверка конфликтов
        existing_vms_check = self._check_existing_vms_in_pools(users, config)
        if not existing_vms_check:
            logger.error("Обнаружены конфликты. Развертывание отменено.")
            return {}

        # Создание пользователей и VMs
        results = {}
        nodes = self.proxmox.get_nodes()
        if not nodes:
            logger.error("Не удалось получить список нод!")
            return {}

        node_index = 0
        for user in users:
            logger.debug(f"Создание пользователя: {user}")
            created_user, password = self.user_manager.create_user_and_pool(user)
            if not created_user:
                logger.error(f"Ошибка создания пользователя {user}")
                continue
            results[user] = password

            user_node = self._select_node_for_user(nodes, node_selection, target_node)
            if not user_node:
                logger.error(f"Не удалось выбрать ноду для пользователя {user}")
                continue
            if node_selection == 'balanced' and len(nodes) > 1:
                user_node = nodes[node_index % len(nodes)]
                node_index += 1

            pool_name = user.split('@')[0]
            self._create_user_vms(config, user_node, pool_name)

        # Вывод результатов
        if results:
            print(f"\n✅ Развертывание завершено для {len(results)} пользователей")
            print("Учетные данные:")
            for user, password in results.items():
                print(f"  {user} : {password}")
        else:
            print("❌ Развертывание не удалось")

        # Сохраняем локальные шаблоны
        if self.template_manager.local_templates:
            self.template_manager.save_local_templates_to_config()

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
        """Создание виртуальных машин для пользователя"""
        for machine_config in config.get('machines', []):
            device_type = machine_config.get('device_type', 'linux')
            new_vmid = self.proxmox.get_next_vmid()
            while not self.proxmox.check_vmid_unique(new_vmid):
                new_vmid += 1

            # Определяем параметры шаблона
            template_node = machine_config.get('template_node', target_node)
            original_template_vmid = machine_config['template_vmid']

            # Получаем локальный шаблон для целевой ноды
            actual_template_vmid = self.template_manager.get_template_for_node(original_template_vmid, target_node)

            if template_node != target_node and actual_template_vmid is None:
                # Fallback: локальный шаблон должен был быть подготовлен заранее
                logger.error(f"Локальный шаблон для VMID {original_template_vmid} на ноде '{target_node}' не найден")
                logger.warning("Попытка использования оригинального шаблона как запасного варианта...")
                actual_template_vmid = original_template_vmid
                actual_template_node = template_node
                machine_config['full_clone'] = True
                logger.info(f"Используем оригинальный шаблон для ВМ {machine_config['name']}")
            else:
                # Используем локальный шаблон или оригинальный на той же ноде
                actual_template_vmid = actual_template_vmid if actual_template_vmid is not None else original_template_vmid
                actual_template_node = target_node if actual_template_vmid != original_template_vmid else template_node

            logger.debug(f"Создаем ВМ из шаблона VMID {actual_template_vmid} на ноде '{target_node}'")

            # Создаем ВМ из шаблона
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
                logger.success(f"Успешно создана ВМ {emphasize(machine_config['name'])} (VMID: {emphasize(str(new_vmid))})")
                self._configure_network(new_vmid, target_node, machine_config['networks'], pool, device_type)
                self.proxmox.ensure_vm_in_pool(pool, new_vmid)
            else:
                logger.error(f"Ошибка создания ВМ {machine_config['name']}")
                if actual_template_node != target_node:
                    logger.warning(f"Рекомендация: Проверьте локальный шаблон VMID {actual_template_vmid} на ноде '{actual_template_node}'")
                else:
                    logger.warning("Проверьте, что шаблон доступен и не поврежден.")
    
    def _configure_network(self, vmid: int, node: str, networks: List[dict], pool: str, device_type: str = 'linux'):
        next_index_offset = 0
        mgmt_created = False
        if device_type == 'ecorouter':
            try:
                mgmt_net_id = 'net0'
                mgmt_vmbr = 'vmbr0'
                mac = self._generate_ecorouter_mac()
                value = f'model=vmxnet3,bridge={mgmt_vmbr},macaddr={mac},link_down=1'
                self.proxmox.proxmox.nodes(node).qemu(vmid).config.post(**{mgmt_net_id: value, f'{mgmt_net_id}_comments': 'Management Network: vmbr0'})
                logger.success(f"  Создан управляющий адаптер {emphasize(mgmt_net_id)} (ecorouter) на bridge {emphasize(mgmt_vmbr)}")
                mgmt_created = True
            except Exception as e:
                print(f"  Ошибка создания управляющего адаптера net0 (сеть: vmbr0): {e}")
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
                config_params = { f'{net_id}': value, f'{net_id}_comments': f'Network: {alias}' }
                self.proxmox.proxmox.nodes(node).qemu(vmid).config.post(**config_params)
                logger.success(f"  Настроен сетевой адаптер {emphasize(net_id)} на bridge {emphasize(vmbr)} (сеть: {emphasize(alias)})")
            except Exception as e:
                print(f"  Ошибка настройки сетевого адаптера {i} (сеть: {emphasize(alias)}): {e}")
        if device_type == 'ecorouter' and not mgmt_created:
            try:
                mgmt_net_id = 'net0'
                mgmt_vmbr = 'vmbr0'
                mac = self._generate_ecorouter_mac()
                value = f'model=vmxnet3,bridge={mgmt_vmbr},macaddr={mac},link_down=1'
                self.proxmox.proxmox.nodes(node).qemu(vmid).config.post(**{mgmt_net_id: value, f'{mgmt_net_id}_comments': 'Management Network: vmbr0'})
                logger.success(f"  Повторно создан управляющий адаптер {emphasize(mgmt_net_id)} (ecorouter) на bridge {emphasize(mgmt_vmbr)}")
            except Exception as e:
                print(f"  Не удалось создать управляющий адаптер net0 повторно (сеть: vmbr0): {e}")
    
    def _generate_ecorouter_mac(self) -> str:
        tail = [random.randint(0x00, 0xFF) for _ in range(2)]
        return '1C:87:76:40:{:02X}:{:02X}'.format(tail[0], tail[1])





    def _prepare_all_templates(self, config: dict[str, Any], node_selection: str = None, target_node: str = None) -> bool:
        """Предварительная подготовка всех необходимых шаблонов перед созданием пользователей"""
        try:
            # Загружаем существующие локальные шаблоны из конфигурации
            logger.debug("Загружаем существующие локальные шаблоны из конфигурации...")
            self.template_manager.load_local_templates_from_config()

            nodes = self.proxmox.get_nodes()
            if not nodes:
                logger.error("Не удалось получить список нод!")
                return False

            # Определяем целевые ноды для подготовки шаблонов
            target_nodes = []
            if node_selection == "specific" and target_node:
                target_nodes = [target_node]
            elif node_selection == "balanced":
                target_nodes = nodes
            else:
                # Если не указан режим, используем первую ноду как целевую
                target_nodes = [nodes[0]]

            logger.debug(f"Целевые ноды для подготовки шаблонов: {target_nodes}")

            # Собираем все уникальные комбинации шаблонов и целевых нод
            required_templates = {}  # key: "original_vmid:target_node", value: template_info

            for machine_config in config.get('machines', []):
                original_template_vmid = machine_config['template_vmid']
                template_node = machine_config.get('template_node', target_nodes[0])

                # Для каждой целевой ноды проверяем необходимость локального шаблона
                for node in target_nodes:
                    template_key = f"{original_template_vmid}:{node}"

                    # Пропускаем если шаблон уже на той же ноде
                    if template_node == node:
                        continue

                    # Пропускаем если уже есть локальный шаблон
                    if template_key in self.template_manager.local_templates:
                        logger.debug(f"Локальный шаблон уже существует для {template_key}")
                        continue

                    # Добавляем в список необходимых шаблонов
                    required_templates[template_key] = {
                        'original_vmid': original_template_vmid,
                        'template_node': template_node,
                        'target_node': node,
                        'machine_config': machine_config
                    }

            if not required_templates:
                logger.info("Все необходимые шаблоны уже подготовлены")
                return True

            logger.info(f"Требуется подготовить {len(required_templates)} локальных шаблонов...")

            # Подготавливаем каждый требуемый шаблон
            for template_key, template_info in required_templates.items():
                logger.debug(f"Подготовка шаблона: {template_key}")
                original_vmid = template_info['original_vmid']
                template_node = template_info['template_node']
                target_node = template_info['target_node']

                # Генерируем уникальный VMID для локального шаблона
                temp_vmid = self.proxmox.get_next_vmid()
                while not self.proxmox.check_vmid_unique(temp_vmid):
                    temp_vmid += 1

                logger.debug(f"Создаем локальный шаблон VMID {temp_vmid} на ноде '{target_node}' из оригинала {original_vmid}...")

                template_create_ok = self.proxmox._create_local_template_via_migration(
                    template_node=template_node,
                    template_vmid=original_vmid,
                    target_node=target_node,
                    new_vmid=temp_vmid,
                    name=f"template-{original_vmid}-{target_node}",
                    pool=None
                )

                if template_create_ok:
                    # Сохраняем информацию о локальном шаблоне
                    self.template_manager.local_templates[template_key] = temp_vmid
                    logger.debug(f"Локальный шаблон подготовлен: VMID {temp_vmid} на ноде '{target_node}'")
                else:
                    logger.error(f"Не удалось подготовить локальный шаблон для {template_key}")
                    return False

            # Сохраняем все подготовленные шаблоны в конфигурацию
            if self.template_manager.local_templates:
                logger.debug(f"Сохраняем информацию о {len(self.template_manager.local_templates)} подготовленных шаблонах в конфигурацию...")
                self.template_manager.save_local_templates_to_config()

            logger.success("Фаза подготовки шаблонов завершена успешно")
            return True

        except Exception as e:
            logger.error(f"Ошибка подготовки шаблонов: {e}")
            return False

    def _check_existing_vms_in_pools(self, users: List[str], config: dict[str, Any]) -> bool:
        """Проверить наличие существующих машин в пулах пользователей"""
        try:
            logger.info("Проверка наличия машин в пулах пользователей...")

            # Получаем список всех машин из конфигурации
            required_machines = {}
            for machine_config in config.get('machines', []):
                machine_name = machine_config['name']
                required_machines[machine_name] = []

                # Для каждой машины собираем пользователей, которые ее получат
                for user in users:
                    pool_name = user.split('@')[0]
                    required_machines[machine_name].append(pool_name)

            # Проверяем каждый пул пользователя
            for user in users:
                pool_name = user.split('@')[0]

                try:
                    # Получаем информацию о пуле
                    pool_info = self.proxmox.proxmox.pools(pool_name).get()
                    members = pool_info.get('members', [])

                    # Проверяем каждую VM в пуле
                    for member in members:
                        if member.get('type') == 'qemu':
                            vmid = int(member['vmid'])
                            node = member.get('node') or self.proxmox.get_vm_node(vmid)

                            if node:
                                try:
                                    # Получаем конфигурацию VM для получения имени
                                    vm_config = self.proxmox.proxmox.nodes(node).qemu(vmid).config.get()
                                    vm_name = vm_config.get('name', f'VM-{vmid}')

                                    # Проверяем, конфликтует ли имя с требуемыми машинами
                                    for required_name, user_pools in required_machines.items():
                                        if vm_name == required_name and pool_name in user_pools:
                                            print(f"❌ Конфликт обнаружен!")
                                            print(f"   Пул: {emphasize(pool_name)}")
                                            print(f"   Существующая VM: {emphasize(vm_name)} (VMID: {vmid})")
                                            print(f"   Требуемая VM: {emphasize(required_name)}")
                                            print(f"💡 Удалите существующую VM или измените имя в конфигурации")
                                            return False

                                except Exception as e:
                                    print(f"⚠️ Не удалось получить конфигурацию VM {vmid}: {e}")

                except Exception:
                    # Пул не существует - это нормально для новых пользователей
                    continue

            logger.info("Проверка завершена. Конфликтов не обнаружено.")
            return True

        except Exception as e:
            logger.error(f"Ошибка проверки существующих машин: {e}")
            return False
