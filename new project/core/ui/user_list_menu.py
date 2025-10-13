#!/usr/bin/env python3
"""
Меню управления пользователями и списками пользователей
"""

import os
import yaml as yaml_module
from typing import Dict, List, Any, Optional

from ..utils import Logger, ConfigValidator


class UserListMenu:
    """Меню управления пользователями"""

    CONFIG_DIR = "data"

    def __init__(self, logger_instance):
        self.logger = logger_instance
        self.validator = ConfigValidator()
        self._ensure_directories()

    def _ensure_directories(self):
        """Создать необходимые директории если они не существуют"""
        try:
            os.makedirs(self.CONFIG_DIR, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Ошибка создания директории: {e}")

    def show(self) -> str:
        """Показать меню управления пользователями"""
        print("\n👥 Управление пользователями")
        print("=" * 50)

        print("Доступные действия:")
        print("  [1] Создать список пользователей")
        print("  [2] Показать существующие списки")
        print("  [3] Удалить список пользователей")
        print("  [0] Назад")

        choice = input("Выберите действие: ").strip()

        if choice == "1":
            return self._create_users_list()
        elif choice == "2":
            return self._show_users_lists()
        elif choice == "3":
            return self._delete_users_list()
        elif choice == "0":
            return "back"
        else:
            print("❌ Неверный выбор!")
            return "repeat"

    def _create_users_list(self) -> str:
        """Создание нового списка пользователей"""
        print("\n📝 Создание списка пользователей")
        print("-" * 40)

        try:
            # Ввод имени списка
            list_name = input("Имя списка пользователей: ").strip()
            if not list_name:
                print("❌ Имя списка обязательно!")
                return "repeat"

            # Проверка существования списка
            if self._list_exists(list_name):
                overwrite = input(f"Список '{list_name}' уже существует. Перезаписать? (y/N): ").strip().lower()
                if overwrite != 'y':
                    return "repeat"

            # Выбор способа ввода пользователей
            print("\nСпособ создания списка:")
            print("  [1] Ввести пользователей вручную")
            print("  [2] Загрузить из файла")

            method_choice = input("Выберите способ [1]: ").strip() or "1"

            users = []
            if method_choice == "1":
                users = self._input_users_manually()
            elif method_choice == "2":
                users = self._load_users_from_file(list_name)
            else:
                print("❌ Неверный выбор способа!")
                return "repeat"

            if not users:
                print("ℹ️  Список пользователей пуст")
                return "repeat"

            # Валидация пользователей
            if not self._validate_users_list(users):
                return "repeat"

            # Показать превью перед созданием
            self._show_creation_preview(list_name, users)

            # Подтверждение создания
            confirm = input(f"Создать список '{list_name}' с {len(users)} пользователями? (y/N): ").strip().lower()
            if confirm != 'y':
                print("ℹ️  Создание отменено")
                return "repeat"

            # Сохранение списка
            if self._save_users_list(list_name, users):
                self._show_import_success_message(list_name, users)
                self.logger.info(f"Создан список пользователей '{list_name}' с {len(users)} пользователями")
                return "success"
            else:
                print("❌ Ошибка сохранения списка пользователей")
                return "error"

        except Exception as e:
            self.logger.error(f"Ошибка создания списка пользователей: {e}")
            print(f"❌ Ошибка: {e}")
            return "error"

    def _input_users_manually(self) -> List[str]:
        """Ввод пользователей вручную через запятую"""
        users_input = input("Введите пользователей через запятую (user1@pve,user2@pve): ").strip()
        if not users_input:
            return []

        users = [user.strip() for user in users_input.split(',') if user.strip()]
        return users

    def _load_users_from_file(self, list_name: str) -> List[str]:
        """Загрузка пользователей из файла"""
        file_path = input("Путь к файлу со списком пользователей: ").strip()
        if not file_path:
            return []

        try:
            users = []
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Если у пользователя нет домена, добавить @pve
                        if '@' not in line:
                            line += '@pve'
                        users.append(line)

            if users:
                print(f"✅ Загружено {len(users)} пользователей из файла")
            else:
                print("ℹ️  Файл пуст или не содержит пользователей")

            return users

        except Exception as e:
            self.logger.error(f"Ошибка чтения файла: {e}")
            print(f"❌ Ошибка чтения файла: {e}")
            return []

    def _show_users_lists(self) -> str:
        """Показать существующие списки пользователей"""
        print("\n📋 Существующие списки пользователей:")
        print("-" * 50)

        try:
            lists = self._get_users_lists()
            if not lists:
                print("ℹ️  Нет сохраненных списков пользователей")
            else:
                for i, list_name in enumerate(lists, 1):
                    users = self._load_users_list(list_name)
                    num_users = len(users)
                    print(f"{i}. {list_name} ({num_users} пользователей)")

                    # Опционально показать превью пользователей
                    if num_users > 0:
                        preview_users = users[:3]  # Показать первых 3
                        preview = ", ".join(preview_users)
                        if num_users > 3:
                            preview += f" ... и еще {num_users - 3}"
                        print(f"   👤 {preview}")

        except Exception as e:
            self.logger.error(f"Ошибка показа списков пользователей: {e}")
            print(f"❌ Ошибка: {e}")

        input("\nНажмите Enter для продолжения...")
        return "repeat"

    def _delete_users_list(self) -> str:
        """Удалить список пользователей"""
        print("\n🗑️  Удаление списка пользователей")
        print("-" * 40)

        try:
            lists = self._get_users_lists()
            if not lists:
                print("ℹ️  Нет списков пользователей для удаления")
                return "repeat"

            print("Доступные списки:")
            for i, list_name in enumerate(lists, 1):
                users = self._load_users_list(list_name)
                print(f"  [{i}] {list_name} ({len(users)} пользователей)")

            while True:
                choice_input = input(f"Выберите список для удаления (1-{len(lists)}) или 0 для отмены: ").strip()
                if choice_input == "0":
                    return "repeat"
                try:
                    choice = int(choice_input) - 1
                    if 0 <= choice < len(lists):
                        break
                    else:
                        print(f"❌ Выберите число от 1 до {len(lists)}")
                except ValueError:
                    print("❌ Введите корректное число!")

            list_name = lists[choice]
            confirm = input(f"Удалить список '{list_name}'? (y/N): ").strip().lower()

            if confirm == 'y':
                if self._delete_users_list_file(list_name):
                    print(f"✅ Список '{list_name}' удален")
                    self.logger.info(f"Удален список пользователей '{list_name}'")
                    return "success"
                else:
                    print("❌ Ошибка удаления списка пользователей")
                    return "error"
            else:
                print("ℹ️  Удаление отменено")
                return "repeat"

        except Exception as e:
            self.logger.error(f"Ошибка удаления списка пользователей: {e}")
            print(f"❌ Ошибка: {e}")
            return "error"

    def _validate_users_list(self, users: List[str]) -> bool:
        """Валидация списка пользователей"""
        if not users:
            print("❌ Список пользователей не может быть пустым")
            return False

        invalid_users = []
        seen_users = set()

        for user in users:
            # Проверка формата
            if '@' not in user:
                invalid_users.append(user)
                continue

            # Проверка дубликатов
            if user.lower() in (u.lower() for u in seen_users):
                print(f"⚠️  Пользователь '{user}' уже есть в списке")
                invalid_users.append(user)
                continue

            seen_users.add(user)

            # Проверка корректности домена
            username, domain = user.split('@', 1)
            if not username or not domain:
                invalid_users.append(user)
                continue

        if invalid_users:
            print(f"❌ Найдены некорректные пользователи: {', '.join(invalid_users)}")
            return False

        return True

    def _save_users_list(self, list_name: str, users: List[str]) -> bool:
        """Сохранить список пользователей"""
        try:
            config = {'users': users}
            file_path = os.path.join(self.CONFIG_DIR, f"users_{list_name}.yml")
            return self._save_yaml_file(file_path, config)
        except Exception as e:
            self.logger.error(f"Ошибка сохранения списка пользователей {list_name}: {e}")
            return False

    def _load_users_list(self, list_name: str) -> List[str]:
        """Загрузить список пользователей"""
        try:
            file_path = os.path.join(self.CONFIG_DIR, f"users_{list_name}.yml")
            config = self._load_yaml_file(file_path)
            if config and 'users' in config:
                return config['users']
            return []
        except Exception as e:
            self.logger.error(f"Ошибка загрузки списка пользователей {list_name}: {e}")
            return []

    def _get_users_lists(self) -> List[str]:
        """Получить список доступных списков пользователей"""
        try:
            if not os.path.exists(self.CONFIG_DIR):
                return []

            lists = []
            for file in os.listdir(self.CONFIG_DIR):
                if file.startswith('users_') and file.endswith('.yml'):
                    list_name = file[6:-4]  # Убрать префикс 'users_' и суффикс '.yml'
                    lists.append(list_name)
            return sorted(lists)
        except Exception as e:
            self.logger.error(f"Ошибка получения списка пользователей: {e}")
            return []

    def _list_exists(self, list_name: str) -> bool:
        """Проверить существование списка"""
        file_path = os.path.join(self.CONFIG_DIR, f"users_{list_name}.yml")
        return os.path.exists(file_path)

    def _delete_users_list_file(self, list_name: str) -> bool:
        """Удалить файл списка пользователей"""
        try:
            file_path = os.path.join(self.CONFIG_DIR, f"users_{list_name}.yml")
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Ошибка удаления файла списка пользователей {list_name}: {e}")
            return False

    def _load_yaml_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Загрузить YAML файл"""
        try:
            if not os.path.exists(file_path):
                return None

            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                if not content.strip():
                    return None

                data = yaml_module.safe_load(content)
                return data if data is not None else None

        except yaml_module.YAMLError as e:
            self.logger.error(f"Ошибка парсинга YAML файла {file_path}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Ошибка чтения файла {file_path}: {e}")
            return None

    def _show_creation_preview(self, list_name: str, users: List[str]) -> None:
        """Показать превью перед созданием списка пользователей"""
        print(f"\n📋 Превью списка '{list_name}' ({len(users)} пользователей):")
        print("-" * 50)

        # Показать первых 5 пользователей
        max_preview = min(5, len(users))
        for i, user in enumerate(users[:max_preview], 1):
            print(f"  {i}. {user}")

        if len(users) > max_preview:
            print(f"  ... и еще {len(users) - max_preview} пользователей")

        print("-" * 50)

    def _show_import_success_message(self, list_name: str, users: List[str]) -> None:
        """Показать сообщение об успешном импорте пользователей"""
        print(f"\n✅ Список пользователей '{list_name}' успешно создан!")
        print("=" * 60)
        print(f"📊 Всего пользователей: {len(users)}")
        print("\n👥 Список импортированных пользователей:")
        print("-" * 40)

        # Показать всех пользователей с нумерацией
        for i, user in enumerate(users, 1):
            print(f"  {i:2d}. {user}")

        print("-" * 40)
        input("\nДля продолжения нажмите Enter...")

    def _save_yaml_file(self, file_path: str, data: Dict[str, Any]) -> bool:
        """Сохранить данные в YAML файл"""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as file:
                yaml_module.dump(
                    data,
                    file,
                    default_flow_style=False,
                    allow_unicode=True
                )

            return True

        except Exception as e:
            self.logger.error(f"Ошибка сохранения файла {file_path}: {e}")
            return False
