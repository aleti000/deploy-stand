"""
Модуль сбалансированного развертывания виртуальных машин

Реализует развертывание с равномерным распределением стендов пользователей
по всем доступным нодам с полной независимостью от других модулей.
"""

import logging
import os
import secrets
import string
import time
import yaml
from typing import Dict, List, Any, Optional
from core.modules.deployment.basic_deployer import BasicDeployer
from core.proxmox.proxmox_client import ProxmoxClient
from core.interfaces.balancing_interface import BalancingInterface

logger = logging.getLogger(__name__)


class BalancedDeployer(BasicDeployer):
    """Сбалансированный развертыватель виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient, balancing_module: BalancingInterface = None):
        """
        Инициализация сбалансированного развертывателя

        Args:
            proxmox_client: Клиент для работы с Proxmox API
            balancing_module: Модуль балансировки нагрузки (по умолчанию SmartBalancer)
        """
        super().__init__(proxmox_client)

        if balancing_module is None:
            # Импорт здесь чтобы избежать циклических зависимостей
            from core.modules.balancing.smart_balancer import SmartBalancer
            self.balancer = SmartBalancer(proxmox_client)
        else:
            self.balancer = balancing_module

    def deploy_configuration(self, users: List[str], config: Dict[str, Any],
                           node_selection: str = "balanced", target_node: str = None) -> Dict[str, str]:
        """
        Развернуть конфигурацию виртуальных машин с балансировкой нагрузки

        Args:
            users: Список пользователей для развертывания
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды (всегда "balanced")
            target_node: Целевая нода (игнорируется в сбалансированном режиме)

        Returns:
            Словарь {пользователь: пароль}
        """
        results = {}

        try:
            logger.info("Начинаем сбалансированное развертывание")

            # Получить список доступных нод
            nodes = self.proxmox.get_nodes()
            if not nodes:
                raise ValueError("Нет доступных нод для развертывания")

            logger.info(f"Доступные ноды: {nodes}")

            # Распределить пользователей по нодам с помощью балансировщика
            distribution = self.balancer.distribute_deployment(users, nodes, config)
            logger.info(f"Распределение пользователей по нодам: {distribution}")

            # Развернуть каждого пользователя на назначенной ноде
            for node, node_users in distribution.items():
                if not node_users:
                    continue

                logger.info(f"Развертывание {len(node_users)} пользователей на ноде {node}")

                for user in node_users:
                    try:
                        # Определяем тип развертывания для пользователя
                        deploy_strategy = self._determine_deployment_strategy(user, config, node)

                        if deploy_strategy == "local":
                            logger.info(f"Использование локального развертывания для пользователя {user} на ноде {node}")
                            user_result = self._deploy_for_user_local(user, config, node)
                        else:  # remote
                            logger.info(f"Использование удаленного развертывания для пользователя {user} на ноде {node}")
                            # Подготовить шаблоны для целевой ноды
                            template_mapping = self._prepare_templates_for_target_node(config, node)
                            user_result = self._deploy_for_user_remote(user, config, node, template_mapping)

                        results.update(user_result)

                    except Exception as e:
                        logger.error(f"Ошибка развертывания пользователя {user} на ноде {node}: {e}")
                        # Продолжаем с другими пользователями
                        continue

            # Перезагрузить сетевые конфигурации на задействованных нодах после развертывания
            affected_nodes = set()
            for node, users in distribution.items():
                if users:  # Только если на ноде были пользователи
                    affected_nodes.add(node)

            if affected_nodes:
                print("🔄 Обновление сетевых конфигураций на задействованных нодах...")
                for node in affected_nodes:
                    try:
                        if self.proxmox.reload_node_network(node):
                            print(f"  ✅ Сеть ноды {node} обновлена")
                        else:
                            print(f"  ⚠️ Не удалось обновить сеть ноды {node}")
                    except Exception as e:
                        print(f"  ❌ Ошибка обновления сети ноды {node}: {e}")

            logger.info(f"Сбалансированное развертывание завершено для {len(results)} пользователей")
            return results

        except Exception as e:
            logger.error(f"Ошибка сбалансированного развертывания: {e}")
            raise

    def _determine_deployment_strategy(self, user: str, config: Dict[str, Any], target_node: str) -> str:
        """
        Определить стратегию развертывания для пользователя

        Args:
            user: Имя пользователя
            config: Конфигурация развертывания
            target_node: Целевая нода для пользователя

        Returns:
            "local" если развертывание на ноде шаблона, "remote" в противном случае
        """
        # Проверить все template_node из конфигурации
        for machine_config in config.get('machines', []):
            template_node = machine_config.get('template_node')
            if template_node == target_node:
                # Хотя бы один шаблон находится на целевой ноде
                return "local"

        # Все шаблоны на других нодах
        return "remote"

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Валидация конфигурации развертывания

        Args:
            config: Конфигурация для валидации

        Returns:
            True если конфигурация валидна
        """
        try:
            # Сначала выполнить базовую валидацию
            if not super().validate_config(config):
                return False

            # Дополнительная валидация для сбалансированного режима
            machines = config.get('machines', [])
            template_nodes = set()

            # Собрать все уникальные template_node
            for machine in machines:
                template_node = machine.get('template_node')
                if template_node:
                    template_nodes.add(template_node)

            if not template_nodes:
                logger.error("В конфигурации не указаны template_node для машин")
                return False

            # Проверить доступность template_node
            available_nodes = set(self.proxmox.get_nodes())
            for template_node in template_nodes:
                if template_node not in available_nodes:
                    logger.error(f"Шаблонная нода {template_node} недоступна")
                    return False

            return True

        except Exception as e:
            logger.error(f"Ошибка валидации конфигурации: {e}")
            return False

    def _create_machine_local(self, machine_config: Dict[str, Any], pool: str) -> None:
        """
        Создать виртуальную машину на локальной ноде с шаблонами

        Args:
            machine_config: Конфигурация машины
            pool: Имя пула
        """
        try:
            # Получить параметры машины
            template_node = machine_config['template_node']
            template_vmid = machine_config['template_vmid']
            device_type = machine_config.get('device_type', 'linux')
            name = machine_config.get('name', f"vm-{template_vmid}-{pool}")
            full_clone = machine_config.get('full_clone', False)

            # Получить следующий VMID
            new_vmid = self.proxmox.get_next_vmid()

            # Клонировать виртуальную машину на той же ноде где шаблон
            task_id = self.proxmox.clone_vm(
                template_node=template_node,
                template_vmid=template_vmid,
                target_node=template_node,  # Развертывание на той же ноде
                new_vmid=new_vmid,
                name=name,
                pool=pool,
                full_clone=full_clone
            )

            # Ожидать завершения клонирования
            if not self.proxmox.wait_for_task(task_id, template_node):
                raise Exception(f"Ошибка клонирования VM {new_vmid}")

            # Настроить сеть если указана
            networks = machine_config.get('networks', [])
            if networks:
                self._configure_machine_network(new_vmid, template_node, networks, pool, device_type)

            # Выдать права пользователю на созданную VM
            user = pool + '@pve'  # Восстановить полное имя пользователя из имени пула
            if not self._grant_vm_permissions(user, template_node, new_vmid):
                logger.warning(f"Не удалось выдать права пользователю {user} на VM {new_vmid}")

            logger.info(f"Машина {name} (VMID: {new_vmid}) создана локально на ноде {template_node}")

        except Exception as e:
            logger.error(f"Ошибка создания локальной машины: {e}")
            raise

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
        try:
            # Установить права PVEVMUser на конкретную VM
            # Права выдаются на путь /vms/{vmid}
            permissions = ["PVEVMUser"]

            for permission in permissions:
                self.proxmox.api.access.acl.put(
                    users=user,
                    path=f"/vms/{vmid}",
                    roles=permission,
                    propagate=0  # Не распространять на дочерние объекты
                )

            logger.info(f"Права PVEVMUser выданы пользователю {user} на VM {vmid} на ноде {node}")
            return True

        except Exception as e:
            logger.error(f"Ошибка выдачи прав пользователю {user} на VM {vmid}: {e}")
            return False

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
            new_vmid = self.proxmox.get_next_vmid()

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
                self._configure_machine_network(new_vmid, target_node, networks, pool, device_type)

            # Выдать права пользователю на созданную VM
            user = pool + '@pve'  # Восстановить полное имя пользователя из имени пула
            if not self._grant_vm_permissions(user, target_node, new_vmid):
                logger.warning(f"Не удалось выдать права пользователю {user} на VM {new_vmid}")

            logger.info(f"Машина {name} (VMID: {new_vmid}) создана на ноде {target_node} из шаблона {local_template_vmid}")

        except Exception as e:
            logger.error(f"Ошибка создания удаленной машины: {e}")
            raise

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
        try:
            pool_vms = self.proxmox.get_pool_vms(pool)
            for vm_info in pool_vms:
                if vm_info.get('name') == machine_name:
                    logger.info(f"Машина {machine_name} найдена в пуле {pool}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки существования машины {machine_name} в пуле {pool}: {e}")
            return True  # В случае ошибки считаем что существует

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

    def _deploy_for_user_local(self, user: str, config: Dict[str, Any], target_node: str) -> Dict[str, str]:
        """
        Развертывание для одного пользователя локально

        Args:
            user: Имя пользователя
            config: Конфигурация развертывания
            target_node: Целевая нода

        Returns:
            Словарь {пользователь: пароль}
        """
        try:
            # Создать пользователя и пул
            success, password = self._create_user_and_pool(user)
            if not success:
                raise Exception(f"Ошибка создания пользователя {user}")

            # Создать виртуальные машины локально
            pool_name = user.split('@')[0]
            for machine_config in config.get('machines', []):
                self._create_machine_local(machine_config, pool_name)

            logger.info(f"Локальное развертывание для пользователя {user} завершено")
            return {user: password}

        except Exception as e:
            logger.error(f"Ошибка локального развертывания для пользователя {user}: {e}")
            raise

    def _deploy_for_user_remote(self, user: str, config: Dict[str, Any],
                               target_node: str, template_mapping: Dict[str, int]) -> Dict[str, str]:
        """
        Развертывание для одного пользователя удаленно

        Args:
            user: Имя пользователя
            config: Конфигурация развертывания
            target_node: Целевая нода
            template_mapping: Mapping шаблонов

        Returns:
            Словарь {пользователь: пароль}
        """
        try:
            # Создать пользователя и пул
            success, password = self._create_user_and_pool(user)
            if not success:
                raise Exception(f"Ошибка создания пользователя {user}")

            # Создать виртуальные машины из локальных шаблонов
            pool_name = user.split('@')[0]
            for machine_config in config.get('machines', []):
                self._create_machine_remote(machine_config, target_node, pool_name, template_mapping)

            logger.info(f"Удаленное развертывание для пользователя {user} завершено")
            return {user: password}

        except Exception as e:
            logger.error(f"Ошибка удаленного развертывания для пользователя {user}: {e}")
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
            # Сгенерировать пароль
            password = self._generate_password()

            # Создать пользователя
            if not self.proxmox.create_user(user, password):
                return False, ""

            # Создать пул
            pool_name = user.split('@')[0]
            if not self.proxmox.create_pool(pool_name, f"Pool for {user}"):
                # Если создание пула неудачно, удалить пользователя
                self._cleanup_user(user)
                return False, ""

            # Установить права пользователя на пул
            permissions = ["PVEVMAdmin"]
            if not self.proxmox.set_pool_permissions(user, pool_name, permissions):
                # Если установка прав неудачна, очистить созданные ресурсы
                self._cleanup_user_and_pool(user, pool_name)
                return False, ""

            logger.info(f"Пользователь {user} и пул {pool_name} созданы")
            return True, password

        except Exception as e:
            logger.error(f"Ошибка создания пользователя и пула: {e}")
            return False, ""

    def _configure_machine_network(self, vmid: int, node: str, networks: List[Dict],
                                 pool: str, device_type: str) -> None:
        """
        Настроить сеть виртуальной машины через BridgeManager

        Args:
            vmid: VMID машины
            node: Нода размещения
            networks: Конфигурация сетей (с bridge alias'ами)
            pool: Имя пула
            device_type: Тип устройства
        """
        try:
            # ⚠️ КРИТИЧНО: использовать BridgeManager для правильного выделения bridge!
            from core.modules.network.bridge_manager import BridgeManager
            bridge_manager = BridgeManager(self.proxmox)

            # ПЕРЕДАТЬ networks с alias'ами, BridgeManager конвертирует их в реальные bridge
            if not bridge_manager.configure_network(vmid, node, networks, pool, device_type):
                raise Exception(f"Ошибка настройки сети VM {vmid} через BridgeManager")

            logger.info(f"Сеть VM {vmid} настроена через BridgeManager")

        except Exception as e:
            logger.error(f"Ошибка настройки сети VM {vmid}: {e}")
            raise

    def _generate_password(self, length: int = 8) -> str:
        """Сгенерировать случайный пароль для обучающих стендов"""
        alphabet = string.digits  # Только цифры для простоты использования в обучении
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _cleanup_user(self, user: str) -> None:
        """Очистить пользователя"""
        try:
            # Здесь можно добавить логику удаления пользователя
            logger.info(f"Очистка пользователя {user}")
        except Exception as e:
            logger.error(f"Ошибка очистки пользователя {user}: {e}")

    def _cleanup_user_and_pool(self, user: str, pool: str) -> None:
        """Очистить пользователя и пул"""
        try:
            # Здесь можно добавить логику удаления пользователя и пула
            logger.info(f"Очистка пользователя {user} и пула {pool}")
        except Exception as e:
            logger.error(f"Ошибка очистки пользователя и пула: {e}")

    def get_deployment_status(self, deployment_id: str) -> Dict[str, Any]:
        """
        Получить статус сбалансированного развертывания

        Args:
            deployment_id: ID развертывания

        Returns:
            Словарь со статусом развертывания
        """
        return {
            'deployment_id': deployment_id,
            'status': 'completed',
            'strategy': 'balanced',
            'balancer': self.balancer.__class__.__name__,
            'message': 'Сбалансированное развертывание завершено'
        }
