//+------------------------------------------------------------------+
//| EPCopyFlow_Slave_TCP.mq5                                         |
//| Slave EA - TCP nativo (Python como Server)                       |
//| EPCopyFlow 2.0 - EPFilho                                         |
//+------------------------------------------------------------------+
#property copyright "EPFilho"
#property version   "2.00"
#property strict

#include <Trade\Trade.mqh>

//--- Inputs
input string InpServerIP      = "127.0.0.1";  // IP do Python Server
input int    InpServerPort    = 5555;          // Porta TCP
input string InpSlaveKey      = "SLAVE-01";    // Identificador unico deste Slave
input int    InpTimerMs       = 100;           // Intervalo do timer (ms)
input int    InpMagic         = 123456;        // Magic Number para ordens replicadas

//--- Globals
int      g_socket        = INVALID_HANDLE;
bool     g_registered    = false;
CTrade   g_trade;

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit()
  {
   g_trade.SetExpertMagicNumber(InpMagic);
   
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
//| OnTimer - Reconnect + Check Incoming Commands                    |
//+------------------------------------------------------------------+
void OnTimer()
  {
   //--- Verifica conexao
   if(g_socket == INVALID_HANDLE || !SocketIsConnected(g_socket))
     {
      g_registered = false;
      Print("EPCopyFlow_Slave: conexao perdida, tentando reconectar...");
      if(!ConnectToServer())
         return;
     }

   //--- Processa comandos vindos do Python
   CheckIncoming();
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
      return false;

   if(!SocketConnect(g_socket, InpServerIP, InpServerPort, 3000))
     {
      SocketClose(g_socket);
      g_socket = INVALID_HANDLE;
      return false;
     }

   Print("EPCopyFlow_Slave: conectado em ", InpServerIP, ":", InpServerPort);
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
                + "\"slave_key\":\"" + InpSlaveKey + "\","
                + "\"role\":\"SLAVE\"}";
   if(SendRaw(msg))
     {
      g_registered = true;
      Print("EPCopyFlow_Slave: registrado como ", InpSlaveKey);
     }
  }

//+------------------------------------------------------------------+
//| CheckIncoming - Leitura do socket TCP                            |
//+------------------------------------------------------------------+
void CheckIncoming()
  {
   if(g_socket == INVALID_HANDLE) return;

   while(SocketIsReadable(g_socket))
     {
      uchar header[4];
      if(SocketRead(g_socket, header, 4, 10) != 4) break;

      int len = (header[0] << 24) | (header[1] << 16) | (header[2] << 8) | header[3];
      if(len <= 0) break;

      uchar buf[];
      ArrayResize(buf, len);
      if(SocketRead(g_socket, buf, len, 100) != len) break;

      string msg = CharArrayToString(buf, 0, len, CP_UTF8);
      ProcessMessage(msg);
     }
  }

//+------------------------------------------------------------------+
//| ProcessMessage - Parsing manual simples de JSON                  |
//+------------------------------------------------------------------+
void ProcessMessage(string msg)
  {
   // Nota: Em um projeto real, usariamos uma lib JSON robusta.
   // Aqui faremos parsing simplificado para demonstracao do fluxo.
   
   if(StringFind(msg, "\"type\":\"REQUEST\"") < 0) return;

   string req_id = GetJsonValue(msg, "request_id");
   string command = GetJsonValue(msg, "command");

   if(command == "TRADE_OPEN")
     {
      string sym = GetJsonValue(msg, "symbol");
      string side = GetJsonValue(msg, "side");
      double vol = StringToDouble(GetJsonValue(msg, "volume"));
      double sl = StringToDouble(GetJsonValue(msg, "sl"));
      double tp = StringToDouble(GetJsonValue(msg, "tp"));

      bool res = false;
      if(side == "BUY") res = g_trade.Buy(vol, sym, 0, sl, tp);
      else if(side == "SELL") res = g_trade.Sell(vol, sym, 0, sl, tp);

      if(res) SendResponse(req_id, "OK", g_trade.ResultOrder());
      else SendResponse(req_id, "ERROR", 0, g_trade.ResultComment());
     }
   else if(command == "TRADE_CLOSE")
     {
      long pos_id = (long)StringToInteger(GetJsonValue(msg, "position_id"));
      if(g_trade.PositionClose(pos_id))
         SendResponse(req_id, "OK");
      else
         SendResponse(req_id, "ERROR", 0, g_trade.ResultComment());
     }
   else if(command == "TRADE_MODIFY")
     {
      long pos_id = (long)StringToInteger(GetJsonValue(msg, "position_id"));
      double sl = StringToDouble(GetJsonValue(msg, "sl"));
      double tp = StringToDouble(GetJsonValue(msg, "tp"));
      
      if(g_trade.PositionModify(pos_id, sl, tp))
         SendResponse(req_id, "OK");
      else
         SendResponse(req_id, "ERROR", 0, g_trade.ResultComment());
     }
  }

//+------------------------------------------------------------------+
//| GetJsonValue - Helper para extrair valores simples do JSON       |
//+------------------------------------------------------------------+
string GetJsonValue(string json, string key)
  {
   string search = "\"" + key + "\":";
   int pos = StringFind(json, search);
   if(pos < 0) return "";
   
   int start = pos + StringLen(search);
   // Pula espacos ou aspas
   while(start < StringLen(json) && (StringGetCharacter(json, start) == ' ' || StringGetCharacter(json, start) == '\"' || StringGetCharacter(json, start) == ':'))
      start++;
      
   int end = start;
   while(end < StringLen(json) && StringGetCharacter(json, end) != '\"' && StringGetCharacter(json, end) != ',' && StringGetCharacter(json, end) != '}')
      end++;
      
   return StringSubstr(json, start, end - start);
  }

//+------------------------------------------------------------------+
//| SendResponse - Envia confirmacao de execucao ao Python           |
//+------------------------------------------------------------------+
void SendResponse(string req_id, string status, long ticket=0, string err="")
  {
   string msg = "{\"type\":\"RESPONSE\",\"request_id\":\"" + req_id + "\","
feat: Complete EPCopyFlow_Slave_TCP.mq5 with all trade commands and confirmation logic                + "\"slave_key\":\"" + InpSlaveKey + "\"";
   
   if(ticket > 0) msg += ",\"order\":" + IntegerToString(ticket);
   if(err != "")   msg += ",\"message\":\"" + err + "\"";
   msg += "}";
   
   SendRaw(msg);
  }

//+------------------------------------------------------------------+
//| SendRaw - Envia string via TCP                                   |
//+------------------------------------------------------------------+
bool SendRaw(const string &msg)
  {
   if(g_socket == INVALID_HANDLE) return false;

   uchar buf[];
   int len = StringToCharArray(msg, buf, 0, WHOLE_ARRAY, CP_UTF8) - 1;
   if(len <= 0) return false;

   uchar header[4];
   header[0] = (uchar)((len >> 24) & 0xFF);
   header[1] = (uchar)((len >> 16) & 0xFF);
   header[2] = (uchar)((len >>  8) & 0xFF);
   header[3] = (uchar)( len        & 0xFF);

   if(SocketSend(g_socket, header, 4) != 4) return false;
   if(SocketSend(g_socket, buf, len) != len) return false;
   return true;
  }
//+------------------------------------------------------------------+
