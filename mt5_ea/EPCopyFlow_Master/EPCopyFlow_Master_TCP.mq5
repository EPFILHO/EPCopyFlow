//+------------------------------------------------------------------+
//| EPCopyFlow_Master_TCP.mq5                                        |
//| Master EA - TCP nativo (Python como Server)                      |
//| EPCopyFlow 2.0 - EPFilho                                         |
//+------------------------------------------------------------------+
#property copyright "EPFilho"
#property version   "2.00"
#property strict

//--- Inputs
input string InpServerIP      = "127.0.0.1";  // IP do Python Server
input int    InpServerPort    = 5555;          // Porta TCP
input string InpMasterKey     = "MASTER-01";   // Identificador unico deste Master
input int    InpHeartbeatSec  = 5;             // Intervalo heartbeat (segundos)
input int    InpTimerMs       = 200;           // Intervalo do timer (ms)

//--- Globals
int      g_socket        = INVALID_HANDLE;
bool     g_registered    = false;
datetime g_last_hb       = 0;
int      g_reconnect_cnt = 0;

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit()
  {
   if(!ConnectToServer())
      return INIT_FAILED;
   EventSetMillisecondTimer(InpTimerMs);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| OnDeinit                                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_socket != INVALID_HANDLE)
     {
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
     }
  }

//+------------------------------------------------------------------+
//| OnTimer - heartbeat + reconnect                                  |
//+------------------------------------------------------------------+
void OnTimer()
  {
   //--- Verifica conexao
   if(g_socket == INVALID_HANDLE || !SocketIsConnected(g_socket))
     {
      g_registered = false;
      Print("EPCopyFlow_Master: conexao perdida, tentando reconectar...");
      if(!ConnectToServer())
         return;
     }

   //--- Heartbeat periodico
   if(TimeCurrent() - g_last_hb >= InpHeartbeatSec)
     {
      SendHeartbeat();
      g_last_hb = TimeCurrent();
     }
  }

//+------------------------------------------------------------------+
//| OnTradeTransaction - captura eventos de trade                    |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest      &request,
                        const MqlTradeResult       &result)
  {
   if(g_socket == INVALID_HANDLE || !g_registered)
      return;

   //--- Posicao aberta (deal executado na abertura)
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
     {
      long deal_ticket = (long)trans.deal;
      if(deal_ticket <= 0)
         return;

      if(!HistoryDealSelect(deal_ticket))
         return;

      long deal_entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
      if(deal_entry == DEAL_ENTRY_IN)
         SendEventOpen(deal_ticket);
      else if(deal_entry == DEAL_ENTRY_OUT || deal_entry == DEAL_ENTRY_OUT_BY)
         SendEventClose(deal_ticket);
      return;
     }

   //--- Modificacao de SL/TP
   if(trans.type == TRADE_TRANSACTION_ORDER_UPDATE ||
      trans.type == TRADE_TRANSACTION_POSITION)
     {
      if(trans.position != 0 && (trans.sl != 0.0 || trans.tp != 0.0 ||
         (trans.prev_sl != trans.sl) || (trans.prev_tp != trans.tp)))
        {
         SendEventModifySLTP(trans);
        }
     }
  }

//+------------------------------------------------------------------+
//| ConnectToServer                                                  |
//+------------------------------------------------------------------+
bool ConnectToServer()
  {
   if(g_socket != INVALID_HANDLE)
     {
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
     }

   g_socket = SocketCreate();
   if(g_socket == INVALID_HANDLE)
     {
      Print("EPCopyFlow_Master: falha ao criar socket");
      return false;
     }

   if(!SocketConnect(g_socket, InpServerIP, InpServerPort, 3000))
     {
      Print("EPCopyFlow_Master: falha ao conectar em ", InpServerIP, ":", InpServerPort);
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
      return false;
     }

   Print("EPCopyFlow_Master: conectado em ", InpServerIP, ":", InpServerPort);
   g_registered = false;
   SendRegister();
   return true;
  }

//+------------------------------------------------------------------+
//| SendRegister                                                     |
//+------------------------------------------------------------------+
void SendRegister()
  {
   string msg = "{\"type\":\"SYSTEM\",\"event\":\"REGISTER\","
                + "\"master_key\":\"" + InpMasterKey + "\","
                + "\"role\":\"MASTER\"}";
   if(SendRaw(msg))
     {
      g_registered = true;
      g_reconnect_cnt = 0;
      Print("EPCopyFlow_Master: registrado como ", InpMasterKey);
     }
  }

//+------------------------------------------------------------------+
//| SendHeartbeat                                                    |
//+------------------------------------------------------------------+
void SendHeartbeat()
  {
   string msg = "{\"type\":\"STREAM\",\"event\":\"HEARTBEAT\","
                + "\"master_key\":\"" + InpMasterKey + "\","
                + "\"timestamp\":" + IntegerToString(TimeCurrent()) + "}";
   SendRaw(msg);
  }

