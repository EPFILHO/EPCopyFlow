# gui/mt5_trader_gui.py
# Versão: 1.0.9.p - Envio 3
# Objetivo: Interface gráfica principal do MT5TraderGui, gerenciando layout geral, área de log e comunicação com o EA.
# Ajustes:
# - [1.0.9.p - Envio 3] Adicionado zmq_message_handler na inicialização de ChartsTab para suportar GET_TIME_SERVER.
# - [1.0.9.o - Envio 2] Adicionado conexão do sinal command_requested do ChartsTab ao _handle_admin_command para enviar HISTORY_DATA.
# - [1.0.9.o - Envio 1] Alterado o log.
# - [1.0.9.n - Envio 2] Adicionada aba Gráficos para exibir gráficos de ativos monitorados.
# - [1.0.9.n - Envio 1] Refatorado para separar abas em módulos (AdminTab, TradingTab, IndicatorsTab).
# - [1.0.9.n - Envio 1] Corrigido método _update_stream_ohlc_indicators para tratar stream_data diretamente, eliminando mensagem "Nenhuma atualização de dados".
# - Mantidas funcionalidades de versões anteriores (1.0.9.l, 1.0.9.g, 1.0.9.k):
#   - Suporte a múltiplas corretoras, streaming OHLC+Indicadores, Copy Trade.
#   - Alinhado com ZmqTraderBridge 1.21 e ZmqRouter 1.0.9.b.

# Bloco 1 - Importações e Configuração Inicial
import sys
import json
import time
import logging
import asyncio
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QComboBox, QLabel, QCheckBox, QPushButton, QTextEdit, QTabWidget
)
from PySide6.QtCore import Slot, Signal
from gui.tabs.admin_tab import AdminTab
from gui.tabs.trading_tab import TradingTab
from gui.tabs.indicators_tab import IndicatorsTab
from gui.tabs.charts_tab import ChartsTab

logger = logging.getLogger(__name__)

