//+------------------------------------------------------------------+
//| EPCopyFlow_Slave_TCP.mq5                                         |
//| Slave EA usando TCP nativo (Python como Server)                  |
//+------------------------------------------------------------------+
#property copyright "EPFilho"
#property version   "2.00"
#property strict

#include <Json.mqh>
#include <Trade\Trade.mqh>

input string InpServerIP = "127.0.0.1";
input int    InpServerPort = 5555;
input string InpBrokerKey = "SLAVE-01";
input int    InpTimerMs = 200;

int g_socket = INVALID_HANDLE;
CTrade trade;

int OnInit() {
    g_socket = SocketCreate();
    if(!SocketConnect(g_socket, InpServerIP, InpServerPort, 3000)) {
        Print("Falha ao conectar ao Python Server");
        return INIT_FAILED;
    }
    
    EventSetMillisecondTimer(InpTimerMs);
    SendRegister();
    return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) {
    if(g_socket != INVALID_HANDLE) SocketClose(g_socket);
    EventKillTimer();
}

void OnTimer() {
    CheckIncoming();
}

void SendRegister() {
    JSONNode reg;
    reg["type"] = "SYSTEM";
    reg["event"] = "REGISTER";
    reg["broker_key"] = InpBrokerKey;
    reg["role"] = "SLAVE";
    SendJson(reg);
}

void CheckIncoming() {
    uchar header[4];
    if(SocketIsReadable(g_socket) && SocketRead(g_socket, header, 4, 10) == 4) {
        int length = (header[0] << 24) | (header[1] << 16) | (header[2] << 8) | header[3];
        uchar buf[];
        ArrayResize(buf, length);
        if(SocketRead(g_socket, buf, length, 100) == length) {
            string msg = CharArrayToString(buf, 0, length, CP_UTF8);
            JSONNode root;
            if(root.Deserialize(msg)) {
                ProcessCommand(root);
            }
        }
    }
}

void ProcessCommand(JSONNode &node) {
    string type = node["type"].ToString();
    string command = node["command"].ToString();
    string req_id = node["request_id"].ToString();
    
    if(type == "REQUEST") {
        if(command == "TRADE_ORDER_TYPE_BUY") {
            JSONNode payload = node["payload"];
            string sym = payload["symbol"].ToString();
            double vol = payload["volume"].ToDouble();
            if(trade.Buy(vol, sym)) {
                SendResponse(req_id, "OK", trade.ResultOrder());
            } else {
                SendResponse(req_id, "ERROR", 0, trade.ResultComment());
            }
        }
        // Adicionar outros comandos (SELL, CLOSE, etc)
    }
}

void SendResponse(string req_id, string status, long ticket=0, string err="") {
    JSONNode resp;
    resp["type"] = "RESPONSE";
    resp["request_id"] = req_id;
    resp["status"] = status;
    resp["broker_key"] = InpBrokerKey;
    if(ticket > 0) resp["order"] = ticket;
    if(err != "") resp["message"] = err;
    SendJson(resp);
}

void SendJson(JSONNode &node) {
    string out = node.Serialize();
    uchar buf[];
    int len = StringToCharArray(out, buf, 0, WHOLE_ARRAY, CP_UTF8) - 1;
    uchar header[4];
    header[0] = (uchar)((len >> 24) & 0xFF);
    header[1] = (uchar)((len >> 16) & 0xFF);
    header[2] = (uchar)((len >> 8) & 0xFF);
    header[3] = (uchar)(len & 0xFF);
    SocketSend(g_socket, header, 4);
    SocketSend(g_socket, buf, len);
}
