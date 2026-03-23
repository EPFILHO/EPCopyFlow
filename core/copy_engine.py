# core/copy_engine.py
# EPCopyFlow - Versao 2.0.0
# Responsabilidade: Coracão do copytrade.
#   - Recebe eventos de trade do master (via ZmqBridge)
#   - Calcula volume proporcional por slave (lot_factor)
#   - Replica ordens para todos os slaves conectados
#   - Registra cada operacao e emite sinais para a GUI
#
# Protocolo de mensagem esperado do master (JSON):
#   {
#     "type": "TRADE_EVENT",
#     "action": "OPEN" | "CLOSE" | "MODIFY",
#     "ticket": 123456,
#     "symbol": "EURUSD",
#     "order_type": "BUY" | "SELL",
#     "volume": 0.10,
#     "price": 1.08500,
#     "sl": 1.08000,
#     "tp": 1.09000,
#     "comment": "EPCopyFlow"
#   }

import asyncio
import logging
from datetime import datetime

from PySide6.QtCore import QObject, Signal

from core.config_manager import ConfigManager
from core.zmq_bridge import ZmqBridge

logger = logging.getLogger(__name__)

# Campos obrigatorios em um TRADE_EVENT valido
_REQUIRED_FIELDS_OPEN   = {'type', 'action', 'symbol', 'order_type', 'volume', 'price'}
_REQUIRED_FIELDS_CLOSE  = {'type', 'action', 'ticket'}
_REQUIRED_FIELDS_MODIFY = {'type', 'action', 'ticket', 'sl', 'tp'}


