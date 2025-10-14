"""
Метрики производительности системы Deploy-Stand

Предоставляет функциональность для сбора и анализа метрик производительности
операций развертывания виртуальных машин.
"""

import time
import statistics
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """Менеджер метрик производительности"""

    def __init__(self):
        """Инициализация менеджера метрик"""
        self.metrics = {
            'deployment_time': [],
            'template_creation_time': [],
            'network_setup_time': [],
            'user_creation_time': [],
            'api_call_count': 0,
            'error_count': 0,
            'cache_hit_rate': 0.0,
            'cache_requests': 0,
            'cache_hits': 0
        }

        # Текущие операции
        self.current_operations = {}

    def start_operation(self, operation_name: str) -> str:
        """
        Начать отслеживание операции

        Args:
            operation_name: Название операции

        Returns:
            ID операции для завершения
        """
        operation_id = f"{operation_name}_{time.time()}"
        self.current_operations[operation_id] = {
            'name': operation_name,
            'start_time': time.time()
        }

        logger.debug(f"Начата операция: {operation_name}")
        return operation_id

    def end_operation(self, operation_id: str) -> float:
        """
        Завершить отслеживание операции

        Args:
            operation_id: ID операции

        Returns:
            Длительность операции в секундах
        """
        if operation_id not in self.current_operations:
            logger.warning(f"Операция {operation_id} не найдена")
            return 0.0

        operation = self.current_operations[operation_id]
        duration = time.time() - operation['start_time']

        # Записать метрику в зависимости от типа операции
        operation_name = operation['name']

        if operation_name == 'deployment':
            self.metrics['deployment_time'].append(duration)
        elif operation_name == 'template_creation':
            self.metrics['template_creation_time'].append(duration)
        elif operation_name == 'network_setup':
            self.metrics['network_setup_time'].append(duration)
        elif operation_name == 'user_creation':
            self.metrics['user_creation_time'].append(duration)

        # Очистить текущую операцию
        del self.current_operations[operation_id]

        logger.debug(f"Завершена операция {operation_name} за {duration:.2f}с")
        return duration

    def record_api_call(self):
        """Подсчитать вызов API"""
        self.metrics['api_call_count'] += 1

    def record_error(self):
        """Подсчитать ошибку"""
        self.metrics['error_count'] += 1

    def record_cache_request(self, hit: bool = False):
        """Записать запрос к кешу"""
        self.metrics['cache_requests'] += 1
        if hit:
            self.metrics['cache_hits'] += 1

    def update_cache_hit_rate(self):
        """Обновить коэффициент попаданий в кеш"""
        if self.metrics['cache_requests'] > 0:
            self.metrics['cache_hit_rate'] = (
                self.metrics['cache_hits'] / self.metrics['cache_requests']
            )

    def get_average_deployment_time(self) -> float:
        """Получить среднее время развертывания"""
        if not self.metrics['deployment_time']:
            return 0.0
        return statistics.mean(self.metrics['deployment_time'])

    def get_median_deployment_time(self) -> float:
        """Получить медианное время развертывания"""
        if not self.metrics['deployment_time']:
            return 0.0
        return statistics.median(self.metrics['deployment_time'])

    def get_min_deployment_time(self) -> float:
        """Получить минимальное время развертывания"""
        if not self.metrics['deployment_time']:
            return 0.0
        return min(self.metrics['deployment_time'])

    def get_max_deployment_time(self) -> float:
        """Получить максимальное время развертывания"""
        if not self.metrics['deployment_time']:
            return 0.0
        return max(self.metrics['deployment_time'])

    def get_deployment_time_percentile(self, percentile: float) -> float:
        """Получить перцентиль времени развертывания"""
        if not self.metrics['deployment_time']:
            return 0.0
        return statistics.quantiles(self.metrics['deployment_time'], n=100)[int(percentile) - 1]

    def get_success_rate(self) -> float:
        """Получить коэффициент успешности операций"""
        total_operations = self.metrics['api_call_count']
        if total_operations == 0:
            return 1.0
        return 1.0 - (self.metrics['error_count'] / total_operations)

    def get_cache_hit_rate(self) -> float:
        """Получить коэффициент попаданий в кеш"""
        return self.metrics['cache_hit_rate']

    def get_summary_stats(self) -> Dict[str, Any]:
        """Получить сводную статистику"""
        return {
            'deployment': {
                'count': len(self.metrics['deployment_time']),
                'average_time': self.get_average_deployment_time(),
                'median_time': self.get_median_deployment_time(),
                'min_time': self.get_min_deployment_time(),
                'max_time': self.get_max_deployment_time(),
                'p95_time': self.get_deployment_time_percentile(95),
                'p99_time': self.get_deployment_time_percentile(99)
            },
            'performance': {
                'total_api_calls': self.metrics['api_call_count'],
                'total_errors': self.metrics['error_count'],
                'success_rate': self.get_success_rate(),
                'cache_hit_rate': self.get_cache_hit_rate(),
                'cache_requests': self.metrics['cache_requests'],
                'cache_hits': self.metrics['cache_hits']
            },
            'averages': {
                'template_creation': self._get_average_time('template_creation_time'),
                'network_setup': self._get_average_time('network_setup_time'),
                'user_creation': self._get_average_time('user_creation_time')
            }
        }

    def _get_average_time(self, metric_name: str) -> float:
        """Получить среднее время для указанной метрики"""
        times = self.metrics[metric_name]
        if not times:
            return 0.0
        return statistics.mean(times)

    def reset_metrics(self):
        """Сбросить все метрики"""
        for key in self.metrics:
            if isinstance(self.metrics[key], list):
                self.metrics[key].clear()
            elif isinstance(self.metrics[key], (int, float)):
                self.metrics[key] = 0 if isinstance(self.metrics[key], int) else 0.0

        self.current_operations.clear()
        logger.info("Метрики производительности сброшены")

    def export_metrics(self) -> Dict[str, Any]:
        """Экспортировать метрики для внешнего анализа"""
        return {
            'timestamp': time.time(),
            'metrics': self.metrics.copy(),
            'summary': self.get_summary_stats()
        }

    def print_summary(self):
        """Вывести сводку метрик в консоль"""
        summary = self.get_summary_stats()

        print("\n📊 Сводка производительности")
        print("=" * 50)

        deployment = summary['deployment']
        if deployment['count'] > 0:
            print("🚀 Развертывание:")
            print(f"   Количество операций: {deployment['count']}")
            print(f"   Среднее время: {deployment['average_time']:.2f}с")
            print(f"   Медианное время: {deployment['median_time']:.2f}с")
            print(f"   Мин/Макс: {deployment['min_time']:.2f}с / {deployment['max_time']:.2f}с")
            print(f"   95-й перцентиль: {deployment['p95_time']:.2f}с")

        performance = summary['performance']
        print("\n⚡ Производительность:")
        print(f"   API вызовов: {performance['total_api_calls']}")
        print(f"   Ошибок: {performance['total_errors']}")
        print(f"   Успешность: {performance['success_rate']:.1%}")
        print(f"   Кеш hit rate: {performance['cache_hit_rate']:.1%}")

        averages = summary['averages']
        print("\n⏱️  Средние времена:")
        print(f"   Создание шаблона: {averages['template_creation']:.2f}с")
        print(f"   Настройка сети: {averages['network_setup']:.2f}с")
        print(f"   Создание пользователя: {averages['user_creation']:.2f}с")

        print("=" * 50)


