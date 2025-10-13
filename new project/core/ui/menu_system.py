#!/usr/bin/env python3
"""
Система главного меню пользовательского интерфейса для нового проекта
Реструктурированная версия с разделением на подменю
"""

import logging
import os
import yaml as yaml_module
from typing import Dict, List, Any, Optional

from .stand_config_menu import StandConfigMenu
from .user_list_menu import UserListMenu
from .stand_deploy_menu import StandDeployMenu
from .delete_stand_menu import DeleteStandMenu
from .connections_menu import ConnectionsMenu


class MainMenu:
    """Главное меню системы Deploy-Stand"""

    def __init__(self, logger_instance: logging.Logger):
        """
        Инициализация главного меню

        Args:
            logger_instance: Экземпляр логгера
        """
        self.logger = logger_instance
        self.current_connection = None  # Активное подключение

        # Инициализация подменю
        self.stand_config_menu = StandConfigMenu(logger_instance)
        self.user_list_menu = UserListMenu(logger_instance)
        self.stand_deploy_menu = StandDeployMenu(logger_instance)
        self.delete_stand_menu = DeleteStandMenu(logger_instance)
        self.connections_menu = ConnectionsMenu(logger_instance)

    def show(self) -> None:
        """Показать главное меню"""
        # ПЕРВЫМ ДЕЛОМ - НАСТРОЙКА ПОДКЛЮЧЕНИЯ
        if not self._ensure_connection():
            print("❌ Невозможно продолжить без подключения")
            return

        # Быстрый доступ к часто используемым функциям
        quick_actions = {
            'd': '3',  # d = deploy (развернуть)
            'c': '1',  # c = create config (создать конфигурацию)
            'u': '2',  # u = users (пользователи)
            'x': '4',  # x = cleanup (очистка)
            'n': '5',  # n = connections (подключения)
        }

        while True:
            try:
                # Очистка экрана перед показом меню
                os.system('clear')

                # Показать текущее подключение
                current_connection = self._get_current_connection_info()

                # Оптимизированное отображение меню с горячими клавишами
                print("🚀 Deploy-Stand - Главное меню")
                print("=" * 50)
                print(f"🔌 Текущее подключение: {current_connection}")
                print("=" * 50)
                print("📋 Основные функции:")
                print("  [1] 🛠️  Управление конфигурациями стендов")
                print("  [2] 👥 Управление пользователями")
                print("  [3] 🚀 Развернуть стенд")
                print("  [4] 🗑️  Удалить стенды")
                print("  [5] 🔌 Управление подключениями")
                print("  [0] Выход")
                print("\n⚡ Быстрые команды:")
                print("  c = Конфиги | u = Пользователи | d = Развернуть | x = Очистка | n = Подключения")

                # Оптимизированный ввод с поддержкой быстрых команд
                choice = input("\nВыберите действие: ").strip().lower()

                # Обработка быстрых команд
                if choice in quick_actions:
                    choice = quick_actions[choice]

                # Обработка выбора с улучшенной навигацией
                action_result = self._handle_menu_choice(choice)
                if action_result == "exit":
                    break
                elif action_result == "repeat":
                    continue

            except KeyboardInterrupt:
                print("\n\n👋 До свидания!")
                break
            except Exception as e:
                self.logger.error(f"Ошибка в главном меню: {e}")
                print(f"❌ Ошибка: {e}")
                input("Нажмите Enter для продолжения...")

    def _handle_menu_choice(self, choice: str) -> str:
        """Централизованная обработка выбора меню с переходом к подменю"""
        menu_actions = {
            "1": lambda: self.stand_config_menu.show(),
            "2": lambda: self.user_list_menu.show(),
            "3": lambda: self.stand_deploy_menu.show(),
            "4": lambda: self.delete_stand_menu.show(),
            "5": lambda: self.connections_menu.show(),
            "0": lambda: "exit"
        }

        action = menu_actions.get(choice)
        if action:
            try:
                result = action() if callable(action) else action
                return result if result != "back" else "repeat"
            except Exception as e:
                self.logger.error(f"Ошибка выполнения действия {choice}: {e}")
                print(f"❌ Ошибка: {e}")
                return "repeat"
        else:
            print("❌ Неверный выбор! Используйте цифры 0-5 или быстрые команды (c, u, d, x, n)")
            return "repeat"

    def _ensure_connection(self) -> bool:
        """Обеспечить наличие подключения"""
        try:
            # Получить список доступных подключений
            available_connections = self.connections_menu._get_saved_connections()

            if available_connections:
                print("✅ Доступные подключения:")
                for i, conn in enumerate(available_connections, 1):
                    print(f"  [{i}] {conn['name']} - {conn.get('host', 'не указан')}")

                while True:
                    choice = input(f"Выберите подключение (1-{len(available_connections)}) или [n] для создания нового: ").strip().lower()

                    if choice == 'n':
                        result = self.connections_menu._create_connection()
                        if result == "success":
                            # После создания загрузить новые подключения
                            updated_connections = self.connections_menu._get_saved_connections()
                            if updated_connections:
                                self.current_connection = updated_connections[-1]
                                # Установить глобальное
                                try:
                                    from main import set_current_connection
                                    set_current_connection(self.current_connection)
                                except ImportError:
                                    pass
                        return result == "success"

                    elif choice.isdigit():
                        idx = int(choice) - 1
                        if 0 <= idx < len(available_connections):
                            self.current_connection = available_connections[idx]
                            try:
                                from main import set_current_connection
                                set_current_connection(self.current_connection)
                            except ImportError:
                                pass
                            print(f"✅ Выбрано подключение: {self.current_connection['name']}")
                            return True
                        else:
                            print(f"❌ Введите число от 1 до {len(available_connections)}")
                    elif choice == "0":
                        return False
                    else:
                        print("❌ Неверный ввод")

            else:
                print("ℹ️  Сохраненные подключения не найдены. Необходимо создать новое...")
                result = self.connections_menu._create_connection()
                return result == "success"

        except Exception as e:
            self.logger.error(f"Ошибка проверки подключений: {e}")
            print(f"❌ Ошибка: {e}")
            return False

    def _get_current_connection_info(self) -> str:
        """Получить информацию о текущем подключении"""
        if self.current_connection:
            name = self.current_connection.get('name', 'неизвестно')
            host = self.current_connection.get('host', 'не указан')
            return f"{name} ({host})"
        return "Не подключен"
