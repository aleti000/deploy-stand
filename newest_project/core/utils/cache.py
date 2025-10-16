#!/usr/bin/env python3
"""
Cache - модуль кеширования данных для newest_project

Предоставляет функции для кеширования часто используемых данных,
таких как bridge mapping, конфигурации пользователей и метрики производительности.
"""

import json
import pickle
import hashlib
import time
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class CacheEntry:
    """Элемент кеша с метаданными"""
    key: str
    data: Any
    timestamp: float
    ttl: Optional[int]  # Время жизни в секундах (None = бессрочно)
    hits: int = 0

    def is_expired(self) -> bool:
        """Проверка истечения срока жизни элемента"""
        if self.ttl is None:
            return False
        return (time.time() - self.timestamp) > self.ttl

    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь для сериализации"""
        return asdict(self)


class Cache:
    """
    Класс для кеширования данных в системе развертывания VM

    Поддерживает:
    - Различные типы данных (текст, JSON, pickle)
    - Настраиваемое время жизни элементов
    - Автоматическую очистку устаревших данных
    - Статистику использования кеша
    - Сохранение на диск
    """

    def __init__(self, cache_dir: str = "cache", default_ttl: Optional[int] = None):
        """
        Инициализация кеша

        Args:
            cache_dir: Директория для хранения кеш-файлов
            default_ttl: Время жизни по умолчанию в секундах
        """
        self.cache_dir = Path(cache_dir)
        self.default_ttl = default_ttl
        self.cache: Dict[str, CacheEntry] = {}
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'expired_cleanups': 0
        }

        # Создаем директорию для кеша
        self.cache_dir.mkdir(exist_ok=True)

        # Загружаем существующий кеш с диска
        self._load_from_disk()

    def get(self, key: str) -> Optional[Any]:
        """
        Получение значения из кеша

        Args:
            key: Ключ элемента

        Returns:
            Значение или None если не найдено/истекло
        """
        # Очищаем устаревшие элементы
        self._cleanup_expired()

        if key in self.cache:
            entry = self.cache[key]
            if not entry.is_expired():
                entry.hits += 1
                self.stats['hits'] += 1
                return entry.data
            else:
                # Элемент истек, удаляем его
                del self.cache[key]
                self.stats['expired_cleanups'] += 1

        self.stats['misses'] += 1
        return None

    def set(self, key: str, data: Any, ttl: Optional[int] = None) -> None:
        """
        Сохранение значения в кеш

        Args:
            key: Ключ элемента
            data: Данные для сохранения
            ttl: Время жизни в секундах (используется default_ttl если None)
        """
        if ttl is None:
            ttl = self.default_ttl

        entry = CacheEntry(
            key=key,
            data=data,
            timestamp=time.time(),
            ttl=ttl
        )

        self.cache[key] = entry
        self.stats['sets'] += 1

        # Автосохранение на диск
        self._save_to_disk()

    def delete(self, key: str) -> bool:
        """
        Удаление элемента из кеша

        Args:
            key: Ключ элемента

        Returns:
            True если элемент был удален
        """
        if key in self.cache:
            del self.cache[key]
            self.stats['deletes'] += 1
            self._save_to_disk()
            return True
        return False

    def exists(self, key: str) -> bool:
        """
        Проверка существования элемента в кеше

        Args:
            key: Ключ элемента

        Returns:
            True если элемент существует и не истек
        """
        entry = self.cache.get(key)
        if entry and not entry.is_expired():
            return True
        return False

    def clear(self) -> None:
        """Очистка всего кеша"""
        self.cache.clear()
        self.stats = {k: 0 for k in self.stats}
        self._save_to_disk()

    def cleanup_expired(self) -> int:
        """
        Очистка устаревших элементов

        Returns:
            Количество удаленных элементов
        """
        return self._cleanup_expired()

    def _cleanup_expired(self) -> int:
        """Внутренняя очистка устаревших элементов"""
        expired_keys = [
            key for key, entry in self.cache.items()
            if entry.is_expired()
        ]

        for key in expired_keys:
            del self.cache[key]

        count = len(expired_keys)
        self.stats['expired_cleanups'] += count

        if count > 0:
            self._save_to_disk()

        return count

    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики использования кеша"""
        total_requests = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total_requests * 100) if total_requests > 0 else 0

        return {
            **self.stats,
            'total_requests': total_requests,
            'hit_rate_percent': round(hit_rate, 2),
            'cache_size': len(self.cache),
            'cache_keys': list(self.cache.keys())
        }

    def _get_cache_file(self) -> Path:
        """Получение пути к файлу кеша"""
        return self.cache_dir / "cache.json"

    def _load_from_disk(self) -> None:
        """Загрузка кеша с диска"""
        cache_file = self._get_cache_file()

        if not cache_file.exists():
            return

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Восстанавливаем элементы кеша
            for key, entry_data in data.get('cache', {}).items():
                try:
                    entry = CacheEntry(
                        key=entry_data['key'],
                        data=entry_data['data'],
                        timestamp=entry_data['timestamp'],
                        ttl=entry_data['ttl'],
                        hits=entry_data.get('hits', 0)
                    )
                    self.cache[key] = entry
                except (KeyError, ValueError) as e:
                    print(f"Ошибка загрузки элемента кеша {key}: {e}")
                    continue

            # Восстанавливаем статистику
            if 'stats' in data:
                self.stats.update(data['stats'])

        except (json.JSONDecodeError, IOError) as e:
            print(f"Ошибка загрузки кеша с диска: {e}")

    def _save_to_disk(self) -> None:
        """Сохранение кеша на диск"""
        cache_file = self._get_cache_file()

        try:
            # Подготавливаем данные для сериализации
            cache_data = {}
            for key, entry in self.cache.items():
                cache_data[key] = entry.to_dict()

            data = {
                'cache': cache_data,
                'stats': self.stats,
                'version': '1.0'
            }

            # Сохраняем на диск
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except (IOError, TypeError) as e:
            print(f"Ошибка сохранения кеша на диск: {e}")


