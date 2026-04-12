import asyncio
import json
import logging
import time
import struct
from datetime import datetime

logger = logging.getLogger(__name__)

class TcpRouter:
    def __init__(self, broker_manager):
        self.broker_manager = broker_manager
        self._running = False
        self._message_handler = None
        self._responses = {}
        self._response_events = {}
        self._background_tasks = set()
        self._command_writers = {}  # {broker_key: writer}
        self._lock = asyncio.Lock()

    async def _read_message(self, reader):
        try:
            header = await reader.readexactly(4)
            length = struct.unpack(">I", header)[0]
            raw = await reader.readexactly(length)
            return json.loads(raw.decode('utf-8'))
        except:
            return None

    async def _write_message(self, writer, data):
        raw = json.dumps(data).encode('utf-8')
        header = struct.pack(">I", len(raw))
        writer.write(header + raw)
        await writer.drain()

    async def _handle_client(self, reader, writer):
        addr = writer.get_extra_info('peername')
        logger.info(f"Nova conexão TCP de {addr}")
        broker_key = None
        try:
            while True:
                msg = await self._read_message(reader)
                if not msg: break
                
                msg_type = msg.get("type")
                event = msg.get("event")
                current_broker_key = msg.get("broker_key")
                
                if msg_type == "SYSTEM" and event == "REGISTER":
                    broker_key = current_broker_key
                    async with self._lock:
                        self._command_writers[broker_key] = writer
                    logger.info(f"Broker {broker_key} registrado via TCP")

                self._process_message(msg, broker_key or current_broker_key)
        except:
            pass
        finally:
            if broker_key:
                async with self._lock:
                    self._command_writers.pop(broker_key, None)
            writer.close()

    def _process_message(self, message_data, broker_key):
        msg_type = message_data.get("type")
        request_id = message_data.get("request_id")
        
        if msg_type == "RESPONSE" and request_id:
            self._responses[request_id] = message_data
            if request_id in self._response_events:
                self._response_events[request_id].set()

        if self._message_handler:
            task = asyncio.create_task(self._message_handler.handle_zmq_message(broker_key.encode(), message_data))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def send_command_to_broker(self, broker_key, command, payload=None, request_id=None):
        async with self._lock:
            writer = self._command_writers.get(broker_key)
        
        if not writer:
            return {"status": "ERROR", "message": f"Broker {broker_key} não conectado"}

        request_id = request_id or f"{command.lower()}_{broker_key}_{int(time.time())}"
        message = {
            "type": "REQUEST",
            "command": command,
            "request_id": request_id,
            "broker_key": broker_key,
            "payload": payload or {}
        }
        
        self._response_events[request_id] = asyncio.Event()
        try:
            await self._write_message(writer, message)
            await asyncio.wait_for(self._response_events[request_id].wait(), timeout=5.0)
            return self._responses.pop(request_id, {"status": "ERROR", "message": "Sem resposta"})
        except asyncio.TimeoutError:
            return {"status": "ERROR", "message": "Timeout"}
        finally:
            self._response_events.pop(request_id, None)

    async def run(self, message_handler):
        self._message_handler = message_handler
        self._running = True
        server = await asyncio.start_server(self._handle_client, '127.0.0.1', 5555)
        async with server:
            await server.serve_forever()
