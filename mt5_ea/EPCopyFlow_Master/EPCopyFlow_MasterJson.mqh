//+------------------------------------------------------------------+
//| EPCopyFlow_MasterJson.mqh                                        |
//| Serializa eventos do Master para JSON                            |
//| EPCopyFlow - EPFilho                                             |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_MASTERJSON_MQH
#define EPCOPYFLOW_MASTERJSON_MQH

#include "EPCopyFlow_MasterEvents.mqh"

//--- Helpers de formatacao!
string _MJ_D(double v)   { return DoubleToString(v, 8); }
string _MJ_I(long v)     { return IntegerToString(v); }
string _MJ_S(string v)   { return "\"" + v + "\""; }
string _MJ_T(datetime t) { return "\"" + TimeToString(t, TIME_DATE|TIME_MINUTES|TIME_SECONDS) + "\""; }

//--- Converte preco absoluto em pontos relativos ao open_price
//    is_sl=true  -> calcula distancia do SL ao open
//    is_sl=false -> calcula distancia do TP ao open
long _MJ_PriceToPoints(const string symbol,
                        double       open_price,
                        double       level,
                        bool         is_buy,
                        bool         is_sl)
{
   if(level == 0.0) return 0;

   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(point <= 0.0) return 0;

   double diff = 0.0;
   if(is_buy)
      diff = is_sl ? (open_price - level) : (level - open_price);
   else
      diff = is_sl ? (level - open_price) : (open_price - level);

   if(diff <= 0.0) return 0;   // nivel invalido (ex: SL acima do preco em BUY)
   return (long)MathRound(diff / point);
}

//+------------------------------------------------------------------+
//| Serializa evento OPEN                                            |
//+------------------------------------------------------------------+
string Master_SerializeOpen(const MasterContext &ctx,
                             const MasterEventOpen &evt)
{
   bool is_buy = (evt.order_type == ORDER_TYPE_BUY);
   long sl_pts = _MJ_PriceToPoints(evt.symbol, evt.open_price, evt.sl, is_buy, true);
   long tp_pts = _MJ_PriceToPoints(evt.symbol, evt.open_price, evt.tp, is_buy, false);

   string j = "{";
   j += "\"type\":" + _MJ_S("OPEN") + ",";
   j += "\"master_id\":" + _MJ_S(ctx.master_id) + ",";
   j += "\"protocol_version\":" + _MJ_S(ctx.protocol_version) + ",";
   j += "\"master_ticket\":" + _MJ_I((long)evt.master_ticket) + ",";
   j += "\"symbol\":" + _MJ_S(evt.symbol) + ",";
   j += "\"order_type\":" + _MJ_I((long)evt.order_type) + ",";
   j += "\"volume\":" + _MJ_D(evt.volume) + ",";
   j += "\"open_price\":" + _MJ_D(evt.open_price) + ",";
   j += "\"sl_points\":" + _MJ_I(sl_pts) + ",";
   j += "\"tp_points\":" + _MJ_I(tp_pts) + ",";
   j += "\"magic\":" + _MJ_I(evt.magic) + ",";
   j += "\"comment\":" + _MJ_S(evt.comment) + ",";
   j += "\"timestamp\":" + _MJ_T(evt.timestamp);
   j += "}";
   return j;
}

//+------------------------------------------------------------------+
//| Serializa evento MODIFY_SLTP                                     |
//+------------------------------------------------------------------+
string Master_SerializeModifySLTP(const MasterContext         &ctx,
                                   const MasterEventModifySLTP &evt)
{
   bool is_buy = (evt.order_type == ORDER_TYPE_BUY);
   long sl_pts = _MJ_PriceToPoints(evt.symbol, evt.open_price, evt.sl, is_buy, true);
   long tp_pts = _MJ_PriceToPoints(evt.symbol, evt.open_price, evt.tp, is_buy, false);

   string j = "{";
   j += "\"type\":" + _MJ_S("MODIFY_SLTP") + ",";
   j += "\"master_id\":" + _MJ_S(ctx.master_id) + ",";
   j += "\"protocol_version\":" + _MJ_S(ctx.protocol_version) + ",";
   j += "\"master_ticket\":" + _MJ_I((long)evt.master_ticket) + ",";
   j += "\"symbol\":" + _MJ_S(evt.symbol) + ",";
   j += "\"sl_points\":" + _MJ_I(sl_pts) + ",";
   j += "\"tp_points\":" + _MJ_I(tp_pts) + ",";
   j += "\"timestamp\":" + _MJ_T(evt.timestamp);
   j += "}";
   return j;
}

//+------------------------------------------------------------------+
//| Serializa evento CLOSE                                           |
//+------------------------------------------------------------------+
string Master_SerializeClose(const MasterContext    &ctx,
                              const MasterEventClose &evt)
{
   string j = "{";
   j += "\"type\":" + _MJ_S("CLOSE") + ",";
   j += "\"master_id\":" + _MJ_S(ctx.master_id) + ",";
   j += "\"protocol_version\":" + _MJ_S(ctx.protocol_version) + ",";
   j += "\"master_ticket\":" + _MJ_I((long)evt.master_ticket) + ",";
   j += "\"symbol\":" + _MJ_S(evt.symbol) + ",";
   j += "\"volume_closed\":" + _MJ_D(evt.volume_closed) + ",";
   j += "\"close_price\":" + _MJ_D(evt.close_price) + ",";
   j += "\"reason\":" + _MJ_S(evt.reason) + ",";
   j += "\"timestamp\":" + _MJ_T(evt.timestamp);
   j += "}";
   return j;
}

//+------------------------------------------------------------------+
//| Serializa evento HEARTBEAT                                       |
//+------------------------------------------------------------------+
string Master_SerializeHeartbeat(const MasterContext          &ctx,
                                  const MasterEventHeartbeat   &evt)
{
   string j = "{";
   j += "\"type\":" + _MJ_S("HEARTBEAT") + ",";
   j += "\"master_id\":" + _MJ_S(ctx.master_id) + ",";
   j += "\"protocol_version\":" + _MJ_S(ctx.protocol_version) + ",";
   j += "\"timestamp\":" + _MJ_T(evt.timestamp);
   j += "}";
   return j;
}

#endif // EPCOPYFLOW_MASTERJSON_MQH
//+------------------------------------------------------------------+
