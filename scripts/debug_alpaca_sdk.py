#!/usr/bin/env python3
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import traceback
from quanttrader.alpaca import AlpacaMarketData, AlpacaExecution

print('APCA_API_KEY_ID', os.getenv('APCA_API_KEY_ID'))
print('APCA_API_SECRET_KEY', bool(os.getenv('APCA_API_SECRET_KEY')))
print('APCA_API_BASE_URL', os.getenv('APCA_API_BASE_URL'))

try:
    m = AlpacaMarketData()
    print('market data base_url', m.base_url)
    client = m.connect()
    print('market data client created', type(client))
    print('calling client.get_account()')
    acc = client.get_account()
    print('account', acc)
except Exception as exc:
    traceback.print_exc()

try:
    e = AlpacaExecution()
    print('exec base_url', e.base_url)
    exec_client = e.connect()
    print('exec client created', type(exec_client))
    print('calling exec_client.get_account()')
    acc2 = exec_client.get_account()
    print('exec account', acc2)
except Exception as exc:
    traceback.print_exc()
