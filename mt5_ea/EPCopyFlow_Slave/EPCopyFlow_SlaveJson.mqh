//+------------------------------------------------------------------+
//| EPCopyFlow_SlaveJson.mqh                                         |
//| Faz parse do JSON recebido e preenche structs de comando  .      |
//| EPCopyFlow - EPFilho                                             |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_SLAVEJSON_MQH
#define EPCOPYFLOW_SLAVEJSON_MQH

#include "EPCopyFlow_SlaveEvents.mqh"

//--- Helpers de extracao de campos do JSON (parser minimalista)

// Extrai string entre aspas para o campo dado: "key":"value"
string Json_ExtractString(const string &json, const string key)
{
   string search = "\"" + key + "\":\"";
   int    pos    = StringFind(json, search);
   if(pos < 0) return "";
   pos += StringLen(search);
   int end = StringFind(json, "\"", pos);
   if(end < 0) return "";
   return StringSubstr(json, pos, end - pos);
}

// Extrai valor numerico inteiro para o campo dado: "key":12345
long Json_ExtractLong(const string &json, const string key)
{
   string search = "\"" + key + "\":";
   int    pos    = StringFind(json, search);
   if(pos < 0) return 0;
   pos += StringLen(search);
   // pula espacos eventuais
   while(pos < StringLen(json) && StringSubstr(json, pos, 1) == " ") pos++;
   // le ate encontrar delimitador
   string num = "";
   for(int i = pos; i < StringLen(json); i++)
   {
      string ch = StringSubstr(json, i, 1);
      if(ch == "," || ch == "}" || ch == "]" || ch == " ") break;
      num += ch;
   }
   return (long)StringToInteger(num);
}

// Extrai valor numerico double para o campo dado: "key":1.23456
double Json_ExtractDouble(const string &json, const string key)
{
   string search = "\"" + key + "\":";
   int    pos    = StringFind(json, search);
   if(pos < 0) return 0.0;
   pos += StringLen(search);
   while(pos < StringLen(json) && StringSubstr(json, pos, 1) == " ") pos++;
   string num = "";
   for(int i = pos; i < StringLen(json); i++)
   {
      string ch = StringSubstr(json, i, 1);
      if(ch == "," || ch == "}" || ch == "]" || ch == " ") break;
      num += ch;
   }
   return StringToDouble(num);
}

// Extrai tipo do evento: "type":"OPEN"
string Json_ExtractType(const string &json)
{
   return Json_ExtractString(json, "type");
}

//+------------------------------------------------------------------+
//| Parse de comando OPEN                                            |
//+------------------------------------------------------------------+
bool Slave_ParseOpen(const string &json, SlaveOpenCmd &cmd)
{
   cmd.master_ticket = (ulong)Json_ExtractLong(json, "master_ticket");
   cmd.symbol        = Json_ExtractString(json, "symbol");
   cmd.order_type    = (ENUM_ORDER_TYPE)(int)Json_ExtractLong(json, "order_type");
   cmd.volume        = Json_ExtractDouble(json, "volume");
   cmd.price         = Json_ExtractDouble(json, "open_price");
   cmd.sl_points     = Json_ExtractLong(json, "sl_points");   // <-- pontos
   cmd.tp_points     = Json_ExtractLong(json, "tp_points");   // <-- pontos
   cmd.magic         = Json_ExtractLong(json, "magic");
   cmd.comment       = Json_ExtractString(json, "comment");

   // validacao minima
   if(cmd.symbol == "" || cmd.volume <= 0.0) return false;
   return true;
}

//+------------------------------------------------------------------+
//| Parse de comando MODIFY_SLTP                                     |
//+------------------------------------------------------------------+
bool Slave_ParseModify(const string &json, SlaveModifyCmd &cmd)
{
   cmd.master_ticket = (ulong)Json_ExtractLong(json, "master_ticket");
   cmd.symbol        = Json_ExtractString(json, "symbol");
   cmd.sl_points     = Json_ExtractLong(json, "sl_points");   // <-- pontos
   cmd.tp_points     = Json_ExtractLong(json, "tp_points");   // <-- pontos

   if(cmd.master_ticket == 0) return false;
   return true;
}

//+------------------------------------------------------------------+
//| Parse de comando CLOSE                                           |
//+------------------------------------------------------------------+
bool Slave_ParseClose(const string &json, SlaveCloseCmd &cmd)
{
   cmd.master_ticket = (ulong)Json_ExtractLong(json, "master_ticket");
   cmd.symbol        = Json_ExtractString(json, "symbol");
   cmd.volume_pct    = Json_ExtractDouble(json, "volume_pct");
   cmd.reason        = Json_ExtractString(json, "reason");

   if(cmd.master_ticket == 0) return false;
   if(cmd.volume_pct <= 0.0) cmd.volume_pct = 1.0; // default: fecha tudo
   return true;
}

//+------------------------------------------------------------------+
//| Parse de HEARTBEAT                                               |
//+------------------------------------------------------------------+
bool Slave_ParseHeartbeat(const string &json, SlaveHeartbeatCmd &cmd)
{
   string ts = Json_ExtractString(json, "timestamp");
   cmd.timestamp = (datetime)StringToTime(ts);
   return true;
}

#endif // EPCOPYFLOW_SLAVEJSON_MQH
//+------------------------------------------------------------------+
