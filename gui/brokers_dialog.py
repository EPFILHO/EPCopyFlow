# gui/brokers_dialog.py
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QMessageBox, QToolButton, QDoubleSpinBox
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QIcon, QPixmap, QStandardItemModel, QStandardItem, QColor

logger = logging.getLogger(__name__)

EYE_OPEN_SVG  = ''
EYE_CLOSED_SVG = ''


def svg_icon(svg_data):
    pixmap = QPixmap()
    pixmap.loadFromData(bytearray(svg_data, encoding='utf-8'), "SVG")
    return QIcon(pixmap)


class BrokersDialog(QDialog):
    brokers_updated = Signal()

    def __init__(self, config, broker_manager, parent=None):
        super().__init__(parent)
        self.config         = config
        self.broker_manager = broker_manager
        self.setWindowTitle("Cadastro de Corretoras")
        self.setMinimumWidth(450)
        self._init_ui()
        self._populate_brokers()
        self._clear_fields()
        self._connect_signals()
        self.setModal(True)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Selecao de Corretora
        select_layout = QHBoxLayout()
        select_layout.addWidget(QLabel("Selecionar corretora:"))
        self.combo = QComboBox()
        select_layout.addWidget(self.combo)
        layout.addLayout(select_layout)

        # Campos de Texto
        self.name_edit        = QLineEdit()
        self.client_edit      = QLineEdit()
        self.broker_name_edit = QLineEdit()
        self.login_edit       = QLineEdit()

        # Senha com toggle
        password_layout = QHBoxLayout()
        self.password_edit      = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.show_password_btn  = QToolButton()
        self.show_password_btn.setCheckable(True)
        self.show_password_btn.setIcon(svg_icon(EYE_OPEN_SVG))
        self.show_password_btn.setStyleSheet(
            "QToolButton { background: transparent; border: none; }")
        password_layout.addWidget(self.password_edit)
        password_layout.addWidget(self.show_password_btn)

        self.server_edit = QLineEdit()

        layout.addWidget(QLabel("Nome do Titular:")); layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("Cliente:"));         layout.addWidget(self.client_edit)
        layout.addWidget(QLabel("Nome da Corretora:")); layout.addWidget(self.broker_name_edit)
        layout.addWidget(QLabel("Login:"));           layout.addWidget(self.login_edit)
        layout.addWidget(QLabel("Senha:"));           layout.addLayout(password_layout)
        layout.addWidget(QLabel("Servidor:"));        layout.addWidget(self.server_edit)

        # Modo e Tipo
        mode_type_layout = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Hedge", "Netting"])
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Demo", "Real"])
        mode_type_layout.addWidget(QLabel("Modo:"))
        mode_type_layout.addWidget(self.mode_combo)
        mode_type_layout.addSpacing(20)
        mode_type_layout.addWidget(QLabel("Tipo:"))
        mode_type_layout.addWidget(self.type_combo)
        layout.addLayout(mode_type_layout)

        # Role e Lot Factor
        role_lot_layout = QHBoxLayout()
        self.role_combo = QComboBox()
        self.role_combo.addItems(["master", "slave"])
        self.lot_factor_spin = QDoubleSpinBox()
        self.lot_factor_spin.setRange(0.01, 100.0)
        self.lot_factor_spin.setDecimals(2)
        self.lot_factor_spin.setValue(1.0)
        role_lot_layout.addWidget(QLabel("Role:"))
        role_lot_layout.addWidget(self.role_combo)
        role_lot_layout.addSpacing(20)
        role_lot_layout.addWidget(QLabel("Lot Factor:"))
        role_lot_layout.addWidget(self.lot_factor_spin)
        layout.addLayout(role_lot_layout)

        # Botoes
        btn_layout = QHBoxLayout()
        self.add_or_clear_btn = QPushButton("Adicionar")
        self.modify_btn       = QPushButton("Modificar")
        self.remove_btn       = QPushButton("Excluir")
        self.close_btn        = QPushButton("Fechar")
        btn_layout.addWidget(self.add_or_clear_btn)
        btn_layout.addWidget(self.modify_btn)
        btn_layout.addWidget(self.remove_btn)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

        # Aviso
        self.info_label = QLabel(
            "Não é possível modificar ou excluir uma corretora conectada.")
        self.info_label.setStyleSheet("color: red; font-style: italic;")
        self.info_label.setVisible(False)
        layout.addWidget(self.info_label)

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        self.add_or_clear_btn.clicked.connect(self._on_add_or_clear_clicked)
        self.modify_btn.clicked.connect(self._on_modify_clicked)
        self.remove_btn.clicked.connect(self._on_remove_clicked)
        self.close_btn.clicked.connect(self.close)
        self.show_password_btn.toggled.connect(self._toggle_password_visibility)
        self.role_combo.currentIndexChanged.connect(self._on_role_changed)
        for w in [self.name_edit, self.client_edit, self.broker_name_edit,
                  self.login_edit, self.password_edit, self.server_edit]:
            w.textChanged.connect(self._update_buttons)

    def _on_role_changed(self, idx):
        self.lot_factor_spin.setEnabled(self.role_combo.currentText() == "slave")
        self._update_buttons()

    # ------------------------------------------------------------------
    # Populate / Clear
    # ------------------------------------------------------------------

    def _populate_brokers(self):
        self.combo.blockSignals(True)
        self.combo.clear()
        self._broker_keys = []
        brokers   = self.broker_manager.get_brokers()
        connected = self.broker_manager.get_connected_brokers()
        model = QStandardItemModel()
        for key in sorted(brokers.keys()):
            item = QStandardItem(key)
            is_connected = key in connected
            item.setForeground(QColor("red" if is_connected else "green"))
            model.appendRow(item)
            self._broker_keys.append(key)
        self.combo.setModel(model)
        self.combo.setCurrentIndex(-1)
        self.combo.blockSignals(False)
        self._clear_fields()

    def _on_combo_changed(self, idx):
        if idx < 0:
            self._clear_fields()
            return
        key = self._broker_keys[idx]
        b   = self.broker_manager.get_brokers().get(key, {})
        self.name_edit.setText(b.get("name", ""))
        self.client_edit.setText(b.get("client", ""))
        self.broker_name_edit.setText(b.get("broker_name", ""))
        self.login_edit.setText(b.get("login", ""))
        self.password_edit.setText(b.get("password", ""))
        self.server_edit.setText(b.get("server", ""))
        self.mode_combo.setCurrentText(b.get("mode", "Hedge"))
        self.type_combo.setCurrentText(b.get("type", b.get("type_", "Demo")))
        self.role_combo.setCurrentText(b.get("role", "master"))
        self.lot_factor_spin.setValue(b.get("lot_factor", 1.0))
        self._update_buttons()

    def _clear_fields(self):
        for w in [self.name_edit, self.client_edit, self.broker_name_edit,
                  self.login_edit, self.password_edit, self.server_edit]:
            w.clear()
        self.mode_combo.setCurrentIndex(0)
        self.type_combo.setCurrentIndex(0)
        self.role_combo.setCurrentIndex(0)
        self.lot_factor_spin.setValue(1.0)
        self.combo.setCurrentIndex(-1)
        self._update_buttons()

    def _update_buttons(self):
        idx      = self.combo.currentIndex()
        has_sel  = idx >= 0
        key      = self._broker_keys[idx] if has_sel else None
        is_conn  = key in self.broker_manager.get_connected_brokers() if key else False
        fields_ok = all([
            self.name_edit.text().strip(),
            self.broker_name_edit.text().strip(),
            self.login_edit.text().strip(),
            self.password_edit.text().strip(),
            self.server_edit.text().strip()
        ])
        self.add_or_clear_btn.setText("Limpar" if has_sel else "Adicionar")
        self.add_or_clear_btn.setEnabled(True if has_sel else fields_ok)
        self.modify_btn.setEnabled(has_sel and not is_conn and fields_ok)
        self.remove_btn.setEnabled(has_sel and not is_conn)
        self.info_label.setVisible(has_sel and is_conn)

    # ------------------------------------------------------------------
    # Geracao de portas
    # ------------------------------------------------------------------

    def _generate_ports(self, role: str = 'slave'):
        """
        Gera portas ZMQ livres para o novo broker.
        Master  → 1 porta (trade_port)
        Slave   → 2 portas (trade_port + heartbeat_port)
        Coleta TODOS os campos de porta já usados para evitar colisões.
        """
        BASE_PORT = 15560
        used = set()
        for b in self.broker_manager.get_brokers().values():
            for field in ('push_port', 'trade_port', 'heartbeat_port', 'zmq_port'):
                try:
                    used.add(int(b[field]))
                except (KeyError, TypeError, ValueError):
                    pass

        def next_free(from_port):
            p = from_port
            while p in used:
                p += 1
            used.add(p)
            return p

        trade_port = next_free(BASE_PORT)
        if role.strip().lower() == 'slave':
            heartbeat_port = next_free(trade_port + 1)
            return trade_port, heartbeat_port
        return trade_port, None

    # ------------------------------------------------------------------
    # CRUD handlers
    # ------------------------------------------------------------------

    def _on_add_or_clear_clicked(self):
        if self.combo.currentIndex() >= 0:
            self._clear_fields()
            return
        data = self._get_data()
        role = data.get('role', 'slave')
        trade_port, heartbeat_port = self._generate_ports(role)
        data['trade_port'] = trade_port
        data['push_port']  = trade_port          # compatibilidade com zmq_bridge
        if heartbeat_port:
            data['heartbeat_port'] = heartbeat_port
        if self.broker_manager.add_broker(**data):
            self._populate_brokers()
            QMessageBox.information(self, "Sucesso",
                f"Corretora {data['login']} adicionada.")
        else:
            QMessageBox.warning(self, "Erro",
                "Nao foi possivel adicionar a corretora.")

    def _on_modify_clicked(self):
        idx = self.combo.currentIndex()
        if idx < 0:
            return
        old_key = self._broker_keys[idx]
        data    = self._get_data()
        b       = self.broker_manager.get_brokers().get(old_key, {})
        # Preserva as portas originais ao modificar
        data['trade_port']     = b.get('trade_port', b.get('push_port'))
        data['push_port']      = data['trade_port']
        data['heartbeat_port'] = b.get('heartbeat_port')
        if self.broker_manager.modify_broker(old_key, **data):
            self._populate_brokers()
            QMessageBox.information(self, "Sucesso", "Dados da corretora atualizados.")
        else:
            QMessageBox.warning(self, "Erro", "Erro ao modificar corretora.")

    def _on_remove_clicked(self):
        idx = self.combo.currentIndex()
        if idx < 0:
            return
        key = self._broker_keys[idx]
        if QMessageBox.question(self, "Excluir",
                f"Excluir {key}?") == QMessageBox.Yes:
            if self.broker_manager.remove_broker(key):
                self._populate_brokers()
            else:
                QMessageBox.warning(self, "Erro", "Erro ao remover corretora.")

    def _get_data(self):
        return {
            "name":        self.name_edit.text().strip(),
            "client":      self.client_edit.text().strip(),
            "broker_name": self.broker_name_edit.text().strip(),
            "login":       self.login_edit.text().strip(),
            "password":    self.password_edit.text().strip(),
            "server":      self.server_edit.text().strip(),
            "mode":        self.mode_combo.currentText(),
            "type":        self.type_combo.currentText(),
            "role":        self.role_combo.currentText(),
            "lot_factor":  self.lot_factor_spin.value()
        }

    def _toggle_password_visibility(self, checked):
        self.password_edit.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password)
        self.show_password_btn.setIcon(
            svg_icon(EYE_CLOSED_SVG if checked else EYE_OPEN_SVG))
