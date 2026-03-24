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
        
        # 2. Inicializar Core
        broker_manager = BrokerManager(config, base_mt5, root_path)
        zmq_bridge = ZmqBridge(config)
        copy_engine = CopyEngine(zmq_bridge, config, broker_manager)
        
        # 3. Inicializar GUI
        window = MainWindow(config, broker_manager, zmq_bridge, copy_engine)
        window.show()

        # Iniciar Bridge (async task)
        bridge_task = asyncio.create_task(zmq_bridge.start(broker_manager.get_brokers()))

        # Aguardar o fechamento da janela para encerrar o loop corretamente
        # Usando future para sinalizar encerramento
        close_future = asyncio.Future()
        app.aboutToQuit.connect(lambda: close_future.set_result(True))

        # Rodar o bridge e aguardar encerramento
        try:
            await close_future
        finally:
            # Encerramento limpo
            logger.info("Encerrando aplicação...")
            await zmq_bridge.stop()
            copy_engine.stop()
            bridge_task.cancel()
            try:
                await bridge_task
            except asyncio.CancelledError:
                pass
            loop.stop()
            
    except Exception as e:
        logger.critical(f"Erro fatal na inicialização: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    # O qasync gerencia o loop. Não usamos asyncio.run(main()) direto com qasync.
    # Em vez disso, deixamos o loop do Qt rodar.
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    with loop:
        loop.run_until_complete(main())
