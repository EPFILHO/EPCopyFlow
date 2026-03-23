# core/zmq_bridge.py
# EPCopyFlow - Versao 2.0.0
# Responsabilidade: Gerenciar EXCLUSIVAMENTE os sockets ZMQ entre Python, master e slaves.
# Nao contem logica de negocio — apenas transporte de mensagens.
#
# Arquitetura de sockets:
#   - 1 socket DEALER por instancia MT5 (master e slaves usam o mesmo padrao)
#   - Master: Python ESCUTA (recv) eventos de trade vindos do EA
#   - Slaves: Python ENVIA (send) ordens para o EA executar
#   - Protocolo: JSON em texto puro (UTF-8)

import asyncio
import json
import logging

import zmq
import zmq.asyncio
from PySide6.QtCore import QObject, Signal

from core.config_manager import ConfigManager

logger = logging.getLogger(__name__)


class ZmqBridge(QObject):
    """
    Gerenciador de sockets ZMQ para o EPCopyFlow.

    Sinais emitidos (para uso pelo CopyEngine e GUI):
        master_event_received(dict)          : evento de trade bruto do master
        slave_ack_received(str, dict)        : (broker_key, resposta do slave)
        connection_changed(str, str, bool)   : (broker_key, role, connected)
        bridge_log(str, str)                 : (level, mensagem) para o log da GUI
    """

    master_event_received = Signal(dict)
    slave_ack_received = Signal(str, dict)
    connection_changed = Signal(str, str, bool)
    bridge_log = Signal(str, str)

    # -------------------------------------------------------------------------
    # Bloco 1 - Inicializacao
    # -------------------------------------------------------------------------
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self._config = config
        self._host = config.get('CopyEngine', 'host', fallback='127.0.0.1')
        self._recv_timeout = config.getint('CopyEngine', 'recv_timeout_ms', fallback=1000)
        self._reconnect_interval = config.getint('CopyEngine', 'reconnect_interval_s', fallback=3)

        self._context: zmq.asyncio.Context | None = None
        self._running = False

        # broker_key -> {'socket': zmq.Socket, 'role': 'master'|'slave', 'port': int}
        self._sockets: dict[str, dict] = {}

        # broker_key -> asyncio.Task (loop de recepcao)
        self._recv_tasks: dict[str, asyncio.Task] = {}

        logger.debug("ZmqBridge inicializado. Host: %s", self._host)

    # -------------------------------------------------------------------------
    # Bloco 2 - Ciclo de vida (start / stop)
    # -------------------------------------------------------------------------
    async def start(self, brokers: dict) -> None:
        """
        Inicia o bridge: cria o contexto ZMQ e conecta todos os brokers ativos.

        Args:
            brokers (dict): dicionario completo do brokers.json, ex:
                {
                  'XP-12345': {'role': 'master', 'zmq_port': 15555, ...},
                  'RICO-67890': {'role': 'slave',  'zmq_port': 15556, 'lot_factor': 1.0, ...}
                }
        """
        if self._running:
            logger.warning("ZmqBridge.start() chamado mas bridge ja esta rodando.")
            return

        self._context = zmq.asyncio.Context()
        self._running = True
        logger.info("ZmqBridge iniciado.")
        self.bridge_log.emit('INFO', 'ZmqBridge iniciado.')

        for key, data in brokers.items():
            role = data.get('role', 'slave')
            port = data.get('zmq_port')
            if port:
                await self.connect_peer(key, role, int(port))

    async def stop(self) -> None:
        """Encerra todos os sockets e o contexto ZMQ de forma limpa."""
        if not self._running:
            return
        self._running = False

        # Cancela todos os loops de recepcao
        for key, task in list(self._recv_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._recv_tasks.clear()

        # Fecha os sockets
        for key, peer in list(self._sockets.items()):
            try:
                peer['socket'].close(linger=0)
            except Exception as e:
                logger.warning("Erro ao fechar socket de %s: %s", key, e)
        self._sockets.clear()

        if self._context:
            self._context.term()
            self._context = None

        logger.info("ZmqBridge encerrado.")
        self.bridge_log.emit('INFO', 'ZmqBridge encerrado.')

    # -------------------------------------------------------------------------
    # Bloco 3 - Gerenciamento de peers (connect / disconnect)
    # -------------------------------------------------------------------------
    async def connect_peer(self, broker_key: str, role: str, port: int) -> bool:
        """
        Conecta um peer (master ou slave) via socket DEALER.

        - Master: socket em modo RECV (escuta passiva)
        - Slave:  socket em modo SEND (envio de ordens)

        Args:
            broker_key (str): chave unica do broker (ex: 'XP-12345')
            role (str): 'master' ou 'slave'
            port (int): porta ZMQ deste broker

        Returns:
            bool: True se conectado com sucesso
        """
        if not self._running or not self._context:
            logger.error("connect_peer chamado antes de start().")
            return False

        if broker_key in self._sockets:
            logger.warning("Peer %s ja esta conectado.", broker_key)
            return True

        try:
            sock = self._context.socket(zmq.DEALER)
            sock.setsockopt(zmq.RCVTIMEO, self._recv_timeout)
            sock.setsockopt(zmq.LINGER, 0)
            addr = f"tcp://{self._host}:{port}"
            sock.connect(addr)

            self._sockets[broker_key] = {'socket': sock, 'role': role, 'port': port}
            logger.info("Peer conectado: %s (%s) em %s", broker_key, role, addr)
            self.bridge_log.emit('INFO', f"Conectado: {broker_key} ({role}) porta {port}")
            self.connection_changed.emit(broker_key, role, True)

            # Inicia loop de recepcao para TODOS os peers
            # (slaves tambem podem enviar ACK/NACK de volta)
            task = asyncio.create_task(
                self._recv_loop(broker_key),
                name=f"recv_{broker_key}"
            )
            self._recv_tasks[broker_key] = task
            return True

        except Exception as e:
            logger.error("Falha ao conectar peer %s: %s", broker_key, e)
            self.bridge_log.emit('ERROR', f"Falha ao conectar {broker_key}: {e}")
            return False

    async def disconnect_peer(self, broker_key: str) -> None:
        """Desconecta um peer e cancela seu loop de recepcao."""
        task = self._recv_tasks.pop(broker_key, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        peer = self._sockets.pop(broker_key, None)
        if peer:
            try:
                peer['socket'].close(linger=0)
            except Exception:
                pass
            role = peer.get('role', 'slave')
            logger.info("Peer desconectado: %s", broker_key)
            self.bridge_log.emit('INFO', f"Desconectado: {broker_key}")
            self.connection_changed.emit(broker_key, role, False)

    # -------------------------------------------------------------------------
    # Bloco 4 - Envio de mensagens
    # -------------------------------------------------------------------------
    async def send_to_slave(self, broker_key: str, message: dict) -> bool:
        """
        Envia um comando JSON para um slave especifico.

        Args:
            broker_key (str): chave do slave
            message (dict): payload a enviar

        Returns:
            bool: True se enviado com sucesso
        """
        peer = self._sockets.get(broker_key)
        if not peer:
            logger.error("send_to_slave: peer '%s' nao encontrado.", broker_key)
            return False
        if peer.get('role') != 'slave':
            logger.warning("send_to_slave: '%s' nao e um slave.", broker_key)
            return False
        return await self._send(peer['socket'], broker_key, message)

    async def send_to_all_slaves(self, message: dict) -> dict[str, bool]:
        """
        Envia um comando para TODOS os slaves conectados.

        Returns:
            dict broker_key -> bool (sucesso por slave)
        """
        results = {}
        for key, peer in self._sockets.items():
            if peer.get('role') == 'slave':
                results[key] = await self._send(peer['socket'], key, message)
        return results

    async def _send(self, sock: zmq.asyncio.Socket, broker_key: str, message: dict) -> bool:
        """Serializacao e envio efetivo de uma mensagem JSON."""
        try:
            payload = json.dumps(message, ensure_ascii=False).encode('utf-8')
            await sock.send(payload)
            logger.debug("Enviado para %s: %s", broker_key, message)
            return True
        except Exception as e:
            logger.error("Erro ao enviar para %s: %s", broker_key, e)
            self.bridge_log.emit('ERROR', f"Erro de envio para {broker_key}: {e}")
            return False

    # -------------------------------------------------------------------------
    # Bloco 5 - Loop de recepcao
    # -------------------------------------------------------------------------
    async def _recv_loop(self, broker_key: str) -> None:
        """
        Loop asyncio que fica escutando mensagens de um peer.
        Para o master: emite master_event_received com o dict JSON.
        Para os slaves: emite slave_ack_received com (broker_key, dict).
        Reconecta automaticamente se o socket falhar.
        """
        logger.debug("Loop de recepcao iniciado para: %s", broker_key)
        while self._running and broker_key in self._sockets:
            peer = self._sockets.get(broker_key)
            if not peer:
                break
            sock = peer['socket']
            role = peer.get('role', 'slave')
            try:
                raw = await sock.recv()
                try:
                    data = json.loads(raw.decode('utf-8'))
                    logger.debug("Recebido de %s (%s): %s", broker_key, role, data)
                    if role == 'master':
                        self.master_event_received.emit(data)
                    else:
                        self.slave_ack_received.emit(broker_key, data)
                except json.JSONDecodeError as e:
                    logger.warning("JSON invalido de %s: %s | raw: %s", broker_key, e, raw)
            except zmq.Again:
                # Timeout normal — nao e erro, so nao chegou mensagem no periodo
                await asyncio.sleep(0)
            except asyncio.CancelledError:
                logger.debug("Loop de recepcao cancelado para: %s", broker_key)
                break
            except Exception as e:
                if self._running:
                    logger.error("Erro no loop de recepcao de %s: %s", broker_key, e)
                    self.bridge_log.emit('ERROR', f"Erro de recepcao {broker_key}: {e}")
                    # Aguarda antes de tentar continuar
                    await asyncio.sleep(self._reconnect_interval)

        logger.debug("Loop de recepcao encerrado para: %s", broker_key)

    # -------------------------------------------------------------------------
    # Bloco 6 - Consultas de estado
    # -------------------------------------------------------------------------
    def get_connected_peers(self) -> dict[str, dict]:
        """
        Retorna info dos peers atualmente conectados.

        Returns:
            dict broker_key -> {'role': str, 'port': int}
        """
        return {
            key: {'role': p['role'], 'port': p['port']}
            for key, p in self._sockets.items()
        }

    def is_connected(self, broker_key: str) -> bool:
        """Verifica se um peer especifico esta conectado."""
        return broker_key in self._sockets

    def get_master_key(self) -> str | None:
        """Retorna a chave do peer master conectado, ou None se nao houver."""
        for key, peer in self._sockets.items():
            if peer.get('role') == 'master':
                return key
        return None

    def get_slave_keys(self) -> list[str]:
        """Retorna lista de chaves dos slaves conectados."""
        return [k for k, p in self._sockets.items() if p.get('role') == 'slave']
