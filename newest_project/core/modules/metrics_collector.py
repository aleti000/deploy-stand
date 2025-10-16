#!/usr/bin/env python3
"""
MetricsCollector - сборщик метрик для newest_project

Собирает и анализирует метрики производительности кластера Proxmox VE,
VM и системы развертывания.
"""

import time
import psutil
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque

from ..utils.logger import Logger
from ..utils.validator import Validator
from ..utils.cache import Cache
from .proxmox_client import ProxmoxClient


@dataclass
class SystemMetrics:
    """Системные метрики сервера"""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_total_gb: float
    disk_usage_percent: float
    network_io: Dict[str, int] = field(default_factory=dict)


@dataclass
class ClusterMetrics:
    """Метрики кластера Proxmox"""
    timestamp: float
    total_nodes: int
    active_nodes: int
    total_vms: int
    running_vms: int
    total_memory_gb: float
    used_memory_gb: float
    total_cpu_cores: int
    used_cpu_percent: float


@dataclass
class DeploymentMetrics:
    """Метрики развертывания"""
    timestamp: float
    deployment_name: str
    total_vms_planned: int
    vms_created: int
    vms_failed: int
    duration_seconds: float
    average_creation_time: float


class MetricsCollector:
    """
    Сборщик метрик производительности

    Возможности:
    - Сбор системных метрик сервера
    - Мониторинг метрик кластера Proxmox
    - Отслеживание метрик развертывания
    - Хранение истории метрик
    - Анализ трендов производительности
    """

    def __init__(self, proxmox_client: Optional[ProxmoxClient] = None,
                 logger: Optional[Logger] = None,
                 validator: Optional[Validator] = None,
                 cache: Optional[Cache] = None,
                 history_size: int = 100):
        """
        Инициализация сборщика метрик

        Args:
            proxmox_client: Клиент Proxmox API (опционально)
            logger: Экземпляр логгера
            validator: Экземпляр валидатора
            cache: Экземпляр кеша
            history_size: Размер истории метрик
        """
        self.proxmox = proxmox_client
        self.logger = logger or Logger()
        self.validator = validator or Validator()
        self.cache = cache or Cache()

        # История метрик
        self.history_size = history_size
        self.system_metrics_history: deque = deque(maxlen=history_size)
        self.cluster_metrics_history: deque = deque(maxlen=history_size)
        self.deployment_metrics_history: deque = deque(maxlen=history_size)

        # Кеш для метрик
        self.metrics_cache_ttl = 60  # 1 минута

    def collect_system_metrics(self) -> SystemMetrics:
        """
        Сбор системных метрик сервера

        Returns:
            Системные метрики
        """
        try:
            timestamp = time.time()

            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)

            # Память
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_gb = round(memory.used / (1024**3), 2)
            memory_total_gb = round(memory.total / (1024**3), 2)

            # Диск
            disk = psutil.disk_usage('/')
            disk_usage_percent = disk.percent

            # Сеть (упрощенно)
            network_io = {}
            try:
                network = psutil.net_io_counters()
                if network:
                    network_io = {
                        'bytes_sent': network.bytes_sent,
                        'bytes_recv': network.bytes_recv,
                        'packets_sent': network.packets_sent,
                        'packets_recv': network.packets_recv
                    }
            except Exception:
                pass

            metrics = SystemMetrics(
                timestamp=timestamp,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_used_gb=memory_used_gb,
                memory_total_gb=memory_total_gb,
                disk_usage_percent=disk_usage_percent,
                network_io=network_io
            )

            # Сохраняем в историю
            self.system_metrics_history.append(metrics)

            # Логируем критические значения
            if cpu_percent > 80:
                self.logger.log_performance_metric("high_cpu_usage", cpu_percent, "%")

            if memory_percent > 85:
                self.logger.log_performance_metric("high_memory_usage", memory_percent, "%")

            return metrics

        except Exception as e:
            self.logger.log_validation_error("system_metrics", str(e), "сбор системных метрик")
            return SystemMetrics(timestamp=time.time(), cpu_percent=0, memory_percent=0,
                               memory_used_gb=0, memory_total_gb=0, disk_usage_percent=0)

    def collect_cluster_metrics(self) -> Optional[ClusterMetrics]:
        """
        Сбор метрик кластера Proxmox

        Returns:
            Метрики кластера или None при ошибке
        """
        if not self.proxmox:
            return None

        try:
            timestamp = time.time()

            # Получаем информацию о нодах
            nodes = self.proxmox.get_nodes()
            total_nodes = len(nodes)
            active_nodes = 0

            total_memory_gb = 0
            used_memory_gb = 0
            total_cpu_cores = 0
            total_cpu_usage = 0

            for node in nodes:
                try:
                    node_info = self.proxmox.get_node_info(node)
                    if node_info:
                        active_nodes += 1
                        total_memory_gb += node_info.memory_total / (1024**3)
                        used_memory_gb += (node_info.memory_total * node_info.memory_usage / 100) / (1024**3)
                        total_cpu_cores += 1  # Упрощенно считаем 1 ядро на ноду
                        total_cpu_usage += node_info.cpu_usage
                except Exception as e:
                    self.logger.log_validation_error("node_metrics", node, f"сбор метрик: {str(e)}")
                    continue

            # Получаем информацию о VM
            try:
                cluster_resources = self.proxmox.get_cluster_resources()
                total_vms = sum(1 for res in cluster_resources if res.get('type') == 'qemu')
                running_vms = sum(1 for res in cluster_resources if res.get('type') == 'qemu' and res.get('status') == 'running')
            except Exception:
                total_vms = 0
                running_vms = 0

            metrics = ClusterMetrics(
                timestamp=timestamp,
                total_nodes=total_nodes,
                active_nodes=active_nodes,
                total_vms=total_vms,
                running_vms=running_vms,
                total_memory_gb=round(total_memory_gb, 2),
                used_memory_gb=round(used_memory_gb, 2),
                total_cpu_cores=total_cpu_cores,
                used_cpu_percent=round(total_cpu_usage / max(total_cpu_cores, 1), 2)
            )

            # Сохраняем в историю
            self.cluster_metrics_history.append(metrics)

            return metrics

        except Exception as e:
            self.logger.log_validation_error("cluster_metrics", str(e), "сбор метрик кластера")
            return None

    def record_deployment_metrics(self, deployment_name: str, total_vms: int,
                                 created_vms: int, failed_vms: int, duration: float) -> None:
        """
        Запись метрик развертывания

        Args:
            deployment_name: Имя развертывания
            total_vms: Общее количество планируемых VM
            created_vms: Количество успешно созданных VM
            failed_vms: Количество неудачных VM
            duration: Длительность развертывания в секундах
        """
        try:
            metrics = DeploymentMetrics(
                timestamp=time.time(),
                deployment_name=deployment_name,
                total_vms_planned=total_vms,
                vms_created=created_vms,
                vms_failed=failed_vms,
                duration_seconds=duration,
                average_creation_time=duration / max(created_vms, 1)
            )

            # Сохраняем в историю
            self.deployment_metrics_history.append(metrics)

            # Логируем метрики развертывания
            self.logger.log_performance_metric("deployment_duration", duration, "секунд")
            self.logger.log_performance_metric("deployment_success_rate", created_vms / max(total_vms, 1) * 100, "%")

        except Exception as e:
            self.logger.log_validation_error("deployment_metrics", str(e), "запись метрик развертывания")

    def get_system_metrics_history(self, last_n: Optional[int] = None) -> List[SystemMetrics]:
        """
        Получение истории системных метрик

        Args:
            last_n: Количество последних записей (если None, то все)

        Returns:
            Список системных метрик
        """
        metrics = list(self.system_metrics_history)
        if last_n:
            return metrics[-last_n:]
        return metrics

    def get_cluster_metrics_history(self, last_n: Optional[int] = None) -> List[ClusterMetrics]:
        """
        Получение истории метрик кластера

        Args:
            last_n: Количество последних записей (если None, то все)

        Returns:
            Список метрик кластера
        """
        metrics = list(self.cluster_metrics_history)
        if last_n:
            return metrics[-last_n:]
        return metrics

    def get_deployment_metrics_history(self, last_n: Optional[int] = None) -> List[DeploymentMetrics]:
        """
        Получение истории метрик развертывания

        Args:
            last_n: Количество последних записей (если None, то все)

        Returns:
            Список метрик развертывания
        """
        metrics = list(self.deployment_metrics_history)
        if last_n:
            return metrics[-last_n:]
        return metrics

    def get_current_metrics(self) -> Dict[str, Any]:
        """
        Получение текущих метрик системы

        Returns:
            Словарь с текущими метриками
        """
        try:
            # Системные метрики
            system_metrics = self.collect_system_metrics()

            # Метрики кластера
            cluster_metrics = self.collect_cluster_metrics()

            # Формируем общий отчет
            current_metrics = {
                'timestamp': time.time(),
                'system': {
                    'cpu_percent': system_metrics.cpu_percent,
                    'memory_percent': system_metrics.memory_percent,
                    'memory_used_gb': system_metrics.memory_used_gb,
                    'memory_total_gb': system_metrics.memory_total_gb,
                    'disk_usage_percent': system_metrics.disk_usage_percent
                },
                'cluster': None,
                'deployment_stats': {
                    'total_deployments': len(self.deployment_metrics_history),
                    'recent_deployments': len(self.get_deployment_metrics_history(5))
                }
            }

            if cluster_metrics:
                current_metrics['cluster'] = {
                    'total_nodes': cluster_metrics.total_nodes,
                    'active_nodes': cluster_metrics.active_nodes,
                    'total_vms': cluster_metrics.total_vms,
                    'running_vms': cluster_metrics.running_vms,
                    'memory_usage_percent': round(cluster_metrics.used_memory_gb / max(cluster_metrics.total_memory_gb, 1) * 100, 2),
                    'cpu_usage_percent': cluster_metrics.used_cpu_percent
                }

            return current_metrics

        except Exception as e:
            self.logger.log_validation_error("current_metrics", str(e), "получение текущих метрик")
            return {'error': str(e)}

    def analyze_performance_trends(self) -> Dict[str, Any]:
        """
        Анализ трендов производительности

        Returns:
            Анализ трендов производительности
        """
        try:
            system_history = self.get_system_metrics_history(20)  # Последние 20 записей
            cluster_history = self.get_cluster_metrics_history(20)

            if not system_history:
                return {'error': 'Недостаточно данных для анализа'}

            # Анализ системных метрик
            cpu_trend = self._calculate_trend([m.cpu_percent for m in system_history])
            memory_trend = self._calculate_trend([m.memory_percent for m in system_history])

            # Анализ метрик кластера
            cluster_cpu_trend = None
            cluster_memory_trend = None

            if cluster_history:
                cluster_cpu_trend = self._calculate_trend([m.used_cpu_percent for m in cluster_history])
                cluster_memory_trend = self._calculate_trend([
                    m.used_memory_gb / max(m.total_memory_gb, 1) * 100 for m in cluster_history
                ])

            return {
                'system_trends': {
                    'cpu_trend': cpu_trend,
                    'memory_trend': memory_trend,
                    'trend_direction': self._interpret_trend(cpu_trend, memory_trend)
                },
                'cluster_trends': {
                    'cpu_trend': cluster_cpu_trend,
                    'memory_trend': cluster_memory_trend,
                    'trend_direction': self._interpret_trend(cluster_cpu_trend, cluster_memory_trend) if cluster_cpu_trend else None
                },
                'analysis_timestamp': time.time(),
                'data_points': len(system_history)
            }

        except Exception as e:
            return {'error': f'Ошибка анализа трендов: {str(e)}'}

    def _calculate_trend(self, values: List[float]) -> float:
        """Расчет тренда по списку значений"""
        if len(values) < 2:
            return 0.0

        # Простой расчет тренда (разница первого и последнего значения)
        return values[-1] - values[0]

    def _interpret_trend(self, cpu_trend: Optional[float], memory_trend: Optional[float]) -> str:
        """Интерпретация направления тренда"""
        if cpu_trend is None or memory_trend is None:
            return "unknown"

        avg_trend = (cpu_trend + memory_trend) / 2

        if avg_trend > 5:
            return "increasing"
        elif avg_trend < -5:
            return "decreasing"
        else:
            return "stable"

    def get_deployment_statistics(self) -> Dict[str, Any]:
        """
        Получение статистики развертываний

        Returns:
            Статистика развертываний
        """
        deployments = self.get_deployment_metrics_history()

        if not deployments:
            return {
                'total_deployments': 0,
                'total_vms_created': 0,
                'total_vms_failed': 0,
                'average_duration': 0,
                'success_rate': 0
            }

        total_created = sum(d.vms_created for d in deployments)
        total_failed = sum(d.vms_failed for d in deployments)
        total_planned = sum(d.total_vms_planned for d in deployments)

        total_duration = sum(d.duration_seconds for d in deployments)
        avg_duration = total_duration / len(deployments)

        success_rate = total_created / max(total_planned, 1) * 100

        return {
            'total_deployments': len(deployments),
            'total_vms_created': total_created,
            'total_vms_failed': total_failed,
            'total_vms_planned': total_planned,
            'average_duration_seconds': round(avg_duration, 2),
            'success_rate_percent': round(success_rate, 2),
            'recent_deployments': [
                {
                    'name': d.deployment_name,
                    'created': d.vms_created,
                    'failed': d.vms_failed,
                    'duration': round(d.duration_seconds, 2),
                    'timestamp': d.timestamp
                }
                for d in deployments[-5:]  # Последние 5 развертываний
            ]
        }

    def export_metrics(self, format: str = "json") -> str:
        """
        Экспорт метрик в указанном формате

        Args:
            format: Формат экспорта ("json", "csv")

        Returns:
            Экспортированные метрики в виде строки
        """
        try:
            metrics_data = {
                'export_timestamp': time.time(),
                'system_metrics': [
                    {
                        'timestamp': m.timestamp,
                        'cpu_percent': m.cpu_percent,
                        'memory_percent': m.memory_percent,
                        'memory_used_gb': m.memory_used_gb,
                        'memory_total_gb': m.memory_total_gb,
                        'disk_usage_percent': m.disk_usage_percent
                    }
                    for m in self.system_metrics_history
                ],
                'deployment_metrics': [
                    {
                        'timestamp': d.timestamp,
                        'deployment_name': d.deployment_name,
                        'vms_created': d.vms_created,
                        'vms_failed': d.vms_failed,
                        'duration_seconds': d.duration_seconds,
                        'average_creation_time': d.average_creation_time
                    }
                    for d in self.deployment_metrics_history
                ]
            }

            if format.lower() == "json":
                import json
                return json.dumps(metrics_data, indent=2, default=str)
            else:
                # Простая CSV реализация
                lines = ["timestamp,cpu_percent,memory_percent,memory_used_gb"]

                for metric in metrics_data['system_metrics']:
                    lines.append(f"{metric['timestamp']},{metric['cpu_percent']},{metric['memory_percent']},{metric['memory_used_gb']}")

                return "\n".join(lines)

        except Exception as e:
            return f"Ошибка экспорта метрик: {str(e)}"

    def clear_metrics_history(self) -> None:
        """Очистка истории метрик"""
        self.system_metrics_history.clear()
        self.cluster_metrics_history.clear()
        self.deployment_metrics_history.clear()

        self.logger.log_cache_operation("clear_metrics", "all_histories", True)


# Глобальный экземпляр сборщика метрик
_global_metrics_collector = None


def get_metrics_collector(proxmox_client: Optional[ProxmoxClient] = None) -> MetricsCollector:
    """Получить глобальный экземпляр сборщика метрик"""
    global _global_metrics_collector
    if _global_metrics_collector is None:
        _global_metrics_collector = MetricsCollector(proxmox_client)
    return _global_metrics_collector


# Пример использования
if __name__ == "__main__":
    print("📊 MetricsCollector - сборщик метрик производительности")
    print("📋 Доступные методы:")

    # Получаем все публичные методы
    methods = [method for method in dir(MetricsCollector) if not method.startswith('_') and callable(getattr(MetricsCollector, method))]
    for method in methods:
        print(f"  - {method}")

    print(f"\n📊 Всего методов: {len(methods)}")
    print("✅ Сборщик метрик готов к использованию")
