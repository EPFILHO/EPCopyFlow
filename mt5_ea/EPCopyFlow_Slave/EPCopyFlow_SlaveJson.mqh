//+------------------------------------------------------------------+
//|                                     EPCopyFlow_SlaveJson.mqh   |
//|                                         EP Filho © 2026         |
//|                          https://github.com/EPFILHO/EPCopyFlow  |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_SLAVE_JSON_MQH
#define EPCOPYFLOW_SLAVE_JSON_MQH

#include "EPCopyFlow_SlaveEvents.mqh"
#include "EPCopyFlow_SlaveContext.mqh"

//+------------------------------------------------------------------+
//| Helpers de parsing                                               |
//+------------------------------------------------------------------+
string Json_ExtractString(const string json, const string key)
  {
   string search = "\"" + key + "\":\"";
   int start = StringFind(json, search);
   if(start < 0) return "";
   start += StringLen(search);
   int end = StringFind(json, "\"", start);
   if(end < 0) return "";
   return StringSubstr(json, start, end - start);
  }

double Json_ExtractDouble(const string json, const string key)
  {
   string search = "\"" + key + "\":";
   int start = StringFind(json, search);
   if(start < 0) return 0.0;
   start += StringLen(search);
   int end1 = StringFind(json, ",", start);
   int end2 = StringFind(json, "}", start);
   int end  = (end1 < 0) ? end2 : (end2 < 0) ? end1 : MathMin(end1, end2);
   if(end < 0) return 0.0;
   return StringToDouble(StringSubstr(json, start, end - start));
  }

long Json_ExtractLong(const string json, const string key)
  {
   string search = "\"" + key + "\":";
   int start = StringFind(json, search);
   if(start < 0) return 0;
   start += StringLen(search);
   int end1 = StringFind(json, ",", start);
   int end2 = StringFind(json, "}", start);
   int end  = (end1 < 0) ? end2 : (end2 < 0) ? end1 : MathMin(end1, end2);
   if(end < 0) return 0;
   return StringToInteger(StringSubstr(json, start, end - start));
  }

//+------------------------------------------------------------------+
//| Identifica o tipo de comando no JSON recebido                    |
//+------------------------------------------------------------------+
ENUM_SLAVE_CMD Json_GetCommandType(const string json)
  {
   string event_type = Json_ExtractString(json, "event_type");

   if(event_type == "OPEN")          return SLAVE_CMD_OPEN;
   if(event_type == "CLOSE")         return SLAVE_CMD_CLOSE;
   if(event_type == "PARTIAL_CLOSE") return SLAVE_CMD_PARTIAL_CLOSE;
   if(event_type == "MODIFY_SLTP")   return SLAVE_CMD_MODIFY_SLTP;
   if(event_type == "HEARTBEAT")     return SLAVE_CMD_HEARTBEAT;

   PrintFormat("EPCopyFlow_Slave | JSON: event_type desconhecido → '%s'", event_type);
   return SLAVE_CMD_UNKNOWN;
  }

