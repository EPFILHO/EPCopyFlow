//+------------------------------------------------------------------+
//| EPCopyFlow_MasterJson.mqh                                        |
//| Serializacao JSON dos eventos do EA Master                       |
//| EPCopyFlow - EPFilho                                             |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_MASTERJSON_MQH
#define EPCOPYFLOW_MASTERJSON_MQH

#include "EPCopyFlow_MasterEvents.mqh"

//+------------------------------------------------------------------+
//| Helpers internos de formatacao                                   |
//+------------------------------------------------------------------+
string _MJ_Str(const string &s)
  {
   string out = s;
   StringReplace(out, "\\", "\\\\");
   StringReplace(out, "\"", "\\\"");
   return "\"" + out + "\"";
  }

string _MJ_D(double v, int digits = 8) { return DoubleToString(v, digits); }
string _MJ_I(long v)                   { return IntegerToString((long)v); }
string _MJ_U(ulong v)                  { return IntegerToString((long)v); }

//+------------------------------------------------------------------+
//| Serializa OPEN                                                   |
//+------------------------------------------------------------------+
string Master_SerializeOpen(const MasterContext &ctx,
                            const MasterEventOpen &evt)
  {
   string t = (evt.order_type == ORDER_TYPE_BUY) ? "BUY" : "SELL";
   string j = "{";
   j += "\"protocol_version\":"  + _MJ_Str(ctx.protocol_version) + ",";
   j += "\"event_type\":\"OPEN\",";
   j += "\"master_id\":"         + _MJ_Str(ctx.master_id) + ",";
   j += "\"master_ticket\":"     + _MJ_U(evt.master_ticket) + ",";
   j += "\"symbol\":"            + _MJ_Str(evt.symbol) + ",";
   j += "\"order_type\":\""       + t + "\",";
   j += "\"volume\":"            + _MJ_D(evt.volume, 2) + ",";
   j += "\"open_price\":"        + _MJ_D(evt.open_price) + ",";
   j += "\"sl\":"                + _MJ_D(evt.sl) + ",";
   j += "\"tp\":"                + _MJ_D(evt.tp) + ",";
   j += "\"magic\":"             + _MJ_I(evt.magic) + ",";
   j += "\"comment\":"           + _MJ_Str(evt.comment) + ",";
   j += "\"timestamp\":"         + _MJ_I((long)evt.timestamp);
   j += "}";
   return j;
  }

//+------------------------------------------------------------------+
//| Serializa MODIFY_SLTP                                            |
//+------------------------------------------------------------------+
string Master_SerializeModifySLTP(const MasterContext &ctx,
                                  const MasterEventModifySLTP &evt)
  {
   string j = "{";
   j += "\"protocol_version\":"  + _MJ_Str(ctx.protocol_version) + ",";
   j += "\"event_type\":\"MODIFY_SLTP\",";
   j += "\"master_id\":"         + _MJ_Str(ctx.master_id) + ",";
   j += "\"master_ticket\":"     + _MJ_U(evt.master_ticket) + ",";
   j += "\"symbol\":"            + _MJ_Str(evt.symbol) + ",";
   j += "\"sl\":"                + _MJ_D(evt.sl) + ",";
   j += "\"tp\":"                + _MJ_D(evt.tp) + ",";
   j += "\"timestamp\":"         + _MJ_I((long)evt.timestamp);
   j += "}";
   return j;
  }

//+------------------------------------------------------------------+
//| Serializa CLOSE                                                  |
//+------------------------------------------------------------------+
string Master_SerializeClose(const MasterContext &ctx,
                             const MasterEventClose &evt)
  {
   string j = "{";
   j += "\"protocol_version\":"  + _MJ_Str(ctx.protocol_version) + ",";
   j += "\"event_type\":\"CLOSE\",";
   j += "\"master_id\":"         + _MJ_Str(ctx.master_id) + ",";
   j += "\"master_ticket\":"     + _MJ_U(evt.master_ticket) + ",";
   j += "\"symbol\":"            + _MJ_Str(evt.symbol) + ",";
   j += "\"volume_closed\":"     + _MJ_D(evt.volume_closed, 2) + ",";
   j += "\"close_price\":"       + _MJ_D(evt.close_price) + ",";
   j += "\"reason\":"            + _MJ_Str(evt.reason) + ",";
   j += "\"timestamp\":"         + _MJ_I((long)evt.timestamp);
   j += "}";
   return j;
  }

//+------------------------------------------------------------------+
//| Serializa HEARTBEAT                                              |
//+------------------------------------------------------------------+
string Master_SerializeHeartbeat(const MasterContext &ctx,
                                 const MasterEventHeartbeat &evt)
  {
   string j = "{";
   j += "\"protocol_version\":"  + _MJ_Str(ctx.protocol_version) + ",";
   j += "\"event_type\":\"HEARTBEAT\",";
   j += "\"master_id\":"         + _MJ_Str(ctx.master_id) + ",";
   j += "\"timestamp\":"         + _MJ_I((long)evt.timestamp);
   j += "}";
   return j;
  }

#endif // EPCOPYFLOW_MASTERJSON_MQH
//+------------------------------------------------------------------+
