#!/usr/bin/env python3

def users():
    try:
        with open('users.txt', 'r') as file:
            user_list = [line.strip() for line in file ]
    except FileNotFoundError:
         print("Файл не найден!")
    return user_list