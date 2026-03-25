//+------------------------------------------------------------------+
//| EPCopyFlow_MasterContext.mqh                                     |
//| Leitura do config.ini e inicializacao do MasterContext           |
//| EPCopyFlow - EPFilho                                             |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_MASTERCONTEXT_MQH
#define EPCOPYFLOW_MASTERCONTEXT_MQH

#include "EPCopyFlow_MasterEvents.mqh"

//+------------------------------------------------------------------+
//| Trim auxiliar (igual ao padrao do ZmqTraderBridge)               |
//+------------------------------------------------------------------+
string Master_TrimString(string s)
  {
   StringTrimLeft(s);
   StringTrimRight(s);
   return s;
  }

//+------------------------------------------------------------------+
//| Le config.ini em MQL5\Files da instancia MT5                     |
//|                                                                  |
//| Formato esperado do arquivo:                                     |
//|   [EPCopyFlow]                                                   |
//|   MasterID=MASTER_1                                              |
//|   ProtocolVersion=1.0                                            |
//|   [Ports]                                                        |
//|   MasterPort=5555                                                |
//+------------------------------------------------------------------+
bool Master_LoadConfig(MasterContext &ctx)
  {
   int handle = FileOpen("config.ini", FILE_READ|FILE_ANSI|FILE_TXT);
   if(handle == INVALID_HANDLE)
     {
      int err = GetLastError();
      Print("EPCopyFlow_Master: Falha ao abrir config.ini, erro=", err);
      Print("EPCopyFlow_Master: Caminho esperado: ",
            TerminalInfoString(TERMINAL_DATA_PATH), "\\MQL5\\Files\\config.ini");
      return false;
     }

   //--- defaults
   string master_id        = "MASTER_1";
   string protocol_version = "1.0";
   int    master_port      = 0;
   string section          = "";

   while(!FileIsEnding(handle))
     {
      string line = FileReadString(handle);
      line = Master_TrimString(line);

      if(StringLen(line) == 0 || StringGetCharacter(line,0) == ';')
         continue; // linha vazia ou comentario

      //--- detecta secao [Nome]
      if(StringGetCharacter(line,0) == '[')
        {
         int close = StringFind(line, "]");
         if(close > 1)
            section = StringSubstr(line, 1, close - 1);
         continue;
        }

      int pos = StringFind(line, "=");
      if(pos <= 0)
         continue;

      string key   = Master_TrimString(StringSubstr(line, 0, pos));
      string value = Master_TrimString(StringSubstr(line, pos + 1));

      if(section == "EPCopyFlow")
        {
         if(key == "MasterID")        master_id        = value;
         else if(key == "ProtocolVersion") protocol_version = value;
        }
      else if(section == "Ports")
        {
         if(key == "MasterPort") master_port = (int)StringToInteger(value);
        }
     }

   FileClose(handle);

   if(master_port <= 0)
     {
      Print("EPCopyFlow_Master: MasterPort nao encontrado ou invalido no config.ini");
      return false;
     }

   ctx.master_id        = master_id;
   ctx.protocol_version = protocol_version;
   ctx.zmq_address      = StringFormat("tcp://127.0.0.1:%d", master_port);

   PrintFormat("EPCopyFlow_Master: Config carregada -> MasterID=%s, Protocol=%s, ZMQ=%s",
               ctx.master_id, ctx.protocol_version, ctx.zmq_address);
   return true;
  }

#endif // EPCOPYFLOW_MASTERCONTEXT_MQH
//+------------------------------------------------------------------+
