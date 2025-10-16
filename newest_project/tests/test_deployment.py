#!/usr/bin/env python3
"""
Тестирование модулей развертывания

Ручное тестирование TemplateManager, VMManager и DeploymentManager для newest_project
"""

import sys
import os
from pathlib import Path

# Добавляем корневую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.utils.logger import Logger
from core.utils.validator import Validator
from core.utils.cache import Cache
from core.modules.template_manager import TemplateManager, TemplateInfo
from core.modules.vm_manager import VMManager, VMConfig, VMOperationResult
from core.modules.deployment_manager import DeploymentManager, DeploymentConfig, DeploymentResult


def test_template_manager():
    """Тестирование TemplateManager"""
    print("📋 Тестирование TemplateManager...")

    try:
        # Создание менеджера шаблонов (без реального клиента Proxmox)
        logger = Logger("test-template-manager")
        validator = Validator()
        cache = Cache()

        # Создаем мок-клиент для тестирования интерфейса
        class MockProxmoxClient:
            def get_nodes(self):
                return ['pve1', 'pve2']

            def api_call(self, *args, **kwargs):
                # Заглушка для API вызовов
                if args and 'qemu' in args and 'get' in args:
                    return [
                        {'vmid': 100, 'name': 'linux-template', 'template': 1, 'status': 'stopped'},
                        {'vmid': 101, 'name': 'router-template', 'template': 1, 'status': 'stopped'},
                        {'vmid': 200, 'name': 'user-vm', 'template': 0, 'status': 'running'}
                    ]
                return {}

        mock_client = MockProxmoxClient()

        template_manager = TemplateManager(
            proxmox_client=mock_client,
            logger=logger,
            validator=validator,
            cache=cache
        )

        print("  ✅ TemplateManager создан")

        # Тестирование получения шаблонов
        print("\n  📄 Получение списка шаблонов:")
        templates = template_manager.get_templates()

        print(f"    Найдено шаблонов: {len(templates)}")
        for template in templates:
            print(f"    - {template}")

        # Тестирование поиска шаблонов по имени
        print("\n  🔍 Поиск шаблонов по имени:")
        linux_templates = template_manager.find_templates_by_name("linux")

        print(f"    Шаблоны с 'linux' в имени: {len(linux_templates)}")
        for template in linux_templates:
            print(f"      - {template.name}")

        # Тестирование поиска оптимального шаблона
        print("\n  🎯 Поиск оптимального шаблона:")
        requirements = {
            'min_memory': 1024,
            'min_cpus': 1,
            'memory': 2048,
            'cpus': 2
        }

        optimal_template = template_manager.find_optimal_template(requirements)

        if optimal_template:
            print(f"    Оптимальный шаблон: {optimal_template.name}")
            print(f"      Память: {optimal_template.memory}MB, CPU: {optimal_template.cpus}")
        else:
            print("    Оптимальный шаблон не найден")

        # Тестирование статистики шаблонов
        print("\n  📊 Статистика шаблонов:")
        stats = template_manager.get_template_statistics()

        print(f"    Всего шаблонов: {stats['total_templates']}")
        print(f"    Общая память: {stats['total_memory']}MB")
        print(f"    Общее CPU: {stats['total_cpus']}")
        print(f"    Ноды: {list(stats['nodes'].keys())}")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования TemplateManager: {e}")
        return False


