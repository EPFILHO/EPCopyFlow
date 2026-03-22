# core/mt5_process_monitor.py
# Versão 1.0.9.i - envio 1
import os
import psutil
import subprocess
import time
import logging
import asyncio
import threading

logger = logging.getLogger(__name__)

class MT5ProcessMonitor:
    def __init__(self, broker_manager, event_loop, check_interval=10):
        """
        Inicializa o monitor de processos MT5.

        Args:
            broker_manager (BrokerManager): Instância do BrokerManager para acessar processos e configurações.
            event_loop (asyncio.AbstractEventLoop): Loop de eventos asyncio principal.
            check_interval (int): Intervalo de verificação em segundos.
        """
        self.broker_manager = broker_manager
        self.event_loop = event_loop
        self.check_interval = check_interval
        self.running = False
        self.monitor_thread = None
        logger.info("MT5ProcessMonitor inicializado.")

    def start(self):
        """Inicia a thread de monitoramento."""
        if not self.monitor_thread or not self.monitor_thread.is_alive():
            self.running = True
            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("MT5ProcessMonitor iniciado.")
        else:
            logger.warning("MT5ProcessMonitor já está em execução.")

    def stop(self):
        """Para a thread de monitoramento."""
        if self.running:
            self.running = False
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=5)
                if self.monitor_thread.is_alive():
                    logger.warning("Thread de MT5ProcessMonitor não terminou após join.")
                else:
                    logger.info("Thread de MT5ProcessMonitor encerrada com sucesso.")
            logger.info("MT5ProcessMonitor parado.")

    def monitor_loop(self):
        """Loop principal que verifica e reinicia processos MT5 fechados."""
        while self.running:
            try:
                self.check_and_restart_processes()
            except Exception as e:
                logger.error(f"Erro no loop de monitoramento: {e}")
            time.sleep(self.check_interval)
        logger.debug("Monitoramento de processos MT5 encerrado.")

    def check_and_restart_processes(self):
        """Verifica processos MT5 e reinicia os que estão fechados."""
        # Itera sobre todas as corretoras conhecidas
        for key in self.broker_manager.get_brokers():
            if not self.broker_manager.is_connected(key):
                continue  # Pula corretoras não conectadas

            # Verifica se o processo está registrado e ativo
            process = self.broker_manager.mt5_processes.get(key)
            if process:
                poll_result = process.poll()
                if poll_result is not None:  # Processo terminou
                    logger.warning(f"Processo MT5 para {key} terminou (código de saída: {poll_result}). Reiniciando...")
                    # Remove o processo do rastreamento
                    del self.broker_manager.mt5_processes[key]
                    self.broker_manager.connected_brokers[key] = False
                    # Tenta reconectar
                    self.restart_mt5_instance(key)
            else:
                # Processo não está registrado, mas a corretora está marcada como conectada
                logger.warning(f"Processo MT5 para {key} não encontrado, mas está marcado como conectado. Reiniciando...")
                self.restart_mt5_instance(key)

    def restart_mt5_instance(self, key):
        """Reinicia uma instância MT5 para a corretora especificada."""
        instance_path = os.path.join(self.broker_manager.instances_dir, key, "terminal64.exe")
        if not os.path.exists(instance_path):
            logger.error(f"Instância do MT5 não encontrada para {key}: {instance_path}")
            return False

        try:
            # Obtém configurações da corretora
            broker_config = self.broker_manager.brokers[key]
            # Iniciar minimizado no Windows com parâmetros de login
            if os.name == 'nt':
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 6  # SW_MINIMIZE
                process = subprocess.Popen(
                    [
                        instance_path,
                        "/portable",
                        f"/login:{broker_config['login']}",
                        f"/password:{broker_config['password']}",
                        f"/server:{broker_config['server']}"
                    ],
                    cwd=os.path.dirname(instance_path),
                    startupinfo=si
                )
            else:
                process = subprocess.Popen(
                    [
                        instance_path,
                        "/portable",
                        f"/login:{broker_config['login']}",
                        f"/password:{broker_config['password']}",
                        f"/server:{broker_config['server']}"
                    ],
                    cwd=os.path.dirname(instance_path)
                )
            self.broker_manager.mt5_processes[key] = process
            self.broker_manager.connected_brokers[key] = True
            logger.info(f"MT5 reiniciado com sucesso para {key} (PID: {process.pid}).")

            # Reconecta os sockets ZMQ no loop de eventos principal
            if self.broker_manager.zmq_router:
                asyncio.run_coroutine_threadsafe(
                    self.broker_manager.zmq_router.connect_broker_sockets(key, broker_config),
                    self.event_loop
                )
                logger.info(f"Solicitado ao ZmqRouter para reconectar sockets para {key}.")
            return True
        except Exception as e:
            logger.error(f"Erro ao reiniciar MT5 para {key}: {e}")
            self.broker_manager.connected_brokers[key] = False
            return False

# core/mt5_process_monitor.py
# Versão 1.0.9.i - envio 1