# gui/tabs/status_tab.py
import logging
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt, QTimer

logger = logging.getLogger(__name__)

class StatusTab(QWidget):
    def __init__(self, broker_manager, parent=None):
        super().__init__(parent)
        self.broker_manager = broker_manager
        self._init_ui()
        
        # Timer para atualizar o status a cada 2 segundos
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_status)
        self.timer.start(2000)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Corretora", "Role", "Push Port", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        layout.addWidget(self.table)
        self._update_status()

    def _update_status(self):
        brokers = self.broker_manager.get_brokers()
        connected = self.broker_manager.get_connected_brokers()
        
        self.table.setRowCount(len(brokers))
        
        for i, (key, data) in enumerate(sorted(brokers.items())):
            self.table.setItem(i, 0, QTableWidgetItem(key))
            self.table.setItem(i, 1, QTableWidgetItem(data.get("role", "master")))
            self.table.setItem(i, 2, QTableWidgetItem(str(data.get("push_port", "-"))))
            
            is_conn = key in connected
            status_item = QTableWidgetItem("CONECTADO" if is_conn else "DESCONECTADO")
            status_item.setForeground(Qt.green if is_conn else Qt.red)
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, status_item)
