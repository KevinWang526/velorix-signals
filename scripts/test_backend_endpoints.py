#!/usr/bin/env python3
import json
import traceback
import sys
from pathlib import Path

# Ensure repo root is on sys.path so `backend` package imports correctly
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from backend import app
except Exception as e:
    print('IMPORT_FAILED', repr(e))
    traceback.print_exc()
    raise SystemExit(1)

outputs = {}

try:
    outputs['connect'] = app.trade_connect()
except Exception as e:
    outputs['connect_error'] = repr(e)
    traceback.print_exc()

try:
    outputs['health'] = app.trade_health()
except Exception as e:
    outputs['health_error'] = repr(e)
    traceback.print_exc()

try:
    outputs['run_once'] = app.trade_run_once(confirm=False)
except Exception as e:
    outputs['run_once_error'] = repr(e)
    traceback.print_exc()

print(json.dumps(outputs, indent=2, default=str))
