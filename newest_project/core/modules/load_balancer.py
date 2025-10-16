#!/usr/bin/env python3
"""
LoadBalancer - балансировщик нагрузки для newest_project

Распределяет виртуальные машины по нодам кластера Proxmox VE
на основе анализа текущей нагрузки и ресурсов.
"""

import random
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..utils.logger import Logger
from ..utils.validator import Validator
from ..utils.cache import Cache
from .proxmox_client import ProxmoxClient


class BalancingStrategy(Enum):
    """Стратегии балансировки нагрузки"""
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    RANDOM = "random"
    MEMORY_OPTIMIZED = "memory_optimized"
    CPU_OPTIMIZED = "cpu_optimized"


@dataclass
class NodeLoad:
    """Информация о нагрузке ноды"""
    node: str
    cpu_usage: float
    memory_usage: float
    memory_total: int
    vm_count: int
    uptime: int
    score: float = 0.0

    def calculate_score(self, strategy: BalancingStrategy) -> float:
        """Расчет рейтинга ноды для балансировки"""
        if strategy == BalancingStrategy.LEAST_LOADED:
            # Чем меньше нагрузка, тем выше рейтинг
            return 100 - (self.cpu_usage + self.memory_usage) / 2
        elif strategy == BalancingStrategy.MEMORY_OPTIMIZED:
            # Оптимизация по памяти
            return 100 - self.memory_usage
        elif strategy == BalancingStrategy.CPU_OPTIMIZED:
            # Оптимизация по CPU
            return 100 - self.cpu_usage
        else:
            # По умолчанию используем комбинированную метрику
            return 100 - (self.cpu_usage + self.memory_usage) / 2


@dataclass
class BalancingResult:
    """Результат балансировки нагрузки"""
    selected_node: str
    strategy: BalancingStrategy
    node_scores: Dict[str, float]
    reason: str


