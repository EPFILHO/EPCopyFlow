import asyncio
import zmq
import zmq.asyncio
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class ZmqBridge:
    """
    Gerencia conexoes ZMQ para cada broker cadastrado.
    - Master: socket SUB (recebe eventos do EA Master via PUB)
    - Slave:  socket PUB (envia comandos para o EA Slave via SUB)
    """

    def __init__(self, context: zmq.asyncio.Context = None):
        self.context = context or zmq.asyncio.Context()
        self._sockets: dict[str, zmq.asyncio.Socket] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._callbacks: dict[str, list[Callable]] = {}
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
        for key, sock in self._sockets.items():
            try:
                sock.close()
            except Exception:
                pass
        self._sockets.clear()
        self._tasks.clear()
        logger.info('ZmqBridge encerrado.')

    # ------------------------------------------------------------------
    # Conexao por broker
    # ------------------------------------------------------------------

    async def _connect_broker(self, key: str, data: dict):
        """Cria o socket correto (SUB ou PUB) conforme o Role do broker."""
        role = str(data.get('role', 'slave')).lower()
        port = int(data.get('push_port') or data.get('zmq_port') or 0)

        if not port:
            logger.error(f'[{key}] Porta ZMQ nao definida, broker ignorado.')
            return

        address = f'tcp://127.0.0.1:{port}'

        try:
            if role == 'master':
                sock = self.context.socket(zmq.SUB)
                sock.connect(address)
                sock.setsockopt_string(zmq.SUBSCRIBE, '')  # recebe tudo
                self._sockets[key] = sock
                self._tasks[key] = asyncio.create_task(
                    self._recv_loop(key, sock), name=f'zmq_recv_{key}'
                )
                logger.info(f'[{key}] SUB conectado em {address} (master)')

            else:  # slave
                sock = self.context.socket(zmq.PUB)
                sock.bind(address)
                self._sockets[key] = sock
                logger.info(f'[{key}] PUB bind em {address} (slave)')

        except Exception as e:
            logger.error(f'[{key}] Erro ao criar socket ZMQ: {e}')

    # ------------------------------------------------------------------
    # Loop de recepcao (master)
    # ------------------------------------------------------------------

    async def _recv_loop(self, key: str, sock: zmq.asyncio.Socket):
        """Recebe mensagens do EA Master e dispara callbacks registrados."""
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
    # Envio (slave)
    # ------------------------------------------------------------------

    async def send(self, key: str, message: str) -> bool:
        """
        Envia uma mensagem JSON para um EA Slave.
        Retorna True se enviado com sucesso.
        """
        sock = self._sockets.get(key)
        if not sock:
            logger.error(f'[{key}] Socket nao encontrado para envio.')
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
        Registra um callback async para mensagens recebidas de um master.
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
        return key in self._sockets

    def get_connected_keys(self) -> list[str]:
        return list(self._sockets.keys())
