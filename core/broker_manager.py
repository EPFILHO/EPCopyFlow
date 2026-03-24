# core/broker_manager.py
import json
import os
import shutil
import logging
import subprocess
import sys
from PySide6.QtCore import QObject, Signal
# core/broker_manager.py
import json
import os
import shutil
import logging
import subprocess
import sys
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

class BrokerManager(QObject):
    brokers_updated = Signal()

    def __init__(self, config, base_mt5_path, root_path):
        super().__init__()
        self.config = config
        self.brokers_file = config.get('General', 'brokers_file', fallback='brokers.json')
        self.base_mt5_path = base_mt5_path
        self.root_path = root_path
        self.instances_dir = os.path.join(self.root_path, \".mt5_instances\")
        self.mt5_processes = {}
        self.connected_brokers = {}
        self.brokers = self.load_brokers()

    def load_brokers(self):
        try:
            if os.path.exists(self.brokers_file):
                with open(self.brokers_file, 'r', encoding='utf-8') as f:
                    brokers = json.load(f)
                self.connected_brokers = {key: False for key in brokers}
                return brokers
            return {}
        except Exception as e:
            logger.error(f\"Erro ao carregar corretoras: {e}\")
            return {}

    def save_brokers(self):
        try:
            with open(self.brokers_file, 'w', encoding='utf-8') as f:
                json.dump(self.brokers, f, indent=4)
        except Exception as e:
            logger.error(f\"Erro ao salvar corretoras: {e}\")

    def add_broker(self, **data):
        if 'type_' in data and 'type' not in data:
            data['type'] = data.pop('type_')
        
        key = f\"{data['broker_name'].upper()}-{data['login']}\"
        if key in self.brokers:
            logger.warning(f\"Corretora {key} ja cadastrada.\")
            return None

        instance_path = self.setup_portable_instance(key)
        if not instance_path:
            return None

        self.brokers[key] = data
        self.save_brokers()
        self.connected_brokers[key] = False
        self.create_mt5_config(key, data)
        self.brokers_updated.emit()
        return key

    def remove_broker(self, key):
        if key not in self.brokers:
            return False
        
        if self.is_connected(key):
            self.disconnect_broker(key)
        
        del self.brokers[key]
        self.save_brokers()
        if key in self.connected_brokers:
            del self.connected_brokers[key]

        instance_path = os.path.join(self.instances_dir, key)
        if os.path.exists(instance_path):
            shutil.rmtree(instance_path, ignore_errors=True)
        
        self.brokers_updated.emit()
        return True

    def modify_broker(self, old_key, **data):
        if old_key not in self.brokers:
            return None
        
        if self.is_connected(old_key):
            self.disconnect_broker(old_key)
        
        # Se mudar o login ou corretora, recria a instancia
        new_key = f\"{data['broker_name'].upper()}-{data['login']}\"
        
        if new_key != old_key:
            self.remove_broker(old_key)
            return self.add_broker(**data)
        else:
            self.brokers[old_key] = data
            self.save_brokers()
            self.create_mt5_config(old_key, data)
            self.brokers_updated.emit()
            return old_key

    def setup_portable_instance(self, key):
        \"\"\"
        Cria uma instancia portatil do MT5 para a corretora.
        Copia arquivos essenciais do MT5 base e cria a estrutura MQL5.
        \"\"\"
        instance_path = os.path.join(self.instances_dir, key)
        executable = os.path.join(instance_path, \"terminal64.exe\")

        try:
            os.makedirs(instance_path, exist_ok=True)
            
            # Arquivos essenciais para o MT5 funcionar (minimalista mas funcional)
            essential_files = [\"terminal64.exe\", \"mql5.dll\", \"terminal.ico\"]
            
            for filename in essential_files:
                src = os.path.join(self.base_mt5_path, filename)
                dst = os.path.join(instance_path, filename)
                if os.path.exists(src):
                    shutil.copy2(src, dst)
                    logger.debug(f\"Arquivo copiado: {filename}\")
                elif filename == \"terminal64.exe\":
                    logger.error(f\"terminal64.exe nao encontrado em: {self.base_mt5_path}\")
                    if not os.path.exists(executable):
                        shutil.rmtree(instance_path, ignore_errors=True)
                        return None

            # Cria estrutura de pastas MQL5
            for subdir in [
                \"MQL5\\\\Experts\",
                \"MQL5\\\\Libraries\",
                \"MQL5\\\\Files\",
                \"MQL5\\\\Indicators\",
                \"MQL5\\\\Scripts\",
            ]:
                os.makedirs(os.path.join(instance_path, subdir), exist_ok=True)

            # Copia DLLs e EA
            self.copy_dlls(instance_path)
            self.copy_expert(instance_path)

            # Oculta diretorio no Windows (opcional)
            try:
                import win32api, win32con
                win32api.SetFileAttributes(instance_path, win32con.FILE_ATTRIBUTE_HIDDEN)
            except:
                pass

            logger.info(f\"Instancia MT5 preparada em: {instance_path}\")
            return executable

        except Exception as e:
            logger.error(f\"Erro ao criar instancia para {key}: {e}\")
            return None

    def copy_dlls(self, instance_path):
        src = os.path.join(self.root_path, \"dlls\")
        dst = os.path.join(instance_path, \"MQL5\", \"Libraries\")
        os.makedirs(dst, exist_ok=True)
        if os.path.exists(src):
            for f in os.listdir(src):
                if f.lower().endswith(\".dll\"):
                    shutil.copy2(os.path.join(src, f), dst)
            logger.info(f\"DLLs copiadas para {dst}\")

    def copy_expert(self, instance_path):
        # Tenta encontrar o EA com os nomes possiveis
        possible_names = [\"EPCopyBridge.ex5\", \"ZmqTraderBridge.ex5\"]
        dst_folder = os.path.join(instance_path, \"MQL5\", \"Experts\")
        os.makedirs(dst_folder, exist_ok=True)
        
        found = False
        for name in possible_names:
            src = os.path.join(self.root_path, \"mt5_ea\", name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(dst_folder, \"EPCopyBridge.ex5\")) # Salva como EPCopyBridge
                logger.info(f\"EA {name} copiado como EPCopyBridge.ex5\")
                found = True
                break
        
        if not found:
            logger.warning(f\"Nenhum Expert Advisor encontrado em mt5_ea/\")

    def create_mt5_config(self, key, data):
        path = os.path.join(self.instances_dir, key, \"MQL5\", \"Files\", \"config.ini\")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(\"[ZMQ]\
\")
                f.write(f\"BrokerKey={key}\
\")
                f.write(f\"Role={data.get('role', 'master')}\
\")
                f.write(f\"LotFactor={data.get('lot_factor', 1.0)}\
\")
                f.write(\"[Ports]\
\")
                f.write(f\"PushPort={data.get('push_port', 15555)}\
\")
                f.write(\"[Account]\
\")
                f.write(f\"Login={data.get('login', '')}\
\")
                f.write(f\"Server={data.get('server', '')}\
\")
                f.write(f\"Mode={data.get('mode', 'Hedge')}\
\")
                f.write(f\"Type={data.get('type', 'Demo')}\
\")
            logger.info(f\"Config MT5 criado: {path}\")
        except Exception as e:
            logger.error(f\"Erro ao criar config MT5 para {key}: {e}\")

    def connect_broker(self, key):
        if key not in self.brokers or self.is_connected(key):
            return False
        
        exe = os.path.join(self.instances_dir, key, \"terminal64.exe\")
        if not os.path.exists(exe):
            # Tenta refazer o setup se o exe sumiu
            logger.warning(f\"Executavel sumiu para {key}, tentando recuperar setup...\")
            exe = self.setup_portable_instance(key)
            if not exe: return False

        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 6 # SW_MINIMIZE
            self.mt5_processes[key] = subprocess.Popen(
                [exe, \"/portable\"],
                cwd=os.path.dirname(exe),
                startupinfo=si
            )
            self.connected_brokers[key] = True
            self.brokers_updated.emit()
            logger.info(f\"MT5 iniciado para {key}\")
            return True
        except Exception as e:
            logger.error(f\"Erro ao iniciar MT5 para {key}: {e}\")
            return False

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
        self.brokers_updated.emit()
        logger.info(f\"MT5 encerrado para {key}\")
        return True

    def is_connected(self, key):
        return self.connected_brokers.get(key, False)

    def get_brokers(self):
        return self.brokers

    def get_connected_brokers(self):
        return [k for k, v in self.connected_brokers.items() if v]

logger = logging.getLogger(__name__)

ctrl+a Backspace
class BrokerManager(QObject):
    brokers_updated = Signal()

    def __init__(self, config, base_mt5_path, root_path):
        super().__init__()
        self.config = config
        self.brokers_file = config.get('General', 'brokers_file', fallback='brokers.json')
        self.base_mt5_path = base_mt5_path
        self.root_path = root_path
        self.instances_dir = os.path.join(self.root_path, ".mt5_instances")

        self.mt5_processes = {}
        self.connected_brokers = {}
        self.brokers = self.load_brokers()

    def load_brokers(self):
        try:
            if os.path.exists(self.brokers_file):
                with open(self.brokers_file, 'r') as f:
                    brokers = json.load(f)
                self.connected_brokers = {key: False for key in brokers}
                return brokers
            return {}
        except Exception as e:
            logger.error(f"Erro ao carregar corretoras: {e}")
            return {}

    def save_brokers(self):
        try:
            with open(self.brokers_file, 'w') as f:
                json.dump(self.brokers, f, indent=4)
        except Exception as e:
            logger.error(f"Erro ao salvar corretoras: {e}")

    def add_broker(self, **data):
        # Normaliza chave de tipo (suporta 'type_' ou 'type')
        if 'type_' in data and 'type' not in data:
            data['type'] = data.pop('type_')

        key = f"{data['broker_name'].upper()}-{data['login']}"
        if key in self.brokers:
            logger.warning(f"Corretora {key} ja cadastrada.")
            return None

        instance_path = self.setup_portable_instance(key)
        if not instance_path:
            return None

        self.brokers[key] = data
        self.save_brokers()
        self.connected_brokers[key] = False
        self.create_mt5_config(key, data)
        self.brokers_updated.emit()
        return key

    def remove_broker(self, key):
        if key not in self.brokers:
            return False

        if self.is_connected(key):
            self.disconnect_broker(key)

        del self.brokers[key]
        self.save_brokers()

        if key in self.connected_brokers:
            del self.connected_brokers[key]

        instance_path = os.path.join(self.instances_dir, key)
        if os.path.exists(instance_path):
            shutil.rmtree(instance_path, ignore_errors=True)

        self.brokers_updated.emit()
        return True

    def modify_broker(self, old_key, **data):
        if old_key not in self.brokers:
            return None
        if self.is_connected(old_key):
            self.disconnect_broker(old_key)
        self.remove_broker(old_key)
        return self.add_broker(**data)

    def setup_portable_instance(self, key):
        """
        Cria uma instancia portatil do MT5 para a corretora.
        Em vez de copiar todo o diretorio base (lento/pesado),
        copia apenas o terminal64.exe e cria a estrutura MQL5.
        """
        instance_path = os.path.join(self.instances_dir, key)
        executable = os.path.join(instance_path, "terminal64.exe")

        if os.path.exists(instance_path):
            # Instancia ja existe, apenas retorna o executavel
            return executable

        try:
            # Cria diretorio da instancia
            os.makedirs(instance_path, exist_ok=True)

            # Copia apenas o terminal64.exe do MT5 base
            src_exe = os.path.join(self.base_mt5_path, "terminal64.exe")
            if not os.path.exists(src_exe):
                logger.error(f"terminal64.exe nao encontrado em: {self.base_mt5_path}")
                shutil.rmtree(instance_path, ignore_errors=True)
                return None
            shutil.copy2(src_exe, executable)

            # Cria estrutura de pastas MQL5
            for subdir in [
                "MQL5\\Experts",
                "MQL5\\Libraries",
                "MQL5\\Files",
                "MQL5\\Indicators",
                "MQL5\\Scripts",
            ]:
                os.makedirs(os.path.join(instance_path, subdir), exist_ok=True)

            # Copia DLLs e EA
            self.copy_dlls(instance_path)
            self.copy_expert(instance_path)

            # Oculta diretorio no Windows
            try:
                import win32api
                import win32con
                win32api.SetFileAttributes(instance_path, win32con.FILE_ATTRIBUTE_HIDDEN)
            except ImportError:
                logger.warning("pywin32 nao instalado - diretorio nao sera ocultado.")
            except Exception as e:
                logger.warning(f"Nao foi possivel ocultar diretorio {instance_path}: {e}")

            logger.info(f"Instancia MT5 criada com sucesso: {instance_path}")
            return executable

        except Exception as e:
            logger.error(f"Erro ao criar instancia para {key}: {e}")
            shutil.rmtree(instance_path, ignore_errors=True)
            return None

    def copy_dlls(self, instance_path):
        src = os.path.join(self.root_path, "dlls")
        dst = os.path.join(instance_path, "MQL5", "Libraries")
        os.makedirs(dst, exist_ok=True)
        if os.path.exists(src):
            copied = 0
            for f in os.listdir(src):
                if f.lower().endswith(".dll"):
                    shutil.copy2(os.path.join(src, f), dst)
                    copied += 1
            logger.info(f"{copied} DLL(s) copiada(s) para {dst}")
        else:
            logger.warning(f"Pasta dlls nao encontrada: {src}")

    def copy_expert(self, instance_path):
        src = os.path.join(self.root_path, "mt5_ea", "EPCopyBridge.ex5")
        dst = os.path.join(instance_path, "MQL5", "Experts")
        os.makedirs(dst, exist_ok=True)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            logger.info(f"EA EPCopyBridge.ex5 copiado para {dst}")
        else:
            logger.warning(f"EA nao encontrado: {src}")

    def create_mt5_config(self, key, data):
        """
        Cria arquivo config.ini dentro da instancia MT5,
        na pasta MQL5/Files, para ser lido pelo EA EPCopyBridge.
        """
        path = os.path.join(self.instances_dir, key, "MQL5", "Files", "config.ini")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write("[ZMQ]\n")
                f.write(f"BrokerKey={key}\n")
                f.write(f"Role={data.get('role', 'master')}\n")
                f.write(f"LotFactor={data.get('lot_factor', 1.0)}\n")
                f.write("[Ports]\n")
                f.write(f"PushPort={data.get('push_port', 15555)}\n")
                f.write("[Account]\n")
                f.write(f"Login={data.get('login', '')}\n")
                f.write(f"Server={data.get('server', '')}\n")
                f.write(f"Mode={data.get('mode', 'Hedge')}\n")
                f.write(f"Type={data.get('type', 'Demo')}\n")
            logger.info(f"Config MT5 criado: {path}")
        except Exception as e:
            logger.error(f"Erro ao criar config MT5 para {key}: {e}")

    def connect_broker(self, key):
        if key not in self.brokers or self.is_connected(key):
            return False
        exe = os.path.join(self.instances_dir, key, "terminal64.exe")
        if not os.path.exists(exe):
            logger.error(f"terminal64.exe nao encontrado para {key}: {exe}")
            return False
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 6  # SW_MINIMIZE
            self.mt5_processes[key] = subprocess.Popen(
                [exe, "/portable"],
                cwd=os.path.dirname(exe),
                startupinfo=si
            )
            self.connected_brokers[key] = True
            self.brokers_updated.emit()
            logger.info(f"MT5 iniciado para {key}")
            return True
        except Exception as e:
            logger.error(f"Erro ao iniciar MT5 para {key}: {e}")
            return False

    def disconnect_broker(self, key):
        if key in self.mt5_processes:
            p = self.mt5_processes[key]
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
            del self.mt5_processes[key]
            self.connected_brokers[key] = False
            self.brokers_updated.emit()
            logger.info(f"MT5 encerrado para {key}")
            return True
        return False

    def is_connected(self, key):
        return self.connected_brokers.get(key, False)

    def get_brokers(self):
        return self.brokers

    def get_connected_brokers(self):
        """Retorna lista de keys de corretoras conectadas."""
        return [k for k, v in self.connected_brokers.items() if v]
