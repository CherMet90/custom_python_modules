import datetime

import requests
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

disable_warnings(category=InsecureRequestWarning)


class KeaDHCP:
    def __init__(self, ip, port):
        self.session = requests.Session()
        self.session.verify = False
        self.last_response = None
        self.url = f"http://{ip}:{port}"
        self.config = self.__get_config()
        self.static_list = []
        self.pool_list = []

    def __get_config(self):
        data = {
            "command": "config-get",
            "service": ['dhcp4'],
        }
        response = self.__post(data)
        if response and response[0]["result"] == 0:
            return response[0].get('arguments', {}).get('Dhcp4', {})
        else:
            return {}
    
    def __post(self, data):
        try:
            print(f"Отправка команды: {data.get('command', '')}")
            response = self.session.post(self.url, json=data, verify=False)
            self.last_response = response
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

    def lease_add(self, ip, mac, subnet_id=0):
        data = {
            "command": "lease4-add",
            "arguments": {
                "ip-address": ip,
                "hw-address": mac,
                "subnet-id": subnet_id
            },
            "service": ['dhcp4'],
        }
        self.__post(data)

    def lease_del_by_ip(self, ip):
        data = {
            "command": "lease4-del",
            "arguments": {
                "ip-address": ip
            },
            "service": ['dhcp4'],
        }
        self.__post(data)

    def lease_del_by_mac(self, mac, subnet_id=0):
        data = {
            "command": "lease4-del",
            "arguments": {
                "identifier": mac,
                "identifier-type": "hw-address",
                "subnet-id": subnet_id
            },
            "service": ['dhcp4'],
        }
        self.__post(data)

    def lease_update(self, ip, mac, hostname="", subnet_id=0, force_create=True):
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
        self.__post(data)

    def get_subnets(self):
        return self.config.get('subnet4', [])

    def find_subnet_id(self, subnet_pattern):
        subnets = self.get_subnets()
        found_subnet = [
            {'subnet': subnet.get('subnet'), 'id': subnet.get('id')}
            for subnet in subnets if subnet_pattern in subnet.get('subnet')
        ]
        for subnet in found_subnet:
            print(f"ID: {subnet.get('id')} | Подсеть: {subnet.get('subnet')}")

    def lease_get_all(self):
        data = {
            "command": "lease4-get-all",
            "service": ['dhcp4'],
        }
        response = self.__post(data)
        return response[0].get('arguments', {}).get('leases', []) if response else []

    def find_leases_with_empty_mac(self):
        leases = self.lease_get_all()
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

    def del_leases_with_empty_mac(self):
        leases = self.lease_get_all()
        found_leases = [lease for lease in leases if lease['hw-address'] == '']
        for lease in found_leases:
            cltt = datetime.datetime.fromtimestamp(lease['cltt']).strftime('%Y.%m.%d %H:%M:%S')
            print(f"IP: {lease['ip-address']},\t"
                  f"MAC: {lease['hw-address']},\t"
                  f"Subnet ID: {lease['subnet-id']},\t"
                  f"CLTT: {cltt},\t"
                  f"Valid LFT: {lease['valid-lft']},\t"
                  f"Hostname: '{lease['hostname']}'")
            self.lease_del_by_ip(lease['ip-address'])
        if not found_leases:
            print("Аренды по c пустым MAC не найдены!")

    def find_leases_by_pattern(self, pattern):
        leases = self.lease_get_all()
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

    def lease_write(self, filename='/tmp/lease_file.csv'):
        data = {
            "command": "lease4-write",
            "arguments": {
                "filename": filename
            },
            "service": ['dhcp4'],
        }
        self.__post(data)

    def lease_wipe(self, subnet_id):
        data = {
            "command": "lease4-wipe",
            "arguments": {
                "subnet-id": subnet_id
            },
            "service": ['dhcp4'],
        }
        self.__post(data)

    def list_commands(self):
        data = {
            "command": "list-commands",
            "arguments": {
            },
            "service": ['dhcp4'],
        }
        response = self.__post(data)
        if response:
            print("Список доступных команд:")
            for command in response[0].get('arguments', []):
                print(command)

    def version_get(self):
        data = {
            "command": "version-get",
            "service": ['dhcp4'],
        }
        self.__post(data)

    def dhcp_enable(self):
        data = {
            "command": "dhcp-enable",
            "arguments": {
                "origin": "user"
            },
            "service": ['dhcp4'],
        }
        self.__post(data)

    def dhcp_disable(self):
        data = {
            "command": "dhcp-disable",
            "arguments": {
                "origin": "user"
            },
            "service": ['dhcp4'],
        }
        self.__post(data)

    def static_get_all(self):
        for subnet in self.config.get('subnet4', []):
            for static in subnet.get('reservations', []):
                self.static_list.append({
                    'ip-address': static.get('ip-address'),
                    'hw-address': static.get('hw-address'),
                    'subnet-id': subnet.get('id'),
                    'valid-lft': subnet.get("valid-lifetime"),
                    'hostname': static.get('hostname'),
                    'boot-file-name': static.get('boot-file-name'),
                    'client-classes': static.get('client-classes'),
                    'option-data': static.get('option-data'),
                    'server-hostname': static.get('server-hostname'),
                    'next-server': static.get('next-server'),
                })
        return self.static_list

    def get_pools(self):
        for subnet in self.config.get('subnet4', []):
            for pool in subnet.get('pools', []):
                self.pool_list.append(pool.get('pool'))
        return self.pool_list