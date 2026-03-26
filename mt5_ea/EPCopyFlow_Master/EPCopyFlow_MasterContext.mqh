//+------------------------------------------------------------------+
//| EPCopyFlow_MasterContext.mqh                                     |
//| Leitura do epcopyflow.cfg e inicializacao do MasterContext       |
//| EPCopyFlow - EPFilho                                             |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_MASTERCONTEXT_MQH
#define EPCOPYFLOW_MASTERCONTEXT_MQH

#include "EPCopyFlow_MasterEvents.mqh"

string Master_TrimString(string s)
  {
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
  }

bool Master_LoadConfig(MasterContext &ctx)
  {
   int handle = FileOpen("epcopyflow.cfg", FILE_READ|FILE_ANSI|FILE_TXT);
   if(handle == INVALID_HANDLE)
     {
      int err = GetLastError();
      Print("EPCopyFlow_Master: Falha ao abrir epcopyflow.cfg, erro=", err);
      Print("EPCopyFlow_Master: Caminho esperado: ",
            TerminalInfoString(TERMINAL_DATA_PATH),
            "\\MQL5\\Files\\epcopyflow.cfg");
      return false;
     }

   string master_id        = "MASTER_1";
   string protocol_version = "1.0";
   int    trade_port       = 0;
   string section          = "";

   while(!FileIsEnding(handle))
     {
      string line = Master_TrimString(FileReadString(handle));
      if(StringLen(line) == 0 || StringGetCharacter(line, 0) == ';') continue;

      if(StringGetCharacter(line, 0) == '[')
        {
         int close = StringFind(line, "]");
         if(close > 1) section = StringSubstr(line, 1, close - 1);
         continue;
        }

      int pos = StringFind(line, "=");
      if(pos <= 0) continue;
      string key   = Master_TrimString(StringSubstr(line, 0, pos));
      string value = Master_TrimString(StringSubstr(line, pos + 1));

      if(section == "EPCopyFlow")
        {
         if(key == "MasterId")         master_id        = value;
         else if(key == "ProtocolVersion") protocol_version = value;
        }
      else if(section == "Ports")
        {
         if(key == "TradePort") trade_port = (int)StringToInteger(value);
        }
     }
   FileClose(handle);

   if(trade_port <= 0)
     {
      Print("EPCopyFlow_Master: TradePort nao encontrado ou invalido no epcopyflow.cfg");
      return false;
     }

   ctx.master_id        = master_id;
   ctx.protocol_version = protocol_version;
   ctx.zmq_address      = StringFormat("tcp://127.0.0.1:%d", trade_port);

   PrintFormat("EPCopyFlow_Master: Config OK → MasterId=%s | Protocol=%s | ZMQ=%s",
               ctx.master_id, ctx.protocol_version, ctx.zmq_address);
   return true;
  }

#endif // EPCOPYFLOW_MASTERCONTEXT_MQH
