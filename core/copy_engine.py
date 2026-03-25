import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CopyEngine:
    """
    Motor de copia de trades EPCopyFlow v1.

    Recebe eventos do EA Master (protocolo v1) via ZmqBridge,
    calcula volume proporcional por slave e envia comandos para
    cada EA Slave via ZmqBridge.

    Protocolo v1 esperado do Master:
        {
            "protocol_version": "1.0",
            "event_type": "OPEN" | "MODIFY_SLTP" | "CLOSE" | "HEARTBEAT",
            "master_id": "116486",
            "master_ticket": 123456,
            "symbol": "XAUUSD",
            "order_type": "BUY" | "SELL",
            "volume": 1.0,
            "price": 2345.0,
            "sl": 2330.0,
            "tp": 2360.0,
            "timestamp": 1774466431
        }
    """

    def __init__(self, zmq_bridge, broker_manager):
        self.zmq_bridge = zmq_bridge
        self.broker_manager = broker_manager

        # Mapeia master_ticket → {slave_key: slave_ticket}
        self._ticket_map: dict[int, dict[str, int]] = {}

        # Mapeia master_ticket → volume original do master na abertura
        self._master_volume_open: dict[int, float] = {}

    # ------------------------------------------------------------------
    # Entry point — chamado pelo ZmqBridge ao receber mensagem do master
    # ------------------------------------------------------------------

    async def on_master_message(self, master_key: str, raw: str):
        """Processa uma mensagem JSON recebida do EA Master."""
        event = self._parse(raw)
        if not event:
            return

        if not self._validate(event):
            logger.warning(f'Evento invalido recebido de [{master_key}]: {raw}')
            return

        event_type = event.get('event_type', '').upper()

        if event_type == 'OPEN':
            await self._handle_open(master_key, event)
        elif event_type == 'MODIFY_SLTP':
            await self._handle_modify(master_key, event)
        elif event_type == 'CLOSE':
            await self._handle_close(master_key, event)
        elif event_type == 'HEARTBEAT':
            self._handle_heartbeat(master_key, event)
        else:
            logger.warning(f'[{master_key}] event_type desconhecido: {event_type}')

    # ------------------------------------------------------------------
    # Handlers por event_type
    # ------------------------------------------------------------------

    async def _handle_open(self, master_key: str, event: dict):
        master_ticket = event.get('master_ticket')
        symbol        = event.get('symbol')
        order_type    = event.get('order_type')
        volume_master = float(event.get('volume', 0))
        price         = float(event.get('price', 0))
        sl            = float(event.get('sl', 0))
        tp            = float(event.get('tp', 0))
        timestamp     = event.get('timestamp', 0)

        if not master_ticket or not symbol or not order_type or volume_master <= 0:
            logger.error(f'OPEN invalido — campos obrigatorios ausentes: {event}')
            return

        # Guarda volume de abertura do master para calculos de partial close
        self._master_volume_open[master_ticket] = volume_master
        self._ticket_map[master_ticket] = {}

        slaves = self._get_slaves()
        if not slaves:
            logger.warning('Nenhum slave ativo para copiar OPEN.')
            return

        for slave_key, slave_data in slaves.items():
            volume_slave = self._calc_volume(
                volume_master, slave_data
            )
            if volume_slave <= 0:
                logger.warning(f'[{slave_key}] Volume calculado zerado, OPEN ignorado.')
                continue

            cmd = {
                'protocol_version': '1.0',
                'event_type':       'OPEN',
                'master_id':        event.get('master_id'),
                'master_ticket':    master_ticket,
                'slave_id':         slave_key,
                'symbol':           symbol,
                'order_type':       order_type,
                'volume':           volume_slave,
                'price':            price,
                'sl':               sl,
                'tp':               tp,
                'timestamp':        timestamp,
            }
            sent = await self.zmq_bridge.send(slave_key, json.dumps(cmd))
            if sent:
                logger.info(
                    f'OPEN copiado → [{slave_key}] {symbol} {order_type} '
                    f'{volume_slave} lots (master_ticket={master_ticket})'
                )

    async def _handle_modify(self, master_key: str, event: dict):
        master_ticket = event.get('master_ticket')
        sl            = float(event.get('sl', 0))
        tp            = float(event.get('tp', 0))
        timestamp     = event.get('timestamp', 0)

        if not master_ticket:
            logger.error(f'MODIFY_SLTP sem master_ticket: {event}')
            return

        slaves = self._get_slaves()
        for slave_key in slaves:
            cmd = {
                'protocol_version': '1.0',
                'event_type':       'MODIFY_SLTP',
                'master_id':        event.get('master_id'),
                'master_ticket':    master_ticket,
                'slave_id':         slave_key,
                'sl':               sl,
                'tp':               tp,
                'timestamp':        timestamp,
            }
            sent = await self.zmq_bridge.send(slave_key, json.dumps(cmd))
            if sent:
                logger.info(
                    f'MODIFY_SLTP copiado → [{slave_key}] '
                    f'SL={sl} TP={tp} (master_ticket={master_ticket})'
                )

    async def _handle_close(self, master_key: str, event: dict):
        master_ticket  = event.get('master_ticket')
        volume_closed  = float(event.get('volume', 0))
        timestamp      = event.get('timestamp', 0)

        if not master_ticket:
            logger.error(f'CLOSE sem master_ticket: {event}')
            return

        slaves      = self._get_slaves()
        vol_open    = self._master_volume_open.get(master_ticket, volume_closed)
        is_partial  = volume_closed < vol_open

        for slave_key, slave_data in slaves.items():
            volume_slave = self._calc_volume(volume_closed, slave_data)
            if volume_slave <= 0:
                continue

            cmd = {
                'protocol_version': '1.0',
                'event_type':       'CLOSE',
                'master_id':        event.get('master_id'),
                'master_ticket':    master_ticket,
                'slave_id':         slave_key,
                'volume':           volume_slave,
                'partial':          is_partial,
                'timestamp':        timestamp,
            }
            sent = await self.zmq_bridge.send(slave_key, json.dumps(cmd))
            if sent:
                close_type = 'CLOSE PARCIAL' if is_partial else 'CLOSE TOTAL'
                logger.info(
                    f'{close_type} copiado → [{slave_key}] '
                    f'{volume_slave} lots (master_ticket={master_ticket})'
                )

        # Se fechamento total, limpa o mapa
        if not is_partial:
            self._ticket_map.pop(master_ticket, None)
            self._master_volume_open.pop(master_ticket, None)

    def _handle_heartbeat(self, master_key: str, event: dict):
        ts = event.get('timestamp', 0)
        logger.info(f'[{master_key}] HEARTBEAT recebido ts={ts}')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse(self, raw: str) -> Optional[dict]:
        try:
            return json.loads(raw)
        except Exception as e:
            logger.error(f'Erro ao parsear JSON: {e} | raw: {raw}')
            return None

    def _validate(self, event: dict) -> bool:
        """Valida campos obrigatorios do protocolo v1."""
        if event.get('protocol_version') != '1.0':
            logger.warning(f'protocol_version invalido: {event.get("protocol_version")}')
            return False
        if not event.get('event_type'):
            logger.warning('event_type ausente.')
            return False
        if not event.get('master_id'):
            logger.warning('master_id ausente.')
            return False
        return True

    def _get_slaves(self) -> dict:
        """Retorna apenas brokers com Role=slave e conectados."""
        all_brokers = self.broker_manager.get_brokers()
        return {
            k: v for k, v in all_brokers.items()
            if str(v.get('role', 'slave')).lower() == 'slave'
            and self.broker_manager.is_connected(k)
        }

    def _calc_volume(self, volume_master: float, slave_data: dict) -> float:
        """
        Calcula volume proporcional para o slave.
        Respeita lot_factor, min_lot, max_lot e lot_step.
        """
        lot_factor = float(slave_data.get('lot_factor', 1.0))
        min_lot    = float(slave_data.get('min_lot', 0.01))
        max_lot    = float(slave_data.get('max_lot', 100.0))
        lot_step   = float(slave_data.get('lot_step', 0.01))

        raw = volume_master * lot_factor

        # Arredonda para lot_step
        steps = round(raw / lot_step)
        volume = steps * lot_step
        volume = round(volume, 8)

        # Aplica limites
        volume = max(min_lot, min(max_lot, volume))

        return volume

    # ------------------------------------------------------------------
    # Estado interno (util para debug/GUI)
    # ------------------------------------------------------------------

    def get_ticket_map(self) -> dict:
        return dict(self._ticket_map)

    def get_open_positions_count(self) -> int:
        return len(self._ticket_map)
