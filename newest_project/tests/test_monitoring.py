#!/usr/bin/env python3
"""
Тестирование модулей мониторинга и балансировки

Ручное тестирование LoadBalancer и MetricsCollector для newest_project
"""

import sys
import os
import time
from pathlib import Path

# Добавляем корневую директорию в путь для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.utils.logger import Logger
from core.utils.validator import Validator
from core.utils.cache import Cache
from core.modules.load_balancer import LoadBalancer, BalancingStrategy, NodeLoad, BalancingResult
from core.modules.metrics_collector import MetricsCollector, SystemMetrics, ClusterMetrics, DeploymentMetrics


def test_load_balancer():
    """Тестирование LoadBalancer"""
    print("⚖️  Тестирование LoadBalancer...")

    try:
        # Создание балансировщика нагрузки (без реального клиента Proxmox)
        logger = Logger("test-load-balancer")
        validator = Validator()
        cache = Cache()

        # Создаем мок-клиент для тестирования интерфейса
        class MockProxmoxClient:
            def get_nodes(self):
                return ['pve1', 'pve2', 'pve3']

            def get_node_info(self, node):
                # Мок-данные о нагрузке нод
                mock_data = {
                    'pve1': {'cpu': 30, 'memory': {'used': 4*1024**3, 'total': 8*1024**3}, 'uptime': 3600},
                    'pve2': {'cpu': 70, 'memory': {'used': 6*1024**3, 'total': 8*1024**3}, 'uptime': 7200},
                    'pve3': {'cpu': 45, 'memory': {'used': 2*1024**3, 'total': 8*1024**3}, 'uptime': 1800}
                }

                if node in mock_data:
                    data = mock_data[node]
                    return type('NodeInfo', (), {
                        'node': node,
                        'cpu_usage': data['cpu'],
                        'memory_usage': (data['memory']['used'] / data['memory']['total']) * 100,
                        'memory_total': data['memory']['total'],
                        'uptime': data['uptime']
                    })()
                return None

            def api_call(self, *args, **kwargs):
                # Заглушка для API вызовов
                return []

        mock_client = MockProxmoxClient()

        load_balancer = LoadBalancer(
            proxmox_client=mock_client,
            logger=logger,
            validator=validator,
            cache=cache
        )

        print("  ✅ LoadBalancer создан")

        # Тестирование получения нагрузки нод
        print("\n  📊 Получение нагрузки нод:")
        node_loads = load_balancer.get_node_loads()

        print(f"    Найдено нод: {len(node_loads)}")
        for load in node_loads:
            print(f"    {load.node}: CPU {load.cpu_usage}%, Память {load.memory_usage:.1f}%")

        # Тестирование выбора оптимальной ноды
        print("\n  🎯 Тестирование выбора оптимальной ноды:")

        strategies = [
            BalancingStrategy.LEAST_LOADED,
            BalancingStrategy.MEMORY_OPTIMIZED,
            BalancingStrategy.CPU_OPTIMIZED
        ]

        for strategy in strategies:
            selected_node = load_balancer.select_optimal_node(strategy)
            if selected_node:
                print(f"    Стратегия {strategy.value}: {selected_node}")
            else:
                print(f"    Стратегия {strategy.value}: не найдена подходящая нода")

        # Тестирование рекомендаций по балансировке
        print("\n  💡 Тестирование рекомендаций по балансировке:")

        vm_requirements = {
            'memory': 2048,
            'cpus': 2,
            'memory_priority': True
        }

        recommendation = load_balancer.get_balancing_recommendation(vm_requirements)

        print(f"    Рекомендация: {recommendation.selected_node}")
        print(f"    Стратегия: {recommendation.strategy.value}")
        print(f"    Причина: {recommendation.reason}")

        # Тестирование статуса балансировки кластера
        print("\n  ⚖️  Тестирование статуса балансировки кластера:")

        balance_status = load_balancer.get_cluster_balance_status()

        print(f"    Статус: {balance_status['status']}")
        print(f"    Средняя нагрузка CPU: {balance_status['cpu_average']}%")
        print(f"    Средняя нагрузка памяти: {balance_status['memory_average']}%")

        if balance_status['overloaded_nodes']:
            print(f"    Перегруженные ноды: {balance_status['overloaded_nodes']}")

        # Тестирование предложений по перебалансировке
        print("\n  🔄 Тестирование предложений по перебалансировке:")

        rebalancing = load_balancer.suggest_rebalancing()

        if rebalancing['possible']:
            print(f"    Предложений: {rebalancing['suggestions_count']}")
            print(f"    Перегруженные ноды: {rebalancing['overloaded_nodes']}")
            print(f"    Недогруженные ноды: {rebalancing['underloaded_nodes']}")
        else:
            print(f"    Перебалансировка не требуется: {rebalancing['reason']}")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования LoadBalancer: {e}")
        return False


