import os
import shutil
import subprocess
import logging

logger = logging.getLogger(__name__)


class BrokerManager:
    """
    Gerencia instancias portaveis do MT5.
    Assinatura: BrokerManager(config, base_mt5_path, root_path)
    """

    def __init__(self, config, base_mt5_path, root_path):
        self.config = config
        self.base_mt5_path = base_mt5_path
        self.root_path = root_path

        # Diretorio onde as instancias portaveis ficam
        self.instances_dir = os.path.join(root_path, 'mt5_instances')

        # brokers: {key: data_dict} - todos os brokers configurados
        self.brokers = {}

        # estado de processos e conexao
        self.mt5_processes = {}
        self.connected_brokers = {}  # {key: True/False}

        # Carregar brokers do config
        self._load_brokers()

        os.makedirs(self.instances_dir, exist_ok=True)

    def _load_brokers(self):
        """Carrega brokers da secao [Brokers] do config.ini."""
        try:
            if self.config.has_section('Brokers'):
                for key in self.config.options('Brokers'):
                    import json
                    raw = self.config.get('Brokers', key)
                    try:
                        data = json.loads(raw)
                    except Exception:
                        data = {'name': raw}
                    self.brokers[key] = data
                    self.connected_brokers[key] = False
                logger.info(f'Brokers carregados: {list(self.brokers.keys())}')
        except Exception as e:
            logger.error(f'Erro ao carregar brokers do config: {e}')

    def setup_portable_instance(self, key):
        """Copia a instancia base do MT5 para uma pasta portavel dedicada."""
        instance_path = os.path.join(self.instances_dir, key)
        executable = os.path.join(instance_path, 'terminal64.exe')

        if not os.path.exists(instance_path):
            try:
                if os.path.exists(self.base_mt5_path):
                    shutil.copytree(self.base_mt5_path, instance_path)
                    logger.info(f'Instancia base copiada para {instance_path}')
                else:
                    logger.error(f'Base MT5 path nao encontrado: {self.base_mt5_path}')
                    return None
            except Exception as e:
                logger.error(f'Erro ao copiar base MT5 para {key}: {e}')
                return None

        # Garantir subpastas MQL5
        for subdir in ['MQL5/Experts', 'MQL5/Libraries', 'MQL5/Files',
                        'MQL5/Indicators', 'MQL5/Scripts']:
            os.makedirs(os.path.join(instance_path, subdir), exist_ok=True)

        self.copy_dlls(instance_path)
        self.copy_expert(instance_path)

        try:
            import win32api
            import win32con
            win32api.SetFileAttributes(instance_path, win32con.FILE_ATTRIBUTE_HIDDEN)
        except Exception:
            pass

        logger.info(f'Instancia MT5 preparada em: {instance_path}')
        return executable

    def copy_dlls(self, instance_path):
        """Copia DLLs para a pasta Libraries da instancia."""
        src = os.path.join(self.root_path, 'dlls')
        dst = os.path.join(instance_path, 'MQL5', 'Libraries')
        os.makedirs(dst, exist_ok=True)
        if os.path.exists(src):
            for f in os.listdir(src):
                if f.lower().endswith('.dll'):
                    shutil.copy2(os.path.join(src, f), dst)
            logger.info(f'DLLs copiadas para {dst}')

    def copy_expert(self, instance_path):
        """Copia o EA para a pasta Experts da instancia."""
        possible_names = ['EPCopyBridge.ex5', 'ZmqTraderBridge.ex5']
        dst_folder = os.path.join(instance_path, 'MQL5', 'Experts')
        os.makedirs(dst_folder, exist_ok=True)

        found = False
        for name in possible_names:
            src = os.path.join(self.root_path, 'mt5_ea', name)
            if not os.path.exists(src):
                src = os.path.join(self.root_path, 'mt5_ea', 'ZmqTraderBridge', name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(dst_folder, 'EPCopyBridge.ex5'))
                logger.info(f'EA {name} copiado como EPCopyBridge.ex5')
                found = True
                break

        if not found:
            logger.warning('Nenhum EA encontrado em mt5_ea/')

    def create_mt5_config(self, key, data):
        """Cria o config.ini dentro da instancia do MT5 para o broker."""
        path = os.path.join(self.instances_dir, key, 'MQL5', 'Files', 'config.ini')
        os.makedirs(os.path.dirname(path), exist_ok=True)

        base_port = int(data.get('push_port') or data.get('zmq_port') or 15555)
        nl = chr(10)

        lines = [
            '[ZMQ]',
            'BrokerKey=' + str(key),
            'Role=' + str(data.get('role', 'slave')),
            'LotFactor=' + str(data.get('lot_factor', 1.0)),
            '[Ports]',
            'AdminPort=' + str(base_port),
            'DataPort=' + str(base_port + 1),
            'TradePort=' + str(base_port + 2),
            'LivePort=' + str(base_port + 3),
            'StrPort=' + str(base_port + 4),
            '[Account]',
            'Login=' + str(data.get('login', '')),
            'Server=' + str(data.get('server', '')),
            'Mode=' + str(data.get('mode', 'Hedge')),
            'Type=' + str(data.get('type', 'Demo')),
        ]

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(nl.join(lines) + nl)
            logger.info(f'Config MT5 criado: {path}')
        except Exception as e:
            logger.error(f'Erro ao criar config MT5: {e}')

    def connect_broker(self, key):
        """Inicia o MT5 portavel para o broker indicado."""
        if self.is_connected(key):
            return True

        data = self.brokers.get(key, {})
        exe = self.setup_portable_instance(key)
        if not exe:
            return False

        self.create_mt5_config(key, data)

        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 6  # SW_MINIMIZE

            self.mt5_processes[key] = subprocess.Popen(
                [exe, '/portable'],
                cwd=os.path.dirname(exe),
                startupinfo=si
            )
            self.connected_brokers[key] = True
            logger.info(f'MT5 iniciado para {key}')
            return True
        except Exception as e:
            logger.error(f'Erro ao iniciar MT5 para {key}: {e}')
            return False

    def disconnect_broker(self, key):
        """Encerra o processo MT5 do broker indicado."""
        if key in self.mt5_processes:
            p = self.mt5_processes[key]
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
            del self.mt5_processes[key]
            self.connected_brokers[key] = False
            logger.info(f'MT5 encerrado para {key}')
            return True
        return False

    def is_connected(self, key):
        """Retorna True se o broker esta conectado."""
        return self.connected_brokers.get(key, False)

    def get_brokers(self):
        """Retorna dict com todos os brokers configurados: {key: data}."""
        return self.brokers

    def get_connected_brokers(self):
        """Retorna lista de keys dos brokers atualmente conectados."""
        return [k for k, v in self.connected_brokers.items() if v]

    def add_broker(self, key, data):
        """Adiciona ou atualiza um broker em runtime."""
        self.brokers[key] = data
        if key not in self.connected_brokers:
            self.connected_brokers[key] = False
        logger.info(f'Broker adicionado: {key}')

    def remove_broker(self, key):
        """Remove um broker (desconecta se necessario)."""
        if self.is_connected(key):
            self.disconnect_broker(key)
        self.brokers.pop(key, None)
        self.connected_brokers.pop(key, None)
        logger.info(f'Broker removido: {key}')
