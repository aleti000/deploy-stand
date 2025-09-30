#get_free_vmid

def get_free_vmid(proxmox, start_from=100):
    """
    Находит первый свободный VMID в кластере.
    
    :param proxmox: экземпляр ProxmoxAPI
    :param start_from: с какого ID начинать поиск
    :return: свободный VMID
    """
    used_ids = set()

    # Получаем все ресурсы кластера
    resources = proxmox.cluster.resources.get()
    
    for resource in resources:
        if 'vmid' in resource:  # это ВМ (qemu) или контейнер (lxc)
            used_ids.add(resource['vmid'])

    # Ищем первый свободный ID
    vmid = start_from
    while vmid in used_ids:
        vmid += 1

    return vmid