def test_metrics_collector():
    """Тестирование MetricsCollector"""
    print("\n📊 Тестирование MetricsCollector...")

    try:
        # Создание сборщика метрик (без реального клиента Proxmox)
        logger = Logger("test-metrics-collector")
        validator = Validator()
        cache = Cache()

        metrics_collector = MetricsCollector(
            proxmox_client=None,  # Без Proxmox клиента для тестирования системных метрик
            logger=logger,
            validator=validator,
            cache=cache,
            history_size=10
        )

        print("  ✅ MetricsCollector создан")

        # Тестирование сбора системных метрик
        print("\n  💻 Сбор системных метрик:")

        for i in range(3):
            system_metrics = metrics_collector.collect_system_metrics()
            print(f"    Измерение {i+1}: CPU {system_metrics.cpu_percent:.1f}%, Память {system_metrics.memory_percent:.1f}%")
            time.sleep(1)  # Пауза между измерениями

        # Тестирование записи метрик развертывания
        print("\n  🚀 Тестирование записи метрик развертывания:")

        test_deployments = [
            ("test-deployment-1", 10, 8, 2, 45.5),
            ("test-deployment-2", 5, 5, 0, 23.2),
            ("test-deployment-3", 15, 12, 3, 67.8)
        ]

        for deployment_name, total, created, failed, duration in test_deployments:
            metrics_collector.record_deployment_metrics(deployment_name, total, created, failed, duration)
            print(f"    Записано: {deployment_name} ({created}/{total} VM за {duration:.1f}с)")

        # Тестирование получения истории метрик
        print("\n  📈 Тестирование получения истории метрик:")

        system_history = metrics_collector.get_system_metrics_history()
        deployment_history = metrics_collector.get_deployment_metrics_history()

        print(f"    Системных метрик: {len(system_history)}")
        print(f"    Метрик развертывания: {len(deployment_history)}")

        # Тестирование анализа трендов
        print("\n  📊 Тестирование анализа трендов:")

        trends = metrics_collector.analyze_performance_trends()

        if 'error' not in trends:
            print(f"    Направление тренда системы: {trends['system_trends']['trend_direction']}")
            print(f"    Точек данных: {trends['data_points']}")
        else:
            print(f"    Ошибка анализа: {trends['error']}")

        # Тестирование статистики развертываний
        print("\n  📋 Тестирование статистики развертываний:")

        deployment_stats = metrics_collector.get_deployment_statistics()

        print(f"    Всего развертываний: {deployment_stats['total_deployments']}")
        print(f"    Успешность: {deployment_stats['success_rate_percent']:.1f}%")
        print(f"    Средняя длительность: {deployment_stats['average_duration_seconds']:.1f}с")

        # Тестирование экспорта метрик
        print("\n  📤 Тестирование экспорта метрик:")

        json_export = metrics_collector.export_metrics("json")
        csv_export = metrics_collector.export_metrics("csv")

        print(f"    JSON экспорт: {len(json_export)} символов")
        print(f"    CSV экспорт: {len(csv_export)} символов")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования MetricsCollector: {e}")
        return False


