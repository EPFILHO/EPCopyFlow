# core/__init__.py
# EPCopyFlow - Versao 2.0.0
# Expoe os modulos principais do pacote core para importacao direta.
# Exemplo de uso no main.py:
#   from core import ConfigManager, BrokerManager, ZmqBridge, CopyEngine

from core.config_manager import ConfigManager
from core.broker_manager import BrokerManager
from core.zmq_bridge import ZmqBridge
from core.copy_engine import CopyEngine
from core.mt5_process_monitor import MT5ProcessMonitor

__all__ = [
    'ConfigManager',
    'BrokerManager',
    'ZmqBridge',
    'CopyEngine',
    'MT5ProcessMonitor',
]