//+------------------------------------------------------------------+
//| SendEventOpen - envia evento de abertura de posicao              |
//+------------------------------------------------------------------+
void SendEventOpen(long deal_ticket)
  {
   string   symbol     = HistoryDealGetString(deal_ticket, DEAL_SYMBOL);
   double   volume     = HistoryDealGetDouble(deal_ticket, DEAL_VOLUME);
   double   price      = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);
   long     order_type = HistoryDealGetInteger(deal_ticket, DEAL_TYPE); // 0=BUY, 1=SELL
   long     position   = HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);
   long     magic      = HistoryDealGetInteger(deal_ticket, DEAL_MAGIC);
   string   comment    = HistoryDealGetString(deal_ticket, DEAL_COMMENT);
   datetime ts         = (datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME);

   //--- Busca SL/TP da posicao
   double sl = 0.0, tp = 0.0;
   if(PositionSelectByTicket(position))
     {
      sl = PositionGetDouble(POSITION_SL);
      tp = PositionGetDouble(POSITION_TP);
     }

   string type_str = (order_type == DEAL_TYPE_BUY) ? "BUY" : "SELL";

   string msg = "{\"type\":\"STREAM\",\"event\":\"OPEN\","
                + "\"master_key\":\"" + InpMasterKey + "\","
                + "\"position_id\":" + IntegerToString(position) + ","
                + "\"deal_ticket\":" + IntegerToString(deal_ticket) + ","
                + "\"symbol\":\"" + symbol + "\","
                + "\"order_type\":\"" + type_str + "\","
                + "\"volume\":" + DoubleToString(volume, 2) + ","
                + "\"price\":" + DoubleToString(price, 8) + ","
                + "\"sl\":" + DoubleToString(sl, 8) + ","
                + "\"tp\":" + DoubleToString(tp, 8) + ","
                + "\"magic\":" + IntegerToString(magic) + ","
                + "\"comment\":\"" + comment + "\","
                + "\"timestamp\":" + IntegerToString((long)ts) + "}";

   if(SendRaw(msg))
      Print("EPCopyFlow_Master: OPEN enviado - posicao ", position, " ", symbol, " ", type_str, " ", volume);
  }

//+------------------------------------------------------------------+
//| SendEventClose - envia evento de fechamento de posicao           |
//+------------------------------------------------------------------+
void SendEventClose(long deal_ticket)
  {
   string   symbol        = HistoryDealGetString(deal_ticket, DEAL_SYMBOL);
   double   volume_closed = HistoryDealGetDouble(deal_ticket, DEAL_VOLUME);
   double   close_price   = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);
   long     position      = HistoryDealGetInteger(deal_ticket, DEAL_POSITION_ID);
   datetime ts            = (datetime)HistoryDealGetInteger(deal_ticket, DEAL_TIME);

   //--- Razao do fechamento
   long deal_reason = HistoryDealGetInteger(deal_ticket, DEAL_REASON);
   string reason = "MANUAL";
   if(deal_reason == DEAL_REASON_SL)  reason = "SL";
   if(deal_reason == DEAL_REASON_TP)  reason = "TP";

   string msg = "{\"type\":\"STREAM\",\"event\":\"CLOSE\","
                + "\"master_key\":\"" + InpMasterKey + "\","
                + "\"position_id\":" + IntegerToString(position) + ","
                + "\"deal_ticket\":" + IntegerToString(deal_ticket) + ","
                + "\"symbol\":\"" + symbol + "\","
                + "\"volume_closed\":" + DoubleToString(volume_closed, 2) + ","
                + "\"close_price\":" + DoubleToString(close_price, 8) + ","
                + "\"reason\":\"" + reason + "\","
                + "\"timestamp\":" + IntegerToString((long)ts) + "}";

   if(SendRaw(msg))
      Print("EPCopyFlow_Master: CLOSE enviado - posicao ", position, " ", symbol, " ", reason);
  }

//+------------------------------------------------------------------+
//| SendEventModifySLTP - envia modificacao de SL/TP                 |
//+------------------------------------------------------------------+
void SendEventModifySLTP(const MqlTradeTransaction &trans)
  {
   //--- Evita envio duplicado: so envia se SL ou TP mudou
   if(trans.sl == trans.prev_sl && trans.tp == trans.prev_tp)
      return;

   datetime ts = TimeCurrent();

   string msg = "{\"type\":\"STREAM\",\"event\":\"MODIFY_SLTP\","
                + "\"master_key\":\"" + InpMasterKey + "\","
                + "\"position_id\":" + IntegerToString(trans.position) + ","
                + "\"symbol\":\"" + trans.symbol + "\","
                + "\"sl\":" + DoubleToString(trans.sl, 8) + ","
                + "\"tp\":" + DoubleToString(trans.tp, 8) + ","
                + "\"timestamp\":" + IntegerToString((long)ts) + "}";

   if(SendRaw(msg))
      Print("EPCopyFlow_Master: MODIFY_SLTP enviado - posicao ", trans.position);
  }

//+------------------------------------------------------------------+
//| SendRaw - envia string via TCP com header de 4 bytes (big-endian)|
//+------------------------------------------------------------------+
bool SendRaw(const string &msg)
  {
   if(g_socket == INVALID_HANDLE)
      return false;

   uchar buf[];
   int len = StringToCharArray(msg, buf, 0, WHOLE_ARRAY, CP_UTF8) - 1;
   if(len <= 0)
      return false;

   uchar header[4];
   header[0] = (uchar)((len >> 24) & 0xFF);
   header[1] = (uchar)((len >> 16) & 0xFF);
   header[2] = (uchar)((len >>  8) & 0xFF);
   header[3] = (uchar)( len        & 0xFF);

   if(SocketSend(g_socket, header, 4) != 4)
     {
      Print("EPCopyFlow_Master: erro ao enviar header");
      return false;
     }
   if(SocketSend(g_socket, buf, len) != len)
     {
      Print("EPCopyFlow_Master: erro ao enviar payload");
      return false;
     }
   return true;
  }
//+------------------------------------------------------------------+
