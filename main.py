# main.py
# EPCopyFlow - Fase 2
# Bootstrap principal: ConfigManager -> BrokerManager -> ZmqBridge -> CopyEngine

import sys
import os
import logging
import asyncio
import qasync
from PySide6.QtWidgets import QApplication
from core.config_manager import ConfigManager
from core.broker_manager import BrokerManager
from core.zmq_bridge import ZmqBridge
from core.copy_engine import CopyEngine
from gui.main_window import MainWindow

# Configuração de Logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("epcopyflow.log", encoding='utf-8')
    ]
)
logger = logging.getLogger("EPCopyFlow")

async def main():
    try:
        app = QApplication(sys.argv)
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        # 1. Carregar Configurações
        root_path = os.path.dirname(os.path.abspath(__file__))
        config = ConfigManager(os.path.join(root_path, "config.ini"))
        
        base_mt5 = config.get("General", "base_mt5_path", fallback="C:/Program Files/MetaTrader 5")
        
        # 2. Inicializar Core (Ordem é importante)
        # BrokerManager gerencia as instâncias MT5 e o arquivo brokers.json
        broker_manager = BrokerManager(config, base_mt5, root_path)
        
        # ZmqBridge gerencia os sockets ZMQ com cada instância
        zmq_bridge = ZmqBridge(broker_manager)
        
        # CopyEngine contém a inteligência de replicação (Master -> Slaves)
        copy_engine = CopyEngine(zmq_bridge, broker_manager)
        
        # 3. Inicializar GUI
        window = MainWindow(config, broker_manager, zmq_bridge, copy_engine)
        window.show()

        # Iniciar Bridge (async task)
        # Ela fica rodando em background escutando mensagens dos MT5s
        bridge_task = asyncio.create_task(zmq_bridge.start())

        with loop:
            loop.run_forever()
            
    except Exception as e:
        logger.critical(f"Erro fatal na inicialização: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    # Rodar com qasync para integrar event loop do Qt com o do asyncio
    asyncio.run(main())