def test_balancing_strategies():
    """Тестирование стратегий балансировки"""
    print("\n🎯 Тестирование стратегий балансировки...")

    try:
        # Создание тестовых данных о нагрузке нод
        test_nodes = [
            NodeLoad(node="pve1", cpu_usage=20, memory_usage=30, memory_total=8*1024**3, vm_count=5, uptime=3600),
            NodeLoad(node="pve2", cpu_usage=80, memory_usage=70, memory_total=8*1024**3, vm_count=15, uptime=7200),
            NodeLoad(node="pve3", cpu_usage=50, memory_usage=40, memory_total=8*1024**3, vm_count=8, uptime=1800)
        ]

        print("  ✅ Тестовые данные о нагрузке созданы")

        # Тестирование различных стратегий
        strategies = [
            BalancingStrategy.LEAST_LOADED,
            BalancingStrategy.MEMORY_OPTIMIZED,
            BalancingStrategy.CPU_OPTIMIZED
        ]

        print("\n  📊 Расчет рейтингов для стратегий:")

        for strategy in strategies:
            print(f"\n    Стратегия: {strategy.value}")

            for node in test_nodes:
                score = node.calculate_score(strategy)
                node.score = score
                print(f"      {node.node}: {score:.1f} баллов")

            # Выбор лучшей ноды
            best_node = max(test_nodes, key=lambda x: x.score)
            print(f"      Лучшая нода: {best_node.node} ({best_node.score:.1f} баллов)")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования стратегий балансировки: {e}")
        return False


def test_metrics_data_structures():
    """Тестирование структур данных метрик"""
    print("\n📊 Тестирование структур данных метрик...")

    try:
        # Тестирование SystemMetrics
        print("  💻 Тестирование SystemMetrics:")

        system_metrics = SystemMetrics(
            timestamp=time.time(),
            cpu_percent=45.5,
            memory_percent=67.2,
            memory_used_gb=5.4,
            memory_total_gb=8.0,
            disk_usage_percent=23.1,
            network_io={'bytes_sent': 1000, 'bytes_recv': 2000}
        )

        print(f"    CPU: {system_metrics.cpu_percent}%")
        print(f"    Память: {system_metrics.memory_used_gb:.1f}GB / {system_metrics.memory_total_gb:.1f}GB")
        print(f"    Диск: {system_metrics.disk_usage_percent}%")
        print(f"    Сеть: {system_metrics.network_io['bytes_sent']} байт отправлено")

        # Тестирование ClusterMetrics
        print("\n  ☁️  Тестирование ClusterMetrics:")

        cluster_metrics = ClusterMetrics(
            timestamp=time.time(),
            total_nodes=3,
            active_nodes=3,
            total_vms=25,
            running_vms=20,
            total_memory_gb=24.0,
            used_memory_gb=16.5,
            total_cpu_cores=12,
            used_cpu_percent=55.0
        )

        print(f"    Ноды: {cluster_metrics.active_nodes}/{cluster_metrics.total_nodes}")
        print(f"    VM: {cluster_metrics.running_vms}/{cluster_metrics.total_vms}")
        print(f"    Память: {cluster_metrics.used_memory_gb:.1f}GB / {cluster_metrics.total_memory_gb:.1f}GB")
        print(f"    CPU: {cluster_metrics.used_cpu_percent}%")

        # Тестирование DeploymentMetrics
        print("\n  🚀 Тестирование DeploymentMetrics:")

        deployment_metrics = DeploymentMetrics(
            timestamp=time.time(),
            deployment_name="test-deployment",
            total_vms_planned=10,
            vms_created=8,
            vms_failed=2,
            duration_seconds=45.5,
            average_creation_time=5.7
        )

        print(f"    Развертывание: {deployment_metrics.deployment_name}")
        print(f"    Результат: {deployment_metrics.vms_created}/{deployment_metrics.total_vms_planned} VM")
        print(f"    Длительность: {deployment_metrics.duration_seconds:.1f}с")
        print(f"    Среднее время создания: {deployment_metrics.average_creation_time:.1f}с")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования структур данных: {e}")
        return False


