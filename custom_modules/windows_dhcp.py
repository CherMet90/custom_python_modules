import json
from subprocess import PIPE, Popen
from typing import List
from datetime import datetime, timedelta

from custom_modules.errors import NonCriticalError
from custom_modules.log import logger

class WindowsDHCP:
    def __init__(self, server_name: str):
        """Initialize connection to Windows DHCP server"""
        self.server_name = server_name
        self._scopes = None
        self._leases = None
    
    def _run_powershell_command(self, command: str) -> str:
        """Execute PowerShell command and return its output"""
        try:
            process = Popen(
                ["powershell", "-Command", command],
                stdout=PIPE,
                stderr=PIPE,
                universal_newlines=True
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                raise NonCriticalError(
                    f"Failed to execute PowerShell command: {command}"
                )
            
            return stdout
        except Exception as e:
            raise NonCriticalError(
                f"Failed to execute PowerShell command: {command}"
            )

    @property
    def scopes(self) -> List[dict]:
        """Get all DHCP scopes from Windows Server"""
        if self._scopes is None:
            command = f"""
            Get-DhcpServerv4Scope -ComputerName {self.server_name} |
            Select-Object @{{Name='ScopeId'; Expression={{$_.ScopeId.IPAddressToString}}}}, 
                          @{{Name='StartRange'; Expression={{$_.StartRange.IPAddressToString}}}}, 
                          @{{Name='EndRange'; Expression={{$_.EndRange.IPAddressToString}}}},
                          @{{Name='LeaseDuration'; Expression={{$_.LeaseDuration.ToString()}}}} |
            ConvertTo-Json
            """

            try:
                output = self._run_powershell_command(command)
                scopes_data = json.loads(output)

                # Convert to list if single scope is returned
                if isinstance(scopes_data, dict):
                    scopes_data = [scopes_data]

                self._scopes = scopes_data
                logger.info(f"Got {len(scopes_data)} scopes")
            except Exception as e:
                logger.error(f"Failed to get DHCP scopes: {e}")
                self._scopes = []
        
        return self._scopes
    
    @property
    def leases(self) -> List[dict]:
        """Get all DHCP leases from Windows DHCP server"""
        if self._leases is None:
            all_leases = []
        
            for scope in self.scopes:
                command = f"""
                Get-DhcpServerv4Lease -ComputerName {self.server_name} -ScopeId {scope['ScopeId']} |
                Select-Object @{{Name='IPAddress'; Expression={{$_.IPAddress.IPAddressToString}}}},
                              @{{Name='ClientId'; Expression={{$_.ClientId}}}},
                              HostName,
                              @{{Name='LeaseExpiryTime'; Expression={{$_.LeaseExpiryTime.ToString('o')}}}},
                              AddressState,
                              @{{Name='ScopeId'; Expression={{$_.ScopeId.IPAddressToString}}}} |
                ConvertTo-Json
                """

                try:
                    output = self._run_powershell_command(command)
                    leases_data = json.loads(output)

                    # Convert to list if single lease is returned
                    if isinstance(leases_data, dict):
                        leases_data = [leases_data]
                    elif leases_data is None:
                        continue
                    
                    all_leases.extend(leases_data)
                    logger.info(f"Got {len(leases_data)} leases for scope {scope['ScopeId']}")

                except Exception as e:
                    logger.error(f"Failed to get DHCP leases for scope {scope['ScopeId']}: {e}")
                    continue
            
            self._leases = all_leases
        
        return self._leases

    def get_leases(self, lease_class, skip=False) -> List:
        """
        Get leases from Windows DHCP server and convert them to Lease objects.

        Args:
            lease_class: Class to use for creating lease objects
            skip: If True, skip processing of leases (for debugging)
        Returns:
            List of processed leases
        """
        processed_leases = []

        def get_lease_duration(scope_id: str) -> timedelta:
            """Get lease duration for specific scope"""
            for scope in self.scopes:
                if scope['ScopeId'] == scope_id:
                    duration_str = scope['LeaseDuration']

                    if '.' in duration_str:
                        # Format: 'days.hours:minutes:seconds'
                        days = int(duration_str.split('.')[0])
                        time_parts = duration_str.split('.')[1].split(':')
                    else:
                        # Format: 'hours:minutes:seconds'
                        days = 0
                        time_parts = duration_str.split(':')

                    hours = int(time_parts[0])
                    minutes = int(time_parts[1])
                    seconds = int(time_parts[2])
                    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

            logger.warning(f"Lease duration not found for scope {scope_id}")
            return timedelta(days=8)

        # Process leases
        for lease in self.leases:
            try:
                # Skip processing of leases (for debugging)
                if skip:
                    break

                # Calculate start date from expiry time and lease duration
                if lease.get('LeaseExpiryTime'):
                    expiry_date = datetime.strptime(
                        lease['LeaseExpiryTime'].split('.')[0],
                        '%Y-%m-%dT%H:%M:%S'
                    )
                    # Get lease duration for specific scope
                    lease_duration = get_lease_duration(lease['ScopeId'])
                    start_date = expiry_date - lease_duration
                    start_str = f"{start_date.weekday() + 1} {start_date.strftime('%Y/%m/%d %H:%M:%S')}"
                else:
                    start_str = None
                processed_lease = lease_class(
                    ip_address=lease['IPAddress'],
                    start_date=start_str,
                    mac_address=lease['ClientId'].replace('-', ':').lower() if lease.get('ClientId') else None,
                    vendor_class=None,
                    hostname=lease.get('HostName')
                )
                processed_lease.status = "active"   # Override the status to 'active' for all Windows DHCP leases
                processed_leases.append(processed_lease)
            except Exception as e:
                logger.error(f"Failed to process lease {lease}: {e}")
                continue
        else:
            logger.debug("Skipping processing of leases (for debugging)")

        logger.debug(f'{len(processed_leases)} leases received from {self.server_name}')
        return processed_leases