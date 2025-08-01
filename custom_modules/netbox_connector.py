import inspect
import ipaddress
import os
import re
import traceback

from dotenv import load_dotenv
import pynetbox
from colorama import init
from transliterate import translit, get_available_language_codes

from custom_modules.errors import Error, NonCriticalError
from custom_modules.log import logger

# Initialize Colorama
init()

# Загружаем .env файл
load_dotenv()

class NetboxDevice:
    # Получение переменных окружения
    # =====================================================================
    @staticmethod
    def __get_env_variable(variable_key):
        variable_value = os.environ.get(variable_key)
        if variable_value is None:
            raise ValueError(f"Missing environment variable: {variable_key}")
        return variable_value

    __netbox_url = __get_env_variable("NETBOX_URL")
    __netbox_token = __get_env_variable("NETBOX_TOKEN")
    # ====================================================================

    # Создание netbox соединения

    @classmethod
    def create_connection(cls):
        try:
            cls.netbox_connection = pynetbox.api(
                url=cls.__netbox_url,
                token=cls.__netbox_token
            )
            logger.info("Connection to NetBox established")
        except Exception as e:
            traceback.print_exc()
            raise e
        cls.netbox_prefixes = list(cls.netbox_connection.ipam.prefixes.all())

    # Получение вланов сайта из netbox
    @classmethod
    def get_vlans(cls, site_slug):
        try:
            vlans = list(
                cls.netbox_connection.ipam.vlans.filter(site=site_slug))
            # Extract VLAN IDs from the objects
            vlan_ids = [str(vlan.vid) for vlan in vlans]
            logger.debug(f"Found {len(vlan_ids)} VLANs for site {site_slug}")
            return vlans
        except pynetbox.core.query.RequestError as e:
            error_message = f"Request failed for site {site_slug}"
            calling_function = inspect.stack()[1].function
            NonCriticalError(error_message, site_slug, calling_function)
            return None

    @classmethod
    def get_netbox_ip(cls, ip_with_prefix, create=True):
        logger.info(f'Getting IP object from NetBox...')
        netbox_ip = cls.netbox_connection.ipam.ip_addresses.get(
            address=ip_with_prefix,
        )
        if not netbox_ip:
            if create:
                logger.info(f'IP {ip_with_prefix} not found in NetBox. Creating...')
                netbox_ip = cls.netbox_connection.ipam.ip_addresses.create(
                    address=ip_with_prefix,
                    status='active',
                )
            else:
                logger.info(f'IP {ip_with_prefix} not found in NetBox')
                return None
        
        parent_prefix = list(cls.netbox_connection.ipam.prefixes.filter(contains=ip_with_prefix))
        site_slug = parent_prefix[0].site.slug
        return netbox_ip, site_slug
    
    @classmethod
    def set_description(cls, device_name, interface_name, neighbor_name, neighbor_interface):
        netbox_interface = cls.netbox_connection.dcim.interfaces.get(
            name=interface_name, device=device_name
        )
        netbox_interface.description = f'-={neighbor_name}  {neighbor_interface}=-'
        netbox_interface.save()

    @classmethod
    def get_prefix_for_ip(cls, ip_addr):
        for prefix in cls.netbox_prefixes:
            if ipaddress.ip_address(ip_addr) in ipaddress.ip_network(prefix):
                return prefix
        raise Error("IP address not found in NetBox prefixes", ip_addr)
    
    @classmethod
    def create_ip_address(cls, ip, ip_with_prefix, status='active', description='', dns_name=''):
        logger.debug(f'Checking if IP address {ip_with_prefix} exists...')
        existing_ips = cls.netbox_connection.ipam.ip_addresses.filter(address=ip)
        if existing_ips:
            logger.debug(
                f'IP address {ip_with_prefix} already exists in NetBox (skipping creation, update only)')
            for existing_ip in existing_ips:
                if description and (description != existing_ip.description or status != existing_ip.status):
                    logger.info(f'Updating IP address {ip_with_prefix}...')
                    existing_ip.description = description
                    existing_ip.status = status
                    existing_ip.save()
                    return existing_ip
                if dns_name and dns_name != existing_ip.dns_name:
                    logger.info(f'Updating DNS name for IP address {ip_with_prefix}...')
                    existing_ip.dns_name = dns_name
                    existing_ip.save()
                    return existing_ip
            return
        logger.info(f'Creating IP address {ip_with_prefix}...')
        created_ip = cls.netbox_connection.ipam.ip_addresses.create(
            address=ip_with_prefix,
            status=status,
            description=description,
            dns_name=dns_name
        )
        return created_ip
    
    @classmethod
    def get_roles(cls):
        cls.roles = {
            role.name: role for role in cls.netbox_connection.dcim.device_roles.all()
        }
        logger.debug("Roles retrieved from NetBox API")

    @classmethod
    def get_vms_by_role(cls, role):
        return cls.netbox_connection.virtualization.virtual_machines.filter(
                role_id=role.id
            )

    @classmethod
    def get_services_by_vm(cls, vm):
        return cls.netbox_connection.ipam.services.filter(
            virtual_machine=vm.name
        )

    @classmethod
    def remove_ip_range(cls, start_ip, end_ip):
        start_ip = ipaddress.IPv4Address(start_ip)
        end_ip = ipaddress.IPv4Address(end_ip)
        ip_list = [str(ipaddress.IPv4Address(ip)) for ip in range(int(start_ip), int(end_ip) + 1)]
        for ip in ip_list:
            ip_no_prefix = ip.split('/')[0]
            ip_obj = list(cls.netbox_connection.ipam.ip_addresses.filter(address=ip_no_prefix))
            if len(ip_obj) == 1:
                if ip_obj[0].assigned_object or ip_obj[0].dns_name:
                    ip_obj[0].status = 'dhcp'
                    ip_obj[0].description = ''
                    ip_obj[0].save()
                    logger.debug(f'{ip_no_prefix} status set to DHCP')
                else:
                    ip_obj[0].delete()
                    logger.debug(f'{ip_no_prefix} deleted')
    
    @classmethod
    def get_netbox_objects(cls, *path_segments, action=None, **search_params):
        netbox_api = cls.netbox_connection
        # Flatten out dot-delimited string segments into individual segments
        segments = []
        for segment in path_segments:
            segments.extend(segment.split('.'))
        # Traverse the pynetbox API segments
        for segment in segments:
            netbox_api = getattr(netbox_api, segment)
        if action:
            method = getattr(netbox_api, action)
            try:
                return method(**search_params)
            except Exception as e:
                Error(f"Failed to {action} NetBox object: {e}")
                return None
        else:
            raise ValueError("Action (e.g., 'get', 'filter') must be specified.")

    @classmethod
    def update_ip_address(cls, ip_address, **kwargs):
        """
        Update IP address properties in Netbox.

        Args:
            ip_address (str): IP address to update
            **kwargs: Properties to update (e.g., status, description, etc.)

        Returns:
            bool: True if update was successful, False otherwise
        """
        try:
            prefix = cls.get_prefix_for_ip(ip_address)
            ip_with_prefix = f'{ip_address}/{prefix.prefix.split("/")[1]}'
            netbox_ip, _ = cls.get_netbox_ip(ip_with_prefix, create=False)

            if netbox_ip:
                for key, value in kwargs.items():
                    setattr(netbox_ip, key, value)
                netbox_ip.save()
                logger.debug(f'Updated IP {ip_address} in Netbox: {kwargs}')
                return True
            else:
                logger.warning(f'IP {ip_address} not found in Netbox. Skipping update.')
                return False
        except Exception as e:
            logger.error(f'Error updating IP {ip_address} in Netbox: {e}')
            return False

    # Создаем экземпляр устройства netbox
    def __init__(self, site_slug, role, hostname, vlans=None, vm=False, model=None, serial_number=None, ip_address=None, cluster_name=None, cluster_type=None, status='active', vcpus=None, mem=None, description=None) -> None:
        self.hostname = hostname
        self.__site_slug = site_slug
        self.__model = model
        self.__role = role
        self.__serial_number = serial_number
        self.__vlans = vlans
        self.__ip_address = ip_address
        self.__vm = vm
        self.__netbox_device_role = None
        self.__cluster_name = cluster_name
        self.__cluster_type = cluster_type
        self.__status = status
        self.__vcpus = vcpus
        self.__mem = mem
        self.__description = description
        
        # Константы состояний и атрибут отслеживания изменений
        self.CREATED, self.UPDATED = 1, 2
        self._change_state = 0  # 0 – нет изменений, 1 – создано, 2 – обновлено

        # Получение объекта сайта из NetBox
        self.__netbox_site = self.netbox_connection.dcim.sites.get(
            slug=self.__site_slug)
        if not self.__netbox_site:
            self.__critical_error_not_found("site", self.__site_slug)
        # Получение объекта роли устройства из NetBox
        if self.__role:
            self.__netbox_device_role = self.netbox_connection.dcim.device_roles.get(
                name=self.__role)
        # Разрешить работу без роли для ВМ
        if not self.__netbox_device_role and not self.__vm:
            self.__critical_error_not_found("device role", self.__role)
        # Если есть кластер, получаем его объект из NetBox
        if self.__cluster_name and self.__cluster_type:
            self.__get_netbox_cluster()

        # Создание/получение устройства или ВМ
        self.__netbox_device = self.__create_or_update_netbox_vm() if self.__vm else self.__get_netbox_device()
        
        # Выбор действия в зависимости от наличия или отсутствия устройства в NetBox
        self.__create_device() if not self.__netbox_device else self.__check_serial_number()

    @property
    def change_state(self) -> int:
        """
        Возвращает состояние изменений устройства:
        0 – нет изменений
        1 – устройство создано  
        2 – устройство обновлено
        """
        return self._change_state

    def __create_or_update_netbox_vm(self):
        # Получение списка ВМ по имени (без учета регистра) из Netbox
        vms = self.netbox_connection.virtualization.virtual_machines.filter(
            name=self.hostname
        )
        # Отфильтровываем ВМ, чтобы имя совпадало полностью с учетом регистра
        self.__netbox_device = [vm for vm in vms if vm.name == self.hostname]

        # Если список пустой или содержит больше одного элемента это ошибка
        if len(self.__netbox_device) > 1:
            raise Error(f"{self.hostname}: found several VMs with the same name")
        elif len(self.__netbox_device) == 0:
            pass
        else:
            # Успешно найдена одна ВМ с точно совпадающим именем
            self.__netbox_device = self.__netbox_device[0]  # Выбираем первый (и единственный) элемент списка
        
        if self.__netbox_device:
            # Prepare data for updating
            has_changes = False
            fields_to_update = ['site', 'status', 'vcpus', 'memory', 'cluster', 'comments']
            update_values = {
                'site': self.__netbox_site.id,
                'status': self.__status,
                'vcpus': self.__vcpus,
                'memory': self.__mem,
                'cluster': self.__netbox_cluster.id,
                'comments': self.__description,
                # Add other fields as necessary
            }

            # Check for changes
            for field in fields_to_update:
                if str(getattr(self.__netbox_device, field, '')) != str(update_values[field]):
                    setattr(self.__netbox_device, field, update_values[field])
                    has_changes = True

            if has_changes:
                logger.info(f'Updating virtual machine {self.hostname} in NetBox...')
                try:
                    self.__netbox_device.save()
                    # Устанавливаем флаг обновления, если ещё не было создания
                    if self._change_state == 0:
                        self._change_state = self.UPDATED
                except Exception as e:
                    raise Error(f'Failed to update virtual machine {self.hostname} in NetBox.\n{e}', self.__ip_address)
            else:
                logger.info(f'No updates required for virtual machine {self.hostname}.')
        else:
            logger.debug(f'Virtual machine {self.__ip_address} not found in NetBox')
            if self.__ip_address:
                netbox_device = self.netbox_connection.dcim.devices.get(
                    name=self.__ip_address
                )
                if netbox_device:
                    raise Error(f'There is a device with IP address {self.__ip_address} in NetBox')

            logger.info(f'Creating virtual machine {self.__ip_address} in NetBox...')
            self.__netbox_device = self.netbox_connection.virtualization.virtual_machines.create(
                name=self.hostname,
                site=self.__netbox_site.id,
                status=self.__status,
                vcpus=self.__vcpus,
                memory=self.__mem,
                cluster=self.__netbox_cluster.id,
                comments=self.__description,
            )
            self._change_state = self.CREATED
        
        return self.__netbox_device
    
    def __get_netbox_device(self):
        device = self.netbox_connection.dcim.devices.get(
            name=self.hostname, site=self.__site_slug)
        return device

    def __check_serial_number(self):
        if self.__serial_number and hasattr(self.__netbox_device, 'serial') and self.__netbox_device.serial != self.__serial_number:
            self.__netbox_device.serial = self.__serial_number
            self.__netbox_device.save()

            # Устанавливаем флаг обновления, если ещё не было создания
            if self._change_state == 0:
                self._change_state = self.UPDATED

            logger.debug(
                f'Serial number {self.__netbox_device.serial} was changed to {self.__serial_number}', self.__ip_address)

    def __critical_error_not_found(self, item_type, item_value):
        error_msg = f"{item_type} {item_value} not found in NetBox."
        raise Error(error_msg, self.__ip_address)

    def __create_device(self):
        
        logger.debug("Creating device...")

        self.__netbox_device_type = self.netbox_connection.dcim.device_types.get(
            model=self.__model)
        if not self.__netbox_device_type:
            self.__critical_error_not_found("device type", self.__model)

        # Создаем устройство в NetBox
        self.__netbox_device = self.netbox_connection.dcim.devices.create(
            name=self.hostname,
            device_type=self.__netbox_device_type.id,
            site=self.__netbox_site.id,
            device_role=self.__netbox_device_role.id,
            status="active",
        )
        
        # Устанавливаем флаг создания
        self._change_state = self.CREATED

        # Костыль на случай отсутствия серийного номера
        if self.__serial_number:
            self.__netbox_device.serial = self.__serial_number
            self.__netbox_device.save()

        logger.debug("Device created")

    def __get_netbox_interface(self, interface):
        logger.info(
            f"Checking if interface {interface.name} already exists in NetBox...")
        
        if self.__vm:
            existing_interface = self.netbox_connection.virtualization.interfaces.get(
                name=interface.name, virtual_machine=self.__netbox_device.name
            )
        else:
            existing_interface = self.netbox_connection.dcim.interfaces.get(
                name=interface.name, device=self.__netbox_device.name
            )
        
        if not existing_interface:
            if not interface.type:
                interface.type = "other"
            logger.debug(f"Creating interface {interface.name}...")
            if self.__vm:
                existing_interface = self.netbox_connection.virtualization.interfaces.create(
                    name=interface.name,
                    virtual_machine=self.__netbox_device.id,
                    type=interface.type,
                )
            else:
                existing_interface = self.netbox_connection.dcim.interfaces.create(
                    name=interface.name,
                    device=self.__netbox_device.id,
                    type=interface.type,
                )
        else:
            logger.debug(f"Interface {interface.name} already exists")

        self.__netbox_interface = existing_interface

    def delete_interfaces(self):
        """
        Delete all interfaces of the current device in Netbox
        """
        if not self.__netbox_device:
            raise Error("NetBox device not defined. Cannot delete interfaces.")

        logger.info(f"Deleting all interfaces for device {self.__netbox_device.name}...")

        # Получаем все интерфейсы устройства
        if self.__vm:
            interfaces = self.netbox_connection.virtualization.interfaces.filter(virtual_machine_id=self.__netbox_device.id)
        else:
            interfaces = self.netbox_connection.dcim.interfaces.filter(device_id=self.__netbox_device.id)

        for interface in interfaces:
            if interface.count_ipaddresses == 0:
                logger.debug(f"Deleting interface {interface.name}...")
                try:
                    interface.delete()
                except pynetbox.core.query.RequestError as e:
                    error_message = f"Failed to delete interface {interface.name} for device {self.__netbox_device.name}\n{e}"
                    NonCriticalError(error_message, interface.name, self.delete_interfaces.__name__)
            else:
                logger.debug(f"Skipping interface {interface.name} as it has associated IP addresses.")

        logger.info(f"All unused interfaces for device {self.__netbox_device.name} have been deleted.")

    def add_interface(self, interface):
        self.__get_netbox_interface(interface)

        if self.__netbox_interface:
            update_fields = ['name', 'mtu', 'mac_address', "description", 'mode']
            for field in update_fields:
                val = getattr(interface, field, None)
                if val is not None:
                    setattr(self.__netbox_interface, field, val)
            if hasattr(interface, 'untagged') or hasattr(interface, 'tagged'):
                self.__netbox_interface.untagged_vlan = next(
                    (vlan for vlan in self.__vlans if str(vlan.vid) == interface.untagged), None)
                self.__netbox_interface.tagged_vlans = [
                    vlan for vlan_id in interface.tagged or []
                    for vlan in self.__vlans
                    if str(vlan.vid) == vlan_id
                ]
            self.__netbox_interface.save()

            if hasattr(interface, 'ip_with_prefix'):
                logger.debug(f"Interface {interface.name} has IP addresses")
                if isinstance(interface.ip_with_prefix, list):
                    for ip_with_prefix in interface.ip_with_prefix:
                        self.__create_ip_address(interface, ip_with_prefix)
                else:
                    self.__create_ip_address(interface, interface.ip_with_prefix)

    def __create_ip_address(self, interface, ip_with_prefix):
        try:
            def handle_existing_ip(existing_ip):
                # Проверяем совпадает ли префикс у найденного в NetBox ip-адреса
                if existing_ip.address == ip_with_prefix:
                    logger.debug(
                        f"IP address {ip_with_prefix} already exists")
                    if self.__vm:
                        existing_ip.assigned_object_type = "virtualization.vminterface"
                    else:
                        existing_ip.assigned_object_type = "dcim.interface"
                    existing_ip.assigned_object_id = self.__netbox_interface.id
                    existing_ip.save()
                else:
                    # Удаляем ip в NetBox, если префикс не совпал
                    delete_and_create_new_ip(existing_ip)

            def delete_and_create_new_ip(existing_ip):
                logger.debug(f"Deleting IP address {existing_ip}...")
                existing_ip.delete()
                if len(existing_ips) < 2:
                    create_new_ip()
                existing_ips.remove(existing_ip)   # Remove the deleted IP

            def create_new_ip():
                logger.debug(
                    f"Creating IP address {ip_with_prefix}...")
                if self.__vm:
                    return self.netbox_connection.ipam.ip_addresses.create(
                        address=ip_with_prefix,
                        status="active",
                        assigned_object_type="virtualization.vminterface",
                        assigned_object_id=self.__netbox_interface.id,
                    )
                else:
                    return self.netbox_connection.ipam.ip_addresses.create(
                        address=ip_with_prefix,
                        status="active",
                        assigned_object_type="dcim.interface",
                        assigned_object_id=self.__netbox_interface.id,
                    )

            logger.debug(
                f"Checking if IP address {ip_with_prefix} already exists in NetBox...")
            existing_ips = list(self.netbox_connection.ipam.ip_addresses.filter(
                address=ip_with_prefix
            ))

            if existing_ips:
                for existing_ip in existing_ips:
                    handle_existing_ip(existing_ip)
            else:
                create_new_ip()

            if ip_with_prefix.split('/')[0] == self.__ip_address:
                # if str(self.__netbox_device.primary_ip4) != interface.ip_with_prefix:
                logger.debug(f"Setting {ip_with_prefix} as primary IP address")
                self.__netbox_device.primary_ip4 = {
                    'address': ip_with_prefix}
                self.__netbox_device.save()

        except pynetbox.core.query.RequestError as e:
            error_message = f"Request failed for IP address {ip_with_prefix}\n{e}"
            calling_function = inspect.stack()[1].function
            NonCriticalError(
                error_message, ip_with_prefix, calling_function)

    def connect_to_neighbor(self, neighbor_device, interface):
        def recreate_cable():
            logger.debug(f'Deleting the cable...')
            # Если есть кабель со стороны хоста - удаляем
            if self.__netbox_interface.cable:
                self.__netbox_interface.cable.delete()
            # Дествия с кабелем со стороны свича
            if self.__neighbor_interface.cable:
                # Проверить наличие конечного устройства за портом свича
                if hasattr(self.__neighbor_interface, 'connected_endpoints') and self.__neighbor_interface.connected_endpoints:
                    # Проверить что IP адреса устройств принадлежат одной подсети
                    self.local_device_prefix = NetboxDevice.get_prefix_for_ip(
                        self.__ip_address
                    )
                    self.neighbor_device_prefix = NetboxDevice.get_prefix_for_ip(
                        self.__neighbor_interface.connected_endpoints[0].device.name
                    )
                    if self.local_device_prefix == self.neighbor_device_prefix:
                        logger.info(
                            f'IP addresses {self.__ip_address} and {self.__neighbor_interface.connected_endpoints[0].device.name} belong to the same subnet. Deleting the cable...')
                        # Сверка серийных номеров хостов
                        old_neighbor = self.__neighbor_interface.link_peers[0].device
                        netbox_old_neighbor = self.netbox_connection.dcim.devices.get(
                            id=old_neighbor.id
                        )
                        # Если свич включен в хост
                        if self.__neighbor_interface.link_peers_type == 'dcim.interface':
                            # Если старый сосед имеет тот же серийный номер, то удаляем
                            if netbox_old_neighbor.serial == self.__serial_number:
                                    netbox_old_neighbor.delete()
                                    logger.info(
                                        f'Deleted the old device {old_neighbor.name} with serial number {self.__serial_number}'
                                    )
                            self.__neighbor_interface.cable.delete()
                        # Если между старым хостом и свичём есть розетка
                        elif self.__neighbor_interface.link_peers_type == 'dcim.rearport':
                            netbox_old_neighbor_interface = self.netbox_connection.dcim.interfaces.get(
                                id=self.__neighbor_interface.connected_endpoints[0].id
                            )
                            netbox_old_neighbor_interface.cable.delete()
                            # Если старый сосед имеет тот же серийный номер, то удаляем
                            if netbox_old_neighbor.serial == self.__serial_number:
                                netbox_old_neighbor.delete()
                                logger.info(
                                    f'Deleted the old device {old_neighbor.hostname} with serial number {self.__serial_number}'
                                )
                            # Получить front_port соответствующий rear_port
                            netbox_front_port = self.netbox_connection.dcim.front_ports.get(
                                device_id=self.__neighbor_interface.link_peers[0].device.id,
                            )
                            self.__neighbor_interface = netbox_front_port
                            interface.kind = 'frontport'
                # Если конечного устройства нет
                else:
                    # Если кабель "висит" в воздухе - удаляем
                    if not self.__neighbor_interface.link_peers:
                        self.__neighbor_interface.cable.delete()
                    elif interface.kind == 'frontport':
                        raise Error(
                            f"Can't connect {self.__serial_number} {self.__ip_address} to {neighbor_device.hostname} {self.__neighbor_interface.name}\nSwitch interface was connected to {self.__neighbor_interface.link_peers[0].device}\n{self.__neighbor_interface.link_peers[0].device.url}", self.__ip_address
                        )
                    else:
                        # Получить front_port соответствующий rear_port
                        netbox_front_port = self.netbox_connection.dcim.front_ports.get(
                            device_id=self.__neighbor_interface.link_peers[0].device.id,
                        )
                        self.__neighbor_interface = netbox_front_port
                        interface.kind = 'frontport'
            create_cable()

        def create_cable():
            logger.info(f'Creating the cable...')
            try:
                self.__netbox_interface.cable = self.netbox_connection.dcim.cables.create(
                    a_terminations=[{
                        "object_id": self.__netbox_interface.id,
                        "object_type": 'dcim.interface',
                    }],
                    b_terminations=[{
                        "object_id": self.__neighbor_interface.id,
                        "object_type": f'dcim.{interface.kind}',
                    }]
                )
                logger.debug(f'The cable has been created')
            except Exception as e:
                Error(
                    f"Can't connect {interface.lldp_rem['name']} {interface.rem_ip} to {neighbor_device.hostname} {self.__neighbor_interface.name}\nSwitch interface was connected to {self.__neighbor_interface.connected_endpoints[0].device}\n{self.__neighbor_interface.connected_endpoints[0].device.url}", self.__ip_address)

        def check_and_recreate_cable_if_needed():
            for link_peer in self.__netbox_interface.link_peers:
                # If the cable is connected to another port, delete it and create a new one
                if link_peer.id != self.__neighbor_interface.id:
                    NonCriticalError(
                        f'Кабель включен в другой порт: ({link_peer.device} {link_peer})'
                    )
                    recreate_cable()

        # Mapping between interface kind and corresponding Netbox connection method
        interface_mapping = {
            'interface': self.netbox_connection.dcim.interfaces.get,
            'rearport': self.netbox_connection.dcim.rear_ports.get,
            'frontport': self.netbox_connection.dcim.front_ports.get,
        }

        # Get the neighbor interface based on the kind of interface
        self.__neighbor_interface = interface_mapping[interface.kind](
            device=neighbor_device.hostname,
            name=interface.name if interface.kind == 'interface' else None,
        )

        logger.info(
            f"Checking if cable in {self.__netbox_interface.name} exists...")
        # Если интерфейса хоста нет кабеля - создаем кабель между интерфейсами свича и хостом
        if not self.__netbox_interface.cable and not self.__neighbor_interface.cable:
            create_cable()
        # Если кабель существует, проверяем что он включен в соответсвующий порт свича
        else:
            logger.debug(f'The cable already exists')
            if self.__netbox_interface.link_peers_type:
                # Если сейчас соседский интерфейс dcim.interface
                if self.__netbox_interface.link_peers_type == 'dcim.interface':
                    if self.__netbox_interface.link_peers_type == ('dcim.'+interface.kind):
                        check_and_recreate_cable_if_needed()
                    # Переключать свич или хост в розетку - можно
                    else:
                        logger.info(
                            f'Переключаем устройство в розетку: ({self.__neighbor_interface.device} {self.__neighbor_interface})...'
                        )
                        recreate_cable()
                # Если сейчас соседский интерфейс dcim.rearport
                if self.__netbox_interface.link_peers_type == 'dcim.rearport':
                    # Никогда не отключаем порт свича от розетки в "пустоту"
                    if self.__netbox_interface.link_peers_type == ('dcim.'+interface.kind):
                        check_and_recreate_cable_if_needed()
                # Если сейчас соседский интерфейс dcim.frontport
                if self.__netbox_interface.link_peers_type == 'dcim.frontport':
                    if self.__netbox_interface.link_peers_type == ('dcim.'+interface.kind):
                        check_and_recreate_cable_if_needed()
                    # Переключать хост от розетки в "пустоту" - можно, если при этом меняется порт свича
                    else:
                        for endpoint in self.__netbox_interface.connected_endpoints:
                            if endpoint.id != self.__neighbor_interface.id:
                                logger.info(
                                    f'Отключаем хост от розетки...'
                                )
                                recreate_cable()
            else:
                logger.info(
                    f'Кабель не включен в соседнее устройство: ({self.__neighbor_interface.device} {self.__neighbor_interface})'
                )
                recreate_cable()

    def set_platform(self, csv_os):
        self.__platform = self.netbox_connection.dcim.platforms.get(
            name=csv_os
        )
        if not self.__platform:
            try:
                slug = self.__create_slug(csv_os)
                self.__platform = self.netbox_connection.dcim.platforms.create(
                    name=csv_os,
                    slug=slug,
                )
            except pynetbox.core.query.RequestError as e:
                raise Error(
                    e, self.__ip_address
                )
        self.__netbox_device.platform = self.__platform
        self.__netbox_device.save()

    def set_tenant(self, csv_user, vm_name):
        self.__tenant = self.netbox_connection.tenancy.tenants.get(
            name=csv_user,
        )
        if not self.__tenant:
            try:
                slug = self.__create_slug(csv_user)
                self.__tenant = self.netbox_connection.tenancy.tenants.create(
                    name=csv_user,
                    slug=slug,
                )
            except pynetbox.core.query.RequestError as e:
                NonCriticalError(
                    e, vm_name
                )
                return
        self.__netbox_device.tenant = self.__tenant
        self.__netbox_device.save()
    
    # Creating URL-friendly unique shorthand
    def __create_slug(self, name):
        # Check if name contains non-Latin characters
        if not re.match(r'^[\x00-\x7F]+$', name):
            # Transliterate non-Latin characters
            # assuming the input could be in various languages.
            for language_code in get_available_language_codes():
                name = translit(name, language_code, reversed=True)
        # Replace non-word characters with hyphens and convert to lowercase
        slug = re.sub(r'\W+', '-', name).lower()
        return slug

    def __get_netbox_cluster(self):
        self.__netbox_cluster = self.netbox_connection.virtualization.clusters.get(
            name=self.__cluster_name
        )
        if not self.__netbox_cluster:
            self.__netbox_cluster_type = self.netbox_connection.virtualization.cluster_types.get(
                name=self.__cluster_type
            )
            self.__netbox_cluster = self.netbox_connection.virtualization.clusters.create(
                name=self.__cluster_name,
                type=self.__netbox_cluster_type.id,
                status="active",
                site=self.__netbox_site.id,
            )
            