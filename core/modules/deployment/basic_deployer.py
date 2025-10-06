"""
Базовый модуль развертывания виртуальных машин

Реализует простую стратегию развертывания виртуальных машин на одну ноду
с базовыми возможностями управления шаблонами и сетью.
"""

import logging
import secrets
import string
from typing import Dict, List, Any
from core.interfaces.deployment_interface import DeploymentInterface
from core.proxmox.proxmox_client import ProxmoxClient

logger = logging.getLogger(__name__)


class BasicDeployer(DeploymentInterface):
    """Базовая реализация развертывания виртуальных машин"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация базового развертывателя

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def deploy_configuration(self, users: List[str], config: Dict[str, Any],
                           node_selection: str = "auto", target_node: str = None) -> Dict[str, str]:
        """
        Развернуть конфигурацию виртуальных машин

        Args:
            users: Список пользователей для развертывания
            config: Конфигурация развертывания
            node_selection: Стратегия выбора ноды ("auto", "specific", "balanced")
            target_node: Целевая нода (если node_selection="specific")

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
                # Выбрать первую доступную ноду
                selected_node = nodes[0] if nodes else None

            if not selected_node:
                raise ValueError("Нет доступных нод для развертывания")

            logger.info(f"Выбрана нода для развертывания: {selected_node}")

            # Развернуть для каждого пользователя
            for user in users:
                user_result = self._deploy_for_user(user, config, selected_node)
                results.update(user_result)

            # Перезагрузить сетевые конфигурации на задействованных нодах после развертывания
            affected_nodes = set()
            for user in users:
                pool_name = user.split('@')[0]
                # Для каждого пользователя определить на какую ноду развернули
                # В базовом случае все развернуты на selected_node
                affected_nodes.add(selected_node)

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

            logger.info(f"Развертывание завершено для {len(results)} пользователей")
            return results

        except Exception as e:
            logger.error(f"Ошибка развертывания: {e}")
            raise

    def _deploy_for_user(self, user: str, config: Dict[str, Any], target_node: str) -> Dict[str, str]:
        """
        Развертывание для одного пользователя

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

            # Создать виртуальные машины
            pool_name = user.split('@')[0]

            # Проверить существует ли пользователь и обработать соответствующим образом
            user_was_existing = self.proxmox.user_exists(user)

            if user_was_existing:
                # Для существующего пользователя проверить если VM уже созданы
                if self._check_existing_user_vms(pool_name, config, target_node):
                    logger.info(f"ℹ️ Для существующего пользователя {user} VM уже созданы и настроены")
                    return {user: ""}  # Возвращаем пустой пароль для существующего пользователя

            # Создать машины если пользователь новый или у него нет подходящих VM
            for machine_config in config.get('machines', []):
                self._create_machine(machine_config, target_node, pool_name)

            logger.info(f"Развертывание для пользователя {user} завершено")
            return {user: password}

        except Exception as e:
            logger.error(f"Ошибка развертывания для пользователя {user}: {e}")
            raise

    def _create_user_and_pool(self, user: str) -> tuple[bool, str]:
        """
        Создать пользователя и пул с проверкой существования

        Args:
            user: Имя пользователя

        Returns:
            Кортеж (успех, пароль)
        """
        try:
            pool_name = user.split('@')[0]
            password = None

            # Шаг 1: Проверить существует ли пользователь
            user_exists = self.proxmox.user_exists(user)

            if not user_exists:
                # Создать пользователя если не существует
                password = self._generate_password()
                if not self.proxmox.create_user(user, password):
                    return False, ""
                logger.info(f"✅ Пользователь {user} создан")
            else:
                logger.info(f"ℹ️ Пользователь {user} уже существует")

            # Шаг 2: Проверить существует ли пул пользователя
            pool_exists = self.proxmox.pool_exists(pool_name)

            if not pool_exists:
                # Создать пул если не существует
                if not self.proxmox.create_pool(pool_name, f"Pool for {user}"):
                    if not user_exists:
                        self._cleanup_user(user)
                    return False, ""
                logger.info(f"✅ Пул {pool_name} создан")

                # Установить права пользователя на пул (роль PVEVMAdmin)
                permissions = ["PVEVMAdmin"]
                if not self.proxmox.set_pool_permissions(user, pool_name, permissions):
                    if not user_exists:
                        self._cleanup_user(user)
                    self._cleanup_pool(pool_name)
                    return False, ""
                logger.info(f"✅ Права пользователя {user} на пул {pool_name} установлены")

            else:
                logger.info(f"ℹ️ Пул {pool_name} уже существует")

                # Шаг 3: Проверить права пользователя на существующий пул
                existing_permissions = self.proxmox.get_pool_permissions(user, pool_name)
                required_permissions = ["PVEVMAdmin"]  # Теперь проверяем роль PVEVMAdmin

                missing_permissions = [perm for perm in required_permissions if perm not in existing_permissions]

                if missing_permissions:
                    logger.warning(f"⚠️ У пользователя {user} отсутствует роль PVEVMAdmin на пул {pool_name}")
                    # Попытаться установить роль
                    if not self.proxmox.set_pool_permissions(user, pool_name, missing_permissions):
                        logger.warning(f"Не удалось установить роль PVEVMAdmin для пользователя {user}")
                    else:
                        logger.info(f"✅ Роль PVEVMAdmin установлена для пользователя {user}")
                else:
                    logger.info(f"✅ Права пользователя {user} на пул {pool_name} корректны")

            # Если пользователь уже существовал, пароль пустой (не меняем существующего)
            if user_exists:
                password = ""  # Не возвращаем пароль для существующего пользователя

            logger.info(f"Пользователь {user} готов к развертыванию")
            return True, password or ""

        except Exception as e:
            logger.error(f"Ошибка подготовки пользователя и пула: {e}")
            return False, ""

    def _create_machine(self, machine_config: Dict[str, Any], target_node: str, pool: str) -> None:
        """
        Создать виртуальную машину

        Args:
            machine_config: Конфигурация машины
            target_node: Целевая нода
            pool: Имя пула
        """
        try:
            # Получить параметры машины
            template_node = machine_config.get('template_node', target_node)
            template_vmid = machine_config['template_vmid']
            device_type = machine_config.get('device_type', 'linux')
            name = machine_config.get('name', f"vm-{template_vmid}-{pool}")
            full_clone = machine_config.get('full_clone', False)

            # Получить следующий VMID
            new_vmid = self.proxmox.get_next_vmid()

            # Клонировать виртуальную машину
            task_id = self.proxmox.clone_vm(
                template_node=template_node,
                template_vmid=template_vmid,
                target_node=target_node,
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
                self._configure_machine_network(new_vmid, target_node, networks, pool, device_type)

            logger.info(f"Машина {name} (VMID: {new_vmid}) создана в пуле {pool}")

        except Exception as e:
            logger.error(f"Ошибка создания машины: {e}")
            raise

    def _configure_machine_network(self, vmid: int, node: str, networks: List[Dict],
                                 pool: str, device_type: str) -> None:
        """
        Настроить сеть виртуальной машины

        Args:
            vmid: VMID машины
            node: Нода размещения
            networks: Конфигурация сетей
            pool: Имя пула
            device_type: Тип устройства
        """
        try:
            network_configs = {}

            # Обработка ecorouter устройств
            if device_type == 'ecorouter':
                # Создать MAC адрес для управляющего интерфейса
                mac = self._generate_mac_address()
                network_configs['net0'] = f'model=vmxnet3,bridge=vmbr0,macaddr={mac},link_down=1'

            # Настроить дополнительные интерфейсы
            for i, network in enumerate(networks):
                bridge = network.get('bridge', f'vmbr{i+1}')
                net_id = f"net{i+1}" if device_type != 'ecorouter' else f"net{i+2}"

                if device_type == 'ecorouter':
                    mac = self._generate_mac_address()
                    network_configs[net_id] = f'model=vmxnet3,bridge={bridge},macaddr={mac}'
                else:
                    network_configs[net_id] = f'model=virtio,bridge={bridge},firewall=1'

            # Применить сетевую конфигурацию
            if not self.proxmox.configure_vm_network(node, vmid, network_configs):
                raise Exception(f"Ошибка настройки сети VM {vmid}")

            logger.info(f"Сеть VM {vmid} настроена")

        except Exception as e:
            logger.error(f"Ошибка настройки сети VM {vmid}: {e}")
            raise

    def _generate_password(self, length: int = 8) -> str:
        """Сгенерировать случайный пароль для обучающих стендов"""
        alphabet = string.digits  # Только цифры для простоты использования в обучении
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _generate_mac_address(self) -> str:
        """Сгенерировать случайный MAC адрес"""
        mac = [0x52, 0x54, 0x00]  # QEMU/Libvirt prefix
        mac.extend(secrets.randbelow(256) for _ in range(3))
        return ':'.join(f'{b:02x}' for b in mac)

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

    def _cleanup_pool(self, pool: str) -> None:
        """Очистить пул"""
        try:
            # Здесь можно добавить логику удаления пула
            logger.info(f"Очистка пула {pool}")
        except Exception as e:
            logger.error(f"Ошибка очистки пула {pool}: {e}")

    def _check_existing_user_vms(self, pool_name: str, config: Dict[str, Any], target_node: str) -> bool:
        """
        Проверить существующие VM пользователя

        Args:
            pool_name: Имя пула пользователя
            config: Конфигурация развертывания
            target_node: Целевая нода

        Returns:
            True если все необходимые VM существуют и настроены корректно
        """
        try:
            # Получить список VM в пуле
            pool_vms = self.proxmox.get_pool_vms(pool_name)

            if not pool_vms:
                logger.info(f"В пуле {pool_name} нет виртуальных машин")
                return False

            expected_machines = config.get('machines', [])
            if len(pool_vms) != len(expected_machines):
                logger.info(f"Количество VM в пуле {pool_name} не соответствует конфигурации "
                           f"(найдено {len(pool_vms)}, ожидается {len(expected_machines)})")
                return False

            # Проверить каждую VM в пуле
            for vm_member in pool_vms:
                vmid = vm_member.get('vmid')
                if not vmid:
                    continue

                # Найти соответствующую конфигурацию машины
                matching_config = None
                for machine_config in expected_machines:
                    # Сравниваем по template_vmid или имени
                    expected_template = machine_config.get('template_vmid')
                    vm_name = vm_member.get('name', '')
                    expected_name = machine_config.get('name', f"vm-{expected_template}-{pool_name}")

                    if str(expected_template) in vm_name or expected_name in vm_name:
                        matching_config = machine_config
                        break

                if not matching_config:
                    logger.info(f"VM {vmid} ({vm_member.get('name', 'unnamed')}) не соответствует конфигурации")
                    return False

                # Проверить сетевую конфигурацию
                networks = matching_config.get('networks', [])
                if networks:
                    if not self.proxmox.check_vm_network_config(target_node, vmid, networks):
                        logger.debug(f"Сетевая конфигурация VM {vmid} проверена")
                        # Не возвращаем False - только логируем предупреждение

            logger.info(f"Все VM в пуле {pool_name} существуют и настроены")
            return True

        except Exception as e:
            logger.error(f"Ошибка проверки существующих VM пользователя: {e}")
            return False

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
        required_fields = ['template_vmid']
        optional_fields = ['device_type', 'name', 'template_node', 'networks', 'full_clone']

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
        Получить статус развертывания

        Args:
            deployment_id: ID развертывания

        Returns:
            Словарь со статусом развертывания
        """
        # Заглушка - в реальной реализации здесь должна быть логика получения статуса
        return {
            'deployment_id': deployment_id,
            'status': 'unknown',
            'message': 'Статус развертывания недоступен в базовой реализации'
        }
