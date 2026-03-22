# gui/tabs/charts_tab.py
# Versão: 1.0.9.p - Envio 55 - VALIDADA
# Objetivo: Implementar a aba Gráficos para exibir gráficos de ativos monitorados com dados OHLC e indicadores.
# Ajustes:
# - [1.0.9.p - Envio 54] Ajustado formato de data no eixo X com base no timeframe; excluído candle em formação dos dados históricos; removido timer baseado em tempo; gráfico agora atualiza imediatamente quando novos candles chegam via stream.
# - [1.0.9.p - Envio 55] Reintroduzido temporizador fallback com intervalos ajustados; restaurada verificação de comprimento de dados com rastreamento do último candle; melhorados logs para distinguir trigger de plotagem; corrigidos erros de IndexError e lógica de verificação.

import pandas as pd
import logging
import time
from datetime import datetime
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel
from PySide6.QtCore import Slot, Signal, QEvent, QTimer
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import mplfinance as mpf
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


class ChartsTab(QWidget):
    error_occurred = Signal(str)
    command_requested = Signal(str, dict)

    def __init__(self, broker_combo, zmq_message_handler, parent=None):
        super().__init__(parent)
        self.broker_combo = broker_combo
        self.zmq_message_handler = zmq_message_handler
        self.chart_data = {}  # {broker_key: {symbol: {timeframe: DataFrame}}}
        self.broker_time_offsets = {}  # {broker_key: time_diff_seconds}
        self.paused = False
        self.canvas = None
        self.figure = None
        self.buffer = {}  # {broker_key: {symbol: {timeframe: list of candles}}}
        self.historical_loaded = {}  # {broker_key: {symbol: {timeframe: bool}}}
        self.historical_requested = {}  # {broker_key: {symbol: {timeframe: bool}}}
        self.monitored_pairs = {}  # {broker_key: {symbol: set(timeframes)}}
        self.timers = {}  # {broker_key: {symbol: {timeframe: QTimer}}}
        self.first_stream = {}  # {broker_key: bool}
        self.is_updating_chart = False
        self._is_plotting = False
        self._last_chart_key = None
        self._last_data_length = {}  # {broker_key_symbol_timeframe: int}
        self._last_candle_hash = {}  # {broker_key_symbol_timeframe: str} para rastrear mudanças no último candle
        self.setup_ui()
        self._populate_combos()
        self._connect_signals()
        logger.debug("ChartsTab inicializado com sucesso")

    def _connect_signals(self):
        self.zmq_message_handler.time_server_received.connect(self._update_broker_time_offset)
        self.zmq_message_handler.stream_ohlc_indicators_received.connect(self._update_monitored_pairs)
        self.zmq_message_handler.stream_ohlc_received.connect(self._request_server_time)
        self.zmq_message_handler.history_data_received.connect(self.process_historical_data)
        self.broker_combo.currentTextChanged.connect(self._update_symbol_combo)
        self.symbol_combo.currentTextChanged.connect(self._update_timeframe_combo)
        self.symbol_combo.currentTextChanged.connect(self._on_symbol_timeframe_changed)
        self.timeframe_combo.currentTextChanged.connect(self._on_symbol_timeframe_changed)
        self.zmq_message_handler.stream_ohlc_indicators_received.connect(self.update_stream_data)
        self.candles_combo.currentTextChanged.connect(self.update_chart)
        self.style_combo.currentTextChanged.connect(self.update_chart)
        self.type_combo.currentTextChanged.connect(self.update_chart)
        logger.debug("Sinais conectados com sucesso")

    @Slot(dict)
    def _request_server_time(self, data):
        broker_key = data.get("broker_key", None)
        if isinstance(broker_key,
                      str) and broker_key and broker_key not in self.broker_time_offsets and self.first_stream.get(
                broker_key, True):
            self.command_requested.emit("GET_TIME_SERVER", {"broker_key": broker_key})
            logger.debug(f"Solicitado GET_TIME_SERVER para {broker_key} na primeira stream")
            self.first_stream[broker_key] = False
            QTimer.singleShot(5000, lambda: self._retry_server_time(broker_key))
        else:
            logger.debug(f"Ignorado GET_TIME_SERVER: broker_key={broker_key} inválido ou já solicitado")

    def _retry_server_time(self, broker_key):
        if broker_key not in self.broker_time_offsets:
            logger.warning(f"Retry de GET_TIME_SERVER para {broker_key} após 5 segundos")
            self.command_requested.emit("GET_TIME_SERVER", {"broker_key": broker_key})
            self.first_stream[broker_key] = False

    @Slot(dict)
    def _update_broker_time_offset(self, time_server):
        broker_key = time_server.get("broker_key", None)
        server_time = time_server.get("time_server", None)
        if broker_key and server_time and isinstance(broker_key, str):
            try:
                self.broker_time_offsets[broker_key] = float(server_time)
                logger.debug(f"Tempo do servidor armazenado para {broker_key}: {server_time}")
                if broker_key == self.broker_combo.currentText():
                    self.update_chart()
            except (ValueError, TypeError) as e:
                logger.error(f"Erro ao processar tempo do servidor para {broker_key}: {str(e)}")
                self.broker_time_offsets[broker_key] = 0
                logger.warning(f"Offset de tempo padrão (0 segundos) usado para {broker_key}")
        else:
            logger.error(f"Dados inválidos para time_server: broker_key={broker_key}, time_server={server_time}")
            if broker_key:
                self.broker_time_offsets[broker_key] = 0
                self.error_occurred.emit(f"Erro: Tempo do servidor inválido para {broker_key}")
                logger.warning(f"Offset de tempo padrão (0 segundos) usado para {broker_key}")

    def _update_monitored_pairs(self, data):
        logger.debug(f"_update_monitored_pairs chamado com data: {data}")
        broker_key = data.get("broker_key", None)
        symbol = data.get("symbol", "")
        timeframe = data.get("timeframe", "")
        if broker_key and symbol and timeframe:
            if broker_key not in self.monitored_pairs:
                self.monitored_pairs[broker_key] = {}
            if symbol not in self.monitored_pairs[broker_key]:
                self.monitored_pairs[broker_key][symbol] = set()
            self.monitored_pairs[broker_key][symbol].add(timeframe)
            logger.debug(f"Adicionado {symbol} {timeframe} para {broker_key}")
            self._update_symbol_combo()
        else:
            logger.error(f"Dados inválidos para atualizar pares monitorados: {data}")
            self.error_occurred.emit("Erro: Dados inválidos para pares monitorados")

    def showEvent(self, event):
        if event.type() == QEvent.Type.Show:
            logger.debug("Aba Gráficos exibida, aguardando seleção de ativo/timeframe")
        super().showEvent(event)

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        controls_layout = QHBoxLayout()
        self.symbol_combo = QComboBox()
        self.timeframe_combo = QComboBox()
        self.candles_combo = QComboBox()
        self.style_combo = QComboBox()
        self.type_combo = QComboBox()
        self.candles_combo.addItems(["20", "40", "60", "80", "100"])
        self.candles_combo.setCurrentText("100")
        self.style_combo.addItems(
            ["default", "classic", "yahoo", "charles", "mike", "binance", "nightclouds", "starsandstripes",
             "blueskies"])
        self.style_combo.setCurrentText("yahoo")
        self.type_combo.addItems(["candle", "ohlc", "line"])
        self.type_combo.setCurrentText("candle")
        controls_layout.addWidget(QLabel("Ativo:"))
        controls_layout.addWidget(self.symbol_combo)
        controls_layout.addWidget(QLabel("Timeframe:"))
        controls_layout.addWidget(self.timeframe_combo)
        controls_layout.addWidget(QLabel("Número de Candles:"))
        controls_layout.addWidget(self.candles_combo)
        controls_layout.addWidget(QLabel("Estilo:"))
        controls_layout.addWidget(self.style_combo)
        controls_layout.addWidget(QLabel("Tipo:"))
        controls_layout.addWidget(self.type_combo)
        self.main_layout.addLayout(controls_layout)
        self.chart_widget = QWidget()
        self.main_layout.addWidget(self.chart_widget)
        self.chart_layout = QVBoxLayout(self.chart_widget)
        logger.debug("Interface gráfica configurada com sucesso")

    def _populate_combos(self):
        self.symbol_combo.clear()
        self.timeframe_combo.clear()
        self.symbol_combo.addItem("Selecione um ativo")
        self.timeframe_combo.addItem("Selecione um timeframe")
        logger.debug("Combos populados com valores iniciais")

    def _update_symbol_combo(self):
        current_broker = self.broker_combo.currentText()
        current_symbol = self.symbol_combo.currentText()
        current_timeframe = self.timeframe_combo.currentText()
        self.symbol_combo.blockSignals(True)
        self.symbol_combo.clear()
        self.symbol_combo.addItem("Selecione um ativo")
        if current_broker and current_broker in self.monitored_pairs:
            symbols = sorted(list(self.monitored_pairs[current_broker].keys()))
            for symbol in symbols:
                self.symbol_combo.addItem(symbol)
            logger.debug(f"symbol_combo atualizado para corretora {current_broker}: {symbols}")
        if current_symbol in [self.symbol_combo.itemText(i) for i in range(self.symbol_combo.count())]:
            self.symbol_combo.setCurrentText(current_symbol)
        self.symbol_combo.blockSignals(False)
        if current_broker not in self.first_stream:
            self.first_stream[current_broker] = True
        self._update_timeframe_combo(current_timeframe)

    def _update_timeframe_combo(self, preserve_timeframe=None):
        current_broker = self.broker_combo.currentText()
        current_symbol = self.symbol_combo.currentText()
        current_timeframe = preserve_timeframe or self.timeframe_combo.currentText()
        self.timeframe_combo.blockSignals(True)
        self.timeframe_combo.clear()
        self.timeframe_combo.addItem("Selecione um timeframe")
        if (current_broker and current_symbol != "Selecione um ativo" and
                current_broker in self.monitored_pairs and current_symbol in self.monitored_pairs[current_broker]):
            timeframes = sorted(list(self.monitored_pairs[current_broker][current_symbol]))
            for timeframe in timeframes:
                self.timeframe_combo.addItem(timeframe)
            logger.debug(f"timeframe_combo atualizado para {current_symbol} em {current_broker}: {timeframes}")
        if current_timeframe in [self.timeframe_combo.itemText(i) for i in range(self.timeframe_combo.count())]:
            self.timeframe_combo.setCurrentText(current_timeframe)
        self.timeframe_combo.blockSignals(False)

    def _clear_chart(self):
        logger.debug(f"Limpando gráfico, itens no layout antes: {self.chart_layout.count()}")
        while self.chart_layout.count():
            item = self.chart_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        if hasattr(self, 'figure') and self.figure:
            plt.close(self.figure)
            self.figure = None
        if hasattr(self, 'canvas') and self.canvas:
            self.canvas.setParent(None)
            self.canvas = None
        logger.debug(f"Itens no layout após limpeza: {self.chart_layout.count()}")
        if self.chart_layout.count() > 0:
            logger.error("Itens residuais no layout após limpeza, possível causa de sobreposição")
            self.error_occurred.emit("Erro: Itens residuais no layout do gráfico após limpeza")

    def _clear_buffer(self, broker_key, symbol, timeframe):
        if broker_key in self.timers and symbol in self.timers[broker_key] and timeframe in self.timers[broker_key][
            symbol]:
            self.timers[broker_key][symbol][timeframe].stop()
            self.timers[broker_key][symbol][timeframe].deleteLater()
            del self.timers[broker_key][symbol][timeframe]
            if not self.timers[broker_key][symbol]:
                del self.timers[broker_key][symbol]
            if not self.timers[broker_key]:
                del self.timers[broker_key]
            logger.debug(f"Temporizador removido para {symbol} {timeframe} na corretora {broker_key}")
        if (broker_key in self.buffer and symbol in self.buffer[broker_key] and
                timeframe in self.buffer[broker_key][symbol]):
            self.buffer[broker_key][symbol][timeframe] = []
            logger.debug(f"Buffer limpo para {symbol} {timeframe} na corretora {broker_key}")
        if (broker_key in self.chart_data and symbol in self.chart_data[broker_key] and
                timeframe in self.chart_data[broker_key][symbol]):
            self.chart_data[broker_key][symbol][timeframe] = pd.DataFrame()
            logger.debug(f"chart_data limpo para {symbol} {timeframe} na corretora {broker_key}")
        data_key = f"{broker_key}_{symbol}_{timeframe}"
        if data_key in self._last_data_length:
            del self._last_data_length[data_key]
        if data_key in self._last_candle_hash:
            del self._last_candle_hash[data_key]

    def _generate_candle_hash(self, candle_dict):
        """Gera hash seguro para um candle"""
        try:
            return f"{candle_dict.get('Open', 0)}_{candle_dict.get('High', 0)}_{candle_dict.get('Low', 0)}_{candle_dict.get('Close', 0)}_{candle_dict.get('Volume', 0)}"
        except Exception as e:
            logger.warning(f"Erro ao gerar hash do candle: {e}")
            return ""

    def _on_symbol_timeframe_changed(self):
        self.broker_combo.blockSignals(True)
        broker_key = self.broker_combo.currentText()
        symbol = self.symbol_combo.currentText()
        timeframe = self.timeframe_combo.currentText()
        n_candles = self.candles_combo.currentText()
        style = self.style_combo.currentText()
        chart_type = self.type_combo.currentText()
        logger.debug(
            f"_on_symbol_timeframe_changed: {broker_key}, {symbol}, {timeframe}, n_candles={n_candles}, style={style}, type={chart_type}")
        current_chart_key = f"{broker_key}_{symbol}_{timeframe}_{n_candles}_{style}_{chart_type}"

        # Parar todos os temporizadores para a corretora atual
        if broker_key in self.timers:
            for old_symbol in list(self.timers[broker_key].keys()):
                for old_timeframe in list(self.timers[broker_key][old_symbol].keys()):
                    self.timers[broker_key][old_symbol][old_timeframe].stop()
                    self.timers[broker_key][old_symbol][old_timeframe].deleteLater()
                    del self.timers[broker_key][old_symbol][old_timeframe]
                if not self.timers[broker_key][old_symbol]:
                    del self.timers[broker_key][old_symbol]
            if not self.timers[broker_key]:
                del self.timers[broker_key]
            logger.debug(f"Todos os temporizadores removidos para corretora {broker_key}")

        # Evitar limpeza do gráfico se a seleção não mudou
        if self._last_chart_key != current_chart_key:
            self._clear_chart()
            self._last_chart_key = current_chart_key
            logger.debug(
                f"Mudança detectada para {symbol} {timeframe} com {n_candles} candles, estilo {style}, tipo {chart_type} na corretora {broker_key}")

        if (symbol != "Selecione um ativo" and timeframe != "Selecione um timeframe" and
                symbol and timeframe and broker_key and
                broker_key in self.monitored_pairs and symbol in self.monitored_pairs[broker_key] and
                timeframe in self.monitored_pairs[broker_key][symbol]):
            if not (broker_key in self.historical_loaded and
                    symbol in self.historical_loaded[broker_key] and
                    timeframe in self.historical_loaded[broker_key][symbol] and
                    self.historical_loaded[broker_key][symbol][timeframe]):
                self.load_historical_data()
                logger.debug(f"Solicitando dados históricos para {symbol} {timeframe} na corretora {broker_key}")
            else:
                if (broker_key in self.chart_data and symbol in self.chart_data[broker_key] and
                        timeframe in self.chart_data[broker_key][symbol] and not self.chart_data[broker_key][symbol][
                            timeframe].empty):
                    self.update_chart()
                else:
                    logger.debug(f"Aguardando dados históricos para {symbol} {timeframe} antes de plotar")
            self._start_update_timer(broker_key, symbol, timeframe)
            logger.debug(f"Processando mudança para {symbol} {timeframe} na corretora {broker_key}")
        self.broker_combo.blockSignals(False)

    def _start_update_timer(self, broker_key, symbol, timeframe):
        """Inicia temporizador fallback com intervalos ajustados"""
        time_multipliers = {
            "PERIOD_M1": 70, "PERIOD_M5": 310, "PERIOD_M15": 910, "PERIOD_M30": 1810,
            "PERIOD_H1": 3610, "PERIOD_H4": 14410, "PERIOD_D1": 86410, "PERIOD_W1": 604810, "PERIOD_MN1": 2592010
        }
        interval = time_multipliers.get(timeframe, 3610) * 1000
        timer = QTimer(self)
        timer.timeout.connect(lambda: self.update_chart())
        timer.start(interval)
        if broker_key not in self.timers:
            self.timers[broker_key] = {}
        if symbol not in self.timers[broker_key]:
            self.timers[broker_key][symbol] = {}
        self.timers[broker_key][symbol][timeframe] = timer
        logger.debug(
            f"Temporizador fallback iniciado para {symbol} {timeframe} na corretora {broker_key} com intervalo de {interval / 1000} segundos")

    def load_historical_data(self):
        broker_key = self.broker_combo.currentText()
        symbol = self.symbol_combo.currentText()
        timeframe = self.timeframe_combo.currentText()
        if not all([broker_key, symbol != "Selecione um ativo", timeframe != "Selecione um timeframe"]):
            logger.error("Faltam corretora, ativo ou timeframe para HISTORY_DATA")
            self.error_occurred.emit("Erro: Faltam corretora, ativo ou timeframe para dados históricos")
            return
        try:
            end_time = self.broker_time_offsets.get(broker_key, int(time.time()))
            if (broker_key in self.buffer and symbol in self.buffer[broker_key] and
                    timeframe in self.buffer[broker_key][symbol] and self.buffer[broker_key][symbol][timeframe]):
                end_time = self.buffer[broker_key][symbol][timeframe][0].get("timestamp_mql", end_time)
                if not isinstance(end_time, (int, float)) or end_time <= 0:
                    logger.warning(f"timestamp_mql inválido ({end_time}) para {symbol} {timeframe}, usando tempo atual")
                    end_time = int(time.time())
                logger.debug(
                    f"Usando timestamp_mql do último candle como end_time: {datetime.utcfromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')} UTC")

            time_multipliers = {
                "PERIOD_M1": 60, "PERIOD_M5": 300, "PERIOD_M15": 900, "PERIOD_M30": 1800,
                "PERIOD_H1": 3600, "PERIOD_H4": 14400, "PERIOD_D1": 86400, "PERIOD_W1": 604800, "PERIOD_MN1": 2592000
            }
            tf_mapping = {
                "PERIOD_M1": "M1", "PERIOD_M5": "M5", "PERIOD_M15": "M15", "PERIOD_M30": "M30",
                "PERIOD_H1": "H1", "PERIOD_H4": "H4", "PERIOD_D1": "D1", "PERIOD_W1": "W1", "PERIOD_MN1": "MN1"
            }
            seconds_per_candle = time_multipliers.get(timeframe, 3600)
            payload_timeframe = tf_mapping.get(timeframe, timeframe)
            start_time = end_time - (100 * seconds_per_candle)
            if start_time < 0:
                start_time = 0
            payload = {"symbol": symbol, "timeframe": payload_timeframe, "start_time": start_time, "end_time": end_time,
                       "broker_key": broker_key}
            logger.debug(
                f"Solicitando HISTORY_DATA: start_time={datetime.utcfromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')} UTC, "
                f"end_time={datetime.utcfromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')} UTC "
                f"(100 candles, payload_timeframe={payload_timeframe})")
            self.command_requested.emit("HISTORY_DATA", payload)
            if broker_key not in self.historical_requested:
                self.historical_requested[broker_key] = {}
            if symbol not in self.historical_requested[broker_key]:
                self.historical_requested[broker_key][symbol] = {}
            self.historical_requested[broker_key][symbol][timeframe] = True
            if broker_key not in self.historical_loaded:
                self.historical_loaded[broker_key] = {}
            if symbol not in self.historical_loaded[broker_key]:
                self.historical_loaded[broker_key][symbol] = {}
            self.historical_loaded[broker_key][symbol][timeframe] = False
        except Exception as e:
            logger.error(f"Erro ao enviar HISTORY_DATA: {str(e)}")
            self.error_occurred.emit(f"Erro ao solicitar histórico: {str(e)}")
            if broker_key in self.historical_requested and symbol in self.historical_requested[broker_key]:
                self.historical_requested[broker_key][symbol][timeframe] = False

    @Slot(dict)
    def process_historical_data(self, data):
        broker_key = data.get("broker_key", "N/A")
        symbol = data.get("payload", {}).get("symbol", self.symbol_combo.currentText())
        timeframe = data.get("payload", {}).get("timeframe", self.timeframe_combo.currentText())
        candles = data.get("data", []) or data.get("", [])
        if not all([symbol, timeframe, candles]):
            logger.error(f"Dados históricos inválidos recebidos: {data}")
            self.error_occurred.emit("Erro: Dados históricos inválidos recebidos")
            if broker_key in self.historical_requested and symbol in self.historical_requested[broker_key]:
                self.historical_requested[broker_key][symbol][timeframe] = False
            return
        if len(candles) < 1:
            logger.error(f"Nenhum candle recebido para {symbol} {timeframe}")
            self.error_occurred.emit("Erro: Nenhum dado histórico recebido")
            if broker_key in self.historical_requested and symbol in self.historical_requested[broker_key]:
                self.historical_requested[broker_key][symbol][timeframe] = False
            return
        if len(candles) < 100:
            logger.warning(f"Recebidos apenas {len(candles)} candles para {symbol} {timeframe}, esperado até 100")

        # Filtrar candle em formação
        time_multipliers = {
            "PERIOD_M1": 60, "PERIOD_M5": 300, "PERIOD_M15": 900, "PERIOD_M30": 1800,
            "PERIOD_H1": 3600, "PERIOD_H4": 14400, "PERIOD_D1": 86400, "PERIOD_W1": 604800, "PERIOD_MN1": 2592000
        }
        seconds_per_candle = time_multipliers.get(timeframe, 3600)
        current_time = self.broker_time_offsets.get(broker_key, int(time.time()))
        filtered_candles = [
            candle for candle in candles
            if candle.get("time", 0) < (current_time - seconds_per_candle)
        ]
        if len(candles) > len(filtered_candles):
            logger.debug(
                f"Filtrado {len(candles) - len(filtered_candles)} candle(s) em formação para {symbol} {timeframe}")

        candle_times = [datetime.fromtimestamp(candle.get("time", 0)).strftime('%Y-%m-%d %H:%M:%S') for candle in
                        filtered_candles]
        logger.debug(
            f"Candles recebidos para {symbol} {timeframe}: {len(filtered_candles)} candles, timestamps: {candle_times}")

        if broker_key not in self.buffer:
            self.buffer[broker_key] = {}
        if symbol not in self.buffer[broker_key]:
            self.buffer[broker_key][symbol] = {}
        if timeframe not in self.buffer[broker_key][symbol]:
            self.buffer[broker_key][symbol][timeframe] = []

        # Remover candles duplicados pelo timestamp
        existing_times = {candle.get("time", 0) for candle in self.buffer[broker_key][symbol][timeframe]}
        unique_candles = [candle for candle in filtered_candles if candle.get("time", 0) not in existing_times]
        self.buffer[broker_key][symbol][timeframe].extend(unique_candles)
        self.buffer[broker_key][symbol][timeframe] = sorted(self.buffer[broker_key][symbol][timeframe],
                                                            key=lambda x: x.get("time", 0), reverse=True)[:100]
        logger.debug(
            f"Buffer atualizado com histórico para {symbol} {timeframe}: {len(self.buffer[broker_key][symbol][timeframe])} candles")

        historical_rows = []
        for candle in self.buffer[broker_key][symbol][timeframe]:
            historical_rows.append({
                "Date": pd.to_datetime(candle.get("time", 0), unit="s"),
                "Open": candle.get("open", 0),
                "High": candle.get("high", 0),
                "Low": candle.get("low", 0),
                "Close": candle.get("close", 0),
                "Volume": candle.get("volume", 0)
            })
        df = pd.DataFrame(historical_rows).sort_values("Date")
        if broker_key not in self.chart_data:
            self.chart_data[broker_key] = {}
        if symbol not in self.chart_data[broker_key]:
            self.chart_data[broker_key][symbol] = {}
        self.chart_data[broker_key][symbol][timeframe] = df.tail(100)
        logger.debug(f"Dados históricos processados para {symbol} {timeframe}: {len(df)} candles")
        self.historical_loaded[broker_key][symbol][timeframe] = True
        self.historical_requested[broker_key][symbol][timeframe] = False

        # Atualizar rastreamento de dados
        data_key = f"{broker_key}_{symbol}_{timeframe}"
        self._last_data_length[data_key] = len(df)
        if not df.empty:
            last_candle = df.tail(1).to_dict('records')[0]
            self._last_candle_hash[data_key] = self._generate_candle_hash(last_candle)

        # Garantir que o gráfico seja atualizado com dados históricos
        if (broker_key == self.broker_combo.currentText() and
                symbol == self.symbol_combo.currentText() and
                timeframe == self.timeframe_combo.currentText()):
            self.update_chart()

    @Slot(dict)
    def update_stream_data(self, data):
        if self.paused:
            logger.debug("Atualização de stream pausada")
            return
        broker_key = data.get("broker_key", "N/A")
        symbol = data.get("symbol", None)
        timeframe = data.get("timeframe", None)
        ohlc = data.get("ohlc", {})
        timestamp_mql = data.get("timestamp_mql", 0)
        if not all([symbol, timeframe, ohlc, timestamp_mql]):
            logger.error(f"Dados de stream inválidos recebidos: {data}")
            self.error_occurred.emit("Erro: Dados de stream inválidos recebidos")
            return

        if broker_key not in self.buffer:
            self.buffer[broker_key] = {}
        if symbol not in self.buffer[broker_key]:
            self.buffer[broker_key][symbol] = {}
        if timeframe not in self.buffer[broker_key][symbol]:
            self.buffer[broker_key][symbol][timeframe] = []

        new_candle = {
            "time": ohlc.get("time", 0),
            "open": ohlc.get("open", 0),
            "high": ohlc.get("high", 0),
            "low": ohlc.get("low", 0),
            "close": ohlc.get("close", 0),
            "volume": ohlc.get("volume", 0),
            "timestamp_mql": timestamp_mql
        }
        buffer_list = self.buffer[broker_key][symbol][timeframe]
        # Verificar se o candle já existe pelo timestamp
        if not buffer_list or new_candle["time"] > buffer_list[0]["time"]:
            buffer_list.append(new_candle)
            self.buffer[broker_key][symbol][timeframe] = sorted(buffer_list, key=lambda x: x.get("time", 0),
                                                                reverse=True)[:100]
            logger.debug(f"Novo candle de stream adicionado para {symbol} {timeframe}: {new_candle}")

            historical_rows = [{"Date": pd.to_datetime(candle["time"], unit="s"),
                                "Open": candle["open"], "High": candle["high"],
                                "Low": candle["low"], "Close": candle["close"],
                                "Volume": candle["volume"]} for candle in buffer_list]
            df = pd.DataFrame(historical_rows).sort_values("Date")
            if broker_key not in self.chart_data:
                self.chart_data[broker_key] = {}
            if symbol not in self.chart_data[broker_key]:
                self.chart_data[broker_key][symbol] = {}
            self.chart_data[broker_key][symbol][timeframe] = df.tail(100)

            # Atualizar rastreamento de dados
            data_key = f"{broker_key}_{symbol}_{timeframe}"
            self._last_data_length[data_key] = len(df)
            if not df.empty:
                last_candle = df.tail(1).to_dict('records')[0]
                self._last_candle_hash[data_key] = self._generate_candle_hash(last_candle)

            # Atualizar gráfico imediatamente quando novos dados chegam
            if (broker_key == self.broker_combo.currentText() and
                    symbol == self.symbol_combo.currentText() and
                    timeframe == self.timeframe_combo.currentText()):
                if (broker_key in self.historical_loaded and
                        symbol in self.historical_loaded[broker_key] and
                        timeframe in self.historical_loaded[broker_key][symbol] and
                        self.historical_loaded[broker_key][symbol][timeframe]):
                    logger.debug(f"Atualizando gráfico IMEDIATAMENTE para {symbol} {timeframe} com novo candle")
                    self.update_chart()
                else:
                    logger.debug(
                        f"Aguardando dados históricos para {symbol} {timeframe} antes de atualizar gráfico com stream")
            else:
                logger.debug(f"Candle de stream ignorado: {symbol} {timeframe} não é o par ativo")
        else:
            logger.debug(f"Candle de stream ignorado para {symbol} {timeframe}: timestamp duplicado ou mais antigo")

        logger.debug(f"Estado do buffer após stream: {len(self.buffer[broker_key][symbol][timeframe])} candles")

    def update_chart(self):
        if self._is_plotting:
            logger.debug("Plotagem em andamento, ignorando chamada de update_chart")
            return
        self._is_plotting = True
        plotting_timer = QTimer()
        plotting_timer.setSingleShot(True)
        plotting_timer.timeout.connect(lambda: logger.error("Timeout ao plotar gráfico") or self.error_occurred.emit(
            "Erro: Timeout ao plotar gráfico"))
        plotting_timer.start(5000)  # Timeout de 5 segundos
        try:
            broker_key = self.broker_combo.currentText()
            symbol = self.symbol_combo.currentText()
            timeframe = self.timeframe_combo.currentText()
            n_candles = self.candles_combo.currentText()
            style = self.style_combo.currentText()
            chart_type = self.type_combo.currentText()
            current_chart_key = f"{broker_key}_{symbol}_{timeframe}_{n_candles}_{style}_{chart_type}"
            data_key = f"{broker_key}_{symbol}_{timeframe}"

            if not all([broker_key, symbol,
                        timeframe]) or symbol == "Selecione um ativo" or timeframe == "Selecione um timeframe":
                logger.debug("Não há corretora, ativo ou timeframe selecionados para plotar gráfico")
                self._clear_chart()
                return
            if not (broker_key in self.chart_data and symbol in self.chart_data[broker_key] and
                    timeframe in self.chart_data[broker_key][symbol]):
                logger.debug(f"Aguardando dados para {symbol} {timeframe} na corretora {broker_key}")
                return
            df = self.chart_data[broker_key][symbol][timeframe]
            if df.empty:
                logger.warning(f"Dados vazios para {symbol} {timeframe} na corretora {broker_key}")
                self.error_occurred.emit(f"Erro: Dados vazios para {symbol} {timeframe}")
                return

            n_candles = min(int(self.candles_combo.currentText()), len(df))
            df_plot = df.tail(n_candles).copy()

            # Verificação otimizada de mudanças
            current_data_length = len(df)
            last_data_length = self._last_data_length.get(data_key, 0)
            current_candle_hash = ""
            if not df_plot.empty:
                last_candle = df_plot.tail(1).to_dict('records')[0]
                current_candle_hash = self._generate_candle_hash(last_candle)
            last_candle_hash = self._last_candle_hash.get(data_key, "")

            # Determinar se precisa replotar
            needs_replot = (
                    self._last_chart_key != current_chart_key or  # Mudança de configuração
                    self.canvas is None or  # Primeiro plot
                    current_data_length != last_data_length or  # Novos dados
                    current_candle_hash != last_candle_hash  # Último candle mudou
            )

            if not needs_replot:
                logger.debug(f"Gráfico já atualizado para {symbol} {timeframe}, sem mudanças detectadas")
                return

            # Definir formato de data com base no timeframe
            datetime_format = (
                "%H:%M" if timeframe in ["PERIOD_M1", "PERIOD_M5", "PERIOD_M15", "PERIOD_M30"] else
                "%d %H:%M" if timeframe in ["PERIOD_H1", "PERIOD_H4"] else
                "%b %d"
            )

            # Determinar trigger e fonte dos dados
            is_historical = (broker_key in self.historical_loaded and
                             symbol in self.historical_loaded[broker_key] and
                             timeframe in self.historical_loaded[broker_key][symbol] and
                             self.historical_loaded[broker_key][symbol][timeframe])
            data_source = "históricos" if is_historical else "stream"

            trigger = "combo_change"
            if current_data_length > last_data_length:
                trigger = "new_data"
            elif current_candle_hash != last_candle_hash:
                trigger = "candle_update"
            elif self._last_chart_key != current_chart_key:
                trigger = "config_change"

            logger.debug(f"Plotando gráfico para {symbol} {timeframe} com {n_candles} candles, "
                         f"len(df)={len(df)}, fonte: {data_source}, trigger: {trigger}, "
                         f"estilo: {style}, tipo: {chart_type}, datetime_format: {datetime_format}")

            self._clear_chart()
            fig, axlist = mpf.plot(df_plot.set_index("Date"), type=chart_type, style=style,
                                   volume=True, datetime_format=datetime_format, returnfig=True)
            self.figure = fig
            self.canvas = FigureCanvas(self.figure)
            self.chart_layout.addWidget(self.canvas)
            self.canvas.draw()

            # Atualizar rastreamento
            self._last_chart_key = current_chart_key
            self._last_data_length[data_key] = current_data_length
            self._last_candle_hash[data_key] = current_candle_hash

            logger.debug(f"Gráfico renderizado para {symbol} {timeframe} com {n_candles} candles, "
                         f"estilo {style}, tipo {chart_type}")
        except Exception as e:
            logger.error(f"Erro ao plotar gráfico: {str(e)}")
            self.error_occurred.emit(f"Erro ao plotar gráfico: {str(e)}")
        finally:
            plotting_timer.stop()
            self._is_plotting = False