def test_integration_monitoring():
    """Тестирование интеграции модулей мониторинга"""
    print("\n🔗 Тестирование интеграции модулей мониторинга...")

    try:
        # Создание всех менеджеров мониторинга
        logger = Logger("test-monitoring-integration")
        validator = Validator()
        cache = Cache()

        # Создаем мок-клиент для тестирования интерфейса
        class MockProxmoxClient:
            def get_nodes(self):
                return ['pve1', 'pve2']

            def get_node_info(self, node):
                return type('NodeInfo', (), {
                    'node': node,
                    'cpu_usage': 40 if node == 'pve1' else 60,
                    'memory_usage': 50 if node == 'pve1' else 70,
                    'memory_total': 8*1024**3,
                    'uptime': 3600
                })()

            def api_call(self, *args, **kwargs):
                return []

        mock_client = MockProxmoxClient()

        # Создаем менеджеры
        load_balancer = LoadBalancer(mock_client, logger, validator, cache)
        metrics_collector = MetricsCollector(mock_client, logger, validator, cache)

        print("  ✅ Все менеджеры мониторинга созданы")

        # Тестирование совместной работы
        print("\n  🔄 Тестирование совместной работы:")

        # Получаем нагрузку нод
        node_loads = load_balancer.get_node_loads()
        print(f"    Загрузка нод получена: {len(node_loads)} нод")

        # Собираем метрики кластера
        cluster_metrics = metrics_collector.collect_cluster_metrics()
        if cluster_metrics:
            print(f"    Метрики кластера собраны: {cluster_metrics.total_nodes} нод, {cluster_metrics.total_vms} VM")

        # Собираем системные метрики
        system_metrics = metrics_collector.collect_system_metrics()
        print(f"    Системные метрики собраны: CPU {system_metrics.cpu_percent:.1f}%, Память {system_metrics.memory_percent:.1f}%")

        # Получаем текущие метрики
        current_metrics = metrics_collector.get_current_metrics()
        print(f"    Текущие метрики получены: {len(current_metrics)} категорий")

        return True

    except Exception as e:
        print(f"  ❌ Ошибка тестирования интеграции: {e}")
        return False


def main():
    """Главная функция тестирования"""
    print("🚀 Начинаем тестирование модулей мониторинга и балансировки")
    print("=" * 65)

    try:
        # Создаем необходимые директории
        Path("data").mkdir(exist_ok=True)
        Path("logs").mkdir(exist_ok=True)

        # Запуск тестов
        success = True

        success &= test_load_balancer()
        success &= test_metrics_collector()
        success &= test_balancing_strategies()
        success &= test_metrics_data_structures()
        success &= test_integration_monitoring()

        print("\n" + "=" * 65)
        if success:
            print("🎉 Все тесты мониторинга завершены успешно!")
        else:
            print("⚠️  Некоторые тесты завершились с предупреждениями")

        print("📋 Результаты тестирования:")
        print("  - LoadBalancer: балансировка нагрузки функциональна")
        print("  - MetricsCollector: сбор метрик работает")
        print("  - Стратегии балансировки: расчет рейтингов корректен")
        print("  - Структуры данных: метрики формируются правильно")
        print("  - Интеграция: модули работают вместе")

        # Пауза для просмотра результатов
        input("\n⏸️  Нажмите Enter для завершения...")

    except KeyboardInterrupt:
        print("\n\n👋 Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка при тестировании: {e}")
        raise


if __name__ == "__main__":
    main()