//+------------------------------------------------------------------+
//| Deserializa comando OPEN                                         |
//+------------------------------------------------------------------+
bool Json_ParseOpen(const string json, SlaveOpenCmd &cmd)
  {
   cmd.protocol_version = Json_ExtractString(json, "protocol_version");
   cmd.slave_id         = Json_ExtractString(json, "slave_id");
   cmd.master_id        = Json_ExtractString(json, "master_id");
   cmd.master_ticket    = Json_ExtractLong  (json, "master_ticket");
   cmd.symbol           = Json_ExtractString(json, "symbol");
   cmd.volume           = Json_ExtractDouble(json, "volume");
   cmd.price            = Json_ExtractDouble(json, "price");
   cmd.sl_points        = Json_ExtractLong  (json, "sl_points");  // << ALTERADO
   cmd.tp_points        = Json_ExtractLong  (json, "tp_points");  // << ALTERADO
   cmd.comment          = Json_ExtractString(json, "comment");

   string order_str = Json_ExtractString(json, "order_type");
   cmd.order_type = (order_str == "BUY") ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;

   if(cmd.slave_id == "" || cmd.symbol == "" || cmd.volume <= 0 || cmd.master_ticket == 0)
     {
      Print("EPCopyFlow_Slave | JSON OPEN inválido: campos obrigatórios ausentes.");
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Deserializa comando CLOSE                                        |
//+------------------------------------------------------------------+
bool Json_ParseClose(const string json, SlaveCloseCmd &cmd)
  {
   cmd.protocol_version = Json_ExtractString(json, "protocol_version");
   cmd.slave_id         = Json_ExtractString(json, "slave_id");
   cmd.master_id        = Json_ExtractString(json, "master_id");
   cmd.master_ticket    = Json_ExtractLong  (json, "master_ticket");
   cmd.symbol           = Json_ExtractString(json, "symbol");

   if(cmd.slave_id == "" || cmd.master_ticket == 0)
     {
      Print("EPCopyFlow_Slave | JSON CLOSE inválido: campos obrigatórios ausentes.");
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Deserializa comando PARTIAL_CLOSE                                |
//+------------------------------------------------------------------+
bool Json_ParsePartialClose(const string json, SlavePartialCloseCmd &cmd)
  {
   cmd.protocol_version = Json_ExtractString(json, "protocol_version");
   cmd.slave_id         = Json_ExtractString(json, "slave_id");
   cmd.master_id        = Json_ExtractString(json, "master_id");
   cmd.master_ticket    = Json_ExtractLong  (json, "master_ticket");
   cmd.symbol           = Json_ExtractString(json, "symbol");
   cmd.close_volume     = Json_ExtractDouble(json, "close_volume");

   if(cmd.slave_id == "" || cmd.master_ticket == 0 || cmd.close_volume <= 0)
     {
      Print("EPCopyFlow_Slave | JSON PARTIAL_CLOSE inválido: campos obrigatórios ausentes.");
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Deserializa comando MODIFY_SLTP                                  |
//+------------------------------------------------------------------+
bool Json_ParseModify(const string json, SlaveModifyCmd &cmd)
  {
   cmd.protocol_version = Json_ExtractString(json, "protocol_version");
   cmd.slave_id         = Json_ExtractString(json, "slave_id");
   cmd.master_id        = Json_ExtractString(json, "master_id");
   cmd.master_ticket    = Json_ExtractLong  (json, "master_ticket");
   cmd.symbol           = Json_ExtractString(json, "symbol");
   cmd.sl_points        = Json_ExtractLong  (json, "sl_points");  // << ALTERADO
   cmd.tp_points        = Json_ExtractLong  (json, "tp_points");  // << ALTERADO

   if(cmd.slave_id == "" || cmd.master_ticket == 0)
     {
      Print("EPCopyFlow_Slave | JSON MODIFY inválido: campos obrigatórios ausentes.");
      return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
//| Serializa SlaveHeartbeat para JSON                               |
//+------------------------------------------------------------------+
string Json_BuildHeartbeat(const SlaveHeartbeat &hb)
  {
   string json = "{";
   json += "\"protocol_version\":\"" + hb.protocol_version + "\",";
   json += "\"event_type\":\"HEARTBEAT\",";
   json += "\"slave_id\":\""         + hb.slave_id         + "\",";
   json += "\"master_id\":\""        + hb.master_id        + "\",";
   json += "\"timestamp\":"          + IntegerToString((long)hb.timestamp) + ",";
   json += "\"positions_count\":"    + IntegerToString(hb.positions_count) + ",";
   json += "\"positions\":[";

   for(int i = 0; i < hb.positions_count; i++)
     {
      if(i > 0) json += ",";
      json += "{";
      json += "\"ticket\":"        + IntegerToString(hb.positions[i].ticket)          + ",";
      json += "\"symbol\":\""      + hb.positions[i].symbol                           + "\",";
      json += "\"type\":"          + IntegerToString((int)hb.positions[i].type)       + ",";
      json += "\"volume\":"        + DoubleToString(hb.positions[i].volume, 2)        + ",";
      json += "\"open_price\":"    + DoubleToString(hb.positions[i].open_price, 5)    + ",";
      json += "\"sl\":"            + DoubleToString(hb.positions[i].sl, 5)            + ",";
      json += "\"tp\":"            + DoubleToString(hb.positions[i].tp, 5)            + ",";
      json += "\"profit\":"        + DoubleToString(hb.positions[i].profit, 2)        + ",";
      json += "\"master_ticket\":" + IntegerToString(hb.positions[i].master_ticket)   + ",";
      json += "\"comment\":\""     + hb.positions[i].comment                          + "\"";
      json += "}";
     }

   json += "]}";
   return json;
  }

#endif // EPCOPYFLOW_SLAVE_JSON_MQH
