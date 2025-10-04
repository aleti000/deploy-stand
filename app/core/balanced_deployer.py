from typing import List, Dict, Any
from app.core.proxmox_manager import ProxmoxManager
from app.core.vm_deployer import VMDeployer
from app.core.template_manager import TemplateManager
from app.core.template_operations import TemplateOperations
from app.core.vm_operations import VMOperations
from app.core.deployment_distributor import DeploymentDistributor
from app.utils.logger import logger
from app.utils.console import emphasize

class BalancedDeployer:
    """Класс для развертывания виртуальных машин с равномерным распределением по нодам кластера"""

    def __init__(self, proxmox_manager: ProxmoxManager, vm_deployer: VMDeployer = None):
        self.proxmox = proxmox_manager
        self.vm_deployer = vm_deployer if vm_deployer is not None else VMDeployer(proxmox_manager)
        self.template_manager = TemplateManager.get_instance(proxmox_manager)
        self.template_ops = TemplateOperations(proxmox_manager)
        self.vm_ops = VMOperations(proxmox_manager)
        self.distributor = DeploymentDistributor(proxmox_manager)

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

        # Шаг 5: Сохраняем локальные шаблоны (теперь сохраняются в template_mapping.yml)
        if self.template_manager.local_templates:
            self.template_manager.save_template_mapping()

        logger.success(f"✅ Развертывание завершено для {len(results)} пользователей")
        return results

    def _distribute_users_to_nodes(self, users: List[str]) -> dict[str, str]:
        """Распределить пользователей по нодам равномерно"""
        return self.distributor.distribute_users_to_nodes(users)

    def _prepare_templates_for_balanced(self, config: dict[str, Any]) -> bool:
        """Подготовить шаблоны для равномерного распределения по всем нодам"""
        return self.template_ops.prepare_templates_for_balanced(config)

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
