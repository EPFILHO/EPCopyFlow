import os
import json
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
        self.instances_dir = os.path.join(root_path, 'mt5_instances')
        self.brokers = {}
        self.mt5_processes = {}
        self.connected_brokers = {}
        self._load_brokers()
        os.makedirs(self.instances_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _get_parser(self):
        """Retorna o configparser interno do ConfigManager."""
        if hasattr(self.config, 'config'):
            return self.config.config
        return self.config

    def _save_broker_to_config(self, key, data):
        """Persiste os dados do broker na secao [Brokers] do config.ini."""
        parser = self._get_parser()
        if not parser.has_section('Brokers'):
            parser.add_section('Brokers')
        parser.set('Brokers', key, json.dumps(data))
        if hasattr(self.config, 'save_config'):
            self.config.save_config()
        else:
            try:
                with open(self.config.config_file, 'w', encoding='utf-8') as f:
                    parser.write(f)
            except Exception as e:
                logger.error(f'Erro ao salvar config: {e}')

    def _remove_broker_from_config(self, key):
        """Remove o broker da secao [Brokers] do config.ini."""
        parser = self._get_parser()
        if parser.has_section('Brokers') and parser.has_option('Brokers', key):
            parser.remove_option('Brokers', key)
        if hasattr(self.config, 'save_config'):
            self.config.save_config()
        else:
            try:
                with open(self.config.config_file, 'w', encoding='utf-8') as f:
                    parser.write(f)
            except Exception as e:
                logger.error(f'Erro ao salvar config: {e}')

    # ------------------------------------------------------------------
    # Carregamento
    # ------------------------------------------------------------------

    def _load_brokers(self):
        """Carrega brokers da secao [Brokers] do config.ini."""
        try:
            parser = self._get_parser()
            if parser.has_section('Brokers'):
                for key in parser.options('Brokers'):
                    raw = parser.get('Brokers', key)
                    try:
                        data = json.loads(raw)
                    except Exception:
                        data = {'name': raw}
                    self.brokers[key] = data
                    self.connected_brokers[key] = False
            logger.info(f'Brokers carregados: {list(self.brokers.keys())}')
        except Exception as e:
            logger.error(f'Erro ao carregar brokers do config: {e}')

    # ------------------------------------------------------------------
    # Setup de instancia
    # ------------------------------------------------------------------

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

        for subdir in ['MQL5/Experts', 'MQL5/Libraries', 'MQL5/Files',
                       'MQL5/Indicators', 'MQL5/Scripts']:
            os.makedirs(os.path.join(instance_path, subdir), exist_ok=True)

        self.copy_dlls(instance_path)

        role = self.brokers.get(key, {}).get('role', 'slave')
        self.copy_expert(instance_path, role)

        logger.info(f'Instancia MT5 preparada em: {instance_path}')
        return executable

    def copy_dlls(self, instance_path):
        src = os.path.join(self.root_path, 'dlls')
        dst = os.path.join(instance_path, 'MQL5', 'Libraries')
        os.makedirs(dst, exist_ok=True)
        if not os.path.exists(src):
            return
        for f in os.listdir(src):
            if not f.lower().endswith('.dll'):
                continue
            src_file = os.path.join(src, f)
            dst_file = os.path.join(dst, f)
            if self._should_copy(src_file, dst_file):
                shutil.copy2(src_file, dst_file)
                logger.info(f'DLL copiada: {f}')
            else:
                logger.debug(f'DLL ja atualizada, pulando: {f}')

    def copy_expert(self, instance_path, role: str = 'slave'):
        role = role.strip().lower()
        ea_name = 'EPCopyFlow_Master.ex5' if role == 'master' else 'EPCopyFlow_Slave.ex5'
        # Busca o .ex5 na instalacao base do MT5
        src = os.path.join(self.base_mt5_path, 'MQL5', 'Experts', ea_name)
        dst_folder = os.path.join(instance_path, 'MQL5', 'Experts')
        os.makedirs(dst_folder, exist_ok=True)
        dst = os.path.join(dst_folder, ea_name)
        if not os.path.exists(src):
            logger.warning(f'EA nao encontrado: {src}')
        return
        if self._should_copy(src, dst):
            shutil.copy2(src, dst)
            logger.info(f'EA copiado: {ea_name} → {dst_folder}')
        else:
            logger.debug(f'EA ja atualizado, pulando: {ea_name}')

    def _should_copy(self, src: str, dst: str) -> bool:
        """Retorna True se o arquivo destino nao existe ou tem tamanho diferente."""
        if not os.path.exists(dst):
            return True
        return os.path.getsize(src) != os.path.getsize(dst)

    def create_mt5_config(self, key, data):
        """
        Cria o epcopyflow.cfg dentro de MQL5/Files/ da instancia MT5.

        Formato Master:
            [EPCopyFlow]
            MasterId=<key>
            ProtocolVersion=1.0
            Role=master
            [Ports]
            TradePort=<port>

        Formato Slave:
            [EPCopyFlow]
            SlaveId=<key>
            MasterId=<master_id>
            ProtocolVersion=1.0
            Role=slave
            [Ports]
            TradePort=<port>
            HeartbeatPort=<port>
        """
        path = os.path.join(self.instances_dir, key, 'MQL5', 'Files', 'epcopyflow.cfg')
        os.makedirs(os.path.dirname(path), exist_ok=True)

        role = str(data.get('role', 'slave')).lower()

        if role == 'master':
            trade_port = int(data.get('push_port') or data.get('zmq_port') or 15560)
            lines = [
                '[EPCopyFlow]',
                f'MasterId={key}',
                'ProtocolVersion=1.0',
                'Role=master',
                '',
                '[Ports]',
                f'TradePort={trade_port}',
            ]
            log_info = f'MasterId={key}, TradePort={trade_port}'
        else:
            trade_port     = int(data.get('trade_port')     or data.get('push_port') or 15556)
            heartbeat_port = int(data.get('heartbeat_port') or data.get('sub_port')  or 15557)
            master_id      = str(data.get('master_id', 'MASTER_1'))
            lines = [
                '[EPCopyFlow]',
                f'SlaveId={key}',
                f'MasterId={master_id}',
                'ProtocolVersion=1.0',
                'Role=slave',
                '',
                '[Ports]',
                f'TradePort={trade_port}',
                f'HeartbeatPort={heartbeat_port}',
            ]
            log_info = (f'SlaveId={key}, MasterId={master_id}, '
                        f'TradePort={trade_port}, HeartbeatPort={heartbeat_port}')

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
            logger.info(f'epcopyflow.cfg criado: {path} [{log_info}]')
        except Exception as e:
            logger.error(f'Erro ao criar epcopyflow.cfg ({path}): {e}')

    # ------------------------------------------------------------------
    # Conexao / Desconexao
    # ------------------------------------------------------------------

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
            si.wShowWindow = 6
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

    def disconnect_all_brokers(self):
        """Encerra todos os processos MT5 abertos."""
        logger.info('Encerrando todos os processos MT5...')
        for key in list(self.mt5_processes.keys()):
            self.disconnect_broker(key)
        logger.info('Todos os processos MT5 foram encerrados.')

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def is_connected(self, key):
        """Retorna True se o broker esta conectado."""
        return self.connected_brokers.get(key, False)

    def get_brokers(self):
        """Retorna dict com todos os brokers cadastrados: {key: data}."""
        return self.brokers

    def get_connected_brokers(self):
        """Retorna lista de keys dos brokers atualmente conectados."""
        return [k for k, v in self.connected_brokers.items() if v]

    # ------------------------------------------------------------------
    # CRUD de brokers
    # ------------------------------------------------------------------

    def add_broker(self, **kwargs):
        """
        Adiciona um broker em runtime e persiste no config.ini.
        A 'key' e derivada como BROKER-LOGIN (ex: 'XM-116486').
        Retorna True em caso de sucesso.
        """
        login       = str(kwargs.get('login', '')).strip()
        broker_name = str(kwargs.get('broker_name', '')).strip().replace(' ', '_')
        if not login:
            logger.error('add_broker: campo login e obrigatorio')
            return False
        if not broker_name:
            logger.error('add_broker: campo broker_name e obrigatorio')
            return False
        key = f'{broker_name}-{login}'
        self.brokers[key] = dict(kwargs)
        if key not in self.connected_brokers:
            self.connected_brokers[key] = False
        self._save_broker_to_config(key, self.brokers[key])
        logger.info(f'Broker adicionado: {key}')
        return True

    def modify_broker(self, key, **kwargs):
        """
        Atualiza os dados de um broker existente e persiste no config.ini.
        Retorna True em caso de sucesso.
        """
        if key not in self.brokers:
            logger.error(f'modify_broker: broker {key} nao encontrado')
            return False
        self.brokers[key].update(kwargs)
        self._save_broker_to_config(key, self.brokers[key])
        logger.info(f'Broker modificado: {key}')
        return True

    def remove_broker(self, key):
        """Remove um broker (desconecta, apaga diretorio e config)."""
        if self.is_connected(key):
            self.disconnect_broker(key)
        # Apaga o diretorio da instancia portavel
        instance_path = os.path.join(self.instances_dir, key)
        if os.path.exists(instance_path):
            try:
                shutil.rmtree(instance_path)
                logger.info(f'Diretorio removido: {instance_path}')
            except Exception as e:
                logger.error(f'Erro ao remover diretorio {instance_path}: {e}')
        self.brokers.pop(key, None)
        self.connected_brokers.pop(key, None)
        self._remove_broker_from_config(key)
        logger.info(f'Broker removido: {key}')
        return True