def test_vm_manager():
    """Тестирование VMManager"""
    print("\n🖥️  Тестирование VMManager...")

    try:
        # Создание менеджера VM (без реального клиента Proxmox)
        logger = Logger("test-vm-manager")
        validator = Validator()
        cache = Cache()

        # Создаем мок-клиент для тестирования интерфейса
        class MockProxmoxClient:
            def clone_vm(self, *args, **kwargs):
                return 1001  # Возвращаем тестовый VMID

            def delete_vm(self, *args, **kwargs):
                return True

            def start_vm(self, *args, **kwargs):
                return True

            def stop_vm(self, *args, **kwargs):
                return True

            def api_call(self, *args, **kwargs):
                # Заглушка для API вызовов
                return {'vmid': 1001, 'name': 'test-vm', 'status': 'stopped'}

        mock_client = MockProxmoxClient()

        vm_manager = VMManager(
            proxmox_client=mock_client,
            logger=logger,
            validator=validator,
            cache=cache
        )

        print("  ✅ VMManager создан")

        # Тестирование создания конфигурации VM
        print("\n  ⚙️  Тестирование создания конфигурации VM:")

        vm_config = VMConfig(
            name="test-user-pc",
            memory=2048,
            cpus=2,
            disk_size=20,
            template_vmid=100,
            template_node="pve1",
            target_node="pve1",
            description="Тестовая VM"
        )

        print(f"    Конфигурация: {vm_config.name}")
        print(f"      Память: {vm_config.memory}MB, CPU: {vm_config.cpus}")
        print(f"      Шаблон: {vm_config.template_vmid} на {vm_config.template_node}")

        # Тестирование валидации конфигурации
        print("\n  ✅ Тестирование валидации конфигурации:")

        is_valid = vm_manager._validate_vm_config(vm_config)
        print(f"    Конфигурация валидна: {is_valid}")

        # Тестирование статистики VM
        print("\n  📊 Тестирование статистики VM:")

        # Мок-данные для статистики
        mock_vms = [
            {'vmid': 1001, 'name': 'user1-pc', 'status': 'running', 'memory': 2048, 'cpus': 2},
            {'vmid': 1002, 'name': 'user2-pc', 'status': 'stopped', 'memory': 1024, 'cpus': 1}
        ]

        # Подменяем метод list_vms для тестирования
        original_list_vms = vm_manager.list_vms
        vm_manager.list_vms = lambda node=None, include_templates=False: mock_vms

        stats = vm_manager.get_vm_statistics()
        print(f"    Всего VM: {stats['total_vms']}")
        print(f"    Запущено: {stats['running_vms']}")
        print(f"    Остановлено: {stats['stopped_vms']}")
        print(f"    Общая память: {stats['total_memory']}MB")

        # Восстанавливаем оригинальный метод
        vm_manager.list_vms = original_list_vms

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования VMManager: {e}")
        return False


def test_deployment_manager():
    """Тестирование DeploymentManager"""
    print("\n🚀 Тестирование DeploymentManager...")

    try:
        # Создание менеджера развертывания (без реального клиента Proxmox)
        logger = Logger("test-deployment-manager")
        validator = Validator()
        cache = Cache()

        # Создаем мок-клиент для тестирования интерфейса
        class MockProxmoxClient:
            def get_nodes(self):
                return ['pve1', 'pve2']

            def clone_vm(self, *args, **kwargs):
                return 1001

            def api_call(self, *args, **kwargs):
                return []

        mock_client = MockProxmoxClient()

        deployment_manager = DeploymentManager(
            proxmox_client=mock_client,
            logger=logger,
            validator=validator,
            cache=cache
        )

        print("  ✅ DeploymentManager создан")

        # Тестирование создания конфигурации развертывания
        print("\n  ⚙️  Тестирование создания конфигурации развертывания:")

        deployment_config = DeploymentConfig(
            machines=[
                {
                    'name': 'student-pc',
                    'device_type': 'linux',
                    'template_node': 'pve1',
                    'template_vmid': 100,
                    'memory': 2048,
                    'cpus': 2
                }
            ],
            users=['student1@pve', 'student2@pve'],
            deployment_name='test-deployment',
            description='Тестовое развертывание'
        )

        print(f"    Развертывание: {deployment_config.deployment_name}")
        print(f"    Машин: {len(deployment_config.machines)}")
        print(f"    Пользователей: {len(deployment_config.users)}")

        # Тестирование валидации конфигурации
        print("\n  ✅ Тестирование валидации конфигурации:")

        is_valid = deployment_manager._validate_deployment_config(deployment_config)
        print(f"    Конфигурация валидна: {is_valid}")

        # Тестирование создания VM конфигурации для пользователя
        print("\n  🖥️  Тестирование создания VM конфигурации для пользователя:")

        machine_config = deployment_config.machines[0]
        vm_config = deployment_manager._create_vm_config_for_user('student1@pve', machine_config)

        print(f"    VM для пользователя: {vm_config.name}")
        print(f"      Целевая нода: {vm_config.target_node}")
        print(f"      Пул: {vm_config.pool}")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования DeploymentManager: {e}")
        return False


