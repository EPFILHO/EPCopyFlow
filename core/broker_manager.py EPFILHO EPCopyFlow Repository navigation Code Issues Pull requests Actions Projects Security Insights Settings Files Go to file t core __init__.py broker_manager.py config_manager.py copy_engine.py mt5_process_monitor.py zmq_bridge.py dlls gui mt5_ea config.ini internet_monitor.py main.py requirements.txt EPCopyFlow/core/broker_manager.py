import os
import shutil
import subprocess
import logging

logger = logging.getLogger(__name__)

class BrokerManager:
    def __init__(self, root_path, instances_dir, base_mt5_path):
        self.root_path = root_path
        self.instances_dir = instances_dir
        self.base_mt5_path = base_mt5_path
        self.brokers = {}
        self.mt5_processes = {}
        self.connected_brokers = {}
        
        if not os.path.exists(self.instances_dir):
            os.makedirs(self.instances_dir)

    def setup_portable_instance(self, key):
        instance_path = os.path.join(self.instances_dir, key)
        executable = os.path.join(instance_path, 'terminal64.exe')
        
        if not os.path.exists(instance_path):
            try:
                os.makedirs(self.instances_dir, exist_ok=True)
                if os.path.exists(self.base_mt5_path):
                    shutil.copytree(self.base_mt5_path, instance_path)
                    logger.info(f'Instancia base copiada para {instance_path}')
                else:
                    logger.error(f'Base MT5 path nao encontrado: {self.base_mt5_path}')
                    return None
            except Exception as e:
                logger.error(f'Erro ao copiar arvore base do MT5 para {key}: {e}')
                return None
        
        # Garantir subpastas MQL5
        for subdir in ['MQL5/Experts', 'MQL5/Libraries', 'MQL5/Files', 'MQL5/Indicators', 'MQL5/Scripts']:
            os.makedirs(os.path.join(instance_path, subdir), exist_ok=True)
            
        self.copy_dlls(instance_path)
        self.copy_expert(instance_path)
        
        try:
            import win32api, win32con
            win32api.SetFileAttributes(instance_path, win32con.FILE_ATTRIBUTE_HIDDEN)
        except:
            pass
            
        logger.info(f'Instancia MT5 preparada em: {instance_path}')
        return executable

    def copy_dlls(self, instance_path):
        src = os.path.join(self.root_path, 'dlls')
        dst = os.path.join(instance_path, 'MQL5', 'Libraries')
        os.makedirs(dst, exist_ok=True)
        if os.path.exists(src):
            for f in os.listdir(src):
                if f.lower().endswith('.dll'):
                    shutil.copy2(os.path.join(src, f), dst)
            logger.info(f'DLLs copiadas para {dst}')

    def copy_expert(self, instance_path):
        possible_names = ['EPCopyBridge.ex5', 'ZmqTraderBridge.ex5']
        dst_folder = os.path.join(instance_path, 'MQL5', 'Experts')
        os.makedirs(dst_folder, exist_ok=True)
        
        found = False
        for name in possible_names:
            src = os.path.join(self.root_path, 'mt5_ea', name)
            if not os.path.exists(src):
                # Tentar subpasta se não encontrar na raiz de mt5_ea
                src = os.path.join(self.root_path, 'mt5_ea', 'ZmqTraderBridge', name)
            
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(dst_folder, 'EPCopyBridge.ex5'))
                logger.info(f'EA {name} copiado como EPCopyBridge.ex5')
                found = True
                break
        
        if not found:
            logger.warning('Nenhum Expert Advisor encontrado em mt5_ea/')

    def create_mt5_config(self, key, data):
        path = os.path.join(self.instances_dir, key, 'MQL5', 'Files', 'config.ini')
        os.makedirs(os.path.join(self.instances_dir, key, 'MQL5', 'Files'), exist_ok=True)
        
        base_port = int(data.get('push_port') or data.get('zmq_port') or 15555)
        
        lines = [
            '[ZMQ]',
            f'BrokerKey={key}',
            f"Role={data.get('role', 'slave')}",
            f"LotFactor={data.get('lot_factor', 1.0)}",
            '[Ports]',
            f'AdminPort={base_port}',
            f'DataPort={base_port+1}',
            f'TradePort={base_port+2}',
            f'LivePort={base_port+3}',
            f'StrPort={base_port+4}',
            '[Account]',
            f"Login={data.get('login', '')}",
            f"Server={data.get('server', '')}",
            f"Mode={data.get('mode', 'Hedge')}",
            f"Type={data.get('type', 'Demo')}"
        ]
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                                f.write(chr(10).join(lines) + chr(10))
                            logger.info(f'Config MT5 criado: {path}')
        except Exception as e:
            logger.error(f'Erro ao criar config MT5: {e}')

    def connect_broker(self, key, data):
        if key not in self.connected_brokers or not self.connected_brokers[key]:
            exe = self.setup_portable_instance(key)
            if not exe:
                return False
                
            self.create_mt5_config(key, data)
            
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 6 # SW_MINIMIZE
                
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
        return True

    def disconnect_broker(self, key):
        if key in self.mt5_processes:
            p = self.mt5_processes[key]
            p.terminate()
            try:
                p.wait(timeout=5)
            except:
                p.kill()
            del self.mt5_processes[key]
            self.connected_brokers[key] = False
            logger.info(f'MT5 encerrado para {key}')
            return True
        return False

    def is_connected(self, key):
        return self.connected_brokers.get(key, False)

    def get_brokers(self):
        return self.connected_brokers