class MetricsCollector:
    """Коллектор метрик для системы Deploy-Stand"""

    def __init__(self):
        """Инициализация сборщика метрик"""
        self.performance_metrics = PerformanceMetrics()

    def start_operation(self, operation_name: str) -> str:
        """Начать отслеживание операции"""
        return self.performance_metrics.start_operation(operation_name)

    def end_operation(self, operation_id: str) -> float:
        """Завершить отслеживание операции"""
        return self.performance_metrics.end_operation(operation_id)

    def record_api_call(self):
        """Подсчитать вызов API"""
        self.performance_metrics.record_api_call()

    def record_error(self):
        """Подсчитать ошибку"""
        self.performance_metrics.record_error()

    def record_cache_request(self, hit: bool = False):
        """Записать запрос к кешу"""
        self.performance_metrics.record_cache_request(hit)
        self.performance_metrics.update_cache_hit_rate()

    def get_summary_stats(self) -> Dict[str, Any]:
        """Получить сводную статистику"""
        return self.performance_metrics.get_summary_stats()

    def print_summary(self):
        """Вывести сводку метрик"""
        self.performance_metrics.print_summary()

    def reset_metrics(self):
        """Сбросить метрики"""
        self.performance_metrics.reset_metrics()

    def export_metrics(self) -> Dict[str, Any]:
        """Экспортировать метрики"""
        return self.performance_metrics.export_metrics()
