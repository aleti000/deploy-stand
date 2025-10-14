"""
Валидатор конфигурации развертывания

Предоставляет централизованную валидацию конфигурационных файлов
для всех стратегий развертывания виртуальных машин.
"""

import logging
from typing import Dict, List, Any
from .deployment_utils import DeploymentUtils

logger = logging.getLogger(__name__)


class ValidationResult:
    """Результат валидации конфигурации"""

    def __init__(self, errors: List[str] = None, warnings: List[str] = None):
        self.errors = errors or []
        self.warnings = warnings or []
        self.is_valid = len(self.errors) == 0

    def add_error(self, message: str):
        """Добавить ошибку валидации"""
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str):
        """Добавить предупреждение валидации"""
        self.warnings.append(message)

    def __str__(self) -> str:
        result = []
        if self.errors:
            result.append(f"❌ Ошибки ({len(self.errors)}):")
            for error in self.errors:
                result.append(f"  • {error}")
        if self.warnings:
            result.append(f"⚠️  Предупреждения ({len(self.warnings)}):")
            for warning in self.warnings:
                result.append(f"  • {warning}")
        return "\n".join(result)


class ConfigValidator:
    """Валидатор конфигурации развертывания"""

    def __init__(self):
        self.utils = DeploymentUtils()

    def validate_deployment_config(self, config: Dict[str, Any]) -> ValidationResult:
        """
        Валидация полной конфигурации развертывания

        Args:
            config: Конфигурация для валидации

        Returns:
            Результат валидации
        """
        result = ValidationResult()

        try:
            # Проверка наличия секции machines
            if 'machines' not in config:
                result.add_error("Конфигурация не содержит секцию 'machines'")
                return result

            machines = config['machines']
            if not isinstance(machines, list):
                result.add_error("Секция 'machines' должна быть списком")
                return result

            if len(machines) == 0:
                result.add_error("Секция 'machines' не должна быть пустой")
                return result

            # Валидация каждой машины
            for i, machine in enumerate(machines):
                machine_result = self.validate_machine_config(machine, i)
                result.errors.extend(machine_result.errors)
                result.warnings.extend(machine_result.warnings)

            # Дополнительные проверки на уровне конфигурации
            self._validate_config_level_constraints(config, result)

        except Exception as e:
            result.add_error(f"Ошибка валидации конфигурации: {e}")

        return result

    def validate_machine_config(self, machine: Dict[str, Any], index: int) -> ValidationResult:
        """
        Валидация конфигурации одной машины

        Args:
            machine: Конфигурация машины
            index: Индекс машины в списке

        Returns:
            Результат валидации
        """
        result = ValidationResult()

        # Проверка обязательных полей
        required_fields = ['template_vmid', 'template_node']
        for field in required_fields:
            if field not in machine:
                result.add_error(f"Машина {index}: отсутствует обязательное поле '{field}'")
                continue

            if machine[field] is None:
                result.add_error(f"Машина {index}: поле '{field}' не может быть пустым")

        # Проверка типа template_vmid
        template_vmid = machine.get('template_vmid')
        if template_vmid is not None:
            if not isinstance(template_vmid, int):
                result.add_error(f"Машина {index}: поле 'template_vmid' должно быть числом")
            elif template_vmid < 100:
                result.add_warning(f"Машина {index}: VMID {template_vmid} меньше рекомендуемого минимума 100")

        # Проверка template_node
        template_node = machine.get('template_node')
        if template_node is not None:
            if not isinstance(template_node, str) or not template_node.strip():
                result.add_error(f"Машина {index}: поле 'template_node' должно быть непустой строкой")

        # Проверка device_type
        device_type = machine.get('device_type', 'linux')
        if device_type not in ['linux', 'ecorouter']:
            result.add_error(f"Машина {index}: недопустимый тип устройства '{device_type}'")

        # Проверка имени машины
        machine_name = machine.get('name')
        if machine_name is not None:
            if not isinstance(machine_name, str):
                result.add_error(f"Машина {index}: поле 'name' должно быть строкой")
            elif not self.utils.validate_machine_name(machine_name):
                result.add_error(f"Машина {index}: некорректное имя '{machine_name}'")

        # Проверка типа full_clone
        full_clone = machine.get('full_clone')
        if full_clone is not None and not isinstance(full_clone, bool):
            result.add_error(f"Машина {index}: поле 'full_clone' должно быть true/false")

        # Проверка сетевой конфигурации
        networks = machine.get('networks')
        if networks is not None:
            network_result = self.validate_network_config(networks, index)
            result.errors.extend(network_result.errors)
            result.warnings.extend(network_result.warnings)

        return result

    def validate_network_config(self, networks: List[Dict[str, Any]], machine_index: int) -> ValidationResult:
        """
        Валидация сетевой конфигурации

        Args:
            networks: Конфигурация сетей
            machine_index: Индекс машины для сообщений об ошибках

        Returns:
            Результат валидации
        """
        result = ValidationResult()

        if not isinstance(networks, list):
            result.add_error(f"Машина {machine_index}: поле 'networks' должно быть списком")
            return result

        if len(networks) == 0:
            result.add_warning(f"Машина {machine_index}: не указаны сетевые интерфейсы")
            return result

        # Проверка каждого сетевого интерфейса
        for i, network in enumerate(networks):
            if not isinstance(network, dict):
                result.add_error(f"Машина {machine_index}, сеть {i}: должна быть объектом")
                continue

            # Проверка bridge
            bridge = network.get('bridge')
            if bridge is None:
                result.add_error(f"Машина {machine_index}, сеть {i}: отсутствует поле 'bridge'")
            elif not isinstance(bridge, str) or not bridge.strip():
                result.add_error(f"Машина {machine_index}, сеть {i}: поле 'bridge' должно быть непустой строкой")

        # Проверка на дублирование bridge'ей
        bridges = [net.get('bridge') for net in networks if net.get('bridge')]
        if len(bridges) != len(set(bridges)):
            result.add_warning(f"Машина {machine_index}: обнаружены дублирующиеся bridge'ы")

        return result

    def validate_user_list(self, users: List[str]) -> ValidationResult:
        """
        Валидация списка пользователей

        Args:
            users: Список пользователей для валидации

        Returns:
            Результат валидации
        """
        result = ValidationResult()

        if not isinstance(users, list):
            result.add_error("Список пользователей должен быть списком")
            return result

        if len(users) == 0:
            result.add_error("Список пользователей не должен быть пустым")
            return result

        seen_users = set()
        for i, user in enumerate(users):
            # Проверка типа
            if not isinstance(user, str):
                result.add_error(f"Пользователь {i}: должен быть строкой")
                continue

            user = user.strip()
            if not user:
                result.add_error(f"Пользователь {i}: пустое имя пользователя")
                continue

            # Проверка формата user@realm
            if '@' not in user:
                result.add_warning(f"Пользователь {i}: отсутствует realm, используется 'pve' по умолчанию")
                user = f"{user}@pve"

            # Проверка дубликатов
            if user in seen_users:
                result.add_error(f"Пользователь {i}: дубликат пользователя '{user}'")
            seen_users.add(user)

            # Проверка имени пользователя
            pool_name = self.utils.extract_pool_name(user)
            if not pool_name:
                result.add_error(f"Пользователь {i}: некорректное имя пользователя '{user}'")

        return result

    def _validate_config_level_constraints(self, config: Dict[str, Any], result: ValidationResult):
        """
        Валидация ограничений на уровне всей конфигурации

        Args:
            config: Полная конфигурация
            result: Результат валидации для добавления ошибок/предупреждений
        """
        machines = config.get('machines', [])

        # Проверка на дублирование имен машин
        machine_names = [m.get('name') for m in machines if m.get('name')]
        if len(machine_names) != len(set(machine_names)):
            result.add_warning("Обнаружены дублирующиеся имена виртуальных машин")

        # Проверка на использование одного шаблона для разных нод
        template_usage = {}
        for machine in machines:
            template_key = f"{machine.get('template_vmid')}:{machine.get('template_node')}"
            if template_key in template_usage:
                result.add_warning(f"Шаблон {template_key} используется несколько раз")
            template_usage[template_key] = True

        # Проверка рекомендаций по количеству машин
        if len(machines) > 50:
            result.add_warning(f"Большое количество машин ({len(machines)}) может повлиять на производительность")

        # Проверка сетевой конфигурации на уровне конфигурации
        all_bridges = set()
        for machine in machines:
            for network in machine.get('networks', []):
                bridge = network.get('bridge')
                if bridge:
                    all_bridges.add(bridge)

        if len(all_bridges) > 10:
            result.add_warning(f"Используется большое количество различных bridge'ей ({len(all_bridges)})")

    def get_config_summary(self, config: Dict[str, Any]) -> str:
        """
        Получить краткую информацию о конфигурации

        Args:
            config: Конфигурация развертывания

        Returns:
            Строковое представление конфигурации
        """
        machines = config.get('machines', [])
        machine_types = {}
        total_networks = 0

        for machine in machines:
            device_type = machine.get('device_type', 'linux')
            machine_types[device_type] = machine_types.get(device_type, 0) + 1
            total_networks += len(machine.get('networks', []))

        summary = []
        summary.append(f"📋 Конфигурация развертывания:")
        summary.append(f"  Машины: {len(machines)} шт.")

        for device_type, count in machine_types.items():
            summary.append(f"    {device_type}: {count} шт.")

        summary.append(f"  Сетевые интерфейсы: {total_networks} шт.")

        # Анализ сложности конфигурации
        if len(machines) <= 5:
            complexity = "Простая"
        elif len(machines) <= 20:
            complexity = "Средняя"
        else:
            complexity = "Сложная"

        summary.append(f"  Сложность: {complexity}")

        return "\n".join(summary)
