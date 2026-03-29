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
        _ticket_map[master_ticket] = {
            'order_type':   'BUY' | 'SELL',
            'open_price':   float,   <- open_price do Master
            'symbol':       str,
            'point':        float,   <- tamanho do ponto do símbolo
            slave_key:      {
                'ticket':       int,
                'open_price':   float,  <- open_price do Slave
            },
            ...
        }
    """

    def __init__(self, zmq_bridge, broker_manager):
        self.zmq     = zmq_bridge
        self.brokers = broker_manager
        self._ticket_map: dict[int, dict] = {}

    # ------------------------------------------------------------------
    # Registro de callbacks no ZmqBridge
    # ------------------------------------------------------------------
    def register_callbacks(self):
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
        e slave_open_price a partir do master_ticket reportado.
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
            master_ticket    = int(pos.get('master_ticket', 0))
            slave_ticket     = int(pos.get('ticket', 0))
            slave_open_price = float(pos.get('open_price', 0.0))

            if master_ticket and slave_ticket:
                if master_ticket not in self._ticket_map:
                    self._ticket_map[master_ticket] = {}

                ctx = self._ticket_map[master_ticket]

                if slave_key not in ctx:
                    logger.info(
                        f'[{slave_key}] slave_ticket mapeado: '
                        f'master={master_ticket} → slave={slave_ticket} '
                        f'open={slave_open_price}'
                    )
                    ctx[slave_key] = {}

                ctx[slave_key]['ticket']     = slave_ticket
                ctx[slave_key]['open_price'] = slave_open_price

    # ------------------------------------------------------------------
    # Handlers — eventos do Master
    # ------------------------------------------------------------------
    async def _handle_open(self, key: str, msg: dict):
        master_ticket  = int(msg.get('master_ticket') or msg.get('ticket') or 0)
        symbol         = msg.get('symbol', '')
        order_type     = msg.get('order_type', '')
        open_price     = float(msg.get('open_price', 0.0))
        sl             = float(msg.get('sl', 0))
        tp             = float(msg.get('tp', 0))
        volume_master  = float(msg.get('volume', 0))
        comment        = msg.get('comment', '')

        if not master_ticket or not symbol or not volume_master:
            logger.error(f'[{key}] OPEN incompleto: {msg}')
            return

        # Salva contexto do Master para uso posterior no MODIFY_SLTP
        point = self._symbol_point(symbol)
        self._ticket_map.setdefault(master_ticket, {})
        ctx = self._ticket_map[master_ticket]
        ctx['order_type'] = order_type
        ctx['open_price'] = open_price
        ctx['symbol']     = symbol
        ctx['point']      = point

        logger.info(
            f'[{key}] OPEN master_ticket={master_ticket} {symbol} {order_type} '
            f'vol={volume_master} open={open_price} sl={sl} tp={tp}'
        )

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
        reason = msg.get('reason', '')
        if reason == 'PARTIAL':
            await self._handle_partial_close(key, msg)
            return

        master_ticket = int(msg.get('master_ticket') or msg.get('ticket') or 0)
        if not master_ticket:
            logger.error(f'[{key}] CLOSE sem ticket: {msg}')
            return

        logger.info(f'[{key}] CLOSE master_ticket={master_ticket}')
        ctx = self._ticket_map.get(master_ticket, {})

        for slave_key, _ in self._get_slaves():
            slave_info   = ctx.get(slave_key, {})
            slave_ticket = slave_info.get('ticket') if isinstance(slave_info, dict) else None
            if not slave_ticket:
                logger.warning(
                    f'[{slave_key}] slave_ticket não encontrado para '
                    f'master={master_ticket}, CLOSE ignorado.'
                )
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
        master_ticket        = int(msg.get('master_ticket') or msg.get('ticket') or 0)
        symbol               = msg.get('symbol', '')
        volume_master_closed = float(msg.get('volume_closed', 0))

        if not master_ticket:
            logger.error(f'[{key}] PARTIAL_CLOSE sem ticket: {msg}')
            return
        if volume_master_closed <= 0:
            logger.error(f'[{key}] PARTIAL_CLOSE volume_closed inválido: {msg}')
            return

        logger.info(
            f'[{key}] PARTIAL_CLOSE master_ticket={master_ticket} '
            f'vol_closed={volume_master_closed}'
        )
        ctx = self._ticket_map.get(master_ticket, {})

        for slave_key, slave_data in self._get_slaves():
            slave_info   = ctx.get(slave_key, {})
            slave_ticket = slave_info.get('ticket') if isinstance(slave_info, dict) else None
            if not slave_ticket:
                logger.warning(
                    f'[{slave_key}] slave_ticket não encontrado para '
                    f'master={master_ticket}, PARTIAL_CLOSE ignorado.'
                )
                continue

            lot_factor         = float(slave_data.get('lot_factor', 1.0))
            close_volume_slave = self._calc_volume(volume_master_closed, lot_factor, symbol)

            payload = json.dumps({
                'protocol_version': '1.0',
                'event_type':       'PARTIAL_CLOSE',
                'slave_id':         slave_key,
                'master_id':        key,
                'master_ticket':    master_ticket,
                'ticket':           slave_ticket,
                'close_volume':     close_volume_slave,
                'symbol':           symbol,
            }, separators=(',', ':'))
            sent = await self.zmq.send(slave_key, payload)
            if sent:
                logger.info(
                    f'[{slave_key}] PARTIAL_CLOSE enviado: '
                    f'slave_ticket={slave_ticket} close_vol={close_volume_slave}'
                )

    async def _handle_modify(self, key: str, msg: dict):
        master_ticket = int(msg.get('master_ticket') or msg.get('ticket') or 0)
        master_sl     = float(msg.get('sl', 0))
        master_tp     = float(msg.get('tp', 0))

        if not master_ticket:
            logger.error(f'[{key}] MODIFY_SLTP sem ticket: {msg}')
            return

        ctx = self._ticket_map.get(master_ticket)
        if not ctx:
            logger.warning(
                f'[{key}] MODIFY_SLTP master_ticket={master_ticket} '
                f'sem contexto no ticket_map, ignorado.'
            )
            return

        order_type   = ctx.get('order_type', 'BUY')
        master_open  = ctx.get('open_price', 0.0)
        point        = ctx.get('point', 0.00001)

        # Calcula distâncias em pontos (a partir do open do Master)
        if master_open > 0 and point > 0:
            if order_type == 'BUY':
                sl_points = round((master_open - master_sl) / point) if master_sl > 0 else 0
                tp_points = round((master_tp - master_open) / point) if master_tp > 0 else 0
            else:  # SELL
                sl_points = round((master_sl - master_open) / point) if master_sl > 0 else 0
                tp_points = round((master_open - master_tp) / point) if master_tp > 0 else 0
        else:
            sl_points = 0
            tp_points = 0
            logger.warning(
                f'[{key}] MODIFY_SLTP master_ticket={master_ticket}: '
                f'open_price={master_open} ou point={point} inválido, '
                f'enviando sl/tp absolutos do Master.'
            )

        logger.info(
            f'[{key}] MODIFY_SLTP master_ticket={master_ticket} '
            f'sl={master_sl} tp={master_tp} '
            f'→ sl_pts={sl_points} tp_pts={tp_points}'
        )

        for slave_key, _ in self._get_slaves():
            slave_info   = ctx.get(slave_key, {})
            slave_ticket = slave_info.get('ticket') if isinstance(slave_info, dict) else None
            if not slave_ticket:
                logger.warning(
                    f'[{slave_key}] slave_ticket não encontrado para '
                    f'master={master_ticket}, MODIFY ignorado.'
                )
                continue

            slave_open = slave_info.get('open_price', 0.0) if isinstance(slave_info, dict) else 0.0

            # Reconstrói preços absolutos para o Slave com base no seu próprio open
            if slave_open > 0 and point > 0 and (sl_points > 0 or tp_points > 0):
                if order_type == 'BUY':
                    sl_slave = round(slave_open - (sl_points * point), 5) if sl_points > 0 else 0.0
                    tp_slave = round(slave_open + (tp_points * point), 5) if tp_points > 0 else 0.0
                else:  # SELL
                    sl_slave = round(slave_open + (sl_points * point), 5) if sl_points > 0 else 0.0
                    tp_slave = round(slave_open - (tp_points * point), 5) if tp_points > 0 else 0.0
            else:
                # Fallback: sem open_price do Slave, envia os valores absolutos do Master
                sl_slave = master_sl
                tp_slave = master_tp
                logger.warning(
                    f'[{slave_key}] slave_open_price não disponível para '
                    f'master={master_ticket}, usando sl/tp absolutos do Master como fallback.'
                )

            payload = json.dumps({
                'protocol_version': '1.0',
                'event_type':       'MODIFY_SLTP',
                'slave_id':         slave_key,
                'master_id':        key,
                'master_ticket':    master_ticket,
                'ticket':           slave_ticket,
                'sl':               sl_slave,
                'tp':               tp_slave,
            }, separators=(',', ':'))
            sent = await self.zmq.send(slave_key, payload)
            if sent:
                logger.info(
                    f'[{slave_key}] MODIFY_SLTP enviado: slave_ticket={slave_ticket} '
                    f'sl={sl_slave} tp={tp_slave}'
                )

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

    def _symbol_point(self, symbol: str) -> float:
        """
        Retorna o tamanho do ponto para o símbolo.
        Heurística: símbolos com JPY têm point=0.01, demais 0.00001.
        Para precisão real, considere buscar do broker_manager.
        """
        if 'JPY' in symbol.upper():
            return 0.01
        return 0.00001

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
