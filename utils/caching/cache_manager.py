"""
Менеджер кеширования системы Deploy-Stand

Предоставляет функциональность для кеширования часто используемых данных,
метаданных шаблонов и результатов операций для оптимизации производительности.
"""

import time
import hashlib
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class CacheManager:
    """Менеджер кеширования для оптимизации производительности"""

    def __init__(self):
        """Инициализация менеджера кеширования"""
        self.cache = {}
        self.timestamps = {}
        self.default_ttl = 300  # 5 минут по умолчанию

    def get(self, key: str) -> Optional[Any]:
        """
        Получить значение из кеша

        Args:
            key: Ключ кеша

        Returns:
            Значение из кеша или None если ключ не найден или истек
        """
        if key not in self.cache:
            return None

        # Проверить истечение TTL
        if self._is_expired(key):
            self.delete(key)
            return None

        logger.debug(f"Кеш hit для ключа: {key}")
        return self.cache[key]

    def set(self, key: str, value: Any, ttl: int = None) -> None:
        """
        Установить значение в кеш

        Args:
            key: Ключ кеша
            value: Значение для кеширования
            ttl: Время жизни в секундах (используется default_ttl если не указано)
        """
        if ttl is None:
            ttl = self.default_ttl

        self.cache[key] = value
        self.timestamps[key] = time.time() + ttl

        logger.debug(f"Установлен кеш для ключа: {key} (TTL: {ttl}с)")

    def delete(self, key: str) -> bool:
        """
        Удалить значение из кеша

        Args:
            key: Ключ для удаления

        Returns:
            True если ключ был найден и удален
        """
        if key in self.cache:
            del self.cache[key]
            del self.timestamps[key]
            logger.debug(f"Удален кеш для ключа: {key}")
            return True
        return False

    def clear(self) -> None:
        """Очистить весь кеш"""
        self.cache.clear()
        self.timestamps.clear()
        logger.info("Кеш полностью очищен")

    def cleanup_expired(self) -> int:
        """
        Очистить истекшие записи кеша

        Returns:
            Количество удаленных записей
        """
        current_time = time.time()
        expired_keys = [
            key for key, timestamp in self.timestamps.items()
            if current_time > timestamp
        ]

        for key in expired_keys:
            self.delete(key)

        if expired_keys:
            logger.info(f"Очищено {len(expired_keys)} истекших записей кеша")

        return len(expired_keys)

    def _is_expired(self, key: str) -> bool:
        """Проверить истекло ли время жизни записи"""
        if key not in self.timestamps:
            return True
        return time.time() > self.timestamps[key]

    def get_stats(self) -> Dict[str, Any]:
        """
        Получить статистику кеша

        Returns:
            Словарь со статистикой кеша
        """
        current_time = time.time()
        active_entries = sum(1 for ts in self.timestamps.values() if ts > current_time)
        expired_entries = len(self.timestamps) - active_entries

        return {
            'total_entries': len(self.cache),
            'active_entries': active_entries,
            'expired_entries': expired_entries,
            'cache_size_mb': self._estimate_size_mb()
        }

    def _estimate_size_mb(self) -> float:
        """Оценить размер кеша в мегабайтах"""
        try:
            import sys
            size_bytes = sys.getsizeof(self.cache) + sum(
                sys.getsizeof(value) for value in self.cache.values()
            )
            return size_bytes / (1024 * 1024)
        except:
            return 0.0

    # Специализированные методы для кеширования конкретных типов данных

    def get_template_info(self, template_key: str) -> Optional[Dict]:
        """Получить информацию о шаблоне из кеша"""
        return self.get(f"template:{template_key}")

    def set_template_info(self, template_key: str, info: Dict, ttl: int = 600) -> None:
        """Сохранить информацию о шаблоне в кеш"""
        self.set(f"template:{template_key}", info, ttl)

    def get_node_metrics(self, node: str) -> Optional[Dict]:
        """Получить метрики ноды из кеша"""
        return self.get(f"node_metrics:{node}")

    def set_node_metrics(self, node: str, metrics: Dict, ttl: int = 60) -> None:
        """Сохранить метрики ноды в кеш"""
        self.set(f"node_metrics:{node}", metrics, ttl)

    def get_distribution_cache(self, distribution_key: str) -> Optional[Dict]:
        """Получить распределение пользователей из кеша"""
        return self.get(f"distribution:{distribution_key}")

    def set_distribution_cache(self, distribution_key: str, distribution: Dict, ttl: int = 300) -> None:
        """Сохранить распределение пользователей в кеш"""
        self.set(f"distribution:{distribution_key}", distribution, ttl)

    def get_deployment_status(self, deployment_id: str) -> Optional[Dict]:
        """Получить статус развертывания из кеша"""
        return self.get(f"deployment_status:{deployment_id}")

    def set_deployment_status(self, deployment_id: str, status: Dict, ttl: int = 1800) -> None:
        """Сохранить статус развертывания в кеш"""
        self.set(f"deployment_status:{deployment_id}", status, ttl)

    def generate_cache_key(self, *args) -> str:
        """
        Сгенерировать ключ кеша на основе аргументов

        Args:
            *args: Аргументы для генерации ключа

        Returns:
            Хеш-код в виде строки
        """
        key_string = ":".join(str(arg) for arg in args)
        return hashlib.md5(key_string.encode()).hexdigest()

    def get_or_compute(self, key: str, compute_func, ttl: int = None):
        """
        Получить значение из кеша или вычислить если отсутствует

        Args:
            key: Ключ кеша
            compute_func: Функция для вычисления значения
            ttl: Время жизни кеша

        Returns:
            Значение из кеша или результат compute_func
        """
        cached_value = self.get(key)
        if cached_value is not None:
            return cached_value

        # Вычислить значение
        computed_value = compute_func()

        # Сохранить в кеш
        self.set(key, computed_value, ttl)

        return computed_value
