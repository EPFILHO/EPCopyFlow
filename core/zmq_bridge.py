# +------------------------------------------------------------------+
# |                                              core/zmq_bridge.py  |
# |                                              EP Filho © 2026     |
# |                  https://github.com/EPFILHO/EPCopyFlow           |
# +------------------------------------------------------------------+
import asyncio
import zmq
import zmq.asyncio
import logging
from typing import Callable

logger = logging.getLogger(__name__)


class ZmqBridge:
    """
    Gerencia conexoes ZMQ para cada broker cadastrado.

    Padrão de sockets:
      - Master → Python : PULL bind()  (recebe eventos do EA Master via PUSH)
      - Python → Slaves : PUB  bind()  (envia comandos para EA Slaves via SUB)
      - Slave  → Python : PULL bind()  (recebe heartbeat do EA Slave via PUSH)
    """

    def __init__(self, context: zmq.asyncio.Context = None):
        self.context   = context or zmq.asyncio.Context()
        self._cmd_sockets:  dict[str, zmq.asyncio.Socket] = {}  # PUB → Slave (comandos)
        self._pull_sockets: dict[str, zmq.asyncio.Socket] = {}  # PULL ← Master ou Slave HB
        self._tasks:        dict[str, asyncio.Task]        = {}
        self._callbacks:    dict[str, list[Callable]]      = {}
        self._running = False

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    async def start(self, brokers: dict):
        """
        Inicializa sockets para todos os brokers cadastrados.
        brokers: {key: data} vindo do BrokerManager.get_brokers()
        """
        self._running = True
        for key, data in brokers.items():
            await self._connect_broker(key, data)
        logger.info(f'ZmqBridge iniciado com {len(brokers)} broker(s).')

    async def stop(self):
        """Encerra todos os sockets e tasks."""
        self._running = False

        for key in list(self._tasks.keys()):
            self._tasks[key].cancel()
            try:
                await self._tasks[key]
            except asyncio.CancelledError:
                pass

        for sock in list(self._cmd_sockets.values()):
            try: sock.close()
            except Exception: pass

        for sock in list(self._pull_sockets.values()):
            try: sock.close()
            except Exception: pass

        self._cmd_sockets.clear()
        self._pull_sockets.clear()
        self._tasks.clear()
        logger.info('ZmqBridge encerrado.')

    # ------------------------------------------------------------------
    # Conexao por broker
    # ------------------------------------------------------------------
    async def _connect_broker(self, key: str, data: dict):
        """Cria os sockets corretos conforme o Role do broker."""
        role       = str(data.get('role', 'slave')).lower()
        trade_port = int(data.get('trade_port') or data.get('zmq_port') or 0)

        if not trade_port:
            logger.error(f'[{key}] TradePort nao definida, broker ignorado.')
            return

        try:
            if role == 'master':
                # PULL bind — recebe eventos PUSH do EA Master
                addr = f'tcp://127.0.0.1:{trade_port}'
                sock = self.context.socket(zmq.PULL)
                sock.bind(addr)
                self._pull_sockets[key] = sock
                self._tasks[key] = asyncio.create_task(
                    self._recv_loop(key, sock),
                    name=f'zmq_recv_{key}'
                )
                logger.info(f'[{key}] PULL bind em {addr} (master)')

            else:  # slave
                # PUB bind — envia comandos para SUB do EA Slave
                addr_cmd = f'tcp://127.0.0.1:{trade_port}'
                sock_pub  = self.context.socket(zmq.PUB)
                sock_pub.bind(addr_cmd)
                self._cmd_sockets[key] = sock_pub
                logger.info(f'[{key}] PUB bind em {addr_cmd} (slave - comandos)')

                # PULL bind — recebe heartbeat PUSH do EA Slave
                hb_port = int(data.get('heartbeat_port') or 0)
                if hb_port:
                    addr_hb  = f'tcp://127.0.0.1:{hb_port}'
                    sock_hb  = self.context.socket(zmq.PULL)
                    sock_hb.bind(addr_hb)
                    hb_key = f'{key}_hb'
                    self._pull_sockets[hb_key] = sock_hb
                    self._tasks[hb_key] = asyncio.create_task(
                        self._recv_loop(hb_key, sock_hb),
                        name=f'zmq_hb_{key}'
                    )
                    logger.info(f'[{key}] PULL bind em {addr_hb} (slave - heartbeat)')
                else:
                    logger.warning(f'[{key}] HeartbeatPort nao definida, heartbeat do Slave ignorado.')

        except Exception as e:
            logger.error(f'[{key}] Erro ao criar socket ZMQ: {e}')

    # ------------------------------------------------------------------
    # Loop de recepcao (master e slave heartbeat)
    # ------------------------------------------------------------------
    async def _recv_loop(self, key: str, sock: zmq.asyncio.Socket):
        """Recebe mensagens e dispara callbacks registrados."""
        logger.info(f'[{key}] Loop de recepcao iniciado.')
        while self._running:
            try:
                raw = await sock.recv_string()
                logger.debug(f'[{key}] Recebido: {raw}')
                for cb in self._callbacks.get(key, []):
                    try:
                        await cb(key, raw)
                    except Exception as e:
                        logger.error(f'[{key}] Erro no callback: {e}')
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f'[{key}] Erro no recv_loop: {e}')
                await asyncio.sleep(1)
        logger.info(f'[{key}] Loop de recepcao encerrado.')

    # ------------------------------------------------------------------
    # Envio de comandos (Python → Slave)
    # ------------------------------------------------------------------
    async def send(self, key: str, message: str) -> bool:
        """
        Envia um comando JSON para um EA Slave pelo socket PUB.
        Retorna True se enviado com sucesso.
        """
        sock = self._cmd_sockets.get(key)
        if not sock:
            logger.error(f'[{key}] Socket de comando nao encontrado.')
            return False
        try:
            await sock.send_string(message)
            logger.debug(f'[{key}] Enviado: {message}')
            return True
        except Exception as e:
            logger.error(f'[{key}] Erro ao enviar mensagem: {e}')
            return False

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def register_callback(self, key: str, callback: Callable):
        """
        Registra callback async para mensagens recebidas.
        - Para master: key = broker_key (ex: 'FOTMARKETS-116486')
        - Para heartbeat slave: key = broker_key + '_hb' (ex: 'FBS-105914573_hb')

        Assinatura: async def callback(key: str, raw_message: str)
        """
        if key not in self._callbacks:
            self._callbacks[key] = []
        self._callbacks[key].append(callback)
        logger.info(f'[{key}] Callback registrado: {callback.__name__}')

    def unregister_callbacks(self, key: str):
        """Remove todos os callbacks de um broker."""
        self._callbacks.pop(key, None)

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def is_connected(self, key: str) -> bool:
        return key in self._cmd_sockets or key in self._pull_sockets

    def get_connected_keys(self) -> list[str]:
        return list(set(list(self._cmd_sockets.keys()) + list(self._pull_sockets.keys())))
