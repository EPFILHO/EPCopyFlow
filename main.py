# main.py
# EPCopyFlow - Fase 2
# Bootstrap principal: ConfigManager -> BrokerManager -> ZmqBridge -> CopyEngine -> MT5ProcessMonitor

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
from core.mt5_process_monitor import MT5ProcessMonitor
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

class EPCopyFlowApp:
    def __init__(self):
        # 1. Carregar Configuracoes
        root_path = os.path.dirname(os.path.abspath(__file__))
        self.config = ConfigManager(os.path.join(root_path, "config.ini"))
        
        base_mt5 = self.config.get("General", "base_mt5_path", fallback="C:/Program Files/MetaTrader 5")
        
        # 2. Inicializar Core
        self.broker_manager = BrokerManager(self.config, base_mt5, root_path)
        self.zmq_bridge = ZmqBridge(self.config)
        self.copy_engine = CopyEngine(self.zmq_bridge, self.config, self.broker_manager)
        
        # 3. Watchdog: monitora processos MT5 e reinicia em caso de fechamento acidental
        self.mt5_monitor = MT5ProcessMonitor(
            broker_manager=self.broker_manager,
            check_interval=10  # verifica a cada 10 segundos
        )
        
        # 4. Inicializar GUI
        self.window = MainWindow(self.config, self.broker_manager, self.zmq_bridge, self.copy_engine)
        
        # Task do bridge
        self.bridge_task = None
    
    async def start(self):
        """Inicia o bridge, o watchdog e mostra a janela."""
        self.window.show()
        
        # Iniciar watchdog de processos MT5
        self.mt5_monitor.start()
        logger.info("MT5ProcessMonitor (watchdog) iniciado.")
        
        # Iniciar Bridge (async task)
        self.bridge_task = asyncio.create_task(self.zmq_bridge.start(self.broker_manager.get_brokers()))
    
    async def cleanup(self):
        """Limpa recursos antes de encerrar."""
        logger.info("Encerrando aplicacao...")
        
        # Parar watchdog graciosamente
        self.mt5_monitor.stop()
        logger.info("MT5ProcessMonitor parado.")
        
        # Fechar todos os processos MT5 antes de encerrar
        self.broker_manager.disconnect_all_brokers()
        logger.info("Todos os processos MT5 foram encerrados.")
        
        try:
            await asyncio.wait_for(self.zmq_bridge.stop(), timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning("ZmqBridge.stop() timeout - forcando encerramento.")
        
        self.copy_engine.stop()
        
        if self.bridge_task:
            self.bridge_task.cancel()
            try:
                await asyncio.wait_for(self.bridge_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        
        logger.info("Aplicacao encerrada com sucesso.")

if __name__ == "__main__":
    try:
        # Criacao UNICA da aplicacao e do loop
        app = QApplication(sys.argv)
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        
        # Criar app e iniciar
        epcopyflow = EPCopyFlowApp()
        
        with loop:
            # Iniciar app
            loop.create_task(epcopyflow.start())
            
            # Conectar sinal de fechamento para cleanup
            def on_closing():
                # Criar task de cleanup e registrar callback para parar o loop quando terminar
                cleanup_task = asyncio.ensure_future(epcopyflow.cleanup())
                cleanup_task.add_done_callback(lambda _: loop.stop())
            
            epcopyflow.window.closing.connect(on_closing)
            
            # Rodar event loop
            loop.run_forever()
    
    except Exception as e:
        logger.critical(f"Erro fatal na inicializacao: {e}", exc_info=True)
        sys.exit(1)
