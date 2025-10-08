"""
Менеджер пользователей системы Deploy-Stand

Предоставляет функциональность для создания, управления и удаления пользователей
и их ресурсов в кластере Proxmox VE.
"""

import logging
import secrets
import string
from typing import Dict, List, Tuple, Any
from core.proxmox.proxmox_client import ProxmoxClient

logger = logging.getLogger(__name__)


class UserManager:
    """Менеджер пользователей и их ресурсов"""

    def __init__(self, proxmox_client: ProxmoxClient):
        """
        Инициализация менеджера пользователей

        Args:
            proxmox_client: Клиент для работы с Proxmox API
        """
        self.proxmox = proxmox_client

    def create_user_and_pool(self, username: str) -> Tuple[bool, str]:
        """
        Создать пользователя и пул

        Args:
            username: Имя пользователя

        Returns:
            Кортеж (успех, пароль)
        """
        try:
            # Сгенерировать пароль
            password = self._generate_password()

            # Создать пользователя
            if not self.proxmox.create_user(username, password):
                return False, ""

            # Создать пул
            pool_name = username.split('@')[0]
            if not self.proxmox.create_pool(pool_name, f"Pool for {username}"):
                # Если создание пула неудачно, удалить пользователя
                self._cleanup_user(username)
                return False, ""

            # Установить права пользователя на пул
            permissions = ["PVEVMAdmin"]
            if not self.proxmox.set_pool_permissions(username, pool_name, permissions):
                # Если установка прав неудачна, очистить созданные ресурсы
                self._cleanup_user_and_pool(username, pool_name)
                return False, ""

            logger.info(f"Пользователь {username} и пул {pool_name} созданы")
            return True, password

        except Exception as e:
            logger.error(f"Ошибка создания пользователя и пула: {e}")
            return False, ""

    def delete_user_resources_batch(self, users: List[str]) -> Dict[str, List[str]]:
        """
        Удалить ресурсы пользователей пакетно
        Стратегия: пользователь → пул → машины → сетевые интерфейсы → удаление +
        очистка неиспользуемых сетевых мостов

        Args:
            users: Список пользователей для удаления

        Returns:
            Результаты операций {successful: [], failed: [], skipped: []}
        """
        results = {
            'successful': [],
            'failed': [],
            'skipped': []
        }

        for user in users:
            try:
                logger.info(f"Начинаем удаление ресурсов пользователя {user}")
                success = self.delete_user_resources(user)
                if success:
                    results['successful'].append(user)
                    logger.info(f"✅ Ресурсы пользователя {user} успешно удалены")
                else:
                    results['failed'].append(user)
                    logger.error(f"❌ Ошибка удаления ресурсов пользователя {user}")
            except Exception as e:
                logger.error(f"Исключение при удалении ресурсов пользователя {user}: {e}")
                results['failed'].append(user)

        # ПОСЛЕ УДАЛЕНИЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ - ОЧИСТИТЬ НЕИСПОЛЬЗУЕМЫЕ МОСТЫ И ПЕРЕЗАГРУЗИТЬ СЕТЬ
        try:
            nodes = self.proxmox.get_nodes()
            cleaned_bridges = self.proxmox.cleanup_unused_bridges(nodes)

            if cleaned_bridges > 0:
                logger.info(f"🧹 Очищено {cleaned_bridges} неиспользуемых сетевых мостов")
                results['bridges_cleaned'] = cleaned_bridges
            else:
                logger.info("ℹ️ Неиспользуемых мостов для очистки не найдено")

            # ПЕРЕЗАГРУЗИТЬ СЕТЕВЫЕ КОНФИГУРАЦИИ НА ВСЕХ НОДАХ ПОСЛЕ УДАЛЕНИЯ
            print("🔄 Обновление сетевых конфигураций на всех нодах после удаления...")
            for node in nodes:
                try:
                    if self.proxmox.reload_node_network(node):
                        print(f"  ✅ Сеть ноды {node} обновлена")
                    else:
                        print(f"  ⚠️ Не удалось обновить сеть ноды {node}")
                except Exception as e:
                    print(f"  ❌ Ошибка обновления сети ноды {node}: {e}")

        except Exception as e:
            logger.warning(f"⚠️ Ошибка очистки неиспользуемых мостов: {e}")

        logger.info(f"Пакетное удаление завершено: успешных {len(results['successful'])}, "
                   f"неудачных {len(results['failed'])}, пропущенных {len(results['skipped'])}")
        return results

    def delete_user_resources(self, username: str) -> bool:
        """
        Удалить все ресурсы пользователя
        Стратегия: пользователь → пул → машины в пуле → удаление сетевых интерфейсов → удаление машин → проверка → удаление пула → удаление пользователя

        Args:
            username: Имя пользователя

        Returns:
            True если удаление успешно
        """
        try:
            logger.info(f"🔍 Находим ресурсы пользователя {username}")

            # Получить пул пользователя
            pool_name = username.split('@')[0]
            logger.info(f"🔍 Проверяем существование пула {pool_name}")

            # Проверить существует ли пул
            if not self.proxmox.pool_exists(pool_name):
                logger.info(f"ℹ️ Пул {pool_name} не существует, проверяем пользователя")
                # Если пула нет, проверить пользователя
                if self.proxmox.user_exists(username):
                    logger.info(f"👤 Пользователь {username} существует без пула, удаляем пользователя")
                    return self._delete_user(username)
                else:
                    logger.info(f"ℹ️ Ресурсы пользователя {username} уже удалены")
                    return True

            # Получить машины в пуле
            pool_vms = self.proxmox.get_pool_vms(pool_name)
            logger.info(f"🔍 Найдено {len(pool_vms)} VM в пуле {pool_name}")

            # ШАГ 1: Удалить сетевые интерфейсы всех VM (ВНАЧАЛЕ!)
            networks_cleared = self._clear_vm_networks(pool_vms)

            # ШАГ 2: Остановить все виртуальные машины (если не остановлены)
            vms_stopped = self._stop_pool_vms(pool_name, pool_vms)

            # ШАГ 3: Удалить виртуальные машины
            vms_deleted = self._delete_pool_vms(pool_name, pool_vms)

            # ДОПОЛНИТЕЛЬНАЯ ПАУЗА: Подождать завершения асинхронных операций удаления
            logger.info(f"⏳ Ждем завершения операций удаления VM... (10 сек)")
            import time
            time.sleep(10)

            # Проверить что машины удалены (ДОПОЛНИТЕЛЬНАЯ ПРОВЕРКА)
            vms_verified_1 = self._verify_vms_deleted(pool_name)

            # Финальная верификация что машины действительно удалены
            vms_verified = vms_verified_1
            if not vms_verified:
                logger.warning(f"⚠️ Нужна дополнительная пауза - повторная проверка через 10 сек")
                time.sleep(10)
                vms_verified = self._verify_vms_deleted(pool_name)

                if not vms_verified:
                    logger.error(f"❌ ВМ в пуле {pool_name} не удалось удалить полностью, отказываемся удалять пул")
                    return False

            # Только после подтверждения что ВМ удалены - удаляем пул
            pool_deleted = self._delete_user_pool(pool_name)

            # Удалить пользователя
            user_deleted = self._delete_user(username)

            success = vms_stopped and networks_cleared and vms_deleted and vms_verified and pool_deleted and user_deleted

            if success:
                logger.info(f"✅ Все ресурсы пользователя {username} успешно удалены")
            else:
                logger.error(f"❌ Не удалось полностью удалить ресурсы пользователя {username}")

            return success

        except Exception as e:
            logger.error(f"❌ Критическая ошибка удаления ресурсов пользователя {username}: {e}")
            return False

    def _stop_pool_vms(self, pool_name: str, pool_vms: List[Dict]) -> bool:
        """Остановить все виртуальные машины в пуле"""
        try:
            if not pool_vms:
                logger.info(f"ℹ️ В пуле {pool_name} нет VM для остановки")
                return True

            logger.info(f"🛑 Останавливаем {len(pool_vms)} VM в пуле {pool_name}")
            stopped_count = 0

            for vm_member in pool_vms:
                vmid = vm_member.get('vmid')
                if not vmid:
                    continue

                # Определить ноду VM
                # VM может быть на других нодах, проверим все ноды
                nodes = self.proxmox.get_nodes()
                vm_found = False

                for node in nodes:
                    try:
                        # Проверить статус VM на этой ноде
                        vm_status = self.proxmox.get_vm_config(node, vmid)
                        if vm_status:
                            vm_found = True
                            # Проверить текущий статус
                            current_status = self.proxmox.api.nodes(node).qemu(vmid).status.current.get()
                            if current_status.get('status') == 'running':
                                logger.info(f"Останавливаем VM {vmid} на ноде {node}")
                                # Остановить VM
                                task_id = self.proxmox.api.nodes(node).qemu(vmid).status.stop.post()
                                if self.proxmox.wait_for_task(task_id, node, timeout=120):
                                    logger.info(f"✅ VM {vmid} остановлена")
                                    stopped_count += 1
                                else:
                                    logger.error(f"❌ Не удалось остановить VM {vmid}")
                                    return False
                            else:
                                logger.info(f"ℹ️ VM {vmid} уже остановлена")
                                stopped_count += 1
                            break
                    except Exception:
                        continue  # VM не на этой ноде

                if not vm_found:
                    logger.warning(f"⚠️ VM {vmid} не найдена на доступных нодах")
                    return False

            logger.info(f"✅ Остановлено {stopped_count} из {len(pool_vms)} VM")
            return stopped_count == len(pool_vms)

        except Exception as e:
            logger.error(f"Ошибка остановки VM пула {pool_name}: {e}")
            return False

    def _clear_vm_networks(self, pool_vms: List[Dict]) -> bool:
        """Очистить сетевую конфигурацию виртуальных машин"""
        try:
            if not pool_vms:
                logger.info("ℹ️ Нет VM для очистки сетевых интерфейсов")
                return True

            logger.info(f"🧹 Очищаем сетевую конфигурацию {len(pool_vms)} VM")
            cleared_count = 0

            for vm_member in pool_vms:
                vmid = vm_member.get('vmid')
                if not vmid:
                    continue

                # Найти VM на нодах
                nodes = self.proxmox.get_nodes()
                vm_found = False

                for node in nodes:
                    try:
                        vm_config = self.proxmox.get_vm_config(node, vmid)
                        if vm_config:
                            vm_found = True
                            logger.info(f"Очищаем сеть VM {vmid} на ноде {node}")

                            # Очистить сетевую конфигурацию путем удаления всех net* параметров
                            network_updates = {}

                            # Найти и удалить все сетевые интерфейсы
                            vm_full_config = self.proxmox.api.nodes(node).qemu(vmid).config.get()
                            for key in vm_full_config:
                                if key.startswith('net'):
                                    network_updates[key] = None  # None удаляет параметр

                            if network_updates:
                                self.proxmox.api.nodes(node).qemu(vmid).config.put(delete=','.join(network_updates.keys()))
                                logger.info(f"✅ Сетевые интерфейсы VM {vmid} удалены: {list(network_updates.keys())}")
                            else:
                                logger.info(f"ℹ️ VM {vmid} не имеет сетевых интерфейсов")

                            cleared_count += 1
                            break
                    except Exception as ex:
                        # Тихий режим при очистке сети - ожидаемые ошибки, когда VM ищется на всех нодах
                        continue

                if not vm_found:
                    logger.error(f"❌ VM {vmid} не найдена ни на одной ноде для очистки сети")
                    return False

            logger.info(f"✅ Сеть очищена у {cleared_count} из {len(pool_vms)} VM")
            return cleared_count == len(pool_vms)

        except Exception as e:
            logger.error(f"❌ Критическая ошибка очистки сетевых интерфейсов: {e}")
            return False

    def _delete_pool_vms(self, pool_name: str, pool_vms: List[Dict]) -> bool:
        """Удалить все виртуальные машины в пуле"""
        try:
            if not pool_vms:
                logger.info(f"ℹ️ В пуле {pool_name} нет VM для удаления")
                return True

            logger.info(f"🗑️ Удаляем {len(pool_vms)} VM в пуле {pool_name}")
            deleted_count = 0

            for vm_member in pool_vms:
                vmid = vm_member.get('vmid')
                if not vmid:
                    continue

                # Найти VM на нодах
                nodes = self.proxmox.get_nodes()
                vm_found = False

                for node in nodes:
                    try:
                        logger.debug(f"Проверяем VM {vmid} на ноде {node}")
                        vm_config = self.proxmox.get_vm_config(node, vmid)
                        if vm_config:
                            vm_found = True
                            logger.info(f"🚨 НАЧИНАЕМ УДАЛЕНИЕ VM {vmid} с ноды {node}")

                            # Остановить VM перед удалением, если она работает
                            try:
                                status = self.proxmox.api.nodes(node).qemu(vmid).status.current.get()
                                current_status = status.get('status')
                                logger.debug(f"Статус VM {vmid} перед удалением: {current_status}")

                                if current_status == 'running':
                                    logger.info(f"🛑 VM {vmid} еще работает, останавливаем перед удалением")
                                    task_id = self.proxmox.api.nodes(node).qemu(vmid).status.stop.post()
                                    if self.proxmox.wait_for_task(task_id, node, timeout=60):
                                        logger.info(f"✅ VM {vmid} остановлена перед удалением")
                                    else:
                                        logger.error(f"❌ Не удалось остановить VM {vmid} перед удалением")
                                        return False
                            except Exception as stop_e:
                                logger.warning(f"⚠️ Не удалось проверить статус VM {vmid}: {stop_e}")

                            # Попытка удаления VM
                            delete_result = self.proxmox.delete_vm(node, vmid)
                            logger.debug(f"Результат вызова proxmox.delete_vm({node}, {vmid}): {delete_result}")

                            if delete_result:
                                logger.info(f"✅ VM {vmid} УСПЕШНО УДАЛЕНА с ноды {node}")
                                deleted_count += 1
                            else:
                                logger.error(f"❌ proxmox.delete_vm вернул False для VM {vmid} на {node}")
                                return False
                            break
                    except Exception as ex:
                        logger.debug(f"VM {vmid} не найдена на ноде {node}: {ex}")
                        continue

                if not vm_found:
                    # VM не найдена ни на одной ноде - это может быть нормально если она уже удалена
                    logger.warning(f"⚠️ VM {vmid} не найдена на доступных нодах - возможно уже удалена")
                    deleted_count += 1  # Считаем как успешно удаленную

            logger.info(f"✅ Удаление завершено: {deleted_count} из {len(pool_vms)} VM обработано")
            return deleted_count == len(pool_vms)

        except Exception as e:
            logger.error(f"Критическая ошибка удаления VM пула {pool_name}: {e}")
            return False

    def _verify_vms_deleted(self, pool_name: str) -> bool:
        """Проверить что все VM в пуле удалены"""
        try:
            logger.debug(f"Проверяем удаление VM в пуле {pool_name}")
            pool_vms = self.proxmox.get_pool_vms(pool_name)

            if not pool_vms:
                logger.debug(f"В пуле {pool_name} нет VM")
                return True

            # Проверить каждую VM из списка пула - действительно ли она существует
            actually_deleted = 0
            nodes = self.proxmox.get_nodes()

            for vm_member in pool_vms:
                vmid = vm_member.get('vmid')
                if not vmid:
                    continue

                # Проверить существует ли эта VM на самом деле на какой-либо ноде
                vm_exists = False
                for node in nodes:
                    try:
                        vm_config = self.proxmox.get_vm_config(node, vmid)
                        if vm_config:
                            vm_exists = True
                            break
                    except Exception:
                        continue  # VM не на этой ноде

                if not vm_exists:
                    actually_deleted += 1

            # Если все VM из пула фактически удалены - считаем успех
            total_pool_vms = len([vm for vm in pool_vms if vm.get('vmid')])

            if actually_deleted == total_pool_vms:
                logger.debug(f"Все {total_pool_vms} VM из пула {pool_name} удалены")
                return True
            else:
                remaining_count = total_pool_vms - actually_deleted
                logger.warning(f"В пуле {pool_name} еще {remaining_count} VM из {total_pool_vms} не удалены")
                return False

        except Exception:
            # Тихий режим - не логируем ошибки верификации
            return False

    def _delete_user_pool(self, pool_name: str) -> bool:
        """Удалить пул пользователя"""
        try:
            if not self.proxmox.pool_exists(pool_name):
                logger.info(f"ℹ️ Пул {pool_name} уже удален")
                return True

            logger.info(f"🗑️ Удаляем пул {pool_name}")
            # Для удаления пула в Proxmox API используется DELETE /pools/{poolid}
            try:
                self.proxmox.api.pools(pool_name).delete()
                logger.info(f"✅ Пул {pool_name} удален")
                return True
            except Exception as e:
                logger.error(f"Ошибка API при удалении пула {pool_name}: {e}")
                return False

        except Exception as e:
            logger.error(f"Ошибка удаления пула {pool_name}: {e}")
            return False

    def _delete_user(self, username: str) -> bool:
        """Удалить пользователя"""
        try:
            if not self.proxmox.user_exists(username):
                logger.info(f"ℹ️ Пользователь {username} уже удален")
                return True

            logger.info(f"👤 Удаляем пользователя {username}")
            try:
                self.proxmox.api.access.users(username).delete()
                logger.info(f"✅ Пользователь {username} удален")
                return True
            except Exception as e:
                logger.error(f"Ошибка API при удалении пользователя {username}: {e}")
                return False

        except Exception as e:
            logger.error(f"Ошибка удаления пользователя {username}: {e}")
            return False

    def _cleanup_user(self, username: str) -> None:
        """Очистить пользователя при ошибке создания пула"""
        try:
            # Заглушка - в реальности здесь должна быть логика удаления пользователя
            logger.info(f"Очистка пользователя {username}")
        except Exception as e:
            logger.error(f"Ошибка очистки пользователя {username}: {e}")

    def _cleanup_user_and_pool(self, username: str, pool_name: str) -> None:
        """Очистить пользователя и пул при ошибке установки прав"""
        try:
            # Заглушка - в реальности здесь должна быть логика очистки
            logger.info(f"Очистка пользователя {username} и пула {pool_name}")
        except Exception as e:
            logger.error(f"Ошибка очистки пользователя и пула: {e}")

    def _generate_password(self, length: int = 8) -> str:
        """Сгенерировать случайный пароль для обучающих стендов"""
        alphabet = string.digits  # Только цифры для простоты использования в обучении
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def get_user_pools(self) -> List[str]:
        """Получить список всех пулов пользователей"""
        try:
            # Заглушка - в реальности здесь должна быть логика получения пулов
            return []
        except Exception as e:
            logger.error(f"Ошибка получения списка пулов: {e}")
            return []

    def get_pool_users(self, pool_name: str) -> List[str]:
        """Получить список пользователей пула"""
        try:
            # Заглушка - в реальности здесь должна быть логика получения пользователей пула
            return []
        except Exception as e:
            logger.error(f"Ошибка получения пользователей пула {pool_name}: {e}")
            return []

    def _verify_vms_deleted_by_searching_nodes(self, pool_name: str) -> bool:
        """
        Дополнительная проверка - поиск VM по всем нодам кластера

        Args:
            pool_name: Имя пула для проверки

        Returns:
            True если VM не найдены ни на одной ноде
        """
        try:
            logger.info(f"🔍 Дополнительная проверка: поиск VM пула '{pool_name}' по всем нодам кластера")

            # Получить VM из пула
            pool_vms = self.proxmox.get_pool_vms(pool_name)
            vmids_to_check = [vm.get('vmid') for vm in pool_vms if vm.get('vmid')]

            if not vmids_to_check:
                logger.info(f"✅ В пуле {pool_name} нет VM для проверки")
                return True

            logger.info(f"Ищем {len(vmids_to_check)} VM: {vmids_to_check}")

            # Поиск каждой VM на всех нодах кластера
            remaining_vms = []
            nodes = self.proxmox.get_nodes()

            for vmid in vmids_to_check:
                vm_still_exists = False

                for node in nodes:
                    try:
                        # Проверить существует ли VM на этой ноде
                        vm_config = self.proxmox.get_vm_config(node, vmid)
                        if vm_config:
                            logger.error(f"❌ VM {vmid} найдена на ноде {node}!")
                            vm_still_exists = True
                            remaining_vms.append(f"{vmid}@{node}")
                            break  # Найдена, больше не искать
                    except Exception as e:
                        # VM не на этой ноде, продолжаем поиск
                        logger.debug(f"VM {vmid} не найдена на ноде {node}: {e}")
                        continue

                if not vm_still_exists:
                    logger.info(f"✅ VM {vmid} НЕ найдена ни на одной ноде - удалена корректно")

            if remaining_vms:
                logger.error(f"❌ Найдены НЕ УДАЛЕННЫЕ VM: {remaining_vms}")
                return False
            else:
                logger.info(f"✅ Дополнительная проверка пройдена - все VM пула '{pool_name}' удалены")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка дополнительной проверки VM пула {pool_name}: {e}")
            return False

    def audit_user_actions(self, username: str) -> Dict[str, Any]:
        """Получить аудит действий пользователя"""
        try:
            # Заглушка - в реальности здесь должна быть логика аудита
            return {
                'username': username,
                'actions': [],
                'last_login': None,
                'created_vms': 0
            }
        except Exception as e:
            logger.error(f"Ошибка аудита пользователя {username}: {e}")
            return {}