class LoadBalancer:
    """
    Балансировщик нагрузки для кластера Proxmox

    Возможности:
    - Анализ нагрузки нод кластера
    - Выбор оптимальной ноды для размещения VM
    - Поддержка различных стратегий балансировки
    - Мониторинг ресурсов в реальном времени
    - Предотвращение перегрузки нод
    """

    def __init__(self, proxmox_client: ProxmoxClient,
                 logger: Optional[Logger] = None,
                 validator: Optional[Validator] = None,
                 cache: Optional[Cache] = None):
        """
        Инициализация балансировщика нагрузки

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

        # Кеш для информации о нагрузке
        self.load_cache_ttl = 30  # 30 секунд

        # Пороговые значения нагрузки
        self.cpu_threshold = 80.0  # Максимальная нагрузка CPU в процентах
        self.memory_threshold = 85.0  # Максимальная нагрузка памяти в процентах

    def get_node_loads(self) -> List[NodeLoad]:
        """
        Получение информации о нагрузке всех нод

        Returns:
            Список информации о нагрузке нод
        """
        cache_key = "cluster_node_loads"

        # Проверяем кеш
        cached_loads = self.cache.get(cache_key)
        if cached_loads:
            return [self._dict_to_node_load(data) for data in cached_loads]

        try:
            nodes = self.proxmox.get_nodes()
            node_loads = []

            for node in nodes:
                try:
                    node_info = self.proxmox.get_node_info(node)
                    if node_info:
                        # Получаем количество VM на ноде
                        vms = self.proxmox.api_call('nodes', node, 'qemu', 'get')
                        vm_count = sum(1 for vm in vms if vm.get('template') != 1)

                        node_load = NodeLoad(
                            node=node_info.node,
                            cpu_usage=node_info.cpu_usage,
                            memory_usage=node_info.memory_usage,
                            memory_total=node_info.memory_total,
                            vm_count=vm_count,
                            uptime=node_info.uptime
                        )

                        node_loads.append(node_load)

                except Exception as e:
                    self.logger.log_validation_error("node_load", node, f"получение нагрузки: {str(e)}")
                    continue

            # Сохраняем в кеш
            cache_data = [self._node_load_to_dict(load) for load in node_loads]
            self.cache.set(cache_key, cache_data, ttl=self.load_cache_ttl)

            return node_loads

        except Exception as e:
            self.logger.log_validation_error("get_node_loads", str(e), "получение нагрузки кластера")
            return []

    def _dict_to_node_load(self, data: Dict[str, Any]) -> NodeLoad:
        """Преобразование словаря в NodeLoad"""
        return NodeLoad(
            node=data['node'],
            cpu_usage=data['cpu_usage'],
            memory_usage=data['memory_usage'],
            memory_total=data['memory_total'],
            vm_count=data['vm_count'],
            uptime=data['uptime'],
            score=data.get('score', 0.0)
        )

    def _node_load_to_dict(self, node_load: NodeLoad) -> Dict[str, Any]:
        """Преобразование NodeLoad в словарь"""
        return {
            'node': node_load.node,
            'cpu_usage': node_load.cpu_usage,
            'memory_usage': node_load.memory_usage,
            'memory_total': node_load.memory_total,
            'vm_count': node_load.vm_count,
            'uptime': node_load.uptime,
            'score': node_load.score
        }

    def select_optimal_node(self, strategy: BalancingStrategy = BalancingStrategy.LEAST_LOADED,
                           exclude_nodes: Optional[List[str]] = None) -> Optional[str]:
        """
        Выбор оптимальной ноды для размещения VM

        Args:
            strategy: Стратегия балансировки
            exclude_nodes: Список нод для исключения

        Returns:
            Имя оптимальной ноды или None
        """
        try:
            node_loads = self.get_node_loads()

            if not node_loads:
                self.logger.log_validation_error("select_node", "no_nodes", "доступные ноды")
                return None

            # Исключаем указанные ноды
            if exclude_nodes:
                node_loads = [load for load in node_loads if load.node not in exclude_nodes]

            if not node_loads:
                self.logger.log_validation_error("select_node", "no_available_nodes", "доступные ноды после исключения")
                return None

            # Фильтруем ноды по пороговым значениям нагрузки
            available_nodes = []
            for load in node_loads:
                if (load.cpu_usage < self.cpu_threshold and
                    load.memory_usage < self.memory_threshold):
                    available_nodes.append(load)

            if not available_nodes:
                self.logger.log_validation_error("select_node", "all_nodes_overloaded", "ноды с допустимой нагрузкой")
                # Если все ноды перегружены, выбираем наименее загруженную
                available_nodes = node_loads

            # Вычисляем рейтинги для доступных нод
            node_scores = {}
            for load in available_nodes:
                score = load.calculate_score(strategy)
                load.score = score
                node_scores[load.node] = score

            # Выбираем ноду с наивысшим рейтингом
            best_node = max(available_nodes, key=lambda x: x.score)

            # Определяем причину выбора
            if strategy == BalancingStrategy.LEAST_LOADED:
                reason = f"Наименее загруженная нода (CPU: {best_node.cpu_usage}%, Память: {best_node.memory_usage}%)"
            elif strategy == BalancingStrategy.MEMORY_OPTIMIZED:
                reason = f"Оптимизация по памяти (Использование: {best_node.memory_usage}%)"
            elif strategy == BalancingStrategy.CPU_OPTIMIZED:
                reason = f"Оптимизация по CPU (Использование: {best_node.cpu_usage}%)"
            else:
                reason = f"Стратегия {strategy.value} (Рейтинг: {best_node.score:.1f})"

            self.logger.log_performance_metric("node_selection", best_node.score, f"для стратегии {strategy.value}")

            return best_node.node

        except Exception as e:
            self.logger.log_validation_error("select_optimal_node", str(e), "выбор оптимальной ноды")
            return None

    def get_balancing_recommendation(self, vm_requirements: Dict[str, Any]) -> BalancingResult:
        """
        Получение рекомендации по балансировке для конкретной VM

        Args:
            vm_requirements: Требования к VM (memory, cpus)

        Returns:
            Рекомендация по размещению VM
        """
        try:
            # Определяем стратегию балансировки
            if vm_requirements.get('memory_priority'):
                strategy = BalancingStrategy.MEMORY_OPTIMIZED
            elif vm_requirements.get('cpu_priority'):
                strategy = BalancingStrategy.CPU_OPTIMIZED
            else:
                strategy = BalancingStrategy.LEAST_LOADED

            # Получаем нагрузку всех нод
            node_loads = self.get_node_loads()

            if not node_loads:
                return BalancingResult(
                    selected_node="",
                    strategy=strategy,
                    node_scores={},
                    reason="Нет доступных нод"
                )

            # Вычисляем рейтинги для всех нод
            node_scores = {}
            for load in node_loads:
                score = load.calculate_score(strategy)
                load.score = score
                node_scores[load.node] = score

            # Выбираем лучшую ноду
            best_node = max(node_loads, key=lambda x: x.score)

            return BalancingResult(
                selected_node=best_node.node,
                strategy=strategy,
                node_scores=node_scores,
                reason=f"Выбрана стратегия {strategy.value}, лучший рейтинг у {best_node.node}"
            )

        except Exception as e:
            self.logger.log_validation_error("balancing_recommendation", str(e), "получение рекомендации")
            return BalancingResult(
                selected_node="",
                strategy=BalancingStrategy.LEAST_LOADED,
                node_scores={},
                reason=f"Ошибка анализа: {str(e)}"
            )

    def get_cluster_balance_status(self) -> Dict[str, Any]:
        """
        Получение статуса балансировки кластера

        Returns:
            Статус балансировки кластера
        """
        try:
            node_loads = self.get_node_loads()

            if not node_loads:
                return {'balanced': False, 'reason': 'Нет доступных нод'}

            # Анализируем балансировку
            cpu_usages = [load.cpu_usage for load in node_loads]
            memory_usages = [load.memory_usage for load in node_loads]

            cpu_avg = sum(cpu_usages) / len(cpu_usages)
            memory_avg = sum(memory_usages) / len(memory_usages)

            cpu_max = max(cpu_usages)
            memory_max = max(memory_usages)

            # Определяем уровень балансировки
            if cpu_max > self.cpu_threshold or memory_max > self.memory_threshold:
                balance_status = "overloaded"
                reason = f"Перегрузка: CPU {cpu_max:.1f}%, Память {memory_max:.1f}%"
            elif max(cpu_max - cpu_avg, memory_max - memory_avg) > 30:
                balance_status = "unbalanced"
                reason = f"Дисбаланс: CPU {cpu_max - cpu_avg:.1f}%, Память {memory_max - memory_avg:.1f}%"
            else:
                balance_status = "balanced"
                reason = f"Хорошая балансировка: CPU {cpu_avg:.1f}%, Память {memory_avg:.1f}%"

            return {
                'balanced': balance_status == "balanced",
                'status': balance_status,
                'reason': reason,
                'cpu_average': round(cpu_avg, 2),
                'memory_average': round(memory_avg, 2),
                'cpu_max': round(cpu_max, 2),
                'memory_max': round(memory_max, 2),
                'nodes_count': len(node_loads),
                'overloaded_nodes': [
                    load.node for load in node_loads
                    if load.cpu_usage > self.cpu_threshold or load.memory_usage > self.memory_threshold
                ]
            }

        except Exception as e:
            return {
                'balanced': False,
                'status': 'error',
                'reason': f'Ошибка анализа: {str(e)}'
            }

    def suggest_rebalancing(self) -> Dict[str, Any]:
        """
        Предложение по перебалансировке кластера

        Returns:
            Рекомендации по перебалансировке
        """
        try:
            node_loads = self.get_node_loads()

            if not node_loads:
                return {'possible': False, 'reason': 'Нет доступных нод'}

            # Находим перегруженные и недогруженные ноды
            overloaded_nodes = [
                load for load in node_loads
                if load.cpu_usage > self.cpu_threshold or load.memory_usage > self.memory_threshold
            ]

            underloaded_nodes = [
                load for load in node_loads
                if load.cpu_usage < 30 and load.memory_usage < 40  # Произвольные пороги
            ]

            if not overloaded_nodes or not underloaded_nodes:
                return {
                    'possible': False,
                    'reason': 'Нет перегруженных или недогруженных нод для перебалансировки'
                }

            # Предлагаем миграции VM
            suggestions = []
            for overloaded in overloaded_nodes:
                for underloaded in underloaded_nodes:
                    if overloaded.node != underloaded.node:
                        suggestions.append({
                            'from_node': overloaded.node,
                            'to_node': underloaded.node,
                            'reason': f'Перегрузка {overloaded.node}, свободные ресурсы {underloaded.node}'
                        })

            return {
                'possible': True,
                'suggestions_count': len(suggestions),
                'overloaded_nodes': [node.node for node in overloaded_nodes],
                'underloaded_nodes': [node.node for node in underloaded_nodes],
                'suggestions': suggestions[:5]  # Ограничиваем количество предложений
            }

        except Exception as e:
            return {
                'possible': False,
                'reason': f'Ошибка анализа: {str(e)}'
            }

    def get_load_statistics(self) -> Dict[str, Any]:
        """
        Получение детальной статистики нагрузки

        Returns:
            Детальная статистика нагрузки кластера
        """
        try:
            node_loads = self.get_node_loads()

            if not node_loads:
                return {'error': 'Нет доступных нод'}

            # Общие метрики
            total_memory = sum(load.memory_total for load in node_loads)
            total_vms = sum(load.vm_count for load in node_loads)

            # Распределение нагрузки
            cpu_distribution = {
                '0-25%': 0,
                '25-50%': 0,
                '50-75%': 0,
                '75-90%': 0,
                '90-100%': 0
            }

            memory_distribution = cpu_distribution.copy()

            for load in node_loads:
                # CPU распределение
                if load.cpu_usage < 25:
                    cpu_distribution['0-25%'] += 1
                elif load.cpu_usage < 50:
                    cpu_distribution['25-50%'] += 1
                elif load.cpu_usage < 75:
                    cpu_distribution['50-75%'] += 1
                elif load.cpu_usage < 90:
                    cpu_distribution['75-90%'] += 1
                else:
                    cpu_distribution['90-100%'] += 1

                # Memory распределение
                mem_usage = load.memory_usage
                if mem_usage < 25:
                    memory_distribution['0-25%'] += 1
                elif mem_usage < 50:
                    memory_distribution['25-50%'] += 1
                elif mem_usage < 75:
                    memory_distribution['50-75%'] += 1
                elif mem_usage < 90:
                    memory_distribution['75-90%'] += 1
                else:
                    memory_distribution['90-100%'] += 1

            return {
                'total_nodes': len(node_loads),
                'total_memory_gb': round(total_memory / 1024 / 1024, 2),
                'total_vms': total_vms,
                'average_cpu': round(sum(load.cpu_usage for load in node_loads) / len(node_loads), 2),
                'average_memory': round(sum(load.memory_usage for load in node_loads) / len(node_loads), 2),
                'cpu_distribution': cpu_distribution,
                'memory_distribution': memory_distribution,
                'nodes': [
                    {
                        'node': load.node,
                        'cpu_usage': round(load.cpu_usage, 2),
                        'memory_usage': round(load.memory_usage, 2),
                        'vm_count': load.vm_count,
                        'uptime_days': round(load.uptime / 86400, 1)
                    }
                    for load in sorted(node_loads, key=lambda x: x.cpu_usage + x.memory_usage, reverse=True)
                ]
            }

        except Exception as e:
            return {'error': f'Ошибка получения статистики: {str(e)}'}

    def clear_load_cache(self) -> int:
        """
        Очистка кеша информации о нагрузке

        Returns:
            Количество очищенных записей
        """
        cleared_count = 0

        # Очищаем кеш нагрузки нод
        cache_keys = [key for key in self.cache.cache.keys() if 'node_loads' in key or 'cluster_node_loads' in key]
        for key in cache_keys:
            self.cache.delete(key)
            cleared_count += 1

        if cleared_count > 0:
            self.logger.log_cache_operation("clear_load_cache", f"{cleared_count}_entries", True)

        return cleared_count


# Глобальный экземпляр балансировщика нагрузки
_global_load_balancer = None


def get_load_balancer(proxmox_client: ProxmoxClient) -> LoadBalancer:
    """Получить глобальный экземпляр балансировщика нагрузки"""
    global _global_load_balancer
    if _global_load_balancer is None:
        _global_load_balancer = LoadBalancer(proxmox_client)
    return _global_load_balancer


# Пример использования
if __name__ == "__main__":
    print("⚖️  LoadBalancer - балансировщик нагрузки кластера")
    print("📋 Доступные методы:")

    # Получаем все публичные методы
    methods = [method for method in dir(LoadBalancer) if not method.startswith('_') and callable(getattr(LoadBalancer, method))]
    for method in methods:
        print(f"  - {method}")

    print(f"\n📊 Всего методов: {len(methods)}")
    print("✅ Балансировщик нагрузки готов к использованию")
