import json
import os
import requests
from ratelimit import limits, sleep_and_retry
import backoff

from custom_modules.log import logger

# Constants for rate limiting
ONE_SECOND = 1
CALLS_PER_SECOND = 1

def save_to_file(cache, filename='mac_vendor_cache.json'):
    with open(filename, 'w') as f:
        json.dump(cache, f)

def load_from_file(filename='mac_vendor_cache.json'):
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                # If JSON is empty or corrupted, return an empty dictionary
                return {}
    else:
        with open(filename, 'w') as f:
            json.dump({}, f)  # Create an empty JSON file
    return {}

class MacVendorLookup:
    def __init__(self, cache_file='mac_vendor_cache.json'):
        self.cache = load_from_file(cache_file)
        self.cache_file = cache_file

    # Decorator to enforce rate limit
    @sleep_and_retry
    @limits(calls=CALLS_PER_SECOND, period=ONE_SECOND)
    @backoff.on_exception(backoff.expo, requests.exceptions.RequestException, max_tries=2, jitter=backoff.full_jitter)
    def _get_vendor_from_api(self, mac_address_prefix):
        url = f'https://api.macvendors.com/{mac_address_prefix}'
        response = requests.get(url)
        response.raise_for_status()  # Will trigger retries for HTTP error statuses
        return response.text.strip() if response.status_code == 200 else 'unknown vendor'

    def get_vendor_by_mac(self, mac_address):
        if mac_address is None:
            return 'unknown vendor'

        # Normalize MAC address by taking the first 6 characters
        mac_address_prefix = mac_address.replace(':', '').upper()[:6]

        # Check if MAC is already in cache
        vendor = self.cache.get(mac_address_prefix)
        if vendor:
            logger.info(f'Using cached vendor for MAC {mac_address_prefix}: {vendor}')
            return vendor

        try:
            # Fetch the vendor from the API with rate limiting and retry logic
            vendor = self._get_vendor_from_api(mac_address_prefix)

            # Save the result in the cache if it's not 'unknown vendor'
            if vendor != 'unknown vendor':
                self.cache[mac_address_prefix] = vendor
                logger.info(f'Cached vendor for MAC {mac_address_prefix}: {vendor}')
            return vendor
        except requests.exceptions.HTTPError as e:
            # HTTP errors are handled in the retry logic, so this block explicitly handles non-recoverable errors
            logger.debug(f"Error fetching vendor for MAC {mac_address_prefix}: {e}")
            return 'unknown vendor'
        except Exception as e:
            # General exceptions should also be handled properly
            logger.debug(f"Error fetching vendor for MAC {mac_address_prefix}: {e}")
            return 'unknown vendor'

    def save_cache(self):
        save_to_file(self.cache, self.cache_file)