import logging
import sys


def setup_logging(name: str = 'quanttrader', level: int = logging.INFO):
    fmt = '%(asctime)s %(levelname)s %(name)s: %(message)s'
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(handler)
    return logging.getLogger(name)
