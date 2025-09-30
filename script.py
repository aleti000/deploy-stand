#!/usr/bin/env python3
import user_from_file


from proxmoxer import ProxmoxAPI
proxmox = ProxmoxAPI(
    host= '192.168.100.5',
    user='root@pam',
    password='OsI7q3Z',
    verify_ssl=False
)
    ### Считываем количество нод и их имена
nodes=proxmox.nodes.get()
node_names = [node['node'] for node in nodes]
    ### Считывание пользователей из файла users.txt в массив user_list
user_list=user_from_file.users() 
#print(user_list)
def choice_node():
    count=user_list%len(node_names)
    print(count)

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

def main():
    
    for i, user in enumerate(user_list):
        node_claster=node_names[i % len(node_names)]
        try:
            proxmox.access.users(user).get()
            print('Пользователь', user.split('@')[0], 'существует!')
        except Exception as e:
            proxmox.access.users.post(
                userid=user,
                password='12345678'
            )
            print('Пользователь', user.split('@')[0], 'создан!')
        try:
            proxmox.pools(user.split('@')[0]).get()
            print('Пул', user.split('@')[0], 'создан!')
        except Exception as e:
            proxmox.pools.post(
            poolid=user.split('@')[0]
            )
            print('Пул', user.split('@')[0], 'существует!')
        ### клонирование машины altsrv
        new_vmid = get_free_vmid(proxmox, start_from=100)
        proxmox.nodes('SRV1-PVE').qemu('100').clone.post(
            newid=new_vmid,
            target=node_claster,
            pool=user.split('@')[0],
            name='vm1'
        )

if __name__ == "__main__":
    main()