class CopyEngine(QObject):
    """
    Motor de copytrade do EPCopyFlow.

    Sinais emitidos (para GUI):
        trade_copied(dict)        : trade replicado com sucesso em ao menos 1 slave
        trade_failed(dict, str)   : evento + motivo da falha total
        engine_log(str, str)      : (level, mensagem) para o painel de log
        stats_updated(dict)       : estatisticas atualizadas apos cada operacao
    """

    trade_copied  = Signal(dict)
    trade_failed  = Signal(dict, str)
    engine_log    = Signal(str, str)
    stats_updated = Signal(dict)

    # -------------------------------------------------------------------------
    # Bloco 1 - Inicializacao
    # -------------------------------------------------------------------------
    def __init__(self, bridge: ZmqBridge, config: ConfigManager,
                 broker_manager=None, parent=None):
        """
        Args:
            bridge         : instancia de ZmqBridge ja criada
            config         : instancia de ConfigManager
            broker_manager : instancia de BrokerManager (para ler lot_factor dos slaves)
        """
        super().__init__(parent)
        self._bridge  = bridge
        self._config  = config
        self._bm      = broker_manager

        self._default_lot_factor = config.getfloat(
            'CopyEngine', 'default_lot_factor', fallback=1.0
        )

        # trades ativos replicados: ticket_master -> {slave_key: ticket_slave}
        self._active_copies: dict[int, dict[str, int]] = {}

        # estatisticas da sessao
        self._stats = {
            'total_copied': 0,
            'total_failed': 0,
            'session_start': datetime.now().isoformat(),
        }

        self._running = False

        # Conecta o sinal do bridge ao slot de processamento
        self._bridge.master_event_received.connect(self._on_master_event)
        self._bridge.slave_ack_received.connect(self._on_slave_ack)

        logger.debug("CopyEngine inicializado. lot_factor padrao: %.2f",
                     self._default_lot_factor)

    # -------------------------------------------------------------------------
    # Bloco 2 - Ciclo de vida
    # -------------------------------------------------------------------------
    def start(self) -> None:
        """Habilita o processamento de eventos do master."""
        if self._running:
            logger.warning("CopyEngine.start() chamado mas engine ja esta rodando.")
            return
        self._running = True
        logger.info("CopyEngine iniciado.")
        self.engine_log.emit('INFO', 'CopyEngine iniciado — aguardando eventos do master.')

    def stop(self) -> None:
        """Desabilita o processamento. Nao encerra o bridge."""
        self._running = False
        logger.info("CopyEngine parado.")
        self.engine_log.emit('INFO', 'CopyEngine parado.')

    # -------------------------------------------------------------------------
    # Bloco 3 - Recepcao e validacao de eventos
    # -------------------------------------------------------------------------
    def _on_master_event(self, event: dict) -> None:
        """
        Slot chamado pelo ZmqBridge quando o master envia um evento.
        Valida e dispara a replicacao de forma assincrona.
        """
        if not self._running:
            return

        action = event.get('action', '').upper()
        valid, reason = self._validate_event(event, action)
        if not valid:
            logger.warning("Evento invalido ignorado: %s | motivo: %s", event, reason)
            self.engine_log.emit('WARNING', f"Evento invalido ({reason}): {event}")
            return

        logger.info("Evento recebido do master: action=%s symbol=%s volume=%s",
                    action, event.get('symbol'), event.get('volume'))

        # Dispara a corrotina de replicacao no loop de eventos do qasync
        asyncio.ensure_future(self._replicate(event, action))

    def _validate_event(self, event: dict, action: str) -> tuple[bool, str]:
        """Valida campos obrigatorios conforme o tipo de acao."""
        if event.get('type') != 'TRADE_EVENT':
            return False, f"type incorreto: {event.get('type')}"

        if action == 'OPEN':
            missing = _REQUIRED_FIELDS_OPEN - event.keys()
        elif action == 'CLOSE':
            missing = _REQUIRED_FIELDS_CLOSE - event.keys()
        elif action == 'MODIFY':
            missing = _REQUIRED_FIELDS_MODIFY - event.keys()
        else:
            return False, f"action desconhecida: {action}"

        if missing:
            return False, f"campos ausentes: {missing}"

        if action == 'OPEN':
            vol = event.get('volume', 0)
            if not isinstance(vol, (int, float)) or vol <= 0:
                return False, f"volume invalido: {vol}"

        return True, ''

    # -------------------------------------------------------------------------
    # Bloco 4 - Replicacao
    # -------------------------------------------------------------------------
    async def _replicate(self, event: dict, action: str) -> None:
        """
        Replica o evento do master para todos os slaves conectados.
        Para cada slave: calcula volume, monta comando e envia via bridge.
        """
        slave_keys = self._bridge.get_slave_keys()

        if not slave_keys:
            reason = "Nenhum slave conectado."
            logger.warning(reason)
            self.engine_log.emit('WARNING', reason)
            self.trade_failed.emit(event, reason)
            self._stats['total_failed'] += 1
            self.stats_updated.emit(dict(self._stats))
            return

        success_count = 0
        ticket_master = event.get('ticket', 0)

        for slave_key in slave_keys:
            command = self._build_command(event, action, slave_key)
            ok = await self._bridge.send_to_slave(slave_key, command)
            if ok:
                success_count += 1
                # Registra mapeamento ticket master -> slave
                if action == 'OPEN':
                    if ticket_master not in self._active_copies:
                        self._active_copies[ticket_master] = {}
                    # ticket do slave sera atualizado ao receber ACK
                    self._active_copies[ticket_master][slave_key] = 0
                elif action == 'CLOSE' and ticket_master in self._active_copies:
                    self._active_copies.pop(ticket_master, None)
                log_msg = (f"[{action}] {event.get('symbol')} "
                           f"vol={command.get('volume')} -> {slave_key}: OK")
                logger.info(log_msg)
                self.engine_log.emit('INFO', log_msg)
            else:
                log_msg = f"[{action}] {event.get('symbol')} -> {slave_key}: FALHOU"
                logger.error(log_msg)
                self.engine_log.emit('ERROR', log_msg)

        if success_count > 0:
            self._stats['total_copied'] += 1
            self.trade_copied.emit(event)
        else:
            self._stats['total_failed'] += 1
            self.trade_failed.emit(event, "Falha em todos os slaves.")

        self.stats_updated.emit(dict(self._stats))

    def _build_command(self, event: dict, action: str, slave_key: str) -> dict:
        """
        Monta o dict de comando a enviar para o slave,
        ajustando o volume pelo lot_factor do slave.
        """
        cmd = {
            'type':       'COPY_ORDER',
            'action':     action,
            'symbol':     event.get('symbol', ''),
            'order_type': event.get('order_type', ''),
            'volume':     self._calculate_volume(event.get('volume', 0.0), slave_key),
            'price':      event.get('price', 0.0),
            'sl':         event.get('sl', 0.0),
            'tp':         event.get('tp', 0.0),
            'ticket_master': event.get('ticket', 0),
            'comment':    'EPCopyFlow',
        }
        # Para CLOSE e MODIFY, precisamos do ticket do slave
        if action in ('CLOSE', 'MODIFY'):
            ticket_master = event.get('ticket', 0)
            cmd['ticket_slave'] = (
                self._active_copies.get(ticket_master, {}).get(slave_key, 0)
            )
        return cmd

    def _calculate_volume(self, master_vol: float, slave_key: str) -> float:
        """
        Calcula o volume para o slave aplicando seu lot_factor.
        lot_factor lido do brokers.json via BrokerManager.
        Arredonda para 2 casas decimais (precisao padrao MT5).
        """
        lot_factor = self._default_lot_factor

        if self._bm:
            brokers = self._bm.get_brokers()
            slave_data = brokers.get(slave_key, {})
            lot_factor = float(slave_data.get('lot_factor', self._default_lot_factor))

        result = round(master_vol * lot_factor, 2)
        # Volume minimo de seguranca
        return max(result, 0.01)

    # -------------------------------------------------------------------------
    # Bloco 5 - Recepcao de ACK dos slaves
    # -------------------------------------------------------------------------
    def _on_slave_ack(self, slave_key: str, ack: dict) -> None:
        """
        Slot chamado pelo ZmqBridge quando um slave envia resposta.
        Atualiza o mapeamento ticket_master -> ticket_slave.
        """
        ack_type   = ack.get('type', '')
        ticket_m   = ack.get('ticket_master', 0)
        ticket_s   = ack.get('ticket_slave', 0)
        status     = ack.get('status', '')

        if ack_type == 'COPY_ACK' and ticket_m and ticket_s:
            if ticket_m in self._active_copies:
                self._active_copies[ticket_m][slave_key] = ticket_s
            log_msg = (f"ACK {slave_key}: ticket_master={ticket_m} "
                       f"ticket_slave={ticket_s} status={status}")
            logger.info(log_msg)
            self.engine_log.emit('INFO', log_msg)
        elif ack_type == 'COPY_NACK':
            reason = ack.get('reason', 'desconhecido')
            log_msg = f"NACK {slave_key}: ticket_master={ticket_m} motivo={reason}"
            logger.warning(log_msg)
            self.engine_log.emit('WARNING', log_msg)

    # -------------------------------------------------------------------------
    # Bloco 6 - Consultas de estado
    # -------------------------------------------------------------------------
    def get_active_copies(self) -> dict:
        """
        Retorna os trades ativos replicados.

        Returns:
            dict: {ticket_master: {slave_key: ticket_slave}}
        """
        return dict(self._active_copies)

    def get_stats(self) -> dict:
        """Retorna estatisticas da sessao atual."""
        return dict(self._stats)

    def is_running(self) -> bool:
        """Indica se o engine esta ativo."""
        return self._running
