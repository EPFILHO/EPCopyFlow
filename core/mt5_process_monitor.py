# core/mt5_process_monitor.py
# EPCopyFlow - Watchdog de processos MT5
#
# Responsabilidade: monitorar em background se cada instancia MT5 marcada
# como "conectada" no BrokerManager ainda esta rodando. Se detectar que o
# processo terminou (fechamento acidental), reinicia automaticamente.
#
# Design:
#   - Roda em uma thread daemon separada (nao bloqueia o event loop do Qt/asyncio)
#   - Delega o restart ao BrokerManager.connect_broker(key) para reutilizar
#     toda a logica de setup_portable_instance + create_mt5_config ja existente
#   - Sem dependencia de zmq_router ou asyncio event_loop (desacoplado)
#   - check_interval configuravel (padrao: 10 segundos)

import time
import logging
import threading

logger = logging.getLogger(__name__)


class MT5ProcessMonitor:
    """
    Watchdog que monitora processos MT5 e os reinicia em caso de fechamento acidental.

    Uso:
        monitor = MT5ProcessMonitor(broker_manager)
        monitor.start()   # inicia a thread de monitoramento
        ...               # durante a vida do app
        monitor.stop()    # encerra a thread graciosamente no shutdown
    """

    def __init__(self, broker_manager, check_interval=10):
        """
        Args:
            broker_manager (BrokerManager): Gerenciador de corretoras/instancias.
            check_interval (int): Intervalo em segundos entre cada verificacao (padrao: 10).
        """
        self.broker_manager = broker_manager
        self.check_interval = check_interval
        self.running = False
        self._thread = None
        logger.info(f"MT5ProcessMonitor inicializado (intervalo: {check_interval}s).")

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def start(self):
        """Inicia a thread de monitoramento em background."""
        if self._thread and self._thread.is_alive():
            logger.warning("MT5ProcessMonitor ja esta em execucao. Ignorando start().")
            return
        self.running = True
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="MT5ProcessMonitor",
            daemon=True  # encerra automaticamente quando o processo principal terminar
        )
        self._thread.start()
        logger.info("MT5ProcessMonitor iniciado.")

    def stop(self, timeout=6):
        """
        Para a thread de monitoramento.

        Args:
            timeout (int): Tempo maximo de espera pelo encerramento da thread (segundos).
        """
        if not self.running:
            return
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("Thread do MT5ProcessMonitor nao terminou apos join — sera encerrada pelo OS.")
            else:
                logger.info("Thread do MT5ProcessMonitor encerrada com sucesso.")
        logger.info("MT5ProcessMonitor parado.")

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------

    def _monitor_loop(self):
        """Loop que roda na thread daemon e chama _check_and_restart periodicamente."""
        logger.debug("MT5ProcessMonitor: loop de monitoramento iniciado.")
        while self.running:
            try:
                self._check_and_restart()
            except Exception as e:
                logger.error(f"MT5ProcessMonitor: erro inesperado no loop: {e}", exc_info=True)
            # Espera fracionada para responder ao stop() mais rapidamente
            for _ in range(self.check_interval * 2):
                if not self.running:
                    break
                time.sleep(0.5)
        logger.debug("MT5ProcessMonitor: loop de monitoramento encerrado.")

    # ------------------------------------------------------------------
    # Logica de verificacao
    # ------------------------------------------------------------------

    def _check_and_restart(self):
        """
        Verifica cada broker marcado como conectado:
          - Se o processo MT5 nao existe mais (poll() != None ou entrada ausente),
            limpa o estado e chama connect_broker() para reabrir o MT5.
        """
        brokers = list(self.broker_manager.get_brokers().keys())  # copia para evitar race condition

        for key in brokers:
            # So monitora brokers que o usuario conectou intencionalmente
            if not self.broker_manager.is_connected(key):
                continue

            process = self.broker_manager.mt5_processes.get(key)

            if process is None:
                # Broker marcado como conectado mas sem processo registrado
                logger.warning(
                    f"Watchdog: broker '{key}' esta marcado como conectado mas sem processo registrado. "
                    f"Reiniciando MT5..."
                )
                self._restart(key)

            elif process.poll() is not None:
                # Processo terminou (exit code qualquer)
                exit_code = process.poll()
                logger.warning(
                    f"Watchdog: MT5 do broker '{key}' fechou inesperadamente "
                    f"(exit code: {exit_code}). Reiniciando..."
                )
                # Limpa o estado antes de reconectar
                self.broker_manager.mt5_processes.pop(key, None)
                self.broker_manager.connected_brokers[key] = False
                self._restart(key)

    def _restart(self, key):
        """
        Delega o restart ao BrokerManager.connect_broker(), que ja contem
        toda a logica de setup_portable_instance + create_mt5_config.

        Args:
            key (str): Chave do broker a ser reiniciado.
        """
        try:
            success = self.broker_manager.connect_broker(key)
            if success:
                logger.info(f"Watchdog: MT5 do broker '{key}' reiniciado com sucesso.")
            else:
                logger.error(
                    f"Watchdog: falha ao reiniciar MT5 do broker '{key}'. "
                    f"Verifique os logs do BrokerManager."
                )
        except Exception as e:
            logger.error(f"Watchdog: excecao ao tentar reiniciar broker '{key}': {e}", exc_info=True)
