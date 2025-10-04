import time
from typing import Dict, Any, List
from app.core.proxmox_manager import ProxmoxManager
from app.core.template_manager import TemplateManager
from app.utils.logger import logger


class TemplateOperations:
    """Модуль для операций с шаблонами виртуальных машин"""

    def __init__(self, proxmox_manager: ProxmoxManager):
        self.proxmox = proxmox_manager
        self.template_manager = TemplateManager.get_instance(proxmox_manager)

    def prepare_templates_for_target_node(self, config: dict[str, Any],
                                        node_selection: str = None,
                                        target_node: str = None) -> bool:
        """Подготовить шаблоны для конкретной целевой ноды"""
        try:
            # Загружаем соответствие шаблонов между нодами
            logger.debug("📋 Загружаем соответствие шаблонов между нодами...")
            self.template_manager.load_template_mapping()

            nodes = self.proxmox.get_nodes()
            if not nodes:
                logger.error("❌ Не удалось получить список нод!")
                return False

            # Определяем целевую ноду
            target_node_actual = self._select_target_node(nodes, node_selection, target_node)

            logger.debug(f"🎯 Целевая нода для подготовки шаблонов: {target_node_actual}")

            # Собираем все уникальные комбинации шаблонов и целевой ноды
            required_templates = self._collect_required_templates(config, target_node_actual)

            if not required_templates:
                logger.info("✅ Все необходимые шаблоны уже подготовлены")
                return True

            logger.info(f"📋 Требуется подготовить {len(required_templates)} локальных шаблонов...")

            # Подготавливаем каждый требуемый шаблон
            for template_key, template_info in required_templates.items():
                logger.debug(f"🔄 Подготовка шаблона: {template_key}")
                success = self._prepare_single_template(template_info)
                if not success:
                    logger.error(f"❌ Не удалось подготовить локальный шаблон для {template_key}")
                    return False

            # Сохраняем все подготовленные шаблоны в конфигурацию
            if self.template_manager.local_templates:
                logger.debug(f"💾 Сохраняем информацию о {len(self.template_manager.local_templates)} подготовленных шаблонах в конфигурацию...")
                self.template_manager.save_local_templates_to_config()
                self.template_manager.save_template_mapping()

            logger.success("🎉 Фаза подготовки шаблонов завершена успешно")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка подготовки шаблонов: {e}")
            return False

    def prepare_templates_for_balanced(self, config: dict[str, Any]) -> bool:
        """Подготовить шаблоны для равномерного распределения по всем нодам"""
        try:
            # Загружаем соответствие шаблонов между нодами
            logger.debug("📋 Загружаем соответствие шаблонов между нодами...")
            self.template_manager.load_template_mapping()

            nodes = self.proxmox.get_nodes()
            if not nodes:
                logger.error("❌ Не удалось получить список нод!")
                return False

            logger.debug(f"📋 Доступные ноды кластера: {nodes}")

            # Собираем все уникальные комбинации шаблонов и целевых нод
            required_templates = self._collect_required_templates_balanced(config, nodes)

            logger.info(f"📋 Найдено соответствий в template_mapping: {len(self.template_manager.template_mapping)}")
            logger.info(f"📋 Требуемых шаблонов для подготовки: {len(required_templates)}")

            if not required_templates:
                logger.info("✅ Все необходимые шаблоны уже подготовлены")
                return True

            logger.info(f"📋 Требуется подготовить {len(required_templates)} локальных шаблонов...")

            # Подготавливаем каждый требуемый шаблон
            for template_key, template_info in required_templates.items():
                logger.debug(f"🔄 Подготовка шаблона: {template_key}")
                success = self._prepare_single_template(template_info)
                if not success:
                    logger.error(f"❌ Не удалось подготовить локальный шаблон для {template_key}")
                    return False

            # Сохраняем все подготовленные шаблоны в конфигурацию
            if self.template_manager.local_templates:
                logger.debug(f"💾 Сохраняем информацию о {len(self.template_manager.local_templates)} подготовленных шаблонах в конфигурацию...")
                self.template_manager.save_local_templates_to_config()
                self.template_manager.save_template_mapping()

            logger.success("🎉 Фаза подготовки шаблонов завершена успешно")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка подготовки шаблонов: {e}")
            return False

    def create_local_template_for_target_node(self, template_node: str,
                                           original_template_vmid: int,
                                           target_node: str) -> int:
        """Создать локальный шаблон для конкретной целевой ноды"""
        try:
            logger.info(f"🔄 Создаем локальный шаблон на ноде '{target_node}' из оригинала VMID {original_template_vmid}...")

            # Шаг 1: Создать полный клон на ноде где расположен оригинальный шаблон
            temp_vmid = self._create_full_clone(template_node, original_template_vmid, target_node)

            if temp_vmid == 0:
                return 0

            # Шаг 2: Преобразовать ВМ в шаблон
            if not self._convert_to_template(template_node, temp_vmid):
                logger.warning(f"⚠️  Не удалось преобразовать ВМ в шаблон: {temp_vmid}")
                logger.info("💡 Продолжаем с миграцией...")

            # Шаг 3: Выполнить миграцию шаблона на нужную ноду
            if template_node != target_node:
                if not self._migrate_template(template_node, temp_vmid, target_node):
                    logger.error("❌ Ошибка миграции шаблона")
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
            logger.error(f"❌ Ошибка создания локального шаблона для целевой ноды: {e}")
            return 0

    def verify_template_exists(self, node: str, vmid: int) -> bool:
        """Проверить физическое существование шаблона на ноде"""
        try:
            # Попытаемся получить конфигурацию VM
            vm_config = self.proxmox.proxmox.nodes(node).qemu(vmid).config.get()
            if vm_config:
                # Проверяем, что это действительно шаблон
                template = vm_config.get('template', 0)
                logger.debug(f"VMID {vmid} на ноде '{node}': template={template}")
                return template == 1
            logger.debug(f"VMID {vmid} на ноде '{node}': конфигурация не получена")
            return False
        except Exception as e:
            # Если не можем получить конфигурацию, значит VM не существует
            logger.debug(f"Шаблон VMID {vmid} не найден на ноде '{node}': {e}")
            return False

    def wait_for_task(self, task, node: str, timeout: int = 300) -> bool:
        """Ожидать завершения задачи"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                status = self.proxmox.proxmox.nodes(node).tasks(task).status.get()
                if status['status'] == 'stopped':
                    return status['exitstatus'] == 'OK'
                time.sleep(2)
            except Exception as e:
                logger.error(f"❌ Ошибка проверки статуса задачи: {e}")
                return False
        logger.error("⏰ Таймаут ожидания задачи")
        return False

    def _select_target_node(self, nodes: List[str], selection: str, target_node: str) -> str:
        """Выбрать целевую ноду для развертывания"""
        if len(nodes) == 1:
            return nodes[0]
        if selection == "specific" and target_node:
            return target_node
        else:
            # Используем первую ноду по умолчанию
            return nodes[0]

    def _collect_required_templates(self, config: dict[str, Any], target_node: str) -> Dict[str, Dict[str, Any]]:
        """Собрать все уникальные комбинации шаблонов и целевой ноды"""
        required_templates = {}

        # Проходим по всем машинам в конфигурации
        for machine_config in config.get('machines', []):
            original_template_vmid = machine_config['template_vmid']
            template_node = machine_config.get('template_node', self.proxmox.get_nodes()[0])

            # Если шаблон не на той же ноде, где будет размещена машина
            if template_node != target_node:
                template_key = f"{original_template_vmid}:{target_node}"

                # Проверяем, существует ли локальный шаблон в template_mapping
                existing_template_vmid = self.template_manager.get_mapped_template(original_template_vmid, target_node)
                if existing_template_vmid:
                    # Проверяем, существует ли шаблон физически на целевой ноде
                    if self.verify_template_exists(target_node, existing_template_vmid):
                        logger.debug(f"✅ Локальный шаблон VMID {existing_template_vmid} уже существует на ноде '{target_node}'")
                        continue
                    else:
                        logger.debug(f"🔄 Локальный шаблон VMID {existing_template_vmid} не найден физически на ноде '{target_node}', пересоздаем")

                # Добавляем в список необходимых шаблонов
                required_templates[template_key] = {
                    'original_vmid': original_template_vmid,
                    'template_node': template_node,
                    'target_node': target_node,
                    'machine_config': machine_config
                }

        return required_templates

    def _collect_required_templates_balanced(self, config: dict[str, Any], nodes: List[str]) -> Dict[str, Dict[str, Any]]:
        """Собрать все уникальные комбинации шаблонов для balanced режима"""
        required_templates = {}

        # Проходим по всем машинам в конфигурации
        for machine_config in config.get('machines', []):
            original_template_vmid = machine_config['template_vmid']
            template_node = machine_config.get('template_node', nodes[0])

            # Для каждой ноды, где может быть размещена эта машина
            for node in nodes:
                # Если шаблон не на той же ноде, где будет размещена машина
                if template_node != node:
                    template_key = f"{original_template_vmid}:{node}"

                    # Проверяем, существует ли локальный шаблон в template_mapping
                    existing_template_vmid = self.template_manager.get_mapped_template(original_template_vmid, node)

                    if existing_template_vmid:
                        # Проверяем, существует ли шаблон физически на целевой ноде
                        if self.verify_template_exists(node, existing_template_vmid):
                            continue

                    # Добавляем в список необходимых шаблонов
                    required_templates[template_key] = {
                        'original_vmid': original_template_vmid,
                        'template_node': template_node,
                        'target_node': node,
                        'machine_config': machine_config
                    }
        return required_templates

    def _prepare_single_template(self, template_info: Dict[str, Any]) -> bool:
        """Подготовить один шаблон"""
        original_vmid = template_info['original_vmid']
        template_node = template_info['template_node']
        target_node = template_info['target_node']

        # Создаем локальный шаблон на целевой ноде
        local_template_vmid = self.create_local_template_for_target_node(
            template_node, original_vmid, target_node
        )

        if local_template_vmid:
            # Сохраняем информацию о локальном шаблоне
            template_key = f"{original_vmid}:{target_node}"
            self.template_manager.local_templates[template_key] = local_template_vmid
            # Обновляем соответствие шаблонов между нодами
            self.template_manager.update_template_mapping(original_vmid, template_node, target_node, local_template_vmid)
            logger.success(f"✅ Локальный шаблон VMID {local_template_vmid} подготовлен на ноде '{target_node}'")
            return True
        else:
            return False

    def _create_full_clone(self, template_node: str, original_template_vmid: int, target_node: str) -> int:
        """Создать полный клон на ноде где расположен оригинальный шаблон"""
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
            if not self.wait_for_task(task, template_node):
                logger.error("❌ Ошибка создания полной копии на исходной ноде")
                return 0
            logger.success(f"✅ Полный клон создан на ноде '{template_node}' с VMID {temp_vmid}")
            return temp_vmid
        except Exception as e:
            logger.error(f"❌ Ошибка создания полного клона: {e}")
            return 0

    def _convert_to_template(self, template_node: str, temp_vmid: int) -> bool:
        """Преобразовать ВМ в шаблон"""
        logger.info(f"📋 Шаг 2: Преобразовываем ВМ {temp_vmid} в шаблон...")
        try:
            self.proxmox.proxmox.nodes(template_node).qemu(temp_vmid).template.post()
            logger.success(f"✅ ВМ преобразована в шаблон на ноде '{template_node}'")
            return True
        except Exception as e:
            logger.warning(f"⚠️  Не удалось преобразовать ВМ в шаблон: {e}")
            return False

    def _migrate_template(self, template_node: str, temp_vmid: int, target_node: str) -> bool:
        """Выполнить миграцию шаблона на нужную ноду"""
        logger.info(f"📋 Шаг 3: Выполняем миграцию шаблона на ноду '{target_node}'...")
        try:
            migration_params = {
                'target': target_node,
                'online': 1  # Онлайн миграция
            }

            logger.debug(f"   Миграция шаблона VMID {temp_vmid} с '{template_node}' на '{target_node}'...")
            task = self.proxmox.proxmox.nodes(template_node).qemu(temp_vmid).migrate.post(**migration_params)

            if not self.wait_for_task(task, template_node):
                logger.error("❌ Ошибка миграции шаблона")
                return False

            logger.success(f"✅ Миграция успешно завершена на ноду '{target_node}'")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка миграции: {e}")
            return False
