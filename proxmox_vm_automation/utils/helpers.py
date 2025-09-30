# utils/helpers.py
def find_free_vmid(proxmox_client, start=100, end=999):
    """Находит первый свободный VMID"""
    used_ids = set()

    # Получаем все ресурсы
    resources = proxmox_client.client.cluster.resources.get()
    for item in resources:
        if "vmid" in item:
            used_ids.add(item["vmid"])

    for vmid in range(start, end + 1):
        if vmid not in used_ids:
            return vmid
    raise Exception("Не найдено свободного VMID")