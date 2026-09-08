#!/usr/bin/env python3
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ssl
import requests
import urllib3

print('PYTHON', sys.version)
print('OPENSSL', ssl.OPENSSL_VERSION)
print('HAS_SNI', ssl.HAS_SNI)
print('urllib3', urllib3.__version__)
print('REQUESTS', requests.__version__)
print('APCA_API_BASE_URL', os.getenv('APCA_API_BASE_URL'))
print('APCA_API_KEY_ID', bool(os.getenv('APCA_API_KEY_ID')))
print('APCA_API_SECRET_KEY', bool(os.getenv('APCA_API_SECRET_KEY')))
print('HTTP_PROXY', os.getenv('HTTP_PROXY') or os.getenv('http_proxy'))
print('HTTPS_PROXY', os.getenv('HTTPS_PROXY') or os.getenv('https_proxy'))

from alpaca_trade_api.rest import REST

url = 'https://paper-api.alpaca.markets/v2/account'
print('plain requests GET URL:', url)
try:
    r = requests.get(url, timeout=10)
    print('plain status', r.status_code)
    print('plain headers', r.headers.get('server'))
    print('plain body', r.text[:200])
except Exception as e:
    print('plain GET failed', repr(e))

print('\nALPACA REST direct client test')
client = REST(os.getenv('APCA_API_KEY_ID'), os.getenv('APCA_API_SECRET_KEY'), os.getenv('APCA_API_BASE_URL') or 'https://paper-api.alpaca.markets')
print('REST base_url type', type(client._base_url), client._base_url)
print('REST session type', type(client._session))
print('REST session verify', client._session.verify)
print('REST session adapters', client._session.adapters)

try:
    print('call _session.request directly')
    response = client._session.request('GET', str(client._base_url / 'v2' / 'account'), timeout=10)
    print('direct response status', response.status_code)
    print('direct response text', response.text[:200])
except Exception as e:
    import traceback
    traceback.print_exc()

try:
    print('call get_account via sdk')
    acc = client.get_account()
    print('account', acc)
except Exception as e:
    import traceback
    traceback.print_exc()
