//+------------------------------------------------------------------+
//| EPCopyFlow_Master_TCP.mq5                                        |
//| Master EA usando TCP nativo (Python como Server)                 |
//+------------------------------------------------------------------+
#property copyright "EPFilho"
#property version   "2.00"
#property strict

#include <Json.mqh>

input string InpServerIP = "127.0.0.1";
input int    InpServerPort = 5555;
input string InpBrokerKey = "MASTER-01";
input int    InpTimerMs = 500;

int g_socket = INVALID_HANDLE;
bool g_registered = false;

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

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result) {
    if(trans.type != TRADE_TRANSACTION_REQUEST) return;
    if(result.retcode != TRADE_RETCODE_DONE && result.retcode != TRADE_RETCODE_PLACED) return;

    JSONNode event;
    event["type"] = "STREAM";
    event["event"] = "TRADE_EVENT";
    event["broker_key"] = InpBrokerKey;
    event["role"] = "MASTER";
    
    // Simplificado para EPCopyFlow 2.0
    event["symbol"] = request.symbol;
    event["volume"] = request.volume;
    event["type_order"] = (int)request.type;
    event["price"] = request.price;
    event["position_id"] = (long)result.order; // ou HistoryDealGetInteger se deal
    
    SendJson(event);
}

void SendRegister() {
    JSONNode reg;
    reg["type"] = "SYSTEM";
    reg["event"] = "REGISTER";
    reg["broker_key"] = InpBrokerKey;
    reg["role"] = "MASTER";
    SendJson(reg);
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

void CheckIncoming() {
    // Implementar leitura de comandos se necessário para Master
}
