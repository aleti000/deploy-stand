#!/usr/bin/env python3
"""
Меню удаления стендов
Удаление стендов пользователей с различными опциями
"""

import logging
from typing import List, Dict, Any
from ..utils.user_manager import UserManager
from ..utils.pool_manager import PoolManager
from ..utils.vm_manager import VMManager
from ..utils.network_manager import NetworkManager
from ..utils.proxmox_client import ProxmoxClient


class DeleteStandMenu:
    """Меню удаления стендов"""

    def __init__(self, logger_instance, proxmox_client: ProxmoxClient = None):
        """
        Инициализация меню удаления стендов

        Args:
            logger_instance: Экземпляр логгера
            proxmox_client: Клиент Proxmox (опционально)
        """
        self.logger = logger_instance
        self.proxmox_client = proxmox_client

        # Инициализируем менеджеры если клиент доступен
        if self.proxmox_client:
            self.user_manager = UserManager(self.proxmox_client)
            self.pool_manager = PoolManager(self.proxmox_client)
            self.vm_manager = VMManager(self.proxmox_client)
            self.network_manager = NetworkManager(self.proxmox_client)

    def show(self) -> str:
        """Показать меню удаления стендов"""
        print("\n🗑️  Удаление стендов")
        print("=" * 50)

        print("Доступные действия:")
        print("  [1] 🗑️  Удалить стенды по списку пользователей")
        print("  [2] 🗑️  Удалить стенд отдельного пользователя")
        print("  [0] Назад")

        choice = input("Выберите действие: ").strip()

        if choice == "1":
            return self._delete_stands_by_user_list()
        elif choice == "2":
            return self._delete_single_user_stand()
        elif choice == "0":
            return "back"
        else:
            print("❌ Неверный выбор!")
            return "repeat"

    def _delete_stands_by_user_list(self) -> str:
        """Удалить стенды по списку пользователей"""
        try:
            print("\n🗑️  Удаление стендов по списку пользователей")
            print("=" * 50)

            # Получить доступные списки пользователей
            user_lists = self._get_user_lists()
            if not user_lists:
                print("ℹ️  Нет списков пользователей")
                return "repeat"

            print("Доступные списки пользователей:")
            for i, user_list in enumerate(user_lists, 1):
                users_in_list = self._get_users_from_list(user_list)
                print(f"  [{i}] {user_list} ({len(users_in_list)} пользователей)")

            # Выбор списка
            choice = input(f"\nВыберите список (1-{len(user_lists)}) или 0 для отмены: ").strip()

            if choice == "0":
                return "repeat"

            if not choice.isdigit() or int(choice) < 1 or int(choice) > len(user_lists):
                print("❌ Неверный выбор!")
                return "repeat"

            selected_list = user_lists[int(choice) - 1]
            users_to_delete = self._get_users_from_list(selected_list)

            print(f"\n📋 Пользователи из списка '{selected_list}':")
            for user in users_to_delete:
                print(f"  👤 {user}")

            # Подтверждение
            confirm = input(f"\nУдалить стенды {len(users_to_delete)} пользователей? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("❌ Операция отменена")
                return "repeat"

            # Удалить пользователей
            success_count = 0
            for user in users_to_delete:
                print(f"\n🔄 Удаление пользователя {user}...")
                if self._delete_user_stand_complete(user):
                    success_count += 1
                    print(f"✅ Пользователь {user} удален")
                else:
                    print(f"❌ Ошибка удаления пользователя {user}")

            # Перезагрузить сеть
            if success_count > 0:
                print(f"\n🔄 Перезагрузка сети...")
                self._reload_network_after_deletion()

            print(f"\n📊 Результат: {success_count}/{len(users_to_delete)} пользователей удалено")
            return "repeat"

        except Exception as e:
            self.logger.error(f"Ошибка удаления по списку пользователей: {e}")
            print(f"❌ Ошибка: {e}")
            return "repeat"

    def _get_user_lists(self) -> List[str]:
        """Получить доступные списки пользователей"""
        # Заглушка - в будущем можно реализовать чтение из файлов
        return ["test"]

    def _get_users_from_list(self, user_list: str) -> List[str]:
        """Получить пользователей из списка"""
        # Заглушка - в будущем можно реализовать чтение из файлов
        if user_list == "test":
            return ["user1@pve", "user2@pve", "user3@pve"]
        return []

    def _delete_single_user_stand(self) -> str:
        """Удалить стенд отдельного пользователя"""
        try:
            print("\n🗑️  Удаление стенда отдельного пользователя")
            print("=" * 50)

            # Получить пользователей у которых есть пулы
            users_with_pools = self._get_users_with_pools()
            if not users_with_pools:
                print("ℹ️  Нет пользователей с пулами")
                return "repeat"

            print("Пользователи с пулами:")
            for i, user in enumerate(users_with_pools, 1):
                print(f"  [{i}] {user}")

            # Выбор пользователя
            choice = input(f"\nВыберите пользователя (1-{len(users_with_pools)}) или 0 для отмены: ").strip()

            if choice == "0":
                return "repeat"

            if not choice.isdigit() or int(choice) < 1 or int(choice) > len(users_with_pools):
                print("❌ Неверный выбор!")
                return "repeat"

            selected_user = users_with_pools[int(choice) - 1]
            print(f"👤 Выбран пользователь: {selected_user}")

            # Подтверждение
            confirm = input(f"Удалить стенд пользователя {selected_user}? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("❌ Операция отменена")
                return "repeat"

            # Удалить пользователя
            if self._delete_user_stand_complete(selected_user):
                print(f"✅ Пользователь {selected_user} удален")
                self._reload_network_after_deletion()
            else:
                print(f"❌ Ошибка удаления пользователя {selected_user}")

            return "repeat"

        except Exception as e:
            self.logger.error(f"Ошибка удаления пользователя: {e}")
            print(f"❌ Ошибка: {e}")
            return "repeat"

    def _get_users_with_pools(self) -> List[str]:
        """Получить пользователей у которых есть пулы"""
        try:
            if not self.proxmox_client:
                return []

            all_users = self._get_all_users()
            users_with_pools = []

            for user in all_users:
                pool_name = self.pool_manager.extract_pool_name(user)
                if self.pool_manager.check_pool_exists(pool_name):
                    users_with_pools.append(user)

            return users_with_pools

        except Exception as e:
            self.logger.error(f"Ошибка получения пользователей с пулами: {e}")
            return []

    def _delete_selected_stands(self) -> str:
        """Удалить выбранные стенды"""
        try:
            print("\n🗑️  Удаление выбранных стендов")
            print("=" * 50)

            # Получить всех пользователей
            all_users = self._get_all_users()
            if not all_users:
                print("ℹ️  Нет пользователей для удаления")
                return "repeat"

            print("Выберите пользователей для удаления (введите номера через запятую):")
            for i, user in enumerate(all_users, 1):
                print(f"  [{i}] {user}")

            # Выбор пользователей
            choice = input(f"\nВведите номера (1-{len(all_users)}) через запятую: ").strip()

            if not choice:
                print("❌ Ничего не выбрано")
                return "repeat"

            try:
                selected_indices = [int(x.strip()) - 1 for x in choice.split(",")]
                selected_users = [all_users[i] for i in selected_indices if 0 <= i < len(all_users)]
            except:
                print("❌ Неверный формат ввода")
                return "repeat"

            if not selected_users:
                print("❌ Ничего не выбрано")
                return "repeat"

            print(f"\n👤 Выбрано {len(selected_users)} пользователей:")
            for user in selected_users:
                print(f"  • {user}")

            # Подтверждение
            confirm = input(f"Удалить {len(selected_users)} пользователей? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("❌ Операция отменена")
                return "repeat"

            # Удалить пользователей
            success_count = 0
            for user in selected_users:
                if self._delete_user_stand_complete(user):
                    success_count += 1
                    print(f"✅ Пользователь {user} удален")
                else:
                    print(f"❌ Ошибка удаления пользователя {user}")

            # Перезагрузить сеть
            if success_count > 0:
                self._reload_network_after_deletion()

            print(f"\n📊 Результат: {success_count}/{len(selected_users)} пользователей удалено")
            return "repeat"

        except Exception as e:
            self.logger.error(f"Ошибка удаления выбранных пользователей: {e}")
            print(f"❌ Ошибка: {e}")
            return "repeat"

    def _check_existing_stands(self) -> str:
        """Проверить существующие стенды"""
        try:
            print("\n🔍 Проверка существующих стендов")
            print("=" * 50)

            # Получить всех пользователей
            all_users = self._get_all_users()
            if not all_users:
                print("ℹ️  Нет пользователей")
                return "repeat"

            print(f"📋 Найдено {len(all_users)} пользователей:")
            for user in all_users:
                pool_name = self.pool_manager.extract_pool_name(user)
                vm_count = self.vm_manager.list_user_vms(pool_name)
                print(f"  👤 {user} - {len(vm_count)} VM")

            return "repeat"

        except Exception as e:
            self.logger.error(f"Ошибка проверки стендов: {e}")
            print(f"❌ Ошибка: {e}")
            return "repeat"

    def _delete_user_stand_complete(self, user: str) -> bool:
        """
        Полное удаление стенда пользователя

        Args:
            user: Имя пользователя

        Returns:
            True если удаление успешно
        """
        try:
            # 1. Определить пул пользователя
            pool_name = self.pool_manager.extract_pool_name(user)
            self.logger.info(f"Пользователь {user} -> пул {pool_name}")

            # 2. Найти все VM пула
            pool_vms = self.vm_manager.list_user_vms(pool_name)
            self.logger.info(f"Найдено {len(pool_vms)} VM в пуле {pool_name}")

            # 3. Найти bridge подключенные к машинам и удалить их
            deleted_bridges = set()
            for vm_info in pool_vms:
                vmid = vm_info.get('vmid')
                node = vm_info.get('node')

                if vmid and node:
                    # Получить сетевую конфигурацию VM
                    network_info = self.network_manager.get_network_info(node, vmid)

                    # Найти bridge'ы для удаления
                    for net_config in network_info.values():
                        # Извлечь имя bridge из конфигурации сети
                        if 'bridge=' in net_config:
                            bridge_name = net_config.split('bridge=')[1].split(',')[0]
                            if bridge_name.startswith('vmbr') and bridge_name not in ['vmbr0']:
                                deleted_bridges.add((node, bridge_name))

            # Удалить найденные bridge'ы
            for node, bridge_name in deleted_bridges:
                if self.network_manager.bridge_in_use(node, bridge_name):
                    self.logger.info(f"Удаляем bridge {bridge_name} на ноде {node}")
                    if self.network_manager.delete_bridge(node, bridge_name):
                        self.logger.info(f"✅ Bridge {bridge_name} удален")
                    else:
                        self.logger.warning(f"Не удалось удалить bridge {bridge_name}")

            # 4. Удалить VM пула
            for vm_info in pool_vms:
                vmid = vm_info.get('vmid')
                node = vm_info.get('node')

                if vmid and node:
                    self.logger.info(f"Удаляем VM {vmid} на ноде {node}")
                    if self.vm_manager.delete_vm(node, vmid):
                        self.logger.info(f"✅ VM {vmid} удалена")
                    else:
                        self.logger.warning(f"Не удалось удалить VM {vmid}")

            # 5. Удалить пул пользователя
            self.logger.info(f"Удаляем пул {pool_name}")
            if self.pool_manager.delete_pool(pool_name):
                self.logger.info(f"✅ Пул {pool_name} удален")
            else:
                self.logger.warning(f"Не удалось удалить пул {pool_name}")

            # 6. Удалить пользователя
            self.logger.info(f"Удаляем пользователя {user}")
            if self.user_manager.delete_user(user):
                self.logger.info(f"✅ Пользователь {user} удален")
            else:
                self.logger.warning(f"Не удалось удалить пользователя {user}")

            return True

        except Exception as e:
            self.logger.error(f"Ошибка удаления пользователя {user}: {e}")
            return False

    def _get_all_users(self) -> List[str]:
        """Получить список всех пользователей"""
        try:
            if not self.proxmox_client:
                return []

            users = self.proxmox_client.api.access.users.get()
            return [user.get('userid') for user in users if user.get('userid')]

        except Exception as e:
            self.logger.error(f"Ошибка получения списка пользователей: {e}")
            return []

    def _reload_network_after_deletion(self) -> None:
        """Перезагрузить сеть после удаления"""
        try:
            if not self.proxmox_client:
                return

            # Получить все ноды
            nodes = self.proxmox_client.get_nodes()

            for node in nodes:
                self.logger.info(f"Перезагружаем сеть на ноде {node}")
                if self.network_manager.reload_network(node):
                    self.logger.info(f"✅ Сеть ноды {node} перезагружена")
                else:
                    self.logger.warning(f"Не удалось перезагрузить сеть ноды {node}")

        except Exception as e:
            self.logger.error(f"Ошибка перезагрузки сети: {e}")
