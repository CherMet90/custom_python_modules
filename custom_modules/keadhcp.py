import datetime

import requests
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

disable_warnings(category=InsecureRequestWarning)


class KeaDHCP:
    session = requests.Session()
    session.verify = False
    last_response = None

    # Метод задаёт IP и порт для подключения к Kea-агенту
    @classmethod
    def set_kea_agent_address(cls, ip, port):
        cls.url = f"http://{ip}:{port}"
    
    @classmethod
    def post(cls, data):
        try:
            print(f"Отправка команды: {data.get('command', '')}")
            response = cls.session.post(cls.url, json=data, verify=False)
            cls.last_response = response
            if response.status_code == 200:
                response_data = response.json()
                # Выводим описание ответа, если оно доступно
                print(f'Успешно: {response_data[0].get("text", f"{response.text[:100]} ...")}')
                return response_data
            else:
                try:
                    print(
                        f'Ошибка: {response.json()[0].get("text", f"{response.text[:100]} ...")}')
                except Exception:
                    print(f"Ошибка с кодом: {response.status_code}, тело ответа: {response.text}")
                return None
        except Exception as e:
            print(f"Произошла ошибка: {e}")
            return None

    @classmethod
    def lease_add(cls, ip, mac, subnet_id=0):
        data = {
            "command": "lease4-add",
            "arguments": {
                "ip-address": ip,
                "hw-address": mac,
                "subnet-id": subnet_id
            },
            "service": ['dhcp4'],
        }
        cls.post(data)

    @classmethod
    def lease_del_by_ip(cls, ip):
        data = {
            "command": "lease4-del",
            "arguments": {
                "ip-address": ip
            },
            "service": ['dhcp4'],
        }
        cls.post(data)

    @classmethod
    def lease_del_by_mac(cls, mac, subnet_id=0):
        data = {
            "command": "lease4-del",
            "arguments": {
                "identifier": mac,
                "identifier-type": "hw-address",
                "subnet-id": subnet_id
            },
            "service": ['dhcp4'],
        }
        cls.post(data)

    @classmethod
    def lease_update(cls, ip, mac, hostname="", subnet_id=0, force_create=True):
        data = {
            "command": "lease4-update",
            "arguments": {
                "ip-address": ip,
                "hw-address": mac,
                "subnet-id": subnet_id,
                "hostname": hostname,
                "force-create": force_create
            },
            "service": ['dhcp4'],
        }
        cls.post(data)

    @classmethod
    def config_get(cls):
        data = {
            "command": "config-get",
            "service": ['dhcp4'],
        }
        response = cls.post(data)
        if response and response[0]["result"] == 0:
            return response[0].get('arguments', {}).get('Dhcp4', {})
        else:
            return {}

    @classmethod
    def get_subnets(cls):
        config = cls.config_get()
        return config.get('subnet4', [])

    @classmethod
    def find_subnet_id(cls, subnet_pattern):
        subnets = cls.get_subnets()
        found_subnet = [
            {'subnet': subnet.get('subnet'), 'id': subnet.get('id')}
            for subnet in subnets if subnet_pattern in subnet.get('subnet')
        ]
        for subnet in found_subnet:
            print(f"ID: {subnet.get('id')} | Подсеть: {subnet.get('subnet')}")

    @classmethod
    def lease_get_all(cls):
        data = {
            "command": "lease4-get-all",
            "service": ['dhcp4'],
        }
        response = cls.post(data)
        return response[0].get('arguments', {}).get('leases', []) if response else []

    @classmethod
    def find_leases_with_empty_mac(cls):
        leases = cls.lease_get_all()
        found_leases = [lease for lease in leases if lease['hw-address'] == '']
        for lease in found_leases:
            cltt = datetime.datetime.fromtimestamp(lease['cltt']).strftime('%Y.%m.%d %H:%M:%S')
            print(f"IP: {lease['ip-address']},\t"
                  f"MAC: {lease['hw-address']},\t"
                  f"Subnet ID: {lease['subnet-id']},\t"
                  f"CLTT: {cltt},\t"
                  f"Valid LFT: {lease['valid-lft']},\t"
                  f"Hostname: '{lease['hostname']}'")
        if not found_leases:
            print("Аренды по c пустым MAC не найдены!")

    @classmethod
    def del_leases_with_empty_mac(cls):
        leases = cls.lease_get_all()
        found_leases = [lease for lease in leases if lease['hw-address'] == '']
        for lease in found_leases:
            cltt = datetime.datetime.fromtimestamp(lease['cltt']).strftime('%Y.%m.%d %H:%M:%S')
            print(f"IP: {lease['ip-address']},\t"
                  f"MAC: {lease['hw-address']},\t"
                  f"Subnet ID: {lease['subnet-id']},\t"
                  f"CLTT: {cltt},\t"
                  f"Valid LFT: {lease['valid-lft']},\t"
                  f"Hostname: '{lease['hostname']}'")
            cls.lease_del_by_ip(lease['ip-address'])
        if not found_leases:
            print("Аренды по c пустым MAC не найдены!")

    @classmethod
    def find_leases_by_pattern(cls, pattern):
        leases = cls.lease_get_all()
        found_leases = [lease for lease in leases if
                        pattern in lease.get('ip-address') or pattern in lease.get('hw-address')]
        for lease in found_leases:
            cltt = datetime.datetime.fromtimestamp(lease['cltt']).strftime('%Y.%m.%d %H:%M:%S')
            print(f"IP: {lease['ip-address']},\t"
                  f"MAC: {lease['hw-address']},\t"
                  f"Subnet ID: {lease['subnet-id']},\t"
                  f"CLTT: {cltt},\t"
                  f"Valid LFT: {lease['valid-lft']},\t"
                  f"Hostname: '{lease['hostname']}'")
        if not found_leases:
            print("Аренды по шаблону не найдены!")

    @classmethod
    def lease_write(cls, filename='/tmp/lease_file.csv'):
        data = {
            "command": "lease4-write",
            "arguments": {
                "filename": filename
            },
            "service": ['dhcp4'],
        }
        cls.post(data)

    @classmethod
    def lease_wipe(cls, subnet_id):
        data = {
            "command": "lease4-wipe",
            "arguments": {
                "subnet-id": subnet_id
            },
            "service": ['dhcp4'],
        }
        cls.post(data)

    @classmethod
    def list_commands(cls):
        data = {
            "command": "list-commands",
            "arguments": {
            },
            "service": ['dhcp4'],
        }
        response = cls.post(data)
        if response:
            print("Список доступных команд:")
            for command in response[0].get('arguments', []):
                print(command)

    @classmethod
    def version_get(cls):
        data = {
            "command": "version-get",
            "service": ['dhcp4'],
        }
        cls.post(data)

    @classmethod
    def dhcp_enable(cls):
        data = {
            "command": "dhcp-enable",
            "arguments": {
                "origin": "user"
            },
            "service": ['dhcp4'],
        }
        cls.post(data)

    @classmethod
    def dhcp_disable(cls):
        data = {
            "command": "dhcp-disable",
            "arguments": {
                "origin": "user"
            },
            "service": ['dhcp4'],
        }
        cls.post(data)
