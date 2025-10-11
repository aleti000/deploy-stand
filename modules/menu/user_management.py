#!/usr/bin/env python3
"""
Модуль управления пользователями
Отдельный модуль для работы со списками пользователей
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from .base_menu import BaseMenu
from ..user_list_manager import get_user_list_manager

logger = logging.getLogger(__name__)


class UserManagementMenu(BaseMenu):
    """Меню управления списками пользователей"""

    def __init__(self):
        super().__init__()
        self.user_list_manager = get_user_list_manager()

    async def show_menu(self):
        """Отображение меню управления пользователями"""
        self.clear_screen()

        print("\n" + "="*50)
        print("УПРАВЛЕНИЕ СПИСКАМИ ПОЛЬЗОВАТЕЛЕЙ")
        print("="*50)
        print("1. Ввести список пользователей (через запятую)")
        print("2. Импорт из списка")
        print("3. Вывести существующие списки")
        print("4. Удалить список пользователей")
        print("0. Назад в главное меню")
        print("-"*50)

    async def handle_choice(self, choice: str) -> bool:
        """Обработка выбора пользователя"""
        if choice == "0":
            print("Возврат в главное меню...")
            return False

        elif choice == "1":
            await self.create_user_list_interactive()
        elif choice == "2":
            await self.import_user_list_interactive()
        elif choice == "3":
            await self.show_user_lists()
            await self.show_message("", pause=True)
        elif choice == "4":
            await self.delete_user_list_interactive()
        else:
            print("Неверный выбор. Попробуйте еще раз.")

        return True

    async def create_user_list_interactive(self):
        """Интерактивное создание списка пользователей"""
        self.clear_screen()

        print("\n📝 Создание нового списка пользователей")
        print("Введите пользователей через запятую (например: user1, user2, user3)")
        print("Если пользователь указан без @pve, он будет добавлен автоматически")

        # Ввод имени списка
        list_name = await self.get_user_input("Введите имя списка пользователей: ")
        if not list_name:
            return

        # Ввод пользователей
        users_input = await self.get_user_input("Введите пользователей через запятую: ")
        if not users_input:
            print("❌ Список пользователей не может быть пустым")
            return

        # Парсинг пользователей
        users = self.user_list_manager.parse_user_input(users_input)
        if not users:
            print("❌ Не удалось распознать пользователей")
            return

        # Ввод описания
        description = await self.get_user_input("Описание списка (необязательно): ", required=False)

        # Создание списка
        if self.user_list_manager.create_user_list(list_name, users, description):
            print(f"✅ Список '{list_name}' создан с {len(users)} пользователями")
        else:
            print(f"❌ Ошибка создания списка '{list_name}'")
            return

        # Показываем обновленное меню
        await self.show_menu()

    async def import_user_list_interactive(self):
        """Интерактивный импорт списка пользователей"""
        self.clear_screen()

        print("\n📥 Импорт списка пользователей из файла")
        print("Файл должен содержать пользователей (по одному на строку)")
        print("Строки начинающиеся с # считаются комментариями")
        print("Если пользователь указан без @pve, он будет добавлен автоматически")

        # Ввод имени списка
        list_name = await self.get_user_input("Введите имя нового списка: ")
        if not list_name:
            return

        # Ввод пути к файлу
        file_path = await self.get_user_input("Введите путь к файлу со списком пользователей: ")
        if not file_path:
            print("❌ Путь к файлу не может быть пустым")
            return

        # Проверка существования файла
        if not Path(file_path).exists():
            print(f"❌ Файл '{file_path}' не найден")
            return

        # Ввод описания
        description = await self.get_user_input("Описание списка (необязательно): ", required=False)

        # Импорт списка из файла
        if self.user_list_manager.import_user_list_from_file(list_name, file_path, description):
            print(f"✅ Список '{list_name}' импортирован из файла '{file_path}'")
        else:
            print(f"❌ Ошибка импорта списка '{list_name}' из файла '{file_path}'")

    async def show_user_lists(self):
        """Показать все списки пользователей"""
        self.clear_screen()

        print("\n📋 Существующие списки пользователей:")

        user_lists = self.user_list_manager.get_user_lists()

        if not user_lists:
            print("📭 Нет созданных списков пользователей")
            return

        for list_name, list_data in user_lists.items():
            print(f"\n📁 {list_name}")
            print(f"   Описание: {list_data.get('description', 'Без описания')}")
            print(f"   Количество пользователей: {list_data.get('count', 0)}")

            users = list_data.get('users', [])
            if users:
                print("   Пользователи:")
                for i, user in enumerate(users[:5], 1):  # Показываем первых 5
                    print(f"     {i}. {user}")
                if len(users) > 5:
                    print(f"     ... и еще {len(users) - 5} пользователей")

    async def delete_user_list_interactive(self):
        """Интерактивное удаление списка пользователей"""
        self.clear_screen()

        print("\n🗑️  Удаление списка пользователей")

        # Показываем доступные списки
        list_names = self.user_list_manager.get_user_list_names()
        if not list_names:
            print("❌ Нет списков пользователей для удаления")
            return

        print("\nДоступные списки пользователей:")
        for i, list_name in enumerate(list_names, 1):
            print(f"{i}. {list_name}")

        while True:
            choice = await self.get_user_input("Выберите список для удаления (номер) или 0 для отмены: ")

            if choice == "0":
                print("Операция отменена")
                await self.show_menu()
                return

            try:
                list_index = int(choice) - 1
                if 0 <= list_index < len(list_names):
                    list_to_delete = list_names[list_index]

                    # Подтверждение удаления
                    confirm = await self.get_user_input(
                        f"Вы уверены, что хотите удалить список '{list_to_delete}'? (y/n): ",
                        required=False, default="n"
                    )

                    if confirm.lower() in ['y', 'yes', 'да', 'д']:
                        if self.user_list_manager.delete_user_list(list_to_delete):
                            print(f"✅ Список '{list_to_delete}' успешно удален")
                        else:
                            print(f"❌ Ошибка при удалении списка '{list_to_delete}'")
                    else:
                        print("Операция отменена")

                    await self.show_menu()
                    return
                else:
                    print(f"❌ Выберите номер от 1 до {len(list_names)}")
            except ValueError:
                print("❌ Введите номер списка или 0 для отмены")


def get_user_management_menu() -> UserManagementMenu:
    """Функция для получения экземпляра меню управления пользователями"""
    return UserManagementMenu()
