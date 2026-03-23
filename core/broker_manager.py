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
        self.instances_dir = os.path.join(self.root_path, ".mt5_instances")
        self.brokers = self.load_brokers()
        self.connected_brokers = {}
        self.mt5_processes = {}

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
        key = f"{data['broker_name'].upper()}-{data['login']}"
        if key in self.brokers:
            return None
        
        instance_path = self.setup_portable_instance(key)
        if not instance_path: return None
        
        self.brokers[key] = data
        self.save_brokers()
        self.connected_brokers[key] = False
        self.create_mt5_config(key, data)
        self.brokers_updated.emit()
        return key

    def remove_broker(self, key):
        if key not in self.brokers: return False
        if self.is_connected(key): self.disconnect_broker(key)
        
        del self.brokers[key]
        self.save_brokers()
        if key in self.connected_brokers: del self.connected_brokers[key]
        
        instance_path = os.path.join(self.instances_dir, key)
        if os.path.exists(instance_path):
            shutil.rmtree(instance_path, ignore_errors=True)
        
        self.brokers_updated.emit()
        return True

    def modify_broker(self, old_key, **data):
        if old_key not in self.brokers: return None
        if self.is_connected(old_key): self.disconnect_broker(old_key)
        
        self.remove_broker(old_key)
        return self.add_broker(**data)

    def setup_portable_instance(self, key):
        instance_path = os.path.join(self.instances_dir, key)
        executable = os.path.join(instance_path, "terminal64.exe")
        if not os.path.exists(instance_path):
            try:
                os.makedirs(self.instances_dir, exist_ok=True)
                shutil.copytree(self.base_mt5_path, instance_path)
                self.copy_dlls(instance_path)
                self.copy_expert(instance_path)
                import win32api, win32con
                win32api.SetFileAttributes(instance_path, win32con.FILE_ATTRIBUTE_HIDDEN)
            except Exception as e:
                logger.error(f"Erro ao criar instância para {key}: {e}")
                return None
        return executable

    def copy_dlls(self, instance_path):
        src = os.path.join(self.root_path, "dlls")
        dst = os.path.join(instance_path, "MQL5", "Libraries")
        if not os.path.exists(dst): os.makedirs(dst)
        for f in os.listdir(src):
            if f.endswith(".dll"): shutil.copy2(os.path.join(src, f), dst)

    def copy_expert(self, instance_path):
        src = os.path.join(self.root_path, "mt5_ea", "EPCopyBridge.ex5")
        dst = os.path.join(instance_path, "MQL5", "Experts")
        if not os.path.exists(dst): os.makedirs(dst)
        if os.path.exists(src): shutil.copy2(src, dst)

    def create_mt5_config(self, key, data):
        path = os.path.join(self.instances_dir, key, "MQL5", "Files", "config.ini")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"[ZMQ]
BrokerKey={key}
[Ports]
PushPort={data.get('push_port')}
")

    def connect_broker(self, key):
        if key not in self.brokers or self.is_connected(key): return False
        
        exe = os.path.join(self.instances_dir, key, "terminal64.exe")
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 6 # SW_MINIMIZE
            self.mt5_processes[key] = subprocess.Popen([exe, "/portable"], cwd=os.path.dirname(exe), startupinfo=si)
            self.connected_brokers[key] = True
            self.brokers_updated.emit()
            return True
        except Exception as e:
            logger.error(f"Erro ao iniciar MT5: {e}")
            return False

    def disconnect_broker(self, key):
        if key in self.mt5_processes:
            p = self.mt5_processes[key]
            p.terminate()
            try: p.wait(timeout=5)
            except: p.kill()
            del self.mt5_processes[key]
        self.connected_brokers[key] = False
        self.brokers_updated.emit()
        return True

    def is_connected(self, key):
        return self.connected_brokers.get(key, False)

    def get_brokers(self): return self.brokers
    def get_connected_brokers(self): return [k for k, v in self.connected_brokers.items() if v]
