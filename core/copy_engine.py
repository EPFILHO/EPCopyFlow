# +------------------------------------------------------------------+
# |                        core/copy_engine.py                       |
# |                         EP Filho © 2026                          |
# |                https://github.com/EPFILHO/EPCopyFlow             |
# +------------------------------------------------------------------+
import asyncio
import json
import logging
import math

logger = logging.getLogger(__name__)


class CopyEngine:
    """
    Coração do EPCopyFlow!
    Recebe eventos do EA Master, calcula volumes proporcionais
    e envia comandos para os EA Slaves via ZmqBridge.

    Ticket map:
        _ticket_map[master_ticket] = {slave_key: slave_ticket, ...}

    Slave ticket é preenchido via heartbeat do Slave (campo master_ticket
    em cada posição reportada).
    """

    def __init__(self, zmq_bridge, broker_manager):
        self.zmq     = zmq_bridge
        self.brokers = broker_manager
        self._ticket_map: dict[int, dict[str, int]] = {}

    # ------------------------------------------------------------------
    # Registro de callbacks no ZmqBridge
    # ------------------------------------------------------------------
    def register_callbacks(self):
        """
        Registra callbacks para Master e para heartbeat de cada Slave.
        Deve ser chamado após zmq_bridge.start().
        """
        brokers = self.brokers.get_brokers()
        for key, data in brokers.items():
            role = str(data.get('role', 'slave')).lower()
            if role == 'master':
                self.zmq.register_callback(key, self.on_master_message)
                logger.info(f'[{key}] Callback Master registrado.')
            else:
                hb_key = f'{key}_hb'
                self.zmq.register_callback(hb_key, self.on_slave_heartbeat)
                logger.info(f'[{key}] Callback Slave HB registrado em key={hb_key}')

    # ------------------------------------------------------------------
    # Entry point — mensagens do Master
    # ------------------------------------------------------------------
    async def on_master_message(self, key: str, raw: str):
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f'[{key}] JSON inválido: {raw}')
            return

        event = msg.get('event_type', '')
        handlers = {
            'OPEN':          self._handle_open,
            'CLOSE':         self._handle_close,
            'PARTIAL_CLOSE': self._handle_partial_close,
            'MODIFY_SLTP':   self._handle_modify,
            'HEARTBEAT':     self._handle_master_heartbeat,
        }
        handler = handlers.get(event)
        if handler:
            await handler(key, msg)
        else:
            logger.warning(f'[{key}] Evento desconhecido: {event}')

    # ------------------------------------------------------------------
    # Entry point — heartbeat do Slave
    # ------------------------------------------------------------------
    async def on_slave_heartbeat(self, key: str, raw: str):
        """
        Processa heartbeat do Slave.
        Extrai posições abertas e preenche _ticket_map com slave_ticket
        a partir do master_ticket reportado em cada posição.
        key = '{slave_key}_hb'
        """
        slave_key = key.removesuffix('_hb')
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f'[{slave_key}] Heartbeat JSON inválido: {raw}')
            return

        positions = msg.get('positions', [])
        logger.debug(f'[{slave_key}] Heartbeat recebido: {len(positions)} posição(ões).')

        for pos in positions:
            master_ticket = int(pos.get('master_ticket', 0))
            slave_ticket  = int(pos.get('ticket', 0))
            if master_ticket and slave_ticket:
                if master_ticket not in self._ticket_map:
                    self._ticket_map[master_ticket] = {}
                if slave_key not in self._ticket_map[master_ticket]:
                    logger.info(
                        f'[{slave_key}] slave_ticket mapeado: '
                        f'master={master_ticket} → slave={slave_ticket}'
                    )
                self._ticket_map[master_ticket][slave_key] = slave_ticket

    # ------------------------------------------------------------------
    # Handlers — eventos do Master
    # ------------------------------------------------------------------
    async def _handle_open(self, key: str, msg: dict):
        master_ticket  = int(msg.get('master_ticket') or msg.get('ticket') or 0)
        symbol         = msg.get('symbol', '')
        order_type     = msg.get('order_type', '')
        sl             = float(msg.get('sl', 0))
        tp             = float(msg.get('tp', 0))
        volume_master  = float(msg.get('volume', 0))
        comment        = msg.get('comment', '')

        if not master_ticket or not symbol or not volume_master:
            logger.error(f'[{key}] OPEN incompleto: {msg}')
            return

        self._ticket_map.setdefault(master_ticket, {})
        logger.info(f'[{key}] OPEN master_ticket={master_ticket} {symbol} {order_type} vol={volume_master}')

        for slave_key, slave_data in self._get_slaves():
            lot_factor   = float(slave_data.get('lot_factor', 1.0))
            volume_slave = self._calc_volume(volume_master, lot_factor, symbol)
            if volume_slave <= 0:
                logger.warning(f'[{slave_key}] Volume calculado=0 para {symbol}, OPEN ignorado.')
                continue
            payload = json.dumps({
                'protocol_version': '1.0',
                'event_type':       'OPEN',
                'slave_id':         slave_key,
                'master_id':        key,
                'master_ticket':    master_ticket,
                'symbol':           symbol,
                'order_type':       order_type,
                'volume':           volume_slave,
                'price':            0.0,
                'sl':               sl,
                'tp':               tp,
                'comment':          comment,
            }, separators=(',', ':'))
            sent = await self.zmq.send(slave_key, payload)
            if sent:
                logger.info(f'[{slave_key}] OPEN enviado: {symbol} vol={volume_slave}')

    async def _handle_close(self, key: str, msg: dict):
        # FIX v012 — redireciona para partial_close se reason=PARTIAL
        reason = msg.get('reason', '')
        if reason == 'PARTIAL':
            await self._handle_partial_close(key, msg)
            return

        master_ticket = int(msg.get('master_ticket') or msg.get('ticket') or 0)
        if not master_ticket:
            logger.error(f'[{key}] CLOSE sem ticket: {msg}')
            return

        logger.info(f'[{key}] CLOSE master_ticket={master_ticket}')
        slave_tickets = self._ticket_map.get(master_ticket, {})

        for slave_key, _ in self._get_slaves():
            slave_ticket = slave_tickets.get(slave_key)
            if not slave_ticket:
                logger.warning(f'[{slave_key}] slave_ticket não encontrado para master={master_ticket}, CLOSE ignorado.')
                continue
            payload = json.dumps({
                'protocol_version': '1.0',
                'event_type':       'CLOSE',
                'slave_id':         slave_key,
                'master_id':        key,
                'master_ticket':    master_ticket,
                'ticket':           slave_ticket,
            }, separators=(',', ':'))
            sent = await self.zmq.send(slave_key, payload)
            if sent:
                logger.info(f'[{slave_key}] CLOSE enviado: slave_ticket={slave_ticket}')

        self._ticket_map.pop(master_ticket, None)

    async def _handle_partial_close(self, key: str, msg: dict):
        master_ticket = int(msg.get('master_ticket') or msg.get('ticket') or 0)
        symbol        = msg.get('symbol', '')

        # FIX v012 — usa volume_closed (o que o Master fechou de fato)
        volume_master_closed = float(msg.get('volume_closed', 0))

        if not master_ticket:
            logger.error(f'[{key}] PARTIAL_CLOSE sem ticket: {msg}')
            return
        if volume_master_closed <= 0:
            logger.error(f'[{key}] PARTIAL_CLOSE volume_closed inválido: {msg}')
            return

        logger.info(f'[{key}] PARTIAL_CLOSE master_ticket={master_ticket} vol_closed={volume_master_closed}')
        slave_tickets = self._ticket_map.get(master_ticket, {})

        for slave_key, slave_data in self._get_slaves():
            slave_ticket = slave_tickets.get(slave_key)
            if not slave_ticket:
                logger.warning(f'[{slave_key}] slave_ticket não encontrado para master={master_ticket}, PARTIAL_CLOSE ignorado.')
                continue

            lot_factor         = float(slave_data.get('lot_factor', 1.0))
            # FIX v012 — calcula o volume a FECHAR proporcional ao que o Master fechou
            close_volume_slave = self._calc_volume(volume_master_closed, lot_factor, symbol)

            payload = json.dumps({
                'protocol_version': '1.0',
                'event_type':       'PARTIAL_CLOSE',   # FIX v012 — event_type correto
                'slave_id':         slave_key,
                'master_id':        key,
                'master_ticket':    master_ticket,
                'ticket':           slave_ticket,
                'close_volume':     close_volume_slave, # FIX v012 — campo correto para o Slave
                'symbol':           symbol,
            }, separators=(',', ':'))
            sent = await self.zmq.send(slave_key, payload)
            if sent:
                logger.info(f'[{slave_key}] PARTIAL_CLOSE enviado: slave_ticket={slave_ticket} close_vol={close_volume_slave}')

    async def _handle_modify(self, key: str, msg: dict):
        master_ticket = int(msg.get('master_ticket') or msg.get('ticket') or 0)
        sl = float(msg.get('sl', 0))
        tp = float(msg.get('tp', 0))

        if not master_ticket:
            logger.error(f'[{key}] MODIFY_SLTP sem ticket: {msg}')
            return

        logger.info(f'[{key}] MODIFY_SLTP master_ticket={master_ticket} sl={sl} tp={tp}')
        slave_tickets = self._ticket_map.get(master_ticket, {})

        for slave_key, _ in self._get_slaves():
            slave_ticket = slave_tickets.get(slave_key)
            if not slave_ticket:
                logger.warning(f'[{slave_key}] slave_ticket não encontrado para master={master_ticket}, MODIFY ignorado.')
                continue
            payload = json.dumps({
                'protocol_version': '1.0',
                'event_type':       'MODIFY_SLTP',
                'slave_id':         slave_key,
                'master_id':        key,
                'master_ticket':    master_ticket,
                'ticket':           slave_ticket,
                'sl':               sl,
                'tp':               tp,
            }, separators=(',', ':'))
            sent = await self.zmq.send(slave_key, payload)
            if sent:
                logger.info(f'[{slave_key}] MODIFY_SLTP enviado: slave_ticket={slave_ticket} sl={sl} tp={tp}')

    async def _handle_master_heartbeat(self, key: str, msg: dict):
        ts        = msg.get('timestamp', 0)
        positions = msg.get('positions', [])
        logger.info(f'[{key}] HEARTBEAT recebido ts={ts} posições={len(positions)}')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_slaves(self) -> list[tuple[str, dict]]:
        """Retorna lista de (key, data) de brokers com role=slave."""
        return [
            (k, v)
            for k, v in self.brokers.get_brokers().items()
            if str(v.get('role', 'slave')).lower() == 'slave'
        ]

    def _calc_volume(self, volume_master: float, lot_factor: float, symbol: str = '') -> float:
        """
        Calcula volume proporcional para o Slave.
        Aplica lot_factor e arredonda para lot_step=0.01.
        min_lot=0.01, max_lot=500.0 (defaults conservadores).
        """
        min_lot  = 0.01
        max_lot  = 500.0
        lot_step = 0.01
        raw      = volume_master * lot_factor
        steps    = math.floor(raw / lot_step)
        volume   = steps * lot_step
        volume   = max(min_lot, min(max_lot, volume))
        return round(volume, 2)

    def stop(self):
        """Encerra o CopyEngine (limpeza de estado)."""
        self._ticket_map.clear()
        logger.info('CopyEngine encerrado.')
