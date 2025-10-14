"""
Удаленный модуль развертывания виртуальных машин

Реализует развертывание на удаленной ноде с предварительной
подготовкой шаблона: full clone -> template conversion -> migration -> linked/full clone

РЕФАКТОРИНГ: Упрощенная версия с использованием базовых модулей
"""

import logging
import os
import yaml
from typing import Dict, List, Any, Optional
from core.modules.deployment.basic_deployer import BasicDeployer
from core.proxmox.proxmox_client import ProxmoxClient
from core.modules.common.config_validator import ConfigValidator
from core.modules.common.deployment_utils import DeploymentUtils
from core.modules.users.user_manager import UserManager
from core.modules.templates.template_manager import TemplateManager
from core.modules.deployment.vm_factory import VMFactory

logger = logging.getLogger(__name__)


class RemoteDeployer(BasicDeployer):
    """Удаленный развертыватель виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация удаленного развертывателя

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client
        self.utils = DeploymentUtils()
        self.validator = ConfigValidator()
        self.user_manager = UserManager(proxmox_client)
        self.template_manager = TemplateManager(proxmox_client)
        self.vm_factory = VMFactory(proxmox_client)

    def deploy_configuration(self, users: List[str], config: Dict[str, Any],
                           node_selection: str = "auto", target_node: str = None) -> Dict[str, str]:
        """
        Развернуть конфигурацию виртуальных машин на удаленной ноде

        Args:
            users: Список пользователей для развертывания
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды
            target_node: Целевая нода для развертывания

        Returns:
            Словарь {пользователь: пароль}
        """
        # Валидация конфигурации
        validation_result = self.validator.validate_deployment_config(config)
        if not validation_result.is_valid:
            error_msg = "Ошибка валидации конфигурации:\n" + str(validation_result)
            logger.error(error_msg)
            raise ValueError(error_msg)

        results = {}

        try:
            # Определить целевую ноду
            nodes = self.proxmox.get_nodes()
            if node_selection == "specific" and target_node:
                if target_node not in nodes:
                    raise ValueError(f"Целевая нода {target_node} не найдена")
                selected_node = target_node
            else:
                # Выбрать первую доступную ноду (не рекомендуется для production)
                selected_node = nodes[0] if nodes else None

            if not selected_node:
                raise ValueError("Нет доступных нод для развертывания")

            logger.info(f"Целевая нода для удаленного развертывания: {selected_node}")

            # Подготовить шаблоны для целевой ноды через TemplateManager
            template_mapping = self.template_manager.prepare_templates_for_target_node(config, selected_node)

            # Развернуть для каждого пользователя
            for user in users:
                user_result = self._deploy_for_user(user, config, selected_node, template_mapping)
                results.update(user_result)

            # Перезагрузить сетевые конфигурации на задействованных нодах
            self._reload_affected_nodes_network({selected_node})

            logger.info(f"Удаленное развертывание завершено для {len(results)} пользователей")
            return results

        except Exception as e:
            logger.error(f"Ошибка удаленного развертывания: {e}")
            raise

    def _prepare_templates_for_target_node(self, config: Dict[str, Any], target_node: str) -> Dict[str, int]:
        """
        Подготовить шаблоны для целевой ноды

        Процесс:
        1. Full clone оригинального шаблона
        2. Преобразование в шаблон
        3. Миграция на целевую ноду

        Args:
            config: Конфигурация развертывания
            target_node: Целевая нода

        Returns:
            Mapping оригинальных VMID -> локальных VMID на целевой ноде
        """
        template_mapping = {}

        # Получить уникальные шаблоны из конфигурации
        unique_templates = set()
        for machine_config in config.get('machines', []):
            template_key = f"{machine_config['template_vmid']}:{machine_config['template_node']}"
            unique_templates.add(template_key)

        logger.info(f"Подготовка {len(unique_templates)} уникальных шаблонов для ноды {target_node}")

        for template_key in unique_templates:
            try:
                original_vmid, template_node = template_key.split(':')
                original_vmid = int(original_vmid)

                # Проверить, есть ли уже подготовленный шаблон на целевой ноде
                local_template_vmid = self._find_existing_template_on_node(original_vmid, target_node)
                if local_template_vmid:
                    template_mapping[template_key] = local_template_vmid
                    logger.info(f"Найден существующий шаблон {local_template_vmid} на ноде {target_node}")
                    continue

                # Подготовить новый шаблон
                local_template_vmid = self._prepare_single_template(original_vmid, template_node, target_node)
                if local_template_vmid:
                    template_mapping[template_key] = local_template_vmid
                else:
                    raise Exception(f"Не удалось подготовить шаблон {template_key}")

            except Exception as e:
                logger.error(f"Ошибка подготовки шаблона {template_key}: {e}")
                raise

        return template_mapping

    def _prepare_single_template(self, original_vmid: int, template_node: str, target_node: str) -> int:
        """
        Подготовить один шаблон для целевой ноды

        Args:
            original_vmid: VMID оригинального шаблона
            template_node: Нода где хранится оригинальный шаблон
            target_node: Целевая нода

        Returns:
            VMID подготовленного шаблона на целевой ноде
        """
        try:
            # 1. Full clone оригинального шаблона на той же ноде
            clone_vmid = self.proxmox.get_next_vmid()
            clone_name = f"template-clone-{original_vmid}-{int(time.time())}"

            logger.info(f"Создание full clone VM {original_vmid} -> VM {clone_vmid}")
            clone_task = self.proxmox.clone_vm(
                template_node=template_node,
                template_vmid=original_vmid,
                target_node=template_node,  # Клонируем на той же ноде
                new_vmid=clone_vmid,
                name=clone_name,
                full_clone=True  # Важно: full clone для независимости
            )

            if not self.proxmox.wait_for_task(clone_task, template_node):
                raise Exception(f"Ошибка клонирования VM {clone_vmid}")

            # 2. Преобразовать в шаблон
            logger.info(f"Преобразование VM {clone_vmid} в шаблон")
            if not self.proxmox.convert_to_template(template_node, clone_vmid):
                raise Exception(f"Ошибка преобразования VM {clone_vmid} в шаблон")

            # 3. Миграция на целевую ноду (если ноды разные)
            if template_node != target_node:
                logger.info(f"Миграция шаблона VM {clone_vmid} с {template_node} на {target_node}")
                migrate_task = self.proxmox.migrate_vm(
                    source_node=template_node,
                    target_node=target_node,
                    vmid=clone_vmid,
                    online=False  # Шаблоны миграируем offline
                )

                if not self.proxmox.wait_for_task(migrate_task, template_node):
                    raise Exception(f"Ошибка миграции VM {clone_vmid}")

            logger.info(f"Шаблон VM {clone_vmid} подготовлен на ноде {target_node}")

            # Обновить mapper_template
            self._update_mapper_template(original_vmid, target_node, clone_vmid)

            return clone_vmid

        except Exception as e:
            logger.error(f"Ошибка подготовки шаблона VM {original_vmid}: {e}")
            # Попытка очистки в случае ошибки
            try:
                if 'clone_vmid' in locals():
                    self.proxmox.delete_vm(template_node, clone_vmid)
            except:
                pass
            raise

    def _find_existing_template_on_node(self, original_vmid: int, node: str) -> Optional[int]:
        """
        Найти существующий подготовленный шаблон на ноде

        Сначала проверяет API, затем mapper_template как кэш

        Args:
            original_vmid: VMID оригинального шаблона
            node: Нода для поиска

        Returns:
            VMID найденного шаблона или None
        """
        try:
            # 1. Сначала проверить через API (основной метод)
            vms = self.proxmox.get_vms_on_node(node)
            for vm in vms:
                vm_name = vm.get('name', '')
                if vm_name.startswith(f"template-clone-{original_vmid}-") and vm.get('template', 0) == 1:
                    found_vmid = int(vm['vmid'])
                    logger.info(f"Найден существующий шаблон {found_vmid} через API для {original_vmid} на {node}")
                    # Обновить mapper_template с актуальной информацией
                    self._update_mapper_template(original_vmid, node, found_vmid)
                    return found_vmid

            # 2. Проверить mapper_template только если API ничего не нашел
            mapper_data = self._load_mapper_template()
            template_mapping = mapper_data.get('template_mapping', {})
            original_mapping = template_mapping.get(original_vmid, {})
            local_vmid = original_mapping.get(node)

            if local_vmid:
                logger.warning(f"Шаблон {local_vmid} найден в mapper_template, но отсутствует в API для {original_vmid} на {node}")
                logger.info("Будет создан новый шаблон")
                # Удалить устаревшую запись из mapper_template
                if node in original_mapping:
                    del original_mapping[node]
                    self._save_mapper_template(mapper_data)

            return None
        except Exception as e:
            logger.warning(f"Ошибка поиска существующего шаблона: {e}")
            return None

    def _deploy_for_user(self, user: str, config: Dict[str, Any],
                        target_node: str, template_mapping: Dict[str, int]) -> Dict[str, str]:
        """
        Развертывание для одного пользователя на удаленной ноде

        Args:
            user: Имя пользователя
            config: Конфигурация развертывания
            target_node: Целевая нода
            template_mapping: Mapping шаблонов

        Returns:
            Словарь {пользователь: пароль}
        """
        try:
            # Проверить, существует ли уже пользователь
            if self.user_manager.check_user_exists(user):
                logger.info(f"Пользователь {user} уже существует, пропускаем создание")
                # Получить существующий пароль или сгенерировать новый
                password = self.utils.generate_password()
            else:
                # Создать пользователя и пул через UserManager
                success, password = self.user_manager.create_user_and_pool(user)
                if not success:
                    raise Exception(f"Ошибка создания пользователя {user}")

            # Создать виртуальные машины через VMFactory
            pool_name = self.utils.extract_pool_name(user)
            for machine_config in config.get('machines', []):
                self.vm_factory.create_machine_remote(machine_config, target_node, pool_name, template_mapping)

            logger.info(f"Удаленное развертывание для пользователя {user} завершено")
            return {user: password}

        except Exception as e:
            logger.error(f"Ошибка удаленного развертывания для пользователя {user}: {e}")
            raise

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Валидация конфигурации развертывания

        Args:
            config: Конфигурация для валидации

        Returns:
            True если конфигурация валидна
        """
        validation_result = self.validator.validate_deployment_config(config)
        return validation_result.is_valid

    def _reload_affected_nodes_network(self, nodes: set):
        """
        Перезагрузить сеть на задействованных нодах

        Args:
            nodes: Множество имен нод для перезагрузки
        """
        if not nodes:
            return

        print("🔄 Обновление сетевых конфигураций на задействованных нодах...")
        for node in nodes:
            try:
                if self.proxmox.reload_node_network(node):
                    print(f"  ✅ Сеть ноды {node} обновлена")
                else:
                    print(f"  ⚠️ Не удалось обновить сеть ноды {node}")
            except Exception as e:
                print(f"  ❌ Ошибка обновления сети ноды {node}: {e}")

    def get_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        """
        Получить статус удаленного развертывания

        Args:
            deployment_id: ID развертывания

        Returns:
            Словарь со статусом развертывания
        """
        return {
            'deployment_id': deployment_id,
            'status': 'completed',
            'strategy': 'remote',
            'message': 'Удаленное развертывание с подготовкой шаблонов завершено'
        }
