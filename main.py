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

# Configuracao de Logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("epcopyflow.log", encoding='utf-8')
    ]
)
logger = logging.getLogger("EPCopyFlow")


async def run_app(app, loop):
    try:
        # 1. Carregar Configuracoes
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

        # Aguardar o sinal de fechamento da janela (emitido pelo closeEvent ANTES do Qt encerrar)
        close_future = loop.create_future()

        def _on_closing():
            if not close_future.done():
                close_future.set_result(True)

        # Usar o sinal 'closing' da MainWindow para iniciar shutdown antes do aboutToQuit
        window.closing.connect(_on_closing)
        # Fallback: aboutToQuit como seguranca
        app.aboutToQuit.connect(_on_closing)

        try:
            await close_future
        finally:
            logger.info("Encerrando aplicacao...")
            try:
                await asyncio.wait_for(zmq_bridge.stop(), timeout=3.0)
            except asyncio.TimeoutError:
                logger.warning("ZmqBridge.stop() timeout - forcando encerramento.")
            copy_engine.stop()
            bridge_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(bridge_task), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            logger.info("Aplicacao encerrada com sucesso.")

    except Exception as e:
        logger.critical(f"Erro fatal na inicializacao: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Criacao UNICA da aplicacao e do loop
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        loop.run_until_complete(run_app(app, loop))
