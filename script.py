#!/usr/bin/env python3
import module.user_from_file as user_from_file
import module.get_free_vmid as get_free_vmid
import os

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
        new_vmid = get_free_vmid.get_free_vmid(proxmox, start_from=1000)
        proxmox.nodes('SRV1-PVE').qemu('100').clone.post(
            newid=new_vmid,
            target=node_claster,
            pool=user.split('@')[0],
            name='vm1'
        )

if __name__ == "__main__":
    main()