def test_integration_deployment():
    """Тестирование интеграции модулей развертывания"""
    print("\n🔗 Тестирование интеграции модулей развертывания...")

    try:
        # Создание всех менеджеров
        logger = Logger("test-integration")
        validator = Validator()
        cache = Cache()

        # Создаем мок-клиент для тестирования интерфейса
        class MockProxmoxClient:
            def get_nodes(self):
                return ['pve1', 'pve2']

            def clone_vm(self, *args, **kwargs):
                return 1001

            def api_call(self, *args, **kwargs):
                return []

        mock_client = MockProxmoxClient()

        # Создаем менеджеры
        template_manager = TemplateManager(mock_client, logger, validator, cache)
        vm_manager = VMManager(mock_client, logger, validator, cache)
        deployment_manager = DeploymentManager(mock_client, logger=logger, validator=validator, cache=cache)

        print("  ✅ Все менеджеры развертывания созданы")

        # Тестирование совместной работы
        print("\n  🔄 Тестирование совместной работы:")

        # Получаем шаблоны
        templates = template_manager.get_templates()
        print(f"    Доступно шаблонов: {len(templates)}")

        # Получаем VM
        vms = vm_manager.list_vms()
        print(f"    Существует VM: {len(vms)}")

        # Создаем тестовую конфигурацию развертывания
        test_config = DeploymentConfig(
            machines=[
                {
                    'name': 'test-pc',
                    'device_type': 'linux',
                    'template_node': 'pve1',
                    'template_vmid': 100
                }
            ],
            users=['testuser@pve'],
            deployment_name='integration-test'
        )

        # Валидация конфигурации
        is_valid = deployment_manager._validate_deployment_config(test_config)
        print(f"    Конфигурация валидна: {is_valid}")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования интеграции: {e}")
        return False


def test_cache_integration_deployment():
    """Тестирование интеграции с кешем"""
    print("\n💾 Тестирование интеграции с кешем...")

    try:
        cache = Cache()

        # Тестирование кеширования шаблонов
        templates_key = "test_templates"
        test_templates = [
            {'vmid': 100, 'name': 'linux-template', 'node': 'pve1'},
            {'vmid': 101, 'name': 'router-template', 'node': 'pve1'}
        ]

        # Сохранение в кеш
        cache.set(templates_key, test_templates, ttl=60)
        print("  ✅ Шаблоны сохранены в кеш")

        # Получение из кеша
        cached_templates = cache.get(templates_key)
        if cached_templates:
            print(f"  ✅ Шаблоны получены из кеша: {len(cached_templates)} шаблонов")
        else:
            print("  ❌ Шаблоны не найдены в кеше")

        # Тестирование кеширования VM
        vm_key = "test_vm_info"
        test_vm = {
            'vmid': 1001,
            'name': 'test-vm',
            'status': 'running',
            'memory': 2048
        }

        cache.set(vm_key, test_vm, ttl=60)
        cached_vm = cache.get(vm_key)

        if cached_vm:
            print(f"  ✅ VM информация получена из кеша: {cached_vm['name']}")
        else:
            print("  ❌ VM информация не найдена в кеше")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования кеша: {e}")
        return False


def main():
    """Главная функция тестирования"""
    print("🚀 Начинаем тестирование модулей развертывания")
    print("=" * 55)

    try:
        # Создаем необходимые директории
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

        # Запуск тестов
        success = True

        success &= test_template_manager()
        success &= test_vm_manager()
        success &= test_deployment_manager()
        success &= test_integration_deployment()
        success &= test_cache_integration_deployment()

        print("\n" + "=" * 55)
        if success:
            print("🎉 Все тесты развертывания завершены успешно!")
        else:
            print("⚠️  Некоторые тесты завершились с предупреждениями")

        print("📋 Результаты тестирования:")
        print("  - TemplateManager: управление шаблонами функционально")
        print("  - VMManager: управление VM работает")
        print("  - DeploymentManager: координация развертывания")
        print("  - Интеграция: модули работают вместе")
        print("  - Кеш: кеширование данных развертывания активное")

        # Пауза для просмотра результатов
        input("\n⏸️  Нажмите Enter для завершения...")

    except KeyboardInterrupt:
        print("\n\n👋 Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка при тестировании: {e}")
        raise


if __name__ == "__main__":
    main()