class BridgeMappingCache:
    """
    Специализированный кеш для хранения соответствий bridge алиасов

    Используется для оптимизации повторных развертываний с одинаковыми
    сетевыми конфигурациями.
    """

    def __init__(self, cache: Cache):
        """
        Инициализация кеша bridge mapping

        Args:
            cache: Экземпляр основного кеша
        """
        self.cache = cache
        self.key_prefix = "bridge_mapping"

    def get_bridge_mapping(self, user: str, node: str) -> Optional[Dict[str, str]]:
        """
        Получение соответствий алиасов bridge'ам для пользователя и ноды

        Args:
            user: Имя пользователя
            node: Имя ноды

        Returns:
            Словарь соответствий алиасов или None
        """
        key = f"{self.key_prefix}:{user}:{node}"
        return self.cache.get(key)

    def set_bridge_mapping(self, user: str, node: str, mapping: Dict[str, str],
                          ttl: Optional[int] = 3600) -> None:
        """
        Сохранение соответствий алиасов bridge'ам

        Args:
            user: Имя пользователя
            node: Имя ноды
            mapping: Словарь соответствий алиасов
            ttl: Время жизни в секундах (по умолчанию 1 час)
        """
        key = f"{self.key_prefix}:{user}:{node}"
        self.cache.set(key, mapping, ttl)

    def clear_user_bridges(self, user: str) -> None:
        """Очистка всех bridge mapping для пользователя"""
        keys_to_delete = [
            key for key in self.cache.cache.keys()
            if key.startswith(f"{self.key_prefix}:{user}:")
        ]

        for key in keys_to_delete:
            self.cache.delete(key)


class UserConfigCache:
    """
    Специализированный кеш для хранения конфигураций пользователей

    Оптимизирует загрузку и обработку списков пользователей.
    """

    def __init__(self, cache: Cache):
        """
        Инициализация кеша конфигураций пользователей

        Args:
            cache: Экземпляр основного кеша
        """
        self.cache = cache
        self.key_prefix = "user_config"

    def get_user_config(self, config_hash: str) -> Optional[List[str]]:
        """
        Получение списка пользователей по хешу конфигурации

        Args:
            config_hash: Хеш конфигурационного файла

        Returns:
            Список пользователей или None
        """
        key = f"{self.key_prefix}:{config_hash}"
        return self.cache.get(key)

    def set_user_config(self, config_hash: str, users: List[str],
                       ttl: Optional[int] = 1800) -> None:
        """
        Сохранение списка пользователей

        Args:
            config_hash: Хеш конфигурационного файла
            users: Список пользователей
            ttl: Время жизни в секундах (по умолчанию 30 минут)
        """
        key = f"{self.key_prefix}:{config_hash}"
        self.cache.set(key, users, ttl)

    def generate_config_hash(self, config_path: Union[str, Path]) -> str:
        """
        Генерация хеша конфигурационного файла

        Args:
            config_path: Путь к файлу конфигурации

        Returns:
            Хеш файла в виде строки
        """
        path = Path(config_path)

        if not path.exists():
            return ""

        # Читаем файл и создаем хеш
        content = path.read_bytes()
        hash_obj = hashlib.sha256(content)
        return hash_obj.hexdigest()


# Глобальный экземпляр кеша
_global_cache = None


def get_cache(default_ttl: Optional[int] = None) -> Cache:
    """Получить глобальный экземпляр кеша"""
    global _global_cache
    if _global_cache is None:
        _global_cache = Cache(default_ttl=default_ttl)
    return _global_cache


def get_bridge_cache() -> BridgeMappingCache:
    """Получить экземпляр кеша bridge mapping"""
    cache = get_cache()
    return BridgeMappingCache(cache)


def get_user_config_cache() -> UserConfigCache:
    """Получить экземпляр кеша конфигураций пользователей"""
    cache = get_cache()
    return UserConfigCache(cache)


# Пример использования
if __name__ == "__main__":
    # Тестирование кеша
    cache = Cache(default_ttl=60)  # 1 минута TTL

    # Тестирование основных операций
    print("🧪 Тестирование основных операций кеша...")

    # Сохранение данных
    cache.set("test_key", {"data": "test_value", "number": 42})
    print("✅ Данные сохранены в кеш")

    # Получение данных
    data = cache.get("test_key")
    if data:
        print(f"✅ Данные получены: {data}")
    else:
        print("❌ Данные не найдены")

    # Тестирование истечения TTL
    print("\n⏰ Тестирование истечения TTL...")
    time.sleep(2)  # Ждем 2 секунды

    data = cache.get("test_key")
    if data:
        print("✅ Данные еще доступны (TTL не истек)")
    else:
        print("✅ Данные удалены (TTL истек)")

    # Тестирование специализированных кешей
    print("\n🌉 Тестирование BridgeMappingCache...")

    bridge_cache = BridgeMappingCache(cache)
    bridge_mapping = {
        "hq": "vmbr1000",
        "inet": "vmbr1001",
        "dmz": "vmbr1002"
    }

    bridge_cache.set_bridge_mapping("user1", "pve1", bridge_mapping)
    retrieved_mapping = bridge_cache.get_bridge_mapping("user1", "pve1")

    if retrieved_mapping:
        print(f"✅ Bridge mapping сохранен и получен: {retrieved_mapping}")
    else:
        print("❌ Bridge mapping не найден")

    # Показываем статистику
    print("\n📊 Статистика кеша:")
    stats = cache.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n✅ Тестирование кеша завершено")
