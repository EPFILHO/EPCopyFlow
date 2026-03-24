# gui/tabs/status_tab.py
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor

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

        # 6 colunas: Corretora, Conta, Role, Push Port, Status, Acao
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Corretora", "Conta", "Role", "Push Port", "Status", "Acao"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        layout.addWidget(self.table)
        self._update_status()

    def _update_status(self):
        brokers = self.broker_manager.get_brokers()
        connected = self.broker_manager.get_connected_brokers()

        # Evita recriar botoes desnecessariamente se o numero de linhas nao mudou
        needs_rebuild = self.table.rowCount() != len(brokers)
        if needs_rebuild:
            self.table.setRowCount(len(brokers))

        for i, (key, data) in enumerate(sorted(brokers.items())):
            # Corretora (name ou key)
            broker_name = data.get("name", key)
            # Conta (login)
            account = str(data.get("login", "-"))

            self.table.setItem(i, 0, QTableWidgetItem(broker_name))
            self.table.setItem(i, 1, QTableWidgetItem(account))
            self.table.setItem(i, 2, QTableWidgetItem(data.get("role", "slave")))
            self.table.setItem(i, 3, QTableWidgetItem(str(data.get("push_port", "-"))))

            # Status colorido
            is_conn = key in connected
            status_text = "CONECTADO" if is_conn else "DESCONECTADO"
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor("#00e676") if is_conn else QColor("#ff1744"))
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, status_item)

            # Botao Conectar/Desconectar - so recria se necessario
            if needs_rebuild:
                btn = QPushButton("Desconectar" if is_conn else "Conectar")
                btn.setProperty("broker_key", key)
                btn.clicked.connect(self._on_toggle_connection)
                self._style_button(btn, is_conn)
                self.table.setCellWidget(i, 5, btn)
            else:
                btn = self.table.cellWidget(i, 5)
                if btn:
                    new_label = "Desconectar" if is_conn else "Conectar"
                    if btn.text() != new_label:
                        btn.setText(new_label)
                        btn.setProperty("broker_key", key)
                        self._style_button(btn, is_conn)

    def _style_button(self, btn, is_connected):
        """Aplica estilo visual ao botao conforme estado de conexao."""
        if is_connected:
            btn.setStyleSheet(
                "QPushButton { background-color: #c62828; color: white; border-radius: 4px; padding: 4px 8px; }"
                "QPushButton:hover { background-color: #ef5350; }"
            )
        else:
            btn.setStyleSheet(
                "QPushButton { background-color: #1565c0; color: white; border-radius: 4px; padding: 4px 8px; }"
                "QPushButton:hover { background-color: #42a5f5; }"
            )

    def _on_toggle_connection(self):
        """Slot chamado ao clicar no botao Conectar/Desconectar de uma linha."""
        btn = self.sender()
        if not btn:
            return

        key = btn.property("broker_key")
        is_conn = self.broker_manager.is_connected(key)

        # Feedback visual imediato: desabilita botao enquanto processa
        btn.setEnabled(False)
        btn.setText("Aguarde...")

        try:
            if is_conn:
                success = self.broker_manager.disconnect_broker(key)
                action = "desconectar"
            else:
                success = self.broker_manager.connect_broker(key)
                action = "conectar"

            if not success:
                broker_name = self.broker_manager.get_brokers().get(key, {}).get("name", key)
                QMessageBox.warning(
                    self,
                    "Erro de Conexao",
                    f"Nao foi possivel {action} o broker '{broker_name}' (conta: {key}).\n"
                    f"Verifique os logs para mais detalhes."
                )
        except Exception as e:
            logger.error(f"Erro ao alternar conexao para {key}: {e}")
            QMessageBox.critical(
                self,
                "Erro Inesperado",
                f"Ocorreu um erro ao processar a solicitacao:\n{e}"
            )
        finally:
            # Reabilita o botao e atualiza o estado visual imediatamente
            btn.setEnabled(True)
            self._update_status()
