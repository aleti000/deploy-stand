"""
Клиент для работы с Proxmox VE API

Предоставляет высокоуровневый интерфейс для основных операций с Proxmox:
- Управление виртуальными машинами
- Работа с шаблонами
- Настройка сети
- Управление пользователями и пулами
"""

import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from proxmoxer import ProxmoxAPI

logger = logging.getLogger(__name__)


class ProxmoxClient:
    """Клиент для работы с Proxmox VE API"""

    def __init__(self, host: str, user: str, password: str = None, token_name: str = None, token_value: str = None):
        """
        Инициализация клиента Proxmox

        Args:
            host: Адрес сервера Proxmox (например, "192.168.1.100:8006")
            user: Имя пользователя (например, "root@pam")
            password: Пароль пользователя
            token_name: Имя токена (если используется аутентификация по токену)
            token_value: Значение токена
        """
        self.host = host
        self.user = user
        self.password = password
        self.token_name = token_name
        self.token_value = token_value
        self.api = None
        self._connect()

    def _connect(self):
        """Установить соединение с Proxmox API"""
        try:
            if self.token_name and self.token_value:
                # Аутентификация по токену
                self.api = ProxmoxAPI(
                    self.host,
                    user=self.user,
                    token_name=self.token_name,
                    token_value=self.token_value,
                    verify_ssl=False
                )
            elif self.password:
                # Аутентификация по паролю
                self.api = ProxmoxAPI(
                    self.host,
                    user=self.user,
                    password=self.password,
                    verify_ssl=False
                )
            else:
                raise ValueError("Не указаны данные для аутентификации")

            # Проверка соединения
            self.api.version.get()
            logger.info(f"Успешное подключение к Proxmox {self.host}")

        except Exception as e:
            logger.error(f"Ошибка подключения к Proxmox {self.host}: {e}")
            raise

    def get_nodes(self) -> List[str]:
        """Получить список всех нод в кластере"""
        try:
            nodes = self.api.nodes.get()
            return [node['node'] for node in nodes]
        except Exception as e:
            logger.error(f"Ошибка получения списка нод: {e}")
            raise

    def get_next_vmid(self) -> int:
        """Получить следующий доступный VMID из кластера"""
        try:
            cluster_nextid = self.api.cluster.nextid.get()
            return int(cluster_nextid)
        except Exception as e:
            logger.error(f"Ошибка получения следующего VMID: {e}")
            raise

    def clone_vm(self, template_node: str, template_vmid: int, target_node: str,
                 new_vmid: int, name: str, pool: str = None, full_clone: bool = False) -> str:
        """
        Клонировать виртуальную машину

        Args:
            template_node: Нода где находится шаблон
            template_vmid: VMID шаблона-источника
            target_node: Целевая нода для размещения
            new_vmid: Новый VMID для клонированной машины
            name: Имя новой виртуальной машины
            pool: Пул для размещения (опционально)
            full_clone: True для полного клонирования, False для связанного

        Returns:
            ID задачи клонирования
        """
        try:
            clone_params = {
                'newid': new_vmid,
                'name': name,
                'target': target_node,
                'full': 1 if full_clone else 0
            }

            if pool:
                clone_params['pool'] = pool

            task = self.api.nodes(template_node).qemu(template_vmid).clone.post(**clone_params)
            logger.info(f"Запущено клонирование VM {template_vmid} -> {new_vmid} на ноде {target_node}")
            return task

        except Exception as e:
            logger.error(f"Ошибка клонирования VM: {e}")
            raise

    def wait_for_task(self, task_id: str, node: str, timeout: int = 300) -> bool:
        """
        Ожидать завершения задачи

        Args:
            task_id: ID задачи
            node: Нода где выполняется задача
            timeout: Максимальное время ожидания в секундах

        Returns:
            True если задача завершилась успешно
        """
        start_time = time.time()
        has_been_running = False

        while time.time() - start_time < timeout:
            try:
                task_status = self.api.nodes(node).tasks(task_id).status.get()
                status = task_status.get('status')

                if status == 'stopped':
                    exitstatus = task_status.get('exitstatus', 'OK')
                    logger.info(f"Задача {task_id} завершена со статусом: {exitstatus}")
                    return exitstatus == 'OK'
                elif status == 'running':
                    has_been_running = True
                    time.sleep(2)
                    continue
                else:
                    logger.error(f"Задача {task_id} завершилась со статусом: {status}")
                    return False

            except Exception as e:
                error_str = str(e)
                if 'no such task' in error_str.lower():
                    # Задача могла завершиться и быть удалена
                    # Если задача была запущена и видна как running, считаем успехом
                    if has_been_running:
                        logger.info(f"Задача {task_id} исчезла после выполнения (предполагаем успех)")
                        return True
                    elif time.time() - start_time > 10:  # Ждем минимум 10 сек, чтобы задача запустилась
                        logger.warning(f"Задача {task_id} не найдена по прошествии времени (предполагаем неудачу)")
                        return False
                    else:
                        # Еще рано, задача может не успела запуститься
                        time.sleep(1)
                        continue
                else:
                    logger.error(f"Ошибка проверки статуса задачи {task_id}: {e}")
                    time.sleep(2)

        logger.error(f"Таймаут ожидания задачи {task_id}")
        return False

    def delete_vm(self, node: str, vmid: int) -> bool:
        """
        Удалить виртуальную машину

        Args:
            node: Нода где размещена виртуальная машина
            vmid: VMID машины для удаления

        Returns:
            True если удаление успешно
        """
        try:
            # Сначала остановить машину если она запущена
            try:
                vm_config = self.api.nodes(node).qemu(vmid).status.current.get()
                if vm_config.get('status') == 'running':
                    self.api.nodes(node).qemu(vmid).status.stop.post()
                    # Подождать остановки
                    time.sleep(5)
            except:
                pass  # Игнорируем ошибки остановки

            # Удалить машину
            self.api.nodes(node).qemu(vmid).delete()
            logger.info(f"VM {vmid} удалена с ноды {node}")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления VM {vmid}: {e}")
            return False

    def create_user(self, userid: str, password: str, groups: List[str] = None) -> bool:
        """
        Создать пользователя

        Args:
            userid: ID пользователя (например, "student1@pve")
            password: Пароль пользователя
            groups: Список групп для пользователя

        Returns:
            True если создание успешно или пользователь уже существует
        """
        try:
            # Сначала проверить существует ли пользователь
            if self.user_exists(userid):
                logger.info(f"Пользователь {userid} уже существует")
                return True

            user_params = {
                'userid': userid,
                'password': password
            }

            if groups:
                user_params['groups'] = ','.join(groups)

            self.api.access.users.post(**user_params)
            logger.info(f"Пользователь {userid} создан")
            return True

        except Exception as e:
            logger.error(f"Ошибка создания пользователя {userid}: {e}")
            # Если ошибка из-за того что пользователь уже существует - считаем успехом
            if "already exists" in str(e) or "duplicate" in str(e).lower():
                logger.info(f"Пользователь {userid} уже существует (обработано как успех)")
                return True
            return False

    def create_pool(self, poolid: str, comment: str = "") -> bool:
        """
        Создать пул

        Args:
            poolid: ID пула
            comment: Комментарий к пулу

        Returns:
            True если создание успешно или пул уже существует
        """
        try:
            # Сначала проверить существует ли пул
            if self.pool_exists(poolid):
                logger.info(f"Пул {poolid} уже существует")
                return True

            self.api.pools.post(poolid=poolid, comment=comment)
            logger.info(f"Пул {poolid} создан")
            return True

        except Exception as e:
            logger.error(f"Ошибка создания пула {poolid}: {e}")
            # Если ошибка из-за того что пул уже существует - считаем успехом
            if "already exists" in str(e) or "duplicate" in str(e).lower():
                logger.info(f"Пул {poolid} уже существует (обработано как успех)")
                return True
            return False

    def set_pool_permissions(self, userid: str, poolid: str, permissions: List[str]) -> bool:
        """
        Установить права пользователя на пул

        Args:
            userid: ID пользователя
            poolid: ID пула
            permissions: Список прав (например, ["VM.Allocate", "VM.Clone"])

        Returns:
            True если установка прав успешна
        """
        try:
            for permission in permissions:
                # Используем PUT /access/acl для установки ACL прав
                self.api.access.acl.put(
                    users=userid,
                    path=f"/pool/{poolid}",
                    roles=permission,
                    propagate=1  # Применить права к дочерним объектам
                )

            logger.info(f"Права пользователя {userid} на пул {poolid} установлены")
            return True

        except Exception as e:
            logger.error(f"Ошибка установки прав пользователя {userid}: {e}")
            return False

    def get_vms_on_node(self, node: str) -> List[Dict]:
        """Получить список виртуальных машин на ноде"""
        try:
            vms = self.api.nodes(node).qemu.get()
            return vms or []
        except Exception as e:
            logger.error(f"Ошибка получения списка VM на ноде {node}: {e}")
            return []

    def get_vm_config(self, node: str, vmid: int) -> Dict:
        """Получить конфигурацию виртуальной машины"""
        try:
            config = self.api.nodes(node).qemu(vmid).config.get()
            return config
        except Exception:
            # Тихий режим - не логируем ожидаемые ошибки для VM, которых нет на определенной ноде
            return {}

    def configure_vm_network(self, node: str, vmid: int, network_configs: Dict[str, str]) -> bool:
        """
        Настроить сетевые интерфейсы виртуальной машины

        Args:
            node: Нода размещения
            vmid: VMID машины
            network_configs: Словарь конфигураций сети {net0: "config", net1: "config"}

        Returns:
            True если настройка успешна
        """
        try:
            # Объединить все сетевые конфигурации в один вызов
            config_params = {}
            for net_id, net_config in network_configs.items():
                config_params[net_id] = net_config

            self.api.nodes(node).qemu(vmid).config.post(**config_params)
            logger.info(f"Сеть VM {vmid} настроена")
            return True

        except Exception as e:
            logger.error(f"Ошибка настройки сети VM {vmid}: {e}")
            return False

    def bridge_exists(self, node: str, bridge_name: str) -> bool:
        """Проверить существование сетевого bridge"""
        try:
            # Получить конфигурацию сети ноды
            network_config = self.api.nodes(node).network.get()
            for iface in network_config:
                if iface.get('iface') == bridge_name:
                    return True
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки bridge {bridge_name}: {e}")
            return False

    def create_bridge(self, node: str, bridge_name: str, bridge_vlan_aware: bool = False) -> bool:
        """Создать сетевой bridge"""
        try:
            # Проверить существует ли bridge уже
            if self.bridge_exists(node, bridge_name):
                logger.info(f"Bridge {bridge_name} уже существует на ноде {node}")
                return True

            # Создать bridge интерфейс
            bridge_config = {
                'iface': bridge_name,
                'type': 'bridge',
                'autostart': 1
            }

            # Добавить параметр VLAN-aware если указан
            if bridge_vlan_aware:
                bridge_config['bridge_vlan_aware'] = True

            self.api.nodes(node).network.post(**bridge_config)
            logger.info(f"Bridge {bridge_name} создан на ноде {node}")
            return True

        except Exception as e:
            error_str = str(e)
            # Если bridge уже существует - считаем успехом
            if "already exists" in error_str.lower() or "interface already exists" in error_str.lower():
                logger.info(f"Bridge {bridge_name} уже существует на ноде {node} (обработано как успех)")
                return True
            # Если ошибка типа boolean - логируем и возвращаем False
            elif "type check" in error_str and "boolean" in error_str:
                logger.error(f"Ошибка типа параметра bridge_vlan_aware для bridge {bridge_name}: {e}")
                return False
            else:
                logger.error(f"Ошибка создания bridge {bridge_name}: {e}")
                return False

    def delete_bridge(self, node: str, bridge_name: str) -> bool:
        """Удалить сетевой bridge"""
        try:
            self.api.nodes(node).network.delete(bridge_name)
            logger.info(f"Bridge {bridge_name} удален с ноды {node}")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления bridge {bridge_name}: {e}")
            return False

    def list_bridges(self, node: str) -> List[str]:
        """Получить список всех bridge на ноде"""
        try:
            network_config = self.api.nodes(node).network.get()
            bridges = []
            for iface in network_config:
                if iface.get('type') == 'bridge':
                    bridges.append(iface.get('iface'))
            return bridges
        except Exception as e:
            logger.error(f"Ошибка получения списка bridges: {e}")
            return []

    def get_node_status(self, node: str) -> Dict:
        """
        Получить статус ноды (CPU, память и т.д.)

        Args:
            node: Имя ноды

        Returns:
            Словарь со статусом ноды
        """
        try:
            status = self.api.nodes(node).status.get()
            return status
        except Exception as e:
            logger.error(f"Ошибка получения статуса ноды {node}: {e}")
            return {}

    def convert_to_template(self, node: str, vmid: int) -> bool:
        """
        Преобразовать виртуальную машину в шаблон

        Args:
            node: Нода где размещена машина
            vmid: VMID машины для преобразования

        Returns:
            True если преобразование успешно
        """
        try:
            self.api.nodes(node).qemu(vmid).template.post()
            logger.info(f"VM {vmid} на ноде {node} преобразована в шаблон")
            return True
        except Exception as e:
            logger.error(f"Ошибка преобразования VM {vmid} в шаблон: {e}")
            return False

    def migrate_vm(self, source_node: str, target_node: str, vmid: int, online: bool = False) -> str:
        """
        Миграировать виртуальную машину между нодами

        Args:
            source_node: Исходная нода
            target_node: Целевая нода
            vmid: VMID машины для миграции
            online: True для онлайн миграции, False для оффлайн

        Returns:
            ID задачи миграции
        """
        try:
            migrate_params = {
                'target': target_node,
                'online': 1 if online else 0
            }

            task = self.api.nodes(source_node).qemu(vmid).migrate.post(**migrate_params)
            logger.info(f"Запущена миграция VM {vmid} с {source_node} на {target_node}")
            return task
        except Exception as e:
            logger.error(f"Ошибка миграции VM {vmid}: {e}")
            raise

    def bridge_in_use(self, node: str, bridge_name: str) -> bool:
        """Проверить используется ли bridge виртуальными машинами"""
        try:
            vms = self.get_vms_on_node(node)
            for vm in vms:
                vmid = vm.get('vmid')
                if vmid:
                    config = self.get_vm_config(node, vmid)
                    # Проверить есть ли ссылки на bridge в конфигурации VM
                    for key, value in config.items():
                        if key.startswith('net') and bridge_name in str(value):
                            return True
            return False
        except Exception as e:
            logger.error(f"Ошибка проверки использования bridge {bridge_name}: {e}")
            return True  # В случае ошибки считаем что используется

    def user_exists(self, userid: str) -> bool:
        """
        Проверить существует ли пользователь

        Args:
            userid: ID пользователя

        Returns:
            True если пользователь существует
        """
        try:
            users = self.api.access.users.get()
            return any(user.get('userid') == userid for user in users)
        except Exception as e:
            logger.error(f"Ошибка проверки существования пользователя {userid}: {e}")
            return False

    def pool_exists(self, poolid: str) -> bool:
        """
        Проверить существует ли пул

        Args:
            poolid: ID пула

        Returns:
            True если пул существует
        """
        try:
            pools = self.api.pools.get()
            return any(pool.get('poolid') == poolid for pool in pools)
        except Exception as e:
            logger.error(f"Ошибка проверки существования пула {poolid}: {e}")
            return False

    def get_pool_permissions(self, userid: str, poolid: str) -> List[str]:
        """
        Получить права пользователя на пул

        Args:
            userid: ID пользователя
            poolid: ID пула

        Returns:
            Список прав пользователя
        """
        try:
            acls = self.api.access.acl.get()
            user_permissions = []
            for acl in acls:
                if acl.get('users') == userid and acl.get('path') == f"/pool/{poolid}":
                    role = acl.get('role')
                    if role:
                        user_permissions.append(role)
            return user_permissions
        except Exception as e:
            logger.error(f"Ошибка получения прав пользователя {userid} на пул {poolid}: {e}")
            return []

    def get_pool_vms(self, poolid: str) -> List[Dict]:
        """
        Получить список виртуальных машин в пуле

        Args:
            poolid: ID пула

        Returns:
            Список VM в пуле
        """
        try:
            pool_vms = self.api.pools(poolid).get()
            return pool_vms.get('members', [])
        except Exception as e:
            logger.error(f"Ошибка получения VM пула {poolid}: {e}")
            return []

    def check_vm_network_config(self, node: str, vmid: int, expected_networks: List[Dict]) -> bool:
        """
        Проверить конфигурацию сети VM

        Args:
            node: Нода размещения VM
            vmid: VMID машины
            expected_networks: Ожидаемая конфигурация сети

        Returns:
            True если конфигурация сети соответствует ожиданиям
        """
        try:
            config = self.get_vm_config(node, vmid)

            # Извлечь все сетевые интерфейсы из конфигурации
            actual_networks = {}
            for key, value in config.items():
                if key.startswith('net'):
                    actual_networks[key] = value

            # Проверить соответствие количества интерфейсов
            if len(actual_networks) != len(expected_networks):
                logger.warning(f"VM {vmid}: количество сетевых интерфейсов не совпадает "
                             f"(ожидается {len(expected_networks)}, найдено {len(actual_networks)})")
                return False

            # Проверить каждый ожидаемый сетевой интерфейс
            for i, expected_net in enumerate(expected_networks):
                net_id = f"net{i}"
                if net_id in actual_networks:
                    actual_config = actual_networks[net_id]
                    expected_bridge = expected_net.get('bridge')
                    if expected_bridge not in actual_config:
                        logger.warning(f"VM {vmid}: интерфейс {net_id} не соответствует конфигурации "
                                     f"(ожидается bridge={expected_bridge}, найдено {actual_config})")
                        return False
                else:
                    logger.warning(f"VM {vmid}: отсутствует сетевой интерфейс {net_id}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Ошибка проверки сетевой конфигурации VM {vmid}: {e}")
            return False

    def reload_node_network(self, node: str) -> bool:
        """
        Перезагрузить конфигурацию сети ноды (PUT /nodes/{node}/network)

        Args:
            node: Имя ноды

        Returns:
            True если перезагрузка успешна
        """
        try:
            self.api.nodes(node).network.put()
            logger.info(f"Конфигурация сети ноды {node} обновлена")
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления конфигурации сети ноды {node}: {e}")
            return False

    def cleanup_unused_bridges(self, nodes: List[str]) -> int:
        """
        Очистить неиспользуемые сетевые мосты на всех нодах

        Args:
            nodes: Список нод для очистки

        Returns:
            Количество очищенных мостов
        """
        cleaned_count = 0

        for node in nodes:
            try:
                logger.info(f"🔍 Анализируем мосты на ноде {node}")

                # Получить все мосты на ноде
                bridges = self.list_bridges(node)
                logger.info(f"Найдено {len(bridges)} мостов на ноде {node}: {bridges}")

                # Получить все VM на ноде
                vms = self.get_vms_on_node(node)
                logger.info(f"Найдено {len(vms)} VM на ноде {node}")

                # Найти используемые мосты
                used_bridges = set()

                for vm in vms:
                    vmid = vm.get('vmid')
                    if vmid:
                        try:
                            vm_config = self.get_vm_config(node, vmid)
                            # Проверить все сетевые интерфейсы VM
                            for key, value in vm_config.items():
                                if key.startswith('net') and value:
                                    # Извлечь имя bridge из конфигурации сети
                                    # Формат: model=virtio,bridge=vmbr1001,firewall=1
                                    bridge_part = [part for part in str(value).split(',') if part.startswith('bridge=')]
                                    if bridge_part:
                                        bridge_name = bridge_part[0].split('=')[1]
                                        used_bridges.add(bridge_name)
                        except Exception as e:
                            logger.warning(f"Не удалось проверить конфигурацию VM {vmid}: {e}")

                logger.info(f"Используемые мосты на ноде {node}: {used_bridges}")

                # Найти неиспользуемые мосты (начинающиеся с vmbr и больше vmbr1000)
                unused_bridges = []
                for bridge in bridges:
                    if bridge.startswith('vmbr') and bridge != 'vmbr0':
                        try:
                            bridge_num = int(bridge.replace('vmbr', ''))
                            if bridge_num >= 1000 and bridge not in used_bridges:
                                unused_bridges.append(bridge)
                        except ValueError:
                            # Не числовой bridge, пропускаем
                            continue

                logger.info(f"Неиспользуемые мосты на ноде {node}: {unused_bridges}")

                # Удалить неиспользуемые мосты
                for bridge in unused_bridges:
                    try:
                        logger.info(f"🗑️ Удаляем неиспользуемый мост {bridge} на ноде {node}")
                        if self.delete_bridge(node, bridge):
                            cleaned_count += 1
                            logger.info(f"✅ Мост {bridge} удален")
                        else:
                            logger.error(f"❌ Не удалось удалить мост {bridge}")
                    except Exception as e:
                        logger.error(f"Ошибка удаления моста {bridge}: {e}")

            except Exception as e:
                logger.error(f"Ошибка анализа мостов на ноде {node}: {e}")

        logger.info(f"🧹 Очистка завершена: удалено {cleaned_count} неиспользуемых мостов")
        return cleaned_count
