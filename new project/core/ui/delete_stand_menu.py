#!/usr/bin/env python3
"""
Меню удаления стендов
Отвечает за удаление стендов пользователей целиком
"""

import os
import logging
from typing import Dict, List, Any, Optional, Tuple

from ..utils import Logger, UserManager, PoolManager, VMManager, NetworkManager, ConfigValidator, OtherUtils


class DeleteStandMenu:
    """Меню удаления стендов пользователей"""

    def __init__(self, logger_instance):
        self.logger = logger_instance
        self.validator = ConfigValidator()
        self.other_utils = OtherUtils()

        # Инициализация менеджеров (будут установлены при вызове show)
        self.user_manager = None
        self.pool_manager = None
        self.vm_manager = None
        self.network_manager = None

        # Загружаем списки пользователей
        self._user_lists_dir = "data"

    def show(self) -> str:
        """Показать меню удаления стендов"""
        print("\n🗑️  Удаление стендов")
        print("=" * 50)

        # Инициализация менеджеров с текущим подключением
        try:
            # Импортируем функцию получения текущего клиента
            try:
                from main import get_current_proxmox_client
                proxmox_client = get_current_proxmox_client()
            except ImportError:
                # Fallback: пытаемся получить из глобального контекста
                try:
                    import sys
                    main_module = sys.modules.get('main') or sys.modules.get('__main__')
                    if hasattr(main_module, 'current_connection'):
                        # Создаем клиент на основе текущего подключения
                        from ..utils.connection_manager import ConnectionManager
                        from ..utils.proxmox_client import ProxmoxClient
                        conn_manager = ConnectionManager()
                        connections = conn_manager.load_connections()
                        if connections:
                            # Используем первое доступное подключение
                            conn_data = list(connections.values())[0]
                            proxmox_client = ProxmoxClient(
                                host=conn_data['host'],
                                user=conn_data['user'],
                                password=conn_data.get('password'),
                                token_name=conn_data.get('token_name'),
                                token_value=conn_data.get('token_value')
                            )
                        else:
                            proxmox_client = None
                    else:
                        proxmox_client = None
                except Exception:
                    proxmox_client = None

            if not proxmox_client:
                print("❌ Нет активного подключения к Proxmox")
                return "back"

            self.user_manager = UserManager(proxmox_client)
            self.pool_manager = PoolManager(proxmox_client)
            self.vm_manager = VMManager(proxmox_client)
            self.network_manager = NetworkManager(proxmox_client)

        except Exception as e:
            self.logger.error(f"Ошибка инициализации менеджеров: {e}")
            print(f"❌ Ошибка инициализации: {e}")
            return "back"

        print("Доступные действия:")
        print("  [1] Удалить стенды пользователей по списку")
        print("  [2] Удалить стенд отдельного пользователя")
        print("  [0] Назад")

        choice = input("Выберите действие: ").strip()

        if choice == "1":
            result = self._delete_stands_by_list()
            return result
        elif choice == "2":
            result = self._delete_single_user_stand()
            return result
        elif choice == "0":
            return "back"
        else:
            print("❌ Неверный выбор!")
            return "repeat"

    def _delete_stands_by_list(self) -> str:
        """Удалить стенды пользователей по списку"""
        print("\n📋 Удаление стендов по списку пользователей")
        print("-" * 50)

        try:
            # Получить список доступных списков пользователей
            lists = self._get_user_lists()
            if not lists:
                print("ℹ️  Нет сохраненных списков пользователей")
                input("\nНажмите Enter для продолжения...")
                return "repeat"

            print("Доступные списки пользователей:")
            for i, list_name in enumerate(lists, 1):
                users = self._load_user_list(list_name)
                print(f"  [{i}] {list_name} ({len(users)} пользователей)")

            # Выбор списка
            while True:
                choice_input = input(f"Выберите список (1-{len(lists)}) или 0 для отмены: ").strip()
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
            users = self._load_user_list(list_name)

            # Показать превью списка
            self._show_deletion_preview(list_name, users)

            # Подтверждение удаления
            confirm = input(f"\nУдалить стенды для {len(users)} пользователей из списка '{list_name}'? (y/N): ").strip().lower()
            if confirm != 'y':
                print("ℹ️  Удаление отменено")
                return "repeat"

            # Запуск удаления
            return self._execute_batch_deletion(users, list_name)

        except Exception as e:
            self.logger.error(f"Ошибка удаления стендов по списку: {e}")
            print(f"❌ Ошибка: {e}")
            return "error"

    def _delete_single_user_stand(self) -> str:
        """Удалить стенд отдельного пользователя"""
        print("\n👤 Удаление стенда отдельного пользователя")
        print("-" * 50)

        try:
            # Получить список всех пользователей (из всех пулов)
            all_users = self._get_all_users()

            if not all_users:
                print("ℹ️  Не найдено пользователей с пулами")
                input("\nНажмите Enter для продолжения...")
                return "repeat"

            print("Найденные пользователи:")
            for i, user_info in enumerate(all_users, 1):
                user_name = user_info['user']
                pool_name = user_info['pool']
                vm_count = user_info['vm_count']
                print(f"  [{i}] {user_name} (пул: {pool_name}, VM: {vm_count})")

            # Выбор пользователя
            while True:
                choice_input = input(f"Выберите пользователя (1-{len(all_users)}) или 0 для отмены: ").strip()
                if choice_input == "0":
                    return "repeat"
                try:
                    choice = int(choice_input) - 1
                    if 0 <= choice < len(all_users):
                        break
                    else:
                        print(f"❌ Выберите число от 1 до {len(all_users)}")
                except ValueError:
                    print("❌ Введите корректное число!")

            selected_user = all_users[choice]

            # Показать детали пользователя
            self._show_user_deletion_preview(selected_user)

            # Подтверждение удаления
            user_name = selected_user['user']
            confirm = input(f"\nУдалить стенд пользователя '{user_name}'? (y/N): ").strip().lower()
            if confirm != 'y':
                print("ℹ️  Удаление отменено")
                return "repeat"

            # Запуск удаления для одного пользователя
            users = [user_name]
            return self._execute_batch_deletion(users, f"одиночный пользователь: {user_name}")

        except Exception as e:
            self.logger.error(f"Ошибка удаления стенда пользователя: {e}")
            print(f"❌ Ошибка: {e}")
            return "error"

    def _execute_batch_deletion(self, users: List[str], operation_name: str) -> str:
        """Выполнить пакетное удаление стендов"""
        print(f"\n🚀 Начинаем удаление стендов ({operation_name})")
        print("=" * 60)

        total_users = len(users)
        successful_deletions = 0
        failed_deletions = []

        for i, user in enumerate(users, 1):
            print(f"\n[{i}/{total_users}] Обработка пользователя: {user}")
            print("-" * 40)

            try:
                if self._delete_user_stand(user):
                    successful_deletions += 1
                    print(f"✅ Стенд пользователя {user} успешно удален")
                else:
                    failed_deletions.append(user)
                    print(f"❌ Не удалось удалить стенд пользователя {user}")
            except Exception as e:
                failed_deletions.append(user)
                print(f"❌ Ошибка удаления стенда {user}: {e}")
                self.logger.error(f"Ошибка удаления стенда пользователя {user}: {e}")

        # Итоговый отчет
        print(f"\n📊 Итоги удаления ({operation_name}):")
        print("=" * 60)
        print(f"Всего пользователей: {total_users}")
        print(f"Успешно удалено: {successful_deletions}")
        print(f"Ошибок: {len(failed_deletions)}")

        if failed_deletions:
            print("Не удалось удалить стенды пользователей:")
            for user in failed_deletions:
                print(f"  ❌ {user}")

        input("\nНажмите Enter для продолжения...")
        return "success"

    def _delete_user_stand(self, user: str) -> bool:
        """
        Удалить стенд пользователя по алгоритму:
        1. Найти пользователя, определить пул
        2. Найти все машины в этом пуле
        3. Найти все сетевые интерфейсы которые подключены к ВМ
        4. Удалить сетевые интерфейсы, удалить вм
        5. Когда все сетевые интерфейсы и все вм удалены - удалить пул и пользователя
        """
        try:
            logger.info(f"Начинаем удаление стенда пользователя {user}")

            # ШАГ 1: Определить пул пользователя
            pool_name = self.pool_manager.extract_pool_name(user)
            logger.info(f"Пользователь {user} принадлежит пулу {pool_name}")

            # Проверить существование пула
            if not self.pool_manager.pool_exists(pool_name):
                logger.warning(f"Пул {pool_name} не существует")
                # Если пула нет, но пользователь существует - удаляем только пользователя
                return self._delete_user_only(user)

            # ШАГ 2: Получить все VM в пуле
            pool_vms = self.pool_manager.get_pool_vms(pool_name)
            if not pool_vms:
                logger.info(f"В пуле {pool_name} нет виртуальных машин")
                # Нет VM, удаляем пул и пользователя
                return self._delete_pool_and_user(pool_name, user)

            logger.info(f"Найдено {len(pool_vms)} VM в пуле {pool_name}")

            # ШАГ 3-4: Удалить все VM и их сетевые интерфейсы
            deleted_vms = 0
            for vm_info in pool_vms:
                vmid = vm_info.get('vmid')
                node = vm_info.get('node')

                if vmid and node:
                    # ШАГ 3: Найти сетевые интерфейсы VM
                    network_interfaces = self._get_vm_network_interfaces(node, vmid)

                    # ШАГ 4: Удалить сетевые интерфейсы (в Proxmox это происходит при удалении VM)
                    # Удаляем VM целиком
                    if self.vm_manager.delete_vm(node, vmid):
                        logger.info(f"VM {vmid} пользователя {user} удалена")
                        deleted_vms += 1

                        # Ждем завершения операции
                        task_up = False
                        try:
                            task_up = self.other_utils.wait_for_task_completion("", node, timeout=60)
                        except:
                            pass

                        if not task_up:
                            logger.warning(f"Не удалось дождаться завершения удаления VM {vmid}")
                    else:
                        logger.error(f"Не удалось удалить VM {vmid} пользователя {user}")
                        return False

            logger.info(f"Удалено VM пользователя {user}: {deleted_vms}/{len(pool_vms)}")

            # ШАГ 5: Когда все VM удалены - удалить пул и пользователя
            return self._delete_pool_and_user(pool_name, user)

        except Exception as e:
            logger.error(f"Ошибка удаления стенда пользователя {user}: {e}")
            return False

    def _get_vm_network_interfaces(self, node: str, vmid: int) -> List[str]:
        """Получить список сетевых интерфейсов VM"""
        try:
            network_info = self.network_manager.get_network_info(node, vmid)
            interfaces = [net_id for net_id in network_info.keys() if net_id.startswith('net')]
            logger.debug(f"VM {vmid} имеет сетевые интерфейсы: {interfaces}")
            return interfaces
        except Exception as e:
            logger.error(f"Ошибка получения сетевых интерфейсов VM {vmid}: {e}")
            return []

    def _delete_pool_and_user(self, pool_name: str, user: str) -> bool:
        """Удалить пул и пользователя"""
        try:
            success = True

            # Удалить пул
            if self.pool_manager.delete_pool(pool_name):
                logger.info(f"Пул {pool_name} удален")
            else:
                logger.error(f"Не удалось удалить пул {pool_name}")
                success = False

            # Удалить пользователя
            if self.user_manager.delete_user(user):
                logger.info(f"Пользователь {user} удален")
            else:
                logger.error(f"Не удалось удалить пользователя {user}")
                success = False

            return success

        except Exception as e:
            logger.error(f"Ошибка удаления пула {pool_name} и пользователя {user}: {e}")
            return False

    def _delete_user_only(self, user: str) -> bool:
        """Удалить только пользователя (если пула нет)"""
        try:
            if self.user_manager.delete_user(user):
                logger.info(f"Пользователь {user} удален")
                return True
            else:
                logger.error(f"Не удалось удалить пользователя {user}")
                return False
        except Exception as e:
            logger.error(f"Ошибка удаления пользователя {user}: {e}")
            return False

    def _get_all_users(self) -> List[Dict[str, Any]]:
        """Получить список всех пользователей с пулами"""
        try:
            users_info = []

            # Получить все пулы
            pools = self.pool_manager.list_pools()

            for pool_name in pools:
                pool_vms = self.pool_manager.get_pool_vms(pool_name)
                vm_count = len(pool_vms)

                # Извлечь имя пользователя из пула
                user_name = self.user_manager.extract_user_name(pool_name)

                users_info.append({
                    'user': f"{user_name}@pve",
                    'pool': pool_name,
                    'vm_count': vm_count
                })

            # Сортировать по имени пользователя
            users_info.sort(key=lambda x: x['user'])
            return users_info

        except Exception as e:
            self.logger.error(f"Ошибка получения списка пользователей: {e}")
            return []

    def _get_user_lists(self) -> List[str]:
        """Получить список доступных списков пользователей"""
        try:
            if not os.path.exists(self._user_lists_dir):
                return []

            lists = []
            for file in os.listdir(self._user_lists_dir):
                if file.startswith('users_') and file.endswith('.yml'):
                    list_name = file[6:-4]  # Убрать префикс 'users_' и суффикс '.yml'
                    lists.append(list_name)
            return sorted(lists)
        except Exception as e:
            self.logger.error(f"Ошибка получения списка пользователей: {e}")
            return []

    def _load_user_list(self, list_name: str) -> List[str]:
        """Загрузить список пользователей"""
        try:
            config = self._load_yaml_file(os.path.join(self._user_lists_dir, f"users_{list_name}.yml"))
            if config and 'users' in config:
                return config['users']
            return []
        except Exception as e:
            self.logger.error(f"Ошибка загрузки списка пользователей {list_name}: {e}")
            return []

    def _load_yaml_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Загрузить YAML файл"""
        try:
            import yaml
            if not os.path.exists(file_path):
                return None

            with open(file_path, 'r', encoding='utf-8') as file:
                data = yaml.safe_load(file)
                return data if data is not None else None

        except Exception as e:
            self.logger.error(f"Ошибка чтения файла {file_path}: {e}")
            return None

    def _show_deletion_preview(self, list_name: str, users: List[str]) -> None:
        """Показать превью удаления списка пользователей"""
        print(f"\n📋 Превью удаления из списка '{list_name}' ({len(users)} пользователей):")
        print("-" * 70)

        # Показать первых 5 пользователей
        max_preview = min(5, len(users))
        for i, user in enumerate(users[:max_preview], 1):
            print(f"  {i:2d}. {user}")

        if len(users) > max_preview:
            print(f"  ... и еще {len(users) - max_preview} пользователей")

        print("-" * 70)

        # Показать статистику
        print(f"📊 Будет выполнено удаление {len(users)} стендов пользователей")

    def _show_user_deletion_preview(self, user_info: Dict[str, Any]) -> None:
        """Показать превью удаления одного пользователя"""
        user_name = user_info['user']
        pool_name = user_info['pool']
        vm_count = user_info['vm_count']

        print(f"\n👤 Детали пользователя '{user_name}':")
        print("-" * 50)
        print(f"Пользователь: {user_name}")
        print(f"Пул: {pool_name}")
        print(f"Количество VM: {vm_count}")
        print("-" * 50)

        if vm_count > 0:
            print(f"⚠️  Будут удалены все {vm_count} виртуальные машины пользователя")
        print("Будут удалены сетевые интерфейсы, виртуальные машины, пул и пользователь")