# Bloco 2 - Inicialização da Classe e Estrutura Geral
class MT5TraderGui(QDialog):
    def __init__(self, config, broker_manager, zmq_router, zmq_message_handler, main_window, parent=None):
        super().__init__(parent)
        self.config = config
        self.broker_manager = broker_manager
        self.zmq_router = zmq_router
        self.zmq_message_handler = zmq_message_handler
        self.main_window = main_window
        self.copy_trade_enabled = False
        self.stream_ohlc_indicators_request_ids = {}
        self.streaming_active_by_broker = {}
        self.setWindowTitle("MT5Trader GUI")
        self.setGeometry(100, 100, 800, 600)
        self.setMinimumWidth(800)
        self.setup_ui()
        self._connect_signals()
        self._populate_brokers()
        logger.info("MT5TraderGui inicializado.")

    # Bloco 3 - Configuração da Interface Gráfica
    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Seleção de corretora
        self.broker_combo = QComboBox()
        layout.addWidget(QLabel("Selecione a Corretora:"))
        layout.addWidget(self.broker_combo)

        # Checkbox Copy Trade
        self.copy_trade_checkbox = QCheckBox("Ativar Copy Trade")
        layout.addWidget(self.copy_trade_checkbox)

        # Botão Parar Monitoramento
        self.monitor_btn = QPushButton("Parar Monitoramento")
        self.monitor_btn.setMaximumWidth(150)
        self.monitor_btn.setStyleSheet("padding: 5px;")
        self.monitor_btn.setEnabled(False)
        layout.addWidget(self.monitor_btn)

        # Abas
        tabs = QTabWidget()
        self.admin_tab = AdminTab(self.broker_combo)
        self.trading_tab = TradingTab(self.broker_combo)
        self.indicators_tab = IndicatorsTab(self.broker_combo)
        self.charts_tab = ChartsTab(self.broker_combo, self.zmq_message_handler)  # Alterado
        tabs.addTab(self.admin_tab, "Administrativo")
        tabs.addTab(self.trading_tab, "Trading")
        tabs.addTab(self.indicators_tab, "Indicadores")
        tabs.addTab(self.charts_tab, "Gráficos")
        layout.addWidget(tabs)

        # Área de log
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMinimumHeight(300)
        layout.addWidget(QLabel("Log de Comandos e Respostas:"))
        layout.addWidget(self.log_area)

        # Botão Fechar
        stop_btn = QPushButton("Fechar")
        stop_btn.setMaximumWidth(150)
        stop_btn.setStyleSheet("padding: 5px;")
        stop_btn.clicked.connect(self.close)
        layout.addWidget(stop_btn)

    # Bloco 4 - Conexões de Sinais
    def _connect_signals(self):
        self.broker_combo.currentIndexChanged.connect(self._update_buttons)
        self.copy_trade_checkbox.stateChanged.connect(self.toggle_copy_trade)
        self.zmq_message_handler.log_message_received.connect(self.update_log)
        self.main_window.broker_status_updated.connect(self._handle_broker_status_updated)
        self.main_window.broker_status_updated.connect(self._update_buttons)
        self.main_window.broker_connected.connect(self._select_broker)
        self.zmq_message_handler.positions_received.connect(self._update_positions)
        self.zmq_message_handler.orders_received.connect(self._update_orders)
        self.zmq_message_handler.history_data_received.connect(self._update_history_data)
        self.zmq_message_handler.history_trades_received.connect(self._update_history_trades)
        self.zmq_message_handler.trade_response_received.connect(self._update_trade_response)
        self.zmq_message_handler.indicator_ma_received.connect(self._update_indicator_ma)
        self.zmq_message_handler.ohlc_received.connect(self._update_ohlc)
        self.zmq_message_handler.tick_received.connect(self._update_tick)
        self.zmq_message_handler.stream_ohlc_received.connect(self._update_stream_ohlc)
        self.zmq_message_handler.stream_ohlc_indicators_received.connect(self._update_stream_ohlc_indicators)
        self.zmq_message_handler.stream_ohlc_indicators_received.connect(self.charts_tab.update_stream_data)
        self.charts_tab.error_occurred.connect(self.update_log)
        # Conectar sinais das abas
        self.admin_tab.command_requested.connect(self._handle_admin_command)
        self.trading_tab.command_requested.connect(self._handle_trade_command)
        self.indicators_tab.command_requested.connect(self._handle_indicators_command)
        self.charts_tab.command_requested.connect(self._handle_admin_command)  # Novo
        logger.debug("Sinais conectados no MT5TraderGui.")

    # Bloco 5 - Atualização de Interface
    def _populate_brokers(self):
        self.broker_combo.clear()
        connected_brokers = self.broker_manager.get_connected_brokers()
        for key in sorted(connected_brokers):
            self.broker_combo.addItem(key)
        self._update_buttons()
        logger.info(f"Lista de corretoras atualizada: {[self.broker_combo.itemText(i) for i in range(self.broker_combo.count())]}")

    @Slot(str)
    def _select_broker(self, broker_key: str):
        index = self.broker_combo.findText(broker_key)
        if index >= 0:
            self.broker_combo.setCurrentIndex(index)
            logger.info(f"Corretora {broker_key} selecionada.")
        else:
            logger.debug(f"Corretora {broker_key} não encontrada.")

    @Slot(str)
    def _handle_broker_status_updated(self, broker_key: str):
        for key in self.streaming_active_by_broker.keys():
            is_registered = bool(key in self.main_window.broker_status and self.main_window.broker_status[key])
            if not is_registered and self.streaming_active_by_broker.get(key, False):
                self.streaming_active_by_broker[key] = False
                self.stream_ohlc_indicators_request_ids[key] = None
                logger.info(f"Streaming desativado para {key} (corretora não registrada).")
                self.update_log(f"Streaming desativado para {key}.")
        if self.broker_combo.currentText() == broker_key:
            self._update_buttons()

    def _update_buttons(self):
        selected_key = self.broker_combo.currentText()
        is_registered = bool(selected_key and selected_key in self.main_window.broker_status and self.main_window.broker_status[selected_key])
        streaming_active = selected_key in self.streaming_active_by_broker and self.streaming_active_by_broker[selected_key]
        # Atualizar botões das abas
        self.admin_tab.update_buttons(is_registered)
        self.trading_tab.update_buttons(is_registered)
        self.indicators_tab.update_buttons(is_registered, streaming_active)
        logger.debug(
            f"Botões atualizados para {selected_key}. Registrada: {is_registered}, Streaming: {streaming_active}"
        )

    def toggle_copy_trade(self, state):
        self.copy_trade_enabled = state == 2
        log_msg = f"Copy Trade {'ativado' if self.copy_trade_enabled else 'desativado'}"
        logger.info(log_msg)
        self.update_log(log_msg)

    @Slot(str)
    def update_log(self, message):
        if "TICK" not in message:
            self.log_area.append(message)
            lines = self.log_area.toPlainText().split('\n')
            if len(lines) > 1000:
                self.log_area.setText('\n'.join(lines[-1000:]))

    @Slot(dict)
    def _update_positions(self, positions):
        text = f"Posições: {json.dumps(positions, indent=2)}"
        self.log_area.append(text)
        logger.debug(f"Posições atualizadas: {text}")

    @Slot(dict)
    def _update_orders(self, orders):
        text = f"Ordens: {json.dumps(orders, indent=2)}"
        self.log_area.append(text)
        logger.debug(f"Ordens atualizadas: {text}")

    @Slot(dict)
    def _update_history_data(self, history_data):
        text = f"Histórico de Dados: {json.dumps(history_data, indent=2)}"
        self.log_area.append(text)
        logger.debug(f"Histórico de dados atualizado: {text}")

    @Slot(dict)
    def _update_history_trades(self, history_trades):
        text = f"Histórico de Trades: {json.dumps(history_trades, indent=2)}"
        self.log_area.append(text)
        logger.debug(f"Histórico de trades atualizado: {text}")

    @Slot(dict)
    def _update_trade_response(self, trade_response):
        status = "✅ Sucesso" if trade_response.get('status') == 'OK' else f"❌ Erro: {trade_response.get('error_message', 'Desconhecido')}"
        text = f"Resposta de Trading ({trade_response.get('broker_key')}): {json.dumps(trade_response, indent=2)}\nStatus: {status}"
        self.log_area.append(text)
        logger.debug(f"Resposta de trading atualizada: {text}")

    @Slot(dict)
    def _update_indicator_ma(self, data):
        status = "✅ Sucesso" if 'ma_value' in data else "❌ Erro"
        text = f"Média Móvel ({data.get('broker_key')}): {json.dumps(data, indent=2)}\nStatus: {status}"
        self.log_area.append(text)
        logger.debug(f"Média Móvel atualizada: {text}")

    @Slot(dict)
    def _update_ohlc(self, data):
        status = "✅ Sucesso" if 'ohlc' in data and data['ohlc'] else "❌ Erro"
        text = f"OHLC ({data.get('broker_key')}): {json.dumps(data, indent=2)}\nStatus: {status}"
        self.log_area.append(text)
        logger.debug(f"OHLC atualizado: {text}")

    @Slot(dict)
    def _update_tick(self, data):
        status = "✅ Sucesso" if 'tick' in data and data['tick'] else "❌ Erro"
        text = f"Tick ({data.get('broker_key')}): {json.dumps(data, indent=2)}\nStatus: {status}"
        self.log_area.append(text)
        logger.debug(f"Tick atualizado: {text}")

    @Slot(dict)
    def _update_stream_ohlc(self, data):
        status = "✅ Sucesso" if data.get("status") == "OK" or 'ohlc' in data else "❌ Erro"
        text = f"Stream OHLC ({data.get('broker_key')}): {json.dumps(data, indent=2)}\nStatus: {status}"
        self.log_area.append(text)
        logger.debug(f"Stream OHLC atualizado: {text}")

    @Slot(dict)
    def _update_stream_ohlc_indicators(self, data):
        broker_key = data.get("broker_key", "N/A")
        symbol = data.get("symbol", "N/A")
        timeframe = data.get("timeframe", "N/A")
        ohlc = data.get("ohlc", {})
        indicators = data.get("indicators", [])

        if not ohlc or not indicators:
            self.log_area.append(f"Stream OHLC+Indicadores ({broker_key}): Nenhuma atualização de dados.")
            logger.debug(f"Stream OHLC+Indicadores ({broker_key}): Nenhuma atualização de dados. Recebido: {data}")
            return

        ohlc_str = (
            f"O:{ohlc.get('open', 0):.5f} H:{ohlc.get('high', 0):.5f} "
            f"L:{ohlc.get('low', 0):.5f} C:{ohlc.get('close', 0):.5f}"
        )

        indicators_str_list = []
        for ind in indicators:
            ind_type = ind.get('type', 'N/A')
            ind_period = ind.get('period', 'N/A')
            ind_value = ind.get('value', 'N/A')
            indicators_str_list.append(f"{ind_type}({ind_period}):{ind_value:.5f}")

        indicators_str = ", ".join(indicators_str_list)

        log_message = (
            f"Stream OHLC+Indicadores ({broker_key}) - {symbol} {timeframe}: "
            f"OHLC=[{ohlc_str}] | Indicadores=[{indicators_str}]"
        )
        self.log_area.append(log_message)
        logger.debug(f"Stream OHLC+Indicadores detalhe: {log_message}")

    # Bloco 6 - Comunicação com o EA
    async def send_command(self, broker_key, command, payload, command_type='admin', use_data_port=False, use_trade_port=False):
        request_id = f"{command.lower()}_{broker_key}_{int(time.time())}"
        try:
            response = await self.zmq_router.send_command_to_broker(broker_key, command, payload, request_id, use_data_port=use_data_port, use_trade_port=use_trade_port)
            if isinstance(response, dict):
                if response.get("status") == "ERROR":
                    log_msg = f"Erro: {response.get('message', 'Falha desconhecida')}"
                    self.update_log(log_msg)
                    logger.error(f"Falha ao enviar {command} para {broker_key}: {response.get('message')}")
                else:
                    logger.info(f"Comando {command} enviado para {broker_key}: {response}")
            else:
                log_msg = f"Erro: Resposta inválida para {command}."
                self.update_log(log_msg)
                logger.error(f"Resposta inválida para {command} de {broker_key}: {response}")
        except asyncio.TimeoutError:
            log_msg = f"Erro: Timeout ao aguardar resposta para {command}."
            self.update_log(log_msg)
            logger.error(f"Timeout ao enviar {command} para {broker_key}")
        except Exception as e:
            log_msg = f"Erro ao enviar comando: {str(e)}"
            self.update_log(log_msg)
            logger.error(f"Exceção ao enviar {command} para {broker_key}: {str(e)}")

    async def send_data_command(self, broker_key, command, payload):
        return await self.send_command(broker_key, command, payload, command_type='data', use_data_port=True)

    async def send_copy_trade(self, primary_broker, command, message):
        connected_brokers = self.broker_manager.get_connected_brokers()
        for broker_key in connected_brokers:
            if broker_key != primary_broker and broker_key in self.main_window.broker_status and self.main_window.broker_status[broker_key]:
                copied_msg = message.copy()
                copied_msg["broker_key"] = broker_key
                copied_msg["request_id"] = f"{command.lower()}_{broker_key}_{int(time.time())}"
                await self.zmq_router.send_command_to_broker(
                    broker_key, command, copied_msg["payload"], copied_msg["request_id"], use_trade_port=True
                )
                logger.info(f"Copy Trade: Enviado {command} para {broker_key}")

    # Bloco 7 - Handlers de Comandos das Abas
    @Slot(str, dict)
    def _handle_admin_command(self, command, payload):
        broker_key = self.broker_combo.currentText()
        if not broker_key:
            self.update_log("Erro: Nenhuma corretora selecionada.")
            logger.warning("Nenhuma corretora selecionada.")
            return
        asyncio.create_task(self.send_command(broker_key, command, payload, 'admin'))

    @Slot(str, dict)
    def _handle_trade_command(self, command, payload):
        broker_key = self.broker_combo.currentText()
        if not broker_key:
            self.update_log("Erro: Nenhuma corretora selecionada.")
            logger.warning("Nenhuma corretora selecionada.")
            return
        if self.copy_trade_enabled and command in [
            "TRADE_ORDER_TYPE_BUY", "TRADE_ORDER_TYPE_SELL", "TRADE_ORDER_TYPE_BUY_LIMIT",
            "TRADE_ORDER_TYPE_SELL_LIMIT", "TRADE_ORDER_TYPE_BUY_STOP", "TRADE_ORDER_TYPE_SELL_STOP",
            "TRADE_POSITION_CLOSE"
        ]:
            message = {"broker_key": broker_key, "command": command, "payload": payload, "request_id": f"{command.lower()}_{broker_key}_{int(time.time())}"}
            asyncio.create_task(self.send_copy_trade(broker_key, command, message))
        asyncio.create_task(self.send_command(broker_key, command, payload, 'trade', use_trade_port=True))

    @Slot(str, dict, bool)
    def _handle_indicators_command(self, command, payload, use_data_port):
        broker_key = self.broker_combo.currentText()
        if not broker_key:
            self.update_log("Erro: Nenhuma corretora selecionada.")
            logger.warning("Nenhuma corretora selecionada.")
            self._update_buttons()
            return
        is_registered = bool(broker_key in self.main_window.broker_status and self.main_window.broker_status[broker_key])
        if not is_registered and command in ["START_STREAM_OHLC_INDICATORS", "STOP_STREAM_OHLC_INDICATORS"]:
            self.update_log(f"Erro: Corretora {broker_key} não está registrada.")
            logger.warning(f"Comando {command} bloqueado: corretora {broker_key} não registrada.")
            self.streaming_active_by_broker[broker_key] = False
            self.stream_ohlc_indicators_request_ids[broker_key] = None
            self._update_buttons()
            return
        try:
            if command == "START_STREAM_OHLC_INDICATORS":
                streaming_active = broker_key in self.streaming_active_by_broker and self.streaming_active_by_broker[broker_key]
                if streaming_active:
                    self.update_log("Erro: Streaming já ativo. Clique em STOP_STREAM_OHLC_INDICATORS primeiro.")
                    return
                request_id = f"start_stream_ohlc_indicators_{broker_key}_{int(time.time())}"
                self.stream_ohlc_indicators_request_ids[broker_key] = request_id
                self.streaming_active_by_broker[broker_key] = True
                self.update_log(f"Iniciando streaming com request_id: {request_id} para {broker_key}")
                logger.info(f"Armazenado request_id para START_STREAM_OHLC_INDICATORS de {broker_key}: {request_id}")
                asyncio.create_task(self.send_command(broker_key, command, payload, 'data', use_data_port=True))
                self._update_buttons()
            elif command == "STOP_STREAM_OHLC_INDICATORS":
                if broker_key in self.stream_ohlc_indicators_request_ids and self.stream_ohlc_indicators_request_ids[broker_key]:
                    request_id = self.stream_ohlc_indicators_request_ids[broker_key]
                    self.update_log(f"Parando streaming com request_id: {request_id} para {broker_key}")
                    logger.info(f"Reutilizando request_id para STOP_STREAM_OHLC_INDICATORS de {broker_key}: {request_id}")
                    asyncio.create_task(self.zmq_router.send_command_to_broker(
                        broker_key, command, payload, request_id, use_data_port=True))
                    self.stream_ohlc_indicators_request_ids[broker_key] = None
                    self.streaming_active_by_broker[broker_key] = False
                    self._update_buttons()
                    self.update_log(f"Streaming parado para {broker_key}.")
                    logger.info(f"Streaming parado para {broker_key}.")
                else:
                    self.update_log(f"Aviso: Nenhum streaming ativo para {broker_key}. Estado ajustado.")
                    logger.info(f"Nenhum request_id para STOP_STREAM_OHLC_INDICATORS de {broker_key}. Ajustando estado.")
                    self.streaming_active_by_broker[broker_key] = False
                    self.stream_ohlc_indicators_request_ids[broker_key] = None
                    self._update_buttons()
            else:
                asyncio.create_task(self.send_data_command(broker_key, command, payload))
        except Exception as e:
            self.update_log(f"❌ Erro ao processar comando {command}: {str(e)}")
            logger.error(f"Erro ao processar comando {command} para {broker_key}: {str(e)}")
            if command == "START_STREAM_OHLC_INDICATORS":
                self.streaming_active_by_broker[broker_key] = False
                self.stream_ohlc_indicators_request_ids[broker_key] = None
                self._update_buttons()

# gui/mt5_trader_gui.py
# Versão: 1.0.9.p - Envio 3