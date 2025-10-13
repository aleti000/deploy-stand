#!/usr/bin/env python3
"""
Меню управления подключениями
Управление подключениями к Proxmox кластерам
"""

from ..utils import Logger, ConfigValidator
import os
import yaml as yaml_module
from typing import Dict, List, Any, Optional


class ConnectionsMenu:
    """Меню управления подключениями"""

    CONNECTIONS_DIR = "data"
    CONNECTIONS_FILE = "data/connections_config.yml"

    def __init__(self, logger_instance):
        self.logger = logger_instance
        self.validator = ConfigValidator()
        self._ensure_directories()

    def _ensure_directories(self):
        """Создать необходимые директории если они не существуют"""
        try:
            os.makedirs(self.CONNECTIONS_DIR, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Ошибка создания директории: {e}")

    def show(self) -> str:
        """Показать меню управления подключениями"""
        print("\n🔌 Управление подключениями")
        print("=" * 50)

        # Показать сохраненные подключения
        saved_connections = self._get_saved_connections()

        if saved_connections:
            print("📋 Сохраненные подключения:")
            for i, conn in enumerate(saved_connections, 1):
                name = conn.get('name', 'без имени')
                host = conn.get('host', 'не указан')
                print(f"  [{i}] {name} - {host}")
            print()

        print("Доступные действия:")
        print("  [1] Создать новое подключение")
        print("  [2] Выбрать активное подключение")
        print("  [3] Показать сохраненные подключения")
        print("  [4] Протестировать подключение")
        print("  [5] Удалить подключение")
        print("  [0] Назад")

        choice = input("Выберите действие: ").strip()

        if choice == "1":
            result = self._create_connection()
            return result
        elif choice == "2":
            result = self._select_active_connection(saved_connections)
            return result
        elif choice == "3":
            result = self._show_connections(saved_connections)
            return result
        elif choice == "4":
            result = self._test_connection()
            return result
        elif choice == "5":
            result = self._delete_connection(saved_connections)
            return result
        elif choice == "0":
            return "back"
        else:
            print("❌ Неверный выбор!")
            return "repeat"

    def _get_saved_connections(self) -> list:
        """Получить список сохраненных подключений"""
        try:
            connections_data = self._load_yaml_file(self.CONNECTIONS_FILE) or {}
            # Преобразовать в список для совместимости с интерфейсом и добавить поле 'name'
            connections = []
            for name, config in connections_data.items():
                config['name'] = name
                connections.append(config)
            return connections
        except Exception as e:
            self.logger.error(f"Ошибка получения списка подключений: {e}")
            return []

    def _create_connection(self) -> str:
        """Создать новое подключение через Proxmox API"""
        print("\n➕ Создание нового подключения к Proxmox")
        print("-" * 40)

        try:
            # Сбор данных подключения к Proxmox API
            name = input("Имя подключения: ").strip()
            host = input("Адрес Proxmox сервера (например, 192.168.1.100): ").strip()
            port = input("API порт (по умолчанию 8006): ").strip() or "8006"
            username = input("Имя пользователя API (по умолчанию, root@pam): ").strip() or "root@pam"
            password = input("Пароль API пользователя: ").strip()

            # Валидация
            if not all([name, host, username, password]):
                print("❌ Все поля обязательны для подключения к Proxmox API!")
                return "repeat"

            # Создание полного URL для API
            api_host = f"{host}:{port}"

            # Создание подключения
            new_connection = {
                'name': name,
                'host': api_host,
                'username': username,
                'password': password
            }

            # TODO: Сохранить подключение в persistent storage

            # Тестирование подключения
            print("🔍 Тестирование подключения к Proxmox API...")
            from ..utils import ProxmoxClient
            client = ProxmoxClient(api_host, username, password)
            if client.connect():
                nodes = client.get_nodes()
                print("✅ Подключение успешно! Обнаружено нод:")
                print(f"   {', '.join(nodes) if nodes else 'ноды не найдены'}")

                # Предложить сохранить конфигурацию
                save_confirm = input("💾 Сохранить эту конфигурацию подключения? (Y/n): ").strip().lower()
                if save_confirm in ['', 'y', 'yes']:
                    # Сохранить подключение подобно create_connection_config из старого проекта
                    try:
                        connections = self._load_yaml_file(self.CONNECTIONS_FILE) or {}

                        connection_config = {
                            'host': api_host,
                            'user': username,
                            'password': password,
                            'use_token': False  # Пока только парольная аутентификация
                        }

                        connections[name] = connection_config

                        success = self._save_yaml_file(self.CONNECTIONS_FILE, connections)
                        if success:
                            print("✅ Конфигурация подключения сохранена")
                        else:
                            print("❌ Ошибка сохранения конфигурации")
                    except Exception as e:
                        self.logger.error(f"Ошибка сохранения подключения: {e}")
                        print(f"❌ Ошибка сохранения: {e}")
                else:
                    print("ℹ️  Конфигурация не сохранена")

                return "success"
            else:
                print("❌ Не удалось подключиться к Proxmox API")
                return "error"

        except ValueError as e:
            print(f"❌ Ошибка валидации: {e}")
            return "error"
        except Exception as e:
            self.logger.error(f"Ошибка при создании подключения: {e}")
            print(f"❌ Ошибка: {e}")
            return "error"

    def _select_active_connection(self, connections: list) -> str:
        """Выбрать активное подключение"""
        if not connections:
            print("❌ Нет сохраненных подключений")
            return "repeat"

        print("\n🎯 Выбор активного подключения")

        try:
            choice = input(f"Выберите подключение (1-{len(connections)}) или 0 для отмены: ").strip()

            if choice == "0":
                return "repeat"
            elif not choice.isdigit() or int(choice) - 1 not in range(len(connections)):
                print("❌ Неверный номер подключения")
                return "repeat"

            selected = connections[int(choice) - 1]
            # TODO: Установить как активное
            print(f"✅ Выбрано активное подключение: {selected['name']}")
            return "success"

        except Exception as e:
            self.logger.error(f"Ошибка при выборе подключения: {e}")
            print(f"❌ Ошибка: {e}")
            return "error"

    def _show_connections(self, connections: list) -> str:
        """Показать все сохраненные подключения"""
        print("\n📋 Сохраненные подключения:")
        print("-" * 40)

        if not connections:
            print("ℹ️  Нет сохраненных подключений")
        else:
            for i, conn in enumerate(connections, 1):
                print(f"{i}. {conn.get('name', f'Подключение {i}')}")
                print(f"   📍 {conn.get('host', 'не указан')}")
                print(f"   👤 {conn.get('user', 'не указан')}")
                print()

        input("Нажмите Enter для продолжения...")
        return "repeat"

    def _test_connection(self) -> str:
        """Протестировать подключение"""
        print("\n🔍 Тестирование подключения")
        print("-" * 30)
        print("Функция будет реализована в следующих обновлениях")
        input("Нажмите Enter для продолжения...")
        return "repeat"

    def _delete_connection(self, connections: list) -> str:
        """Удалить подключение"""
        if not connections:
            print("❌ Нет подключений для удаления")
            return "repeat"

        print("\n🗑️  Удаление подключения")

        try:
            choice = input(f"Выберите подключение для удаления (1-{len(connections)}) или 0 для отмены: ").strip()

            if choice == "0":
                return "repeat"
            elif not choice.isdigit() or int(choice) - 1 not in range(len(connections)):
                print("❌ Неверный номер подключения")
                return "repeat"

            conn_to_delete = connections[int(choice) - 1]
            confirm = input(f"Удалить подключение '{conn_to_delete['name']}'? (y/N): ").strip().lower()

            if confirm == 'y':
                # Удалить подключение из файла хранения (подобно delete_connection_config)
                try:
                    connections_data = self._load_yaml_file(self.CONNECTIONS_FILE) or {}

                    # Найти имя подключения для удаления
                    conn_name_to_delete = None
                    for name, config in connections_data.items():
                        if config.get('name') == conn_to_delete.get('name'):
                            conn_name_to_delete = name
                            break

                    if conn_name_to_delete:
                        del connections_data[conn_name_to_delete]
                        success = self._save_yaml_file(self.CONNECTIONS_FILE, connections_data)
                        if success:
                            print(f"✅ Подключение '{conn_to_delete['name']}' удалено")
                            return "success"
                        else:
                            print("❌ Ошибка сохранения после удаления")
                            return "error"
                    else:
                        print("❌ Подключение не найдено для удаления")
                        return "error"
                except Exception as e:
                    self.logger.error(f"Ошибка удаления из файла: {e}")
                    print(f"❌ Ошибка удаления: {e}")
                    return "error"
            else:
                print("Отмена удаления")
                return "repeat"
        except Exception as e:
            self.logger.error(f"Ошибка при удалении подключения: {e}")
            print(f"❌ Ошибка: {e}")
            return "error"

    def _load_yaml_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Загрузить YAML файл

        Args:
            file_path: Путь к файлу

        Returns:
            Словарь с данными или None при ошибке
        """
        try:
            if not os.path.exists(file_path):
                return {}

            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                if not content.strip():
                    return {}

                data = yaml_module.safe_load(content)
                return data if data is not None else {}

        except yaml_module.YAMLError as e:
            self.logger.error(f"Ошибка парсинга YAML файла {file_path}: {e}")
            return {}
        except Exception as e:
            self.logger.error(f"Ошибка чтения файла {file_path}: {e}")
            return {}

    def _save_yaml_file(self, file_path: str, data: Dict[str, Any]) -> bool:
        """
        Сохранить данные в YAML файл

        Args:
            file_path: Путь к файлу
            data: Данные для сохранения

        Returns:
            True если сохранение успешно
        """
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as file:
                yaml_module.dump(
                    data,
                    file,
                    default_flow_style=False,
                    allow_unicode=True
                )

            self.logger.info(f"Данные сохранены в {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"Ошибка сохранения файла {file_path}: {e}")
            return False
