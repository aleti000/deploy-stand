import random
from typing import List, Dict, Any
from app.core.proxmox_manager import ProxmoxManager
from app.core.template_manager import TemplateManager
from app.utils.logger import logger
from app.utils.console import emphasize


class VMOperations:
    """Модуль для операций с виртуальными машинами"""

    def __init__(self, proxmox_manager: ProxmoxManager):
        self.proxmox = proxmox_manager
        self.template_manager = TemplateManager.get_instance(proxmox_manager)
        self.alias_to_vmbr: dict[str, str] = {}

    def create_user_vms(self, config: dict[str, Any], target_node: str, pool: str):
        """Создание виртуальных машин для пользователя"""
        for machine_config in config.get('machines', []):
            success = self._create_single_vm(machine_config, target_node, pool)
            if not success:
                logger.error(f"Ошибка создания ВМ {machine_config['name']}")

    def _create_single_vm(self, machine_config: dict[str, Any], target_node: str, pool: str) -> bool:
        """Создать одну виртуальную машину"""
        device_type = machine_config.get('device_type', 'linux')
        new_vmid = self.proxmox.get_next_vmid()
        while not self.proxmox.check_vmid_unique(new_vmid):
            new_vmid += 1

        # Определяем параметры шаблона
        template_node = machine_config.get('template_node', target_node)
        original_template_vmid = machine_config['template_vmid']

        # Проверяем, существует ли локальный шаблон для целевой ноды
        actual_template_vmid = self.template_manager.get_template_for_node(original_template_vmid, target_node)

        logger.info(f"📋 Создание ВМ '{machine_config['name']}' на ноде '{target_node}'")
        logger.info(f"📋 Оригинальный шаблон: VMID {original_template_vmid} на ноде '{template_node}'")
        logger.info(f"📋 Найден локальный шаблон: VMID {actual_template_vmid}")

        # Проверяем, что локальный шаблон физически существует
        if actual_template_vmid and not self.template_manager.verify_template_exists(target_node, actual_template_vmid):
            logger.warning(f"⚠️ Локальный шаблон VMID {actual_template_vmid} не найден физически на ноде '{target_node}'")
            logger.info("📋 Создаем локальный шаблон на лету...")
            actual_template_vmid = None  # Сбрасываем, чтобы создать заново

        if template_node != target_node and actual_template_vmid is None:
            # Локальный шаблон не найден, создаем его на лету
            logger.warning(f"Локальный шаблон для VMID {original_template_vmid} на ноде '{target_node}' не найден")
            logger.info(f"Создаем локальный шаблон на ноде '{target_node}'...")

            # Создаем локальный шаблон на лету
            local_template_vmid = self._create_local_template_on_demand(
                template_node, original_template_vmid, target_node
            )

            if local_template_vmid:
                # Сохраняем информацию о новом локальном шаблоне
                template_key = f"{original_template_vmid}:{target_node}"
                self.template_manager.local_templates[template_key] = local_template_vmid
                # Обновляем соответствие шаблонов между нодами
                self.template_manager.update_template_mapping(original_template_vmid, template_node, target_node, local_template_vmid)
                self.template_manager.save_template_mapping()

                actual_template_vmid = local_template_vmid
                actual_template_node = target_node
                logger.success(f"Локальный шаблон VMID {local_template_vmid} создан на ноде '{target_node}'")
            else:
                # Fallback: используем оригинальный шаблон
                logger.error("Не удалось создать локальный шаблон")
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
            return True
        else:
            logger.error(f"Ошибка создания ВМ {machine_config['name']}")
            if actual_template_node != target_node:
                logger.warning(f"Рекомендация: Проверьте локальный шаблон VMID {actual_template_vmid} на ноде '{actual_template_node}'")
            else:
                logger.warning("Проверьте, что шаблон доступен и не поврежден.")
            return False

    def _configure_network(self, vmid: int, node: str, networks: List[dict], pool: str, device_type: str = 'linux'):
        """Настроить сеть для виртуальной машины"""
        next_index_offset = 0
        mgmt_created = False

        if device_type == 'ecorouter':
            try:
                mgmt_net_id = 'net0'
                mgmt_vmbr = 'vmbr0'
                mac = self._generate_ecorouter_mac()
                value = f'model=vmxnet3,bridge={mgmt_vmbr},macaddr={mac},link_down=1'
                self.proxmox.proxmox.nodes(node).qemu(vmid).config.post(**{mgmt_net_id: value})
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
                reserved = network.get('reserved', False)
                vmbr = self._allocate_vmbr_for_alias_and_pool(node, alias, pool, reserved)
                self.proxmox.ensure_bridge(node, vmbr)

                if device_type == 'ecorouter':
                    mac = self._generate_ecorouter_mac()
                    value = f'model=vmxnet3,bridge={vmbr},macaddr={mac}'
                else:
                    value = f'model=virtio,bridge={vmbr},firewall=1'

                config_params = {f'{net_id}': value}
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
                self.proxmox.proxmox.nodes(node).qemu(vmid).config.post(**{mgmt_net_id: value})
                logger.success(f"  Повторно создан управляющий адаптер {emphasize(mgmt_net_id)} (ecorouter) на bridge {emphasize(mgmt_vmbr)}")
            except Exception as e:
                print(f"  Не удалось создать управляющий адаптер net0 повторно (сеть: vmbr0): {e}")

    def _allocate_vmbr_for_alias_and_pool(self, node: str, alias: str, pool: str, reserved: bool = False) -> str:
        """Выделить VMBR для алиаса и пула"""
        if alias == 'vmbr0':
            return 'vmbr0'
        # Если интерфейс зарезервированный, используем точное имя без генерации нового
        if reserved:
            return alias
        key = f"{node}:{pool}:{alias}"
        if key in self.alias_to_vmbr:
            return self.alias_to_vmbr[key]
        vmbr = self.proxmox.next_free_bridge_name(node, start_from=1000)
        self.alias_to_vmbr[key] = vmbr
        return vmbr

    def _generate_ecorouter_mac(self) -> str:
        """Генерировать MAC адрес для ecorouter"""
        tail = [random.randint(0x00, 0xFF) for _ in range(2)]
        return '1C:87:76:40:{:02X}:{:02X}'.format(tail[0], tail[1])

    def _create_local_template_on_demand(self, template_node: str, original_template_vmid: int, target_node: str) -> int:
        """Создать локальный шаблон на лету с использованием полного клона и миграции"""
        try:
            logger.info(f"🔄 Создаем локальный шаблон на ноде '{target_node}' из оригинала VMID {original_template_vmid}...")

            # Шаг 1: Создать полный клон на ноде где расположен оригинальный шаблон
            logger.info(f"📋 Шаг 1: Создаем полный клон на ноде '{template_node}'...")
            temp_vmid = self.proxmox.get_next_vmid()
            while not self.proxmox.check_vmid_unique(temp_vmid):
                temp_vmid += 1

            template_name = f"template-{original_template_vmid}-{target_node}"

            # Создаем полный клон на той же ноде сначала
            clone_params = {
                'newid': temp_vmid,
                'name': template_name,
                'target': template_node,  # Создаем на той же ноде сначала
                'full': 1  # Полный клон
            }

            logger.debug(f"   Создаем полную копию VMID {original_template_vmid} на ноде '{template_node}'")
            try:
                task = self.proxmox.proxmox.nodes(template_node).qemu(original_template_vmid).clone.post(**clone_params)
                if not self._wait_for_task(task, template_node):
                    logger.error("❌ Ошибка создания полной копии на исходной ноде")
                    return 0
                logger.success(f"✅ Полный клон создан на ноде '{template_node}' с VMID {temp_vmid}")
            except Exception as e:
                logger.error(f"❌ Ошибка создания полного клона: {e}")
                return 0

            # Шаг 2: Преобразовать ВМ в шаблон
            logger.info(f"📋 Шаг 2: Преобразовываем ВМ {temp_vmid} в шаблон...")
            try:
                self.proxmox.proxmox.nodes(template_node).qemu(temp_vmid).template.post()
                logger.success(f"✅ ВМ преобразована в шаблон на ноде '{template_node}'")
            except Exception as e:
                logger.warning(f"⚠️  Не удалось преобразовать ВМ в шаблон: {e}")
                logger.info("💡 Продолжаем с миграцией...")

            # Шаг 3: Выполнить миграцию шаблона на нужную ноду
            if template_node != target_node:
                logger.info(f"📋 Шаг 3: Выполняем миграцию шаблона на ноду '{target_node}'...")
                try:
                    migration_params = {
                        'target': target_node,
                        'online': 1  # Онлайн миграция
                    }

                    logger.debug(f"   Миграция шаблона VMID {temp_vmid} с '{template_node}' на '{target_node}'...")
                    task = self.proxmox.proxmox.nodes(template_node).qemu(temp_vmid).migrate.post(**migration_params)

                    if not self._wait_for_task(task, template_node):
                        logger.error("❌ Ошибка миграции шаблона")
                        # Попробуем очистить неудачно мигрированный шаблон
                        try:
                            self.proxmox.delete_vm(template_node, temp_vmid)
                        except Exception:
                            pass
                        return 0

                    logger.success(f"✅ Миграция успешно завершена на ноду '{target_node}'")

                except Exception as e:
                    logger.error(f"❌ Ошибка миграции: {e}")
                    # Попробуем очистить неудачно мигрированный шаблон
                    try:
                        self.proxmox.delete_vm(template_node, temp_vmid)
                    except Exception:
                        pass
                    return 0

            # Шаг 4: Возвращаем VMID созданного локального шаблона
            logger.success(f"📋 Локальный шаблон готов: VMID {temp_vmid} на ноде '{target_node}'")
            logger.info(f"💡 Последовательность: полный клон → шаблон → миграция")

            return temp_vmid

        except Exception as e:
            logger.error(f"Ошибка создания локального шаблона на лету: {e}")
            return 0

    def _wait_for_task(self, task, node: str, timeout: int = 300) -> bool:
        """Ожидать завершения задачи"""
        import time
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                status = self.proxmox.proxmox.nodes(node).tasks(task).status.get()
                if status['status'] == 'stopped':
                    return status['exitstatus'] == 'OK'
                time.sleep(2)
            except Exception as e:
                logger.error(f"Ошибка проверки статуса задачи: {e}")
                return False
        logger.error("Таймаут ожидания задачи")
        return False

    def check_existing_vms_in_pools(self, users: List[str], config: dict[str, Any]) -> bool:
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
