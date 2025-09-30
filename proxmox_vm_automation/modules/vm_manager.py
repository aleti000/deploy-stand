# modules/vm_manager.py
from core.api_client import ProxmoxClient
from utils.helpers import find_free_vmid


def get_first_online_node(proxmox_client):
    """
    Возвращает объект ноды (например, proxmox.nodes('SRV1-PVE'))
    Выбирает первую онлайн-ноду из кластера.
    """
    try:
        nodes = proxmox_client.client.nodes.get()
        for node in nodes:
            if node["status"] == "online":
                print(f"✅ Используем ноду: {node['node']}")
                return proxmox_client.client.nodes(node["node"])
        raise Exception("❌ Нет доступных онлайн-нод в кластере.")
    except Exception as e:
        print(f"❌ Ошибка получения списка нод: {e}")
        raise


def create_simple_vm(name: str):
    client_wrapper = ProxmoxClient()
    proxmox = client_wrapper.client

    try:
        # 🔹 Авто-выбор ноды
        node = get_first_online_node(client_wrapper)

        # 🔹 Поиск свободного VMID
        vmid = find_free_vmid(client_wrapper)
        print(f"Найден свободный VMID: {vmid}")

        # 🔹 Создание ВМ
        node.qemu.create(
            vmid=vmid,
            name=name,
            memory=1024,
            cores=1,
            net0="virtio,bridge=vmbr0",
            onboot=1,
            storage="local-lvm",
            virtio0="local-lvm:4",  # диск 4 ГБ
        )

        print(f"✅ ВМ '{name}' (ID: {vmid}) успешно создана на ноде!")
        return True

    except Exception as e:
        print(f"❌ Ошибка создания ВМ: {e}")
        return False