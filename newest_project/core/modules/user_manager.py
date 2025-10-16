#!/usr/bin/env python3
"""
UserManager - менеджер пользователей для newest_project

Управляет списками пользователей Proxmox, их группировкой по пулам,
валидацией и обработкой пользовательских данных.
"""

import re
from typing import Dict, List, Any, Optional, Set, Tuple
from collections import defaultdict

from ..utils.logger import Logger
from ..utils.validator import Validator
from ..utils.cache import Cache


class UserManager:
    """
    Менеджер пользователей Proxmox

    Возможности:
    - Загрузка и обработка списков пользователей
    - Группировка пользователей по пулам
    - Валидация пользователей
    - Генерация имен пользователей
    - Управление пользовательскими пулами
    """

    def __init__(self, logger: Optional[Logger] = None,
                 validator: Optional[Validator] = None,
                 cache: Optional[Cache] = None):
        """
        Инициализация менеджера пользователей

        Args:
            logger: Экземпляр логгера
            validator: Экземпляр валидатора
            cache: Экземпляр кеша
        """
        self.logger = logger or Logger()
        self.validator = validator or Validator()
        self.cache = cache or Cache()

        # Регулярные выражения для парсинга пользователей
        self.user_pattern = re.compile(r'^([a-zA-Z0-9._-]+)(?:@([a-zA-Z0-9._-]+))?(?:\$([a-zA-Z0-9._-]+))?$')

    def parse_user(self, user_string: str) -> Optional[Dict[str, str]]:
        """
        Парсинг строки пользователя в компоненты

        Args:
            user_string: Строка формата user@realm$subuser или user@pve

        Returns:
            Словарь с компонентами пользователя или None при ошибке
        """
        match = self.user_pattern.match(user_string.strip())

        if not match:
            self.logger.log_validation_error("user_parse", user_string, "формат user@realm$subuser")
            return None

        username, realm, subuser = match.groups()

        return {
            'username': username,
            'realm': realm or 'pve',  # По умолчанию pve
            'subuser': subuser,
            'full_user': user_string.strip()
        }

    def validate_user(self, user_string: str) -> bool:
        """
        Валидация строки пользователя

        Args:
            user_string: Строка пользователя для проверки

        Returns:
            True если пользователь валиден
        """
        return self.validator.validate_users_list([user_string])

    def group_users_by_pool(self, users: List[str]) -> Dict[str, List[str]]:
        """
        Группировка пользователей по пулам

        Args:
            users: Список пользователей

        Returns:
            Словарь с пулами и списками пользователей
        """
        pools = defaultdict(list)

        for user in users:
            pool_name = self._extract_pool_from_user(user)
            pools[pool_name].append(user)

        return dict(pools)

    def _extract_pool_from_user(self, user: str) -> str:
        """Извлечение имени пула из пользователя"""
        # По умолчанию пул назвается как realm пользователя
        parsed = self.parse_user(user)
        if parsed:
            return parsed['realm']

        # Fallback: извлекаем часть до первого специального символа
        for i, char in enumerate(user):
            if char in '@$':
                return user[:i]

        return 'default'

    def generate_user_variants(self, base_user: str, count: int = 1) -> List[str]:
        """
        Генерация вариантов пользователей на основе базового

        Args:
            base_user: Базовое имя пользователя
            count: Количество вариантов для генерации

        Returns:
            Список вариантов пользователей
        """
        variants = []
        parsed = self.parse_user(base_user)

        if not parsed:
            self.logger.log_validation_error("generate_variants", base_user, "корректный формат пользователя")
            return variants

        base_username = parsed['username']

        for i in range(1, count + 1):
            variant = f"{base_username}{i}@{parsed['realm']}"
            if parsed['subuser']:
                variant += f"${parsed['subuser']}"

            variants.append(variant)

        return variants

    def filter_users_by_pattern(self, users: List[str], pattern: str) -> List[str]:
        """
        Фильтрация пользователей по шаблону

        Args:
            users: Список пользователей
            pattern: Шаблон для фильтрации (например, "*@pve")

        Returns:
            Отфильтрованный список пользователей
        """
        if pattern == "*":
            return users

        # Преобразуем шаблон в регулярное выражение
        regex_pattern = pattern.replace('*', '.*').replace('?', '.')
        regex = re.compile(f"^{regex_pattern}$")

        filtered_users = []
        for user in users:
            if regex.match(user):
                filtered_users.append(user)

        return filtered_users

    def get_user_statistics(self, users: List[str]) -> Dict[str, Any]:
        """
        Получение статистики по списку пользователей

        Args:
            users: Список пользователей

        Returns:
            Статистика пользователей
        """
        if not users:
            return {'total': 0, 'pools': {}, 'realms': {}}

        # Группируем по пулам
        pools = self.group_users_by_pool(users)

        # Анализируем realms
        realms = defaultdict(int)
        for user in users:
            parsed = self.parse_user(user)
            if parsed:
                realms[parsed['realm']] += 1

        return {
            'total': len(users),
            'pools': {pool: len(users_list) for pool, users_list in pools.items()},
            'realms': dict(realms),
            'unique_pools': len(pools),
            'unique_realms': len(realms)
        }

    def merge_user_lists(self, *user_lists: List[str]) -> List[str]:
        """
        Объединение нескольких списков пользователей

        Args:
            *user_lists: Списки пользователей для объединения

        Returns:
            Объединенный список уникальных пользователей
        """
        merged = set()

        for user_list in user_lists:
            if isinstance(user_list, list):
                merged.update(user_list)

        # Убираем пустые строки и дубликаты
        result = [user for user in merged if user.strip()]

        # Сортируем для консистентности
        result.sort()

        return result

    def find_duplicate_users(self, users: List[str]) -> List[str]:
        """
        Поиск дубликатов пользователей

        Args:
            users: Список пользователей

        Returns:
            Список дублированных пользователей
        """
        seen = set()
        duplicates = set()

        for user in users:
            user_clean = user.strip()
            if user_clean in seen:
                duplicates.add(user_clean)
            else:
                seen.add(user_clean)

        return list(duplicates)

    def validate_user_list(self, users: List[str]) -> Dict[str, Any]:
        """
        Комплексная валидация списка пользователей

        Args:
            users: Список пользователей для проверки

        Returns:
            Результат валидации с деталями
        """
        # Проверяем на дубликаты
        duplicates = self.find_duplicate_users(users)

        # Валидация через Validator
        is_valid = self.validator.validate_users_list(users)

        # Получаем статистику
        stats = self.get_user_statistics(users)

        return {
            'valid': is_valid and len(duplicates) == 0,
            'total_users': len(users),
            'duplicates': duplicates,
            'duplicates_count': len(duplicates),
            'statistics': stats,
            'errors': self.validator.get_errors(),
            'warnings': self.validator.get_warnings()
        }

    def format_user_for_display(self, user: str) -> str:
        """
        Форматирование пользователя для отображения

        Args:
            user: Строка пользователя

        Returns:
            Отформатированная строка
        """
        parsed = self.parse_user(user)
        if not parsed:
            return user

        if parsed['subuser']:
            return f"{parsed['username']}@{parsed['realm']}${parsed['subuser']}"
        else:
            return f"{parsed['username']}@{parsed['realm']}"

    def extract_pool_name(self, user: str) -> str:
        """
        Извлечение имени пула из пользователя

        Args:
            user: Строка пользователя

        Returns:
            Имя пула
        """
        parsed = self.parse_user(user)
        return parsed['realm'] if parsed else 'default'

    def create_user_pool_mapping(self, users: List[str]) -> Dict[str, str]:
        """
        Создание соответствия пользователь -> пул

        Args:
            users: Список пользователей

        Returns:
            Словарь соответствий
        """
        mapping = {}

        for user in users:
            pool = self.extract_pool_name(user)
            mapping[user] = pool

        return mapping

    def get_users_by_pool(self, users: List[str], pool: str) -> List[str]:
        """
        Получение пользователей для указанного пула

        Args:
            users: Список пользователей
            pool: Имя пула

        Returns:
            Список пользователей в пуле
        """
        pool_users = []

        for user in users:
            if self.extract_pool_name(user) == pool:
                pool_users.append(user)

        return pool_users

    def cleanup_user_list(self, users: List[str]) -> List[str]:
        """
        Очистка списка пользователей от некорректных записей

        Args:
            users: Исходный список пользователей

        Returns:
            Очищенный список пользователей
        """
        cleaned = []
        invalid = []

        for user in users:
            user_clean = user.strip()
            if not user_clean:
                continue

            if self.validate_user(user_clean):
                cleaned.append(user_clean)
            else:
                invalid.append(user_clean)

        if invalid:
            self.logger.log_validation_error("cleanup_users", f"{len(invalid)}_invalid", "удаление некорректных пользователей")
            for user in invalid:
                self.logger.log_validation_error("invalid_user", user, "удаление из списка")

        return cleaned

    def split_users_by_realm(self, users: List[str]) -> Dict[str, List[str]]:
        """
        Разделение пользователей по realm'ам

        Args:
            users: Список пользователей

        Returns:
            Словарь realm -> список пользователей
        """
        realms = defaultdict(list)

        for user in users:
            parsed = self.parse_user(user)
            if parsed:
                realms[parsed['realm']].append(user)

        return dict(realms)


# Глобальный экземпляр менеджера пользователей
_global_user_manager = None


def get_user_manager() -> UserManager:
    """Получить глобальный экземпляр менеджера пользователей"""
    global _global_user_manager
    if _global_user_manager is None:
        _global_user_manager = UserManager()
    return _global_user_manager


# Пример использования
if __name__ == "__main__":
    print("👥 UserManager - менеджер пользователей Proxmox")
    print("📋 Доступные методы:")

    # Получаем все публичные методы
    methods = [method for method in dir(UserManager) if not method.startswith('_') and callable(getattr(UserManager, method))]
    for method in methods:
        print(f"  - {method}")

    print(f"\n📊 Всего методов: {len(methods)}")
    print("✅ Менеджер пользователей готов к использованию")
