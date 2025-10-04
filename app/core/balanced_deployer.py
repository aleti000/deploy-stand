from typing import List, Dict, Any
from app.core.proxmox_manager import ProxmoxManager
from app.core.vm_deployer import VMDeployer
from app.core.template_manager import TemplateManager
from app.utils.logger import logger
from app.utils.console import emphasize

class BalancedDeployer:
    """Класс для развертывания виртуальных машин с равномерным распределением по нодам кластера"""

    def __init__(self, proxmox_manager: ProxmoxManager, vm_deployer: VMDeployer = None):
        self.proxmox = proxmox_manager
        self.vm_deployer = vm_deployer if vm_deployer is not None else VMDeployer(proxmox_manager)
        self.template_manager = TemplateManager(proxmox_manager)

    def deploy_balanced(self, users: List[str], config: dict[str, Any]) -> dict[str, str]:
        """
        Развернуть конфигурацию с равномерным распределением пользователей по нодам

        Args:
            users: Список пользователей для развертывания
            config: Конфигурация развертывания

        Returns:
            dict: Словарь с результатами развертывания (пользователь -> пароль)
        """
        logger.info("🚀 Начинаем развертывание с равномерным распределением...")

        # Шаг 1: Подготовка шаблонов для всех нод
        templates_prepared = self._prepare_templates_for_balanced(config)
        if not templates_prepared:
            logger.error("❌ Ошибка подготовки шаблонов для равномерного распределения")
            return {}

        # Шаг 2: Проверка конфликтов
        existing_vms_check = self.vm_deployer._check_existing_vms_in_pools(users, config)
        if not existing_vms_check:
            logger.error("❌ Обнаружены конфликты. Развертывание отменено.")
            return {}

        # Шаг 3: Распределение пользователей по нодам
        user_node_mapping = self._distribute_users_to_nodes(users)

        logger.info("📋 Распределение пользователей по нодам:")
        for user, node in user_node_mapping.items():
            logger.info(f"   {user} → {node}")

        # Шаг 4: Создание пользователей и VMs
        results = {}

        for user in users:
            logger.info(f"🔄 Создание пользователя: {user}")
            created_user, password = self.vm_deployer.user_manager.create_user_and_pool(user)
            if not created_user:
                logger.error(f"❌ Ошибка создания пользователя {user}")
                continue
            results[user] = password

            user_node = user_node_mapping[user]
            logger.debug(f"Пользователь {user} размещается на ноде '{user_node}'")

            pool_name = user.split('@')[0]
            self.vm_deployer._create_user_vms(config, user_node, pool_name)

        # Шаг 5: Сохраняем локальные шаблоны
        if self.template_manager.local_templates:
            self.template_manager.save_local_templates_to_config()

        logger.success(f"✅ Развертывание завершено для {len(results)} пользователей")
        return results

    def _distribute_users_to_nodes(self, users: List[str]) -> dict[str, str]:
        """
        Распределить пользователей по нодам равномерно

        Args:
            users: Список пользователей

        Returns:
            dict: Словарь распределения пользователь -> нода
        """
        nodes = self.proxmox.get_nodes()
        if not nodes:
            logger.error("❌ Не удалось получить список нод!")
            return {}

        if len(nodes) == 1:
            # Если только одна нода, размещаем всех пользователей на ней
            return {user: nodes[0] for user in users}

        # Распределяем пользователей равномерно по всем нодам
        user_node_mapping = {}
        for i, user in enumerate(users):
            node_index = i % len(nodes)
            user_node_mapping[user] = nodes[node_index]

        return user_node_mapping

    def _prepare_templates_for_balanced(self, config: dict[str, Any]) -> bool:
        """
        Подготовить шаблоны для равномерного распределения по всем нодам

        Args:
            config: Конфигурация развертывания

        Returns:
            bool: True если подготовка успешна
        """
        try:
            # Загружаем существующие локальные шаблоны из конфигурации
            logger.debug("📋 Загружаем существующие локальные шаблоны из конфигурации...")
            self.template_manager.load_local_templates_from_config()

            # Загружаем соответствие шаблонов между нодами
            logger.debug("📋 Загружаем соответствие шаблонов между нодами...")
            self.template_manager.load_template_mapping()

            nodes = self.proxmox.get_nodes()
            if not nodes:
                logger.error("❌ Не удалось получить список нод!")
                return False

            logger.debug(f"📋 Доступные ноды кластера: {nodes}")

            # Собираем все уникальные комбинации шаблонов и целевых нод
            required_templates = {}  # key: "original_vmid:target_node", value: template_info

            # Проходим по всем машинам в конфигурации
            for machine_config in config.get('machines', []):
                original_template_vmid = machine_config['template_vmid']
                template_node = machine_config.get('template_node', nodes[0])

                # Для balanced режима машина может быть размещена на любой ноде
                nodes_for_this_machine = nodes

                # Для каждой ноды, где может быть размещена эта машина
                for node in nodes_for_this_machine:
                    # Если шаблон не на той же ноде, где будет размещена машина
                    if template_node != node:
                        template_key = f"{original_template_vmid}:{node}"

                        # Проверяем, существует ли локальный шаблон физически на ноде
                        existing_template_vmid = self.template_manager.local_templates.get(template_key)
                        if existing_template_vmid:
                            # Проверяем, существует ли шаблон физически на целевой ноде
                            if self._verify_template_exists(node, existing_template_vmid):
                                logger.debug(f"✅ Локальный шаблон VMID {existing_template_vmid} уже существует на ноде '{node}'")
                                continue
                            else:
                                logger.debug(f"🔄 Локальный шаблон VMID {existing_template_vmid} не найден физически на ноде '{node}', пересоздаем")

                        # Добавляем в список необходимых шаблонов
                        required_templates[template_key] = {
                            'original_vmid': original_template_vmid,
                            'template_node': template_node,
                            'target_node': node,
                            'machine_config': machine_config
                        }

            if not required_templates:
                logger.info("✅ Все необходимые шаблоны уже подготовлены")
                return True

            logger.info(f"📋 Требуется подготовить {len(required_templates)} локальных шаблонов...")

            # Подготавливаем каждый требуемый шаблон
            for template_key, template_info in required_templates.items():
                logger.debug(f"🔄 Подготовка шаблона: {template_key}")
                original_vmid = template_info['original_vmid']
                template_node = template_info['template_node']
                target_node = template_info['target_node']

                # Создаем локальный шаблон на целевой ноде
                local_template_vmid = self._create_local_template_for_balanced(
                    template_node, original_vmid, target_node
                )

                if local_template_vmid:
                    # Сохраняем информацию о локальном шаблоне
                    self.template_manager.local_templates[template_key] = local_template_vmid
                    # Обновляем соответствие шаблонов между нодами
                    self.template_manager.update_template_mapping(original_vmid, template_node, target_node, local_template_vmid)
                    logger.success(f"✅ Локальный шаблон VMID {local_template_vmid} подготовлен на ноде '{target_node}'")
                else:
                    logger.error(f"❌ Не удалось подготовить локальный шаблон для {template_key}")
                    return False

            # Сохраняем все подготовленные шаблоны в конфигурацию
            if self.template_manager.local_templates:
                logger.debug(f"💾 Сохраняем информацию о {len(self.template_manager.local_templates)} подготовленных шаблонах в конфигурацию...")
                self.template_manager.save_local_templates_to_config()

                # Сохраняем соответствие шаблонов в отдельный файл
                logger.debug("💾 Сохраняем соответствие шаблонов между нодами...")
                self.template_manager.save_template_mapping()

            logger.success("🎉 Фаза подготовки шаблонов завершена успешно")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка подготовки шаблонов: {e}")
            return False

    def _create_local_template_for_balanced(self, template_node: str, original_template_vmid: int, target_node: str) -> int:
        """
        Создать локальный шаблон для балансировки нагрузки

        Args:
            template_node: Нода где находится оригинальный шаблон
            original_template_vmid: VMID оригинального шаблона
            target_node: Целевая нода для локального шаблона

        Returns:
            int: VMID созданного локального шаблона или 0 при ошибке
        """
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
            logger.error(f"❌ Ошибка создания локального шаблона для балансировки: {e}")
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
                logger.error(f"❌ Ошибка проверки статуса задачи: {e}")
                return False
        logger.error("⏰ Таймаут ожидания задачи")
        return False

    def _verify_template_exists(self, node: str, vmid: int) -> bool:
        """Проверить физическое существование шаблона на ноде"""
        try:
            # Попытаемся получить конфигурацию VM
            vm_config = self.proxmox.proxmox.nodes(node).qemu(vmid).config.get()
            if vm_config:
                # Проверяем, что это действительно шаблон
                template = vm_config.get('template', 0)
                return template == 1
            return False
        except Exception as e:
            # Если не можем получить конфигурацию, значит VM не существует
            logger.debug(f"Шаблон VMID {vmid} не найден на ноде '{node}': {e}")
            return False
