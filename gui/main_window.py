# gui/main_window.py
import logging
from PySide6.QtWidgets import QMainWindow, QTabWidget, QVBoxLayout, QWidget, QMenuBar
from PySide6.QtGui import QAction
from gui.brokers_dialog import BrokersDialog

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self, config, broker_manager, zmq_bridge, copy_engine):
        super().__init__()
        self.config = config
        self.broker_manager = broker_manager
        self.zmq_bridge = zmq_bridge
        self.copy_engine = copy_engine
        
        self.setWindowTitle("EPCopyFlow v2.0 - Dashboard")
        self.resize(1000, 600)
        
        self._init_menu()
        self._init_ui()

    def _init_menu(self):
        menubar = self.menuBar()
        
        # Menu Configurações
        config_menu = menubar.addMenu("&Configurações")
        
        brokers_action = QAction("Cadastro de Corretoras", self)
        brokers_action.triggered.connect(self._open_brokers_dialog)
        config_menu.addAction(brokers_action)
        
        exit_action = QAction("Sair", self)
        exit_action.triggered.connect(self.close)
        config_menu.addAction(exit_action)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Placeholder para a aba de status
        self.status_tab = QWidget() 
        self.tabs.addTab(self.status_tab, "Monitor de Status")

    def _open_brokers_dialog(self):
        dialog = BrokersDialog(self.config, self.broker_manager, self)
        dialog.exec()
