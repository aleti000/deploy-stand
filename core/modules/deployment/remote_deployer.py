"""
Удаленный модуль развертывания виртуальных машин

Реализует развертывание на удаленной ноде с предварительной
подготовкой шаблона: full clone -> template conversion -> migration -> linked/full clone

ПОЛНОСТЬЮ НЕЗАВИСИМЫЙ МОДУЛЬ - не зависит от других модулей развертывания
"""

import logging
import os
import time
import yaml
from typing import Dict, List, Any, Optional
from core.interfaces.deployment_interface import DeploymentInterface
from core.proxmox.proxmox_client import ProxmoxClient
from core.modules.network_manager import NetworkManager
from core.modules.vm_manager import VMManager
from core.services.user_service import UserService

logger = logging.getLogger(__name__)


class RemoteDeployer(DeploymentInterface):
    """Удаленный развертыватель виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация удаленного развертывателя

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client
        self.network_manager = NetworkManager(proxmox_client)
        self.vm_manager = VMManager(proxmox_client)
        self.user_service = UserService(proxmox_client)

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

            # Подготовить шаблоны для целевой ноды
            template_mapping = self._prepare_templates_for_target_node(config, selected_node)

            # Развернуть для каждого пользователя
            for user in users:
                user_result = self._deploy_for_user(user, config, selected_node, template_mapping)
                results.update(user_result)

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
            clone_vmid = self.vm_service.get_next_vmid()
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
                    self.vm_service.delete_vm(template_node, clone_vmid)
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
            # Создать пользователя и пул (или проверить существующие)
            success, password = self._create_user_and_pool(user)
            if not success:
                raise Exception(f"Ошибка создания пользователя {user}")

            # Создать виртуальные машины из локальных шаблонов (только недостающие)
            pool_name = user.split('@')[0]
            for machine_config in config.get('machines', []):
                self._create_machine_remote(machine_config, target_node, pool_name, template_mapping)

            logger.info(f"Удаленное развертывание для пользователя {user} завершено")
            return {user: password}

        except Exception as e:
            logger.error(f"Ошибка удаленного развертывания для пользователя {user}: {e}")
            raise

    def _create_machine_remote(self, machine_config: Dict[str, Any],
                              target_node: str, pool: str, template_mapping: Dict[str, int]) -> None:
        """
        Создать виртуальную машину из локального шаблона

        Проверяет наличие машины перед созданием

        Args:
            machine_config: Конфигурация машины
            target_node: Целевая нода
            pool: Имя пула
            template_mapping: Mapping шаблонов
        """
        try:
            # Получить параметры машины
            original_vmid = machine_config['template_vmid']
            template_node = machine_config['template_node']
            template_key = f"{original_vmid}:{template_node}"
            device_type = machine_config.get('device_type', 'linux')
            name = machine_config.get('name', f"vm-{original_vmid}-{pool}")
            full_clone = machine_config.get('full_clone', False)

            # Проверить, существует ли уже машина с таким именем в пуле
            if self._machine_exists_in_pool(name, pool):
                logger.info(f"Машина {name} уже существует в пуле {pool}, пропускаем создание")
                return

            # Найти локальный шаблон
            local_template_vmid = template_mapping.get(template_key)
            if not local_template_vmid:
                raise Exception(f"Локальный шаблон не найден для {template_key}")

            # Получить следующий VMID
            new_vmid = self.vm_service.get_next_vmid()

            # Клонировать из локального шаблона
            task_id = self.proxmox.clone_vm(
                template_node=target_node,
                template_vmid=local_template_vmid,
                target_node=target_node,
                new_vmid=new_vmid,
                name=name,
                pool=pool,
                full_clone=full_clone
            )

            # Ожидать завершения клонирования
            if not self.proxmox.wait_for_task(task_id, target_node):
                raise Exception(f"Ошибка клонирования VM {new_vmid}")

            # Настроить сеть если указана
            networks = machine_config.get('networks', [])
            if networks:
                self.network_manager.configure_machine_network(new_vmid, target_node, networks, pool, device_type)

            # Выдать права пользователю на созданную VM
            user = pool + '@pve'  # Восстановить полное имя пользователя из имени пула
            if not self._grant_vm_permissions(user, target_node, new_vmid):
                logger.warning(f"Не удалось выдать права пользователю {user} на VM {new_vmid}")

            logger.info(f"Машина {name} (VMID: {new_vmid}) создана на ноде {target_node} из шаблона {local_template_vmid}")

        except Exception as e:
            logger.error(f"Ошибка создания удаленной машины: {e}")
            raise

    def _create_user_and_pool(self, user: str) -> tuple[bool, str]:
        """
        Создать пользователя и пул

        Args:
            user: Имя пользователя

        Returns:
            Кортеж (успех, пароль)
        """
        try:
            # Используем UserService для создания пользователя и пула
            success, password = self.user_service.create_user_and_pool(user, "test123")
            if not success:
                logger.error(f"Не удалось создать пользователя и пул для {user}")
                return False, ""

            logger.info(f"Пользователь {user} и пул созданы через UserService")
            return True, password

        except Exception as e:
            logger.error(f"Ошибка создания пользователя и пула: {e}")
            return False, ""

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Валидация конфигурации развертывания

        Args:
            config: Конфигурация для валидации

        Returns:
            True если конфигурация валидна
        """
        try:
            # Проверка наличия секции machines
            if 'machines' not in config:
                logger.error("Конфигурация не содержит секцию 'machines'")
                return False

            machines = config['machines']
            if not isinstance(machines, list) or len(machines) == 0:
                logger.error("Секция 'machines' должна быть непустым списком")
                return False

            # Валидация каждой машины
            for i, machine in enumerate(machines):
                if not self._validate_machine_config(machine, i):
                    return False

            return True

        except Exception as e:
            logger.error(f"Ошибка валидации конфигурации: {e}")
            return False

    def _validate_machine_config(self, machine: Dict[str, Any], index: int) -> bool:
        """
        Валидация конфигурации одной машины

        Args:
            machine: Конфигурация машины
            index: Индекс машины в списке

        Returns:
            True если конфигурация валидна
        """
        required_fields = ['template_vmid', 'template_node']
        optional_fields = ['device_type', 'name', 'networks', 'full_clone']

        # Проверка обязательных полей
        for field in required_fields:
            if field not in machine:
                logger.error(f"Машина {index}: отсутствует обязательное поле '{field}'")
                return False

        # Проверка типа template_vmid
        if not isinstance(machine['template_vmid'], int):
            logger.error(f"Машина {index}: поле 'template_vmid' должно быть числом")
            return False

        # Проверка допустимых значений
        if 'device_type' in machine:
            if machine['device_type'] not in ['linux', 'ecorouter']:
                logger.error(f"Машина {index}: недопустимый тип устройства '{machine['device_type']}'")
                return False

        # Проверка типа full_clone
        if 'full_clone' in machine:
            if not isinstance(machine['full_clone'], bool):
                logger.error(f"Машина {index}: поле 'full_clone' должно быть true/false")
                return False

        # Проверка сетевой конфигурации
        if 'networks' in machine:
            if not isinstance(machine['networks'], list):
                logger.error(f"Машина {index}: поле 'networks' должно быть списком")
                return False

            for j, network in enumerate(machine['networks']):
                if not isinstance(network, dict):
                    logger.error(f"Машина {index}, сеть {j}: должна быть объектом")
                    return False

                if 'bridge' not in network:
                    logger.error(f"Машина {index}, сеть {j}: отсутствует поле 'bridge'")
                    return False

        return True

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

    def _load_mapper_template(self) -> Dict[str, Any]:
        """
        Загрузить mapper_template из файла

        Returns:
            Данные из mapper_template.yml
        """
        mapper_path = os.path.join('data', 'mapper_template.yml')
        try:
            if os.path.exists(mapper_path):
                with open(mapper_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            else:
                logger.warning("Файл mapper_template.yml не найден, создаем пустой")
                return {}
        except Exception as e:
            logger.error(f"Ошибка загрузки mapper_template.yml: {e}")
            return {}

    def _save_mapper_template(self, data: Dict[str, Any]) -> None:
        """
        Сохранить mapper_template в файл

        Args:
            data: Данные для сохранения
        """
        mapper_path = os.path.join('data', 'mapper_template.yml')
        try:
            os.makedirs(os.path.dirname(mapper_path), exist_ok=True)
            with open(mapper_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            logger.info("mapper_template.yml сохранен")
        except Exception as e:
            logger.error(f"Ошибка сохранения mapper_template.yml: {e}")

    def _machine_exists_in_pool(self, machine_name: str, pool: str) -> bool:
        """
        Проверить, существует ли машина с таким именем в пуле

        Args:
            machine_name: Имя машины
            pool: Имя пула

        Returns:
            True если машина существует
        """
        return self.vm_manager.machine_exists_in_pool(machine_name, pool)

    def _update_mapper_template(self, original_vmid: int, node: str, local_vmid: int) -> None:
        """
        Обновить mapper_template с новой информацией о шаблоне

        Args:
            original_vmid: VMID оригинального шаблона
            node: Нода размещения
            local_vmid: VMID локального шаблона
        """
        try:
            mapper_data = self._load_mapper_template()
            template_mapping = mapper_data.setdefault('template_mapping', {})

            original_mapping = template_mapping.setdefault(original_vmid, {})
            original_mapping[node] = local_vmid

            self._save_mapper_template(mapper_data)
            logger.info(f"_mapper_template обновлен: {original_vmid} -> {node}:{local_vmid}")
        except Exception as e:
            logger.error(f"Ошибка обновления mapper_template: {e}")

    def _grant_vm_permissions(self, user: str, node: str, vmid: int) -> bool:
        """
        Выдать права пользователю на конкретную виртуальную машину

        Args:
            user: Имя пользователя (например, "student1@pve")
            node: Нода размещения VM
            vmid: VMID машины

        Returns:
            True если права выданы успешно
        """
        return self.vm_manager.grant_vm_permissions(user, node, vmid)
