#!/usr/bin/env python3
"""
TemplateManager - менеджер шаблонов для newest_project

Управляет шаблонами виртуальных машин в кластере Proxmox VE,
включая получение списка шаблонов, валидацию и подготовку к развертыванию.
"""

from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass

from ..utils.logger import Logger
from ..utils.validator import Validator
from ..utils.cache import Cache
from .proxmox_client import ProxmoxClient


@dataclass
class TemplateInfo:
    """Информация о шаблоне виртуальной машины"""
    vmid: int
    name: str
    node: str
    memory: int
    cpus: int
    disk_size: int
    template: bool = True
    status: str = "stopped"
    description: str = ""

    def __str__(self) -> str:
        return f"Template-{self.vmid}: {self.name} на {self.node} ({self.memory}MB, {self.cpus} CPU)"


@dataclass
class TemplateValidation:
    """Результат валидации шаблона"""
    valid: bool
    template: Optional[TemplateInfo]
    errors: List[str]
    warnings: List[str]


class TemplateManager:
    """
    Менеджер шаблонов виртуальных машин

    Возможности:
    - Получение списка доступных шаблонов
    - Валидация шаблонов для развертывания
    - Подготовка шаблонов к клонированию
    - Кеширование информации о шаблонах
    - Поиск оптимальных шаблонов
    """

    def __init__(self, proxmox_client: ProxmoxClient,
                 logger: Optional[Logger] = None,
                 validator: Optional[Validator] = None,
                 cache: Optional[Cache] = None):
        """
        Инициализация менеджера шаблонов

        Args:
            proxmox_client: Клиент Proxmox API
            logger: Экземпляр логгера
            validator: Экземпляр валидатора
            cache: Экземпляр кеша
        """
        self.proxmox = proxmox_client
        self.logger = logger or Logger()
        self.validator = validator or Validator()
        self.cache = cache or Cache()

        # Кеш для шаблонов
        self.template_cache_ttl = 600  # 10 минут

    def get_templates(self, node: Optional[str] = None) -> List[TemplateInfo]:
        """
        Получение списка шаблонов VM

        Args:
            node: Имя ноды (если None, то все ноды)

        Returns:
            Список доступных шаблонов
        """
        cache_key = f"templates:{node or 'all'}"

        # Проверяем кеш
        cached_templates = self.cache.get(cache_key)
        if cached_templates:
            return [self._dict_to_template_info(data) for data in cached_templates]

        try:
            templates = []

            if node:
                # Получаем шаблоны только для указанной ноды
                nodes_to_check = [node]
            else:
                # Получаем шаблоны для всех нод
                nodes_to_check = self.proxmox.get_nodes()

            for current_node in nodes_to_check:
                try:
                    # Получаем список VM на ноде
                    node_vms = self.proxmox.api_call('nodes', current_node, 'qemu', 'get')

                    for vm_data in node_vms:
                        # Проверяем, является ли VM шаблоном
                        if vm_data.get('template') == 1:
                            template_info = self._parse_template_data(current_node, vm_data)
                            if template_info:
                                templates.append(template_info)

                except Exception as e:
                    self.logger.log_validation_error("templates", current_node, f"доступные шаблоны: {str(e)}")
                    continue

            # Сохраняем в кеш
            cache_data = [self._template_info_to_dict(template) for template in templates]
            self.cache.set(cache_key, cache_data, ttl=self.template_cache_ttl)

            return templates

        except Exception as e:
            self.logger.log_validation_error("get_templates", str(e), "список шаблонов")
            return []

    def _parse_template_data(self, node: str, vm_data: Dict[str, Any]) -> Optional[TemplateInfo]:
        """Парсинг данных шаблона из API ответа"""
        try:
            vmid = vm_data.get('vmid')
            if not vmid:
                return None

            # Получаем детальную информацию о VM
            try:
                vm_config = self.proxmox.api_call('nodes', node, 'qemu', vmid, 'config', 'get')
            except Exception:
                # Если не можем получить конфиг, используем базовую информацию
                vm_config = {}

            template_info = TemplateInfo(
                vmid=vmid,
                name=vm_data.get('name', f'Template-{vmid}'),
                node=node,
                memory=vm_config.get('memory', 0),
                cpus=vm_config.get('cores', 1),
                disk_size=self._calculate_disk_size(vm_config),
                template=True,
                status=vm_data.get('status', 'stopped')
            )

            return template_info

        except Exception as e:
            self.logger.log_validation_error("template_parse", str(vm_data), f"корректные данные шаблона: {str(e)}")
            return None

    def _calculate_disk_size(self, vm_config: Dict[str, Any]) -> int:
        """Расчет размера диска шаблона"""
        total_size = 0

        # Ищем все диски в конфигурации
        for key, value in vm_config.items():
            if key.startswith(('scsi', 'ide', 'sata', 'virtio')) and isinstance(value, str):
                # Извлекаем размер из строки типа "local:100/vm-100-disk-0.qcow2,size=8G"
                if 'size=' in value:
                    size_part = value.split('size=')[1].split(',')[0]
                    total_size += self._parse_disk_size(size_part)

        return total_size

    def _parse_disk_size(self, size_str: str) -> int:
        """Парсинг размера диска из строки"""
        try:
            if size_str.endswith('G'):
                return int(float(size_str[:-1]) * 1024)  # GB в MB
            elif size_str.endswith('M'):
                return int(size_str[:-1])  # MB
            elif size_str.endswith('T'):
                return int(float(size_str[:-1]) * 1024 * 1024)  # TB в MB
            else:
                return int(size_str)  # Предполагаем MB
        except (ValueError, IndexError):
            return 0

    def _dict_to_template_info(self, data: Dict[str, Any]) -> TemplateInfo:
        """Преобразование словаря в TemplateInfo"""
        return TemplateInfo(
            vmid=data['vmid'],
            name=data['name'],
            node=data['node'],
            memory=data['memory'],
            cpus=data['cpus'],
            disk_size=data['disk_size'],
            template=data.get('template', True),
            status=data.get('status', 'stopped'),
            description=data.get('description', '')
        )

    def _template_info_to_dict(self, template: TemplateInfo) -> Dict[str, Any]:
        """Преобразование TemplateInfo в словарь"""
        return {
            'vmid': template.vmid,
            'name': template.name,
            'node': template.node,
            'memory': template.memory,
            'cpus': template.cpus,
            'disk_size': template.disk_size,
            'template': template.template,
            'status': template.status,
            'description': template.description
        }

    def validate_template(self, node: str, vmid: int) -> TemplateValidation:
        """
        Валидация шаблона для развертывания

        Args:
            node: Имя ноды
            vmid: VMID шаблона

        Returns:
            Результат валидации с деталями
        """
        errors = []
        warnings = []

        try:
            # Получаем информацию о шаблоне
            template_info = self.get_template_info(node, vmid)

            if not template_info:
                errors.append(f"Шаблон {vmid} не найден на ноде {node}")
                return TemplateValidation(valid=False, template=None, errors=errors, warnings=warnings)

            # Проверяем, что это действительно шаблон
            if not template_info.template:
                errors.append(f"VM {vmid} не является шаблоном")

            # Проверяем статус шаблона
            if template_info.status != 'stopped':
                warnings.append(f"Шаблон {vmid} не остановлен (статус: {template_info.status})")

            # Проверяем ресурсы
            if template_info.memory <= 0:
                errors.append(f"Шаблон {vmid} не имеет памяти")

            if template_info.cpus <= 0:
                errors.append(f"Шаблон {vmid} не имеет CPU")

            if template_info.disk_size <= 0:
                warnings.append(f"Шаблон {vmid} не имеет дисков или размер неизвестен")

            # Проверяем доступность шаблона для клонирования
            try:
                # Попытка получить конфигурацию шаблона
                self.proxmox.api_call('nodes', node, 'qemu', vmid, 'config', 'get')
            except Exception as e:
                errors.append(f"Не удается получить конфигурацию шаблона {vmid}: {str(e)}")

            return TemplateValidation(
                valid=len(errors) == 0,
                template=template_info if len(errors) == 0 else None,
                errors=errors,
                warnings=warnings
            )

        except Exception as e:
            errors.append(f"Ошибка валидации шаблона: {str(e)}")
            return TemplateValidation(valid=False, template=None, errors=errors, warnings=warnings)

    def get_template_info(self, node: str, vmid: int) -> Optional[TemplateInfo]:
        """
        Получение детальной информации о шаблоне

        Args:
            node: Имя ноды
            vmid: VMID шаблона

        Returns:
            Информация о шаблоне или None если не найден
        """
        cache_key = f"template_info:{node}:{vmid}"

        # Проверяем кеш
        cached_info = self.cache.get(cache_key)
        if cached_info:
            return self._dict_to_template_info(cached_info)

        try:
            # Получаем информацию о VM
            vm_data = self.proxmox.api_call('nodes', node, 'qemu', vmid, 'status', 'current', 'get')

            # Проверяем, является ли VM шаблоном
            if vm_data.get('template') != 1:
                return None

            # Получаем конфигурацию VM
            vm_config = self.proxmox.api_call('nodes', node, 'qemu', vmid, 'config', 'get')

            template_info = TemplateInfo(
                vmid=vmid,
                name=vm_data.get('name', f'Template-{vmid}'),
                node=node,
                memory=vm_config.get('memory', 0),
                cpus=vm_config.get('cores', 1),
                disk_size=self._calculate_disk_size(vm_config),
                template=True,
                status=vm_data.get('status', 'stopped')
            )

            # Сохраняем в кеш
            cache_data = self._template_info_to_dict(template_info)
            self.cache.set(cache_key, cache_data, ttl=self.template_cache_ttl)

            return template_info

        except Exception as e:
            self.logger.log_validation_error("template_info", f"{node}:{vmid}", f"получение информации: {str(e)}")
            return None

    def find_templates_by_name(self, name_pattern: str, node: Optional[str] = None) -> List[TemplateInfo]:
        """
        Поиск шаблонов по имени

        Args:
            name_pattern: Шаблон имени для поиска
            node: Имя ноды (если None, то все ноды)

        Returns:
            Список найденных шаблонов
        """
        import re

        templates = self.get_templates(node)
        pattern = re.compile(name_pattern, re.IGNORECASE)

        matching_templates = []
        for template in templates:
            if pattern.search(template.name):
                matching_templates.append(template)

        return matching_templates

    def find_optimal_template(self, requirements: Dict[str, Any],
                             node: Optional[str] = None) -> Optional[TemplateInfo]:
        """
        Поиск оптимального шаблона по требованиям

        Args:
            requirements: Требования к шаблону (memory, cpus, disk_size)
            node: Имя ноды (если None, то все ноды)

        Returns:
            Оптимальный шаблон или None если не найден
        """
        templates = self.get_templates(node)

        if not templates:
            return None

        optimal_template = None
        min_score = float('inf')

        for template in templates:
            # Проверяем соответствие требованиям
            if requirements.get('min_memory') and template.memory < requirements['min_memory']:
                continue

            if requirements.get('min_cpus') and template.cpus < requirements['min_cpus']:
                continue

            if requirements.get('max_disk_size') and template.disk_size > requirements['max_disk_size']:
                continue

            # Вычисляем "score" - чем ближе к требованиям, тем лучше
            score = 0
            if requirements.get('memory'):
                score += abs(template.memory - requirements['memory'])
            if requirements.get('cpus'):
                score += abs(template.cpus - requirements['cpus']) * 100  # CPU важнее памяти

            if optimal_template is None or score < min_score:
                optimal_template = template
                min_score = score

        return optimal_template

    def get_template_statistics(self, node: Optional[str] = None) -> Dict[str, Any]:
        """
        Получение статистики по шаблонам

        Args:
            node: Имя ноды (если None, то все ноды)

        Returns:
            Статистика шаблонов
        """
        templates = self.get_templates(node)

        if not templates:
            return {
                'total_templates': 0,
                'total_memory': 0,
                'total_cpus': 0,
                'total_disk_size': 0,
                'nodes': {},
                'memory_distribution': {},
                'cpu_distribution': {}
            }

        stats = {
            'total_templates': len(templates),
            'total_memory': 0,
            'total_cpus': 0,
            'total_disk_size': 0,
            'nodes': {},
            'memory_distribution': {},
            'cpu_distribution': {}
        }

        for template in templates:
            # Суммируем ресурсы
            stats['total_memory'] += template.memory
            stats['total_cpus'] += template.cpus
            stats['total_disk_size'] += template.disk_size

            # Статистика по нодам
            if template.node not in stats['nodes']:
                stats['nodes'][template.node] = 0
            stats['nodes'][template.node] += 1

            # Распределение по памяти
            memory_range = f"{template.memory // 512 * 512}-{(template.memory // 512 + 1) * 512}MB"
            if memory_range not in stats['memory_distribution']:
                stats['memory_distribution'][memory_range] = 0
            stats['memory_distribution'][memory_range] += 1

            # Распределение по CPU
            cpu_range = f"{template.cpus} CPU"
            if cpu_range not in stats['cpu_distribution']:
                stats['cpu_distribution'][cpu_range] = 0
            stats['cpu_distribution'][cpu_range] += 1

        return stats

    def prepare_template_for_cloning(self, node: str, vmid: int) -> bool:
        """
        Подготовка шаблона к клонированию

        Args:
            node: Имя ноды
            vmid: VMID шаблона

        Returns:
            True если шаблон готов к клонированию
        """
        try:
            # Проверяем статус шаблона
            template_info = self.get_template_info(node, vmid)
            if not template_info:
                self.logger.log_validation_error("prepare_template", f"{node}:{vmid}", "существующий шаблон")
                return False

            # Проверяем, что шаблон остановлен
            if template_info.status != 'stopped':
                self.logger.log_validation_error("template_status", template_info.status, "остановленный шаблон")
                return False

            # Проверяем доступность конфигурации шаблона
            try:
                self.proxmox.api_call('nodes', node, 'qemu', vmid, 'config', 'get')
            except Exception as e:
                self.logger.log_validation_error("template_config", str(e), "доступная конфигурация")
                return False

            self.logger.log_cache_operation("prepare_template", f"{node}:{vmid}", True)
            return True

        except Exception as e:
            self.logger.log_validation_error("prepare_template", str(e), "подготовка шаблона")
            return False

    def clear_template_cache(self, node: Optional[str] = None) -> int:
        """
        Очистка кеша шаблонов

        Args:
            node: Нода для очистки (если None, то все)

        Returns:
            Количество очищенных записей
        """
        cleared_count = 0

        if node:
            # Очищаем кеш для конкретной ноды
            cache_keys = [key for key in self.cache.cache.keys() if key.startswith(f'template_info:{node}:') or key.startswith(f'templates:{node}')]
            for key in cache_keys:
                self.cache.delete(key)
                cleared_count += 1
        else:
            # Очищаем весь кеш шаблонов
            cache_keys = [key for key in self.cache.cache.keys() if 'template' in key]
            for key in cache_keys:
                self.cache.delete(key)
                cleared_count += 1

        if cleared_count > 0:
            self.logger.log_cache_operation("clear_template_cache", f"{cleared_count}_entries", True)

        return cleared_count


# Глобальный экземпляр менеджера шаблонов
_global_template_manager = None


def get_template_manager(proxmox_client: ProxmoxClient) -> TemplateManager:
    """Получить глобальный экземпляр менеджера шаблонов"""
    global _global_template_manager
    if _global_template_manager is None:
        _global_template_manager = TemplateManager(proxmox_client)
    return _global_template_manager


# Пример использования
if __name__ == "__main__":
    print("📋 TemplateManager - менеджер шаблонов виртуальных машин")
    print("📋 Доступные методы:")

    # Получаем все публичные методы
    methods = [method for method in dir(TemplateManager) if not method.startswith('_') and callable(getattr(TemplateManager, method))]
    for method in methods:
        print(f"  - {method}")

    print(f"\n📊 Всего методов: {len(methods)}")
    print("✅ Менеджер шаблонов готов к использованию")
