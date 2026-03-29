//+------------------------------------------------------------------+
//|                                      EPCopyFlow_SlaveApi.mqh     |
//|                                         EP Filho © 2026          |
//|                    https://github.com/EPFILHO/EPCopyFlow          |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_SLAVE_API_MQH
#define EPCOPYFLOW_SLAVE_API_MQH

#include "EPCopyFlow_SlaveContext.mqh"
#include "EPCopyFlow_SlaveEvents.mqh"
#include "EPCopyFlow_SlaveJson.mqh"
#include "EPCopyFlow_SlaveZmq.mqh"
#include <Trade\Trade.mqh>

CTrade g_trade;
bool   g_slave_debug = true;

//+------------------------------------------------------------------+
//| Converte pontos para preço absoluto no contexto do Slave         |
//+------------------------------------------------------------------+
double Api_PointsToPrice(const string symbol, const double ref_price,
                         const long points, const bool is_buy)
  {
   if(points == 0) return 0.0;
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   // BUY:  SL abaixo do preço (−), TP acima (+)
   // SELL: SL acima do preço (+), TP abaixo (−)
   // O sinal já vem correto dos pontos positivos: SL e TP são sempre >= 0 pontos de distância
   // A direção é inferida pelo tipo da ordem
   if(is_buy)
      return NormalizeDouble(ref_price + points * point, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
   else
      return NormalizeDouble(ref_price - points * point, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS));
  }

//+------------------------------------------------------------------+
//| Busca ticket da posição slave pelo master_ticket gravado no comment
//+------------------------------------------------------------------+
long Api_FindSlaveTicket(const long master_ticket)
  {
   string search = "MT#" + IntegerToString(master_ticket);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;
      if(StringFind(PositionGetString(POSITION_COMMENT), search) >= 0)
         return (long)ticket;
     }
   PrintFormat("EPCopyFlow_Slave | WARN: posição master_ticket=%d não encontrada.", master_ticket);
   return -1;
  }

//+------------------------------------------------------------------+
//| Normaliza volume para o símbolo                                  |
//+------------------------------------------------------------------+
double Api_NormalizeVolume(const string symbol, const double volume)
  {
   double step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   double min  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double max  = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0) step = 0.01;
   double vol = MathRound(volume / step) * step;
   vol = MathMax(min, MathMin(max, vol));
   return NormalizeDouble(vol, 2);
  }

//+------------------------------------------------------------------+
//| Reescreve o comment da posição sobrevivente após Partial Close   |
//| MT5 cria novo ticket sem herdar o comment — esta função restaura |
//+------------------------------------------------------------------+
void Api_RestoreCommentAfterPartialClose(const string symbol,
                                         const long   master_ticket,
                                         const string original_comment)
  {
   string search = "MT#" + IntegerToString(master_ticket);

   // Aguarda MT5 processar a nova posição (até 3 tentativas)
   for(int attempt = 0; attempt < 3; attempt++)
     {
      Sleep(200);
      for(int i = PositionsTotal() - 1; i >= 0; i--)
        {
         ulong ticket = PositionGetTicket(i);
         if(!PositionSelectByTicket(ticket)) continue;
         if(PositionGetString(POSITION_SYMBOL) != symbol) continue;

         string pos_comment = PositionGetString(POSITION_COMMENT);

         // Posição já tem o comment correto — não precisa restaurar
         if(StringFind(pos_comment, search) >= 0) return;

         // Posição do mesmo símbolo sem o nosso comment — é a sobrevivente
         // Verifica se o comment está vazio ou foi alterado pelo MT5
         if(pos_comment == "" || StringFind(pos_comment, "to") >= 0)
           {
            MqlTradeRequest req = {};
            MqlTradeResult  res = {};
            req.action   = TRADE_ACTION_MODIFY;
            req.position = ticket;
            req.symbol   = symbol;
            req.sl       = PositionGetDouble(POSITION_SL);
            req.tp       = PositionGetDouble(POSITION_TP);
            req.comment  = original_comment;

            if(OrderSend(req, res))
               PrintFormat("EPCopyFlow_Slave | COMMENT RESTAURADO → ticket=%d | comment='%s' | master_ticket=%d",
                           ticket, original_comment, master_ticket);
            else
               PrintFormat("EPCopyFlow_Slave | WARN: falha ao restaurar comment → ticket=%d | retcode=%d",
                           ticket, res.retcode);
            return;
           }
        }
     }
   PrintFormat("EPCopyFlow_Slave | WARN: posição sobrevivente não encontrada para restaurar comment | master_ticket=%d",
               master_ticket);
  }

//+------------------------------------------------------------------+
//| Executa OPEN                                                     |
//+------------------------------------------------------------------+
bool Api_ExecuteOpen(const SlaveOpenCmd &cmd)
  {
   if(cmd.slave_id != g_ctx.slave_id) return false;

   double volume  = Api_NormalizeVolume(cmd.symbol, cmd.volume);
   string comment = (cmd.comment != "" ? cmd.comment : "EPSlave") +
                    "|MT#" + IntegerToString(cmd.master_ticket);

   // Converte sl_points / tp_points → preços absolutos no Slave     // << ALTERADO
   bool   is_buy   = (cmd.order_type == ORDER_TYPE_BUY);             // << ALTERADO
   double sl_price = Api_PointsToPrice(cmd.symbol, cmd.price,        // << ALTERADO
                                       cmd.sl_points, !is_buy);      // << ALTERADO
   double tp_price = Api_PointsToPrice(cmd.symbol, cmd.price,        // << ALTERADO
                                       cmd.tp_points, is_buy);       // << ALTERADO

   g_trade.SetExpertMagicNumber(0);
   g_trade.SetDeviationInPoints(30);

   bool result = false;
   if(is_buy)
      result = g_trade.Buy(volume, cmd.symbol, cmd.price, sl_price, tp_price, comment);
   else
      result = g_trade.Sell(volume, cmd.symbol, cmd.price, sl_price, tp_price, comment);

   if(result)
      PrintFormat("EPCopyFlow_Slave | OPEN OK → %s %s %.2f | SL=%.5f | TP=%.5f | master_ticket=%d | deal=%d",
                  (is_buy ? "BUY" : "SELL"),
                  cmd.symbol, volume, sl_price, tp_price, cmd.master_ticket, g_trade.ResultDeal());
   else
      PrintFormat("EPCopyFlow_Slave | OPEN ERRO → %s | retcode=%d | %s",
                  cmd.symbol, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());

   return result;
  }

//+------------------------------------------------------------------+
//| Executa CLOSE                                                    |
//+------------------------------------------------------------------+
bool Api_ExecuteClose(const SlaveCloseCmd &cmd)
  {
   if(cmd.slave_id != g_ctx.slave_id) return false;

   long ticket = Api_FindSlaveTicket(cmd.master_ticket);
   if(ticket < 0) return false;

   bool result = g_trade.PositionClose((ulong)ticket);

   if(result)
      PrintFormat("EPCopyFlow_Slave | CLOSE OK → ticket=%d | master_ticket=%d",
                  ticket, cmd.master_ticket);
   else
      PrintFormat("EPCopyFlow_Slave | CLOSE ERRO → ticket=%d | retcode=%d | %s",
                  ticket, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());

   return result;
  }

//+------------------------------------------------------------------+
//| Executa PARTIAL_CLOSE                                            |
//+------------------------------------------------------------------+
bool Api_ExecutePartialClose(const SlavePartialCloseCmd &cmd)
  {
   if(cmd.slave_id != g_ctx.slave_id) return false;

   long ticket = Api_FindSlaveTicket(cmd.master_ticket);
   if(ticket < 0) return false;

   if(!PositionSelectByTicket((ulong)ticket))
     {
      Print("EPCopyFlow_Slave | PARTIAL_CLOSE: não foi possível selecionar posição.");
      return false;
     }

   // Salva o comment original ANTES do close (pois o MT5 não herda no novo ticket)
   string original_comment = PositionGetString(POSITION_COMMENT);

   double volume = Api_NormalizeVolume(cmd.symbol, cmd.close_volume);
   bool   result = g_trade.PositionClosePartial((ulong)ticket, volume);

   if(result)
     {
      PrintFormat("EPCopyFlow_Slave | PARTIAL_CLOSE OK → ticket=%d | vol=%.2f | master_ticket=%d",
                  ticket, volume, cmd.master_ticket);

      // *** PADRÃO OURO: restaura o comment na posição sobrevivente ***
      // MT5 fecha o ticket original e cria novo sem comment — corrigimos aqui
      Api_RestoreCommentAfterPartialClose(cmd.symbol, cmd.master_ticket, original_comment);
     }
   else
      PrintFormat("EPCopyFlow_Slave | PARTIAL_CLOSE ERRO → ticket=%d | retcode=%d | %s",
                  ticket, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());

   return result;
  }

//+------------------------------------------------------------------+
//| Executa MODIFY_SLTP                                              |
//+------------------------------------------------------------------+
bool Api_ExecuteModify(const SlaveModifyCmd &cmd)
  {
   if(cmd.slave_id != g_ctx.slave_id) return false;

   long ticket = Api_FindSlaveTicket(cmd.master_ticket);
   if(ticket < 0) return false;

   // Busca open_price e tipo da posição Slave para reconstruir preços  // << ALTERADO
   if(!PositionSelectByTicket((ulong)ticket)) return false;             // << ALTERADO
   double open_price = PositionGetDouble(POSITION_PRICE_OPEN);         // << ALTERADO
   bool   is_buy     = (PositionGetInteger(POSITION_TYPE)              // << ALTERADO
                        == POSITION_TYPE_BUY);                         // << ALTERADO
   double sl_price   = Api_PointsToPrice(cmd.symbol, open_price,      // << ALTERADO
                                         cmd.sl_points, !is_buy);     // << ALTERADO
   double tp_price   = Api_PointsToPrice(cmd.symbol, open_price,      // << ALTERADO
                                         cmd.tp_points, is_buy);      // << ALTERADO

   bool result = g_trade.PositionModify((ulong)ticket, sl_price, tp_price);

   if(result)
      PrintFormat("EPCopyFlow_Slave | MODIFY OK → ticket=%d | SL=%.5f | TP=%.5f | master_ticket=%d",
                  ticket, sl_price, tp_price, cmd.master_ticket);
   else
      PrintFormat("EPCopyFlow_Slave | MODIFY ERRO → ticket=%d | retcode=%d | %s",
                  ticket, g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());

   return result;
  }

//+------------------------------------------------------------------+
//| Monta e envia Heartbeat com todas as posições abertas            |
//+------------------------------------------------------------------+
void Api_SendHeartbeat()
  {
   SlaveHeartbeat hb;
   hb.protocol_version = g_ctx.protocol_version;
   hb.event_type       = "HEARTBEAT";
   hb.slave_id         = g_ctx.slave_id;
   hb.master_id        = g_ctx.master_id;
   hb.timestamp        = TimeCurrent();
   hb.positions_count  = PositionsTotal();
   ArrayResize(hb.positions, hb.positions_count);

   for(int i = 0; i < hb.positions_count; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(!PositionSelectByTicket(ticket)) continue;

      hb.positions[i].ticket     = (long)ticket;
      hb.positions[i].symbol     = PositionGetString(POSITION_SYMBOL);
      hb.positions[i].type       = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      hb.positions[i].volume     = PositionGetDouble(POSITION_VOLUME);
      hb.positions[i].open_price = PositionGetDouble(POSITION_PRICE_OPEN);
      hb.positions[i].sl         = PositionGetDouble(POSITION_SL);
      hb.positions[i].tp         = PositionGetDouble(POSITION_TP);
      hb.positions[i].profit     = PositionGetDouble(POSITION_PROFIT);
      hb.positions[i].comment    = PositionGetString(POSITION_COMMENT);

      string comment = hb.positions[i].comment;
      int    mt_pos  = StringFind(comment, "MT#");
      hb.positions[i].master_ticket = (mt_pos >= 0)
                                      ? StringToInteger(StringSubstr(comment, mt_pos + 3))
                                      : 0;
     }

   string json = Json_BuildHeartbeat(hb);

   if(!SlaveZmq_Send(json))
      Print("EPCopyFlow_Slave | Falha ao enviar HEARTBEAT");
   else if(g_slave_debug)
      PrintFormat("EPCopyFlow_Slave | HEARTBEAT enviado → SlaveId=%s | positions=%d | ts=%d",
                  hb.slave_id, hb.positions_count, (long)hb.timestamp);
  }

//+------------------------------------------------------------------+
//| Ponto de entrada único — despacha comando recebido do Python     |
//+------------------------------------------------------------------+
void Api_ProcessMessage(const string json)
  {
   ENUM_SLAVE_CMD cmd_type = Json_GetCommandType(json);

   switch(cmd_type)
     {
      case SLAVE_CMD_OPEN:
        {
         SlaveOpenCmd cmd;
         if(Json_ParseOpen(json, cmd)) Api_ExecuteOpen(cmd);
         break;
        }
      case SLAVE_CMD_CLOSE:
        {
         SlaveCloseCmd cmd;
         if(Json_ParseClose(json, cmd)) Api_ExecuteClose(cmd);
         break;
        }
      case SLAVE_CMD_PARTIAL_CLOSE:
        {
         SlavePartialCloseCmd cmd;
         if(Json_ParsePartialClose(json, cmd)) Api_ExecutePartialClose(cmd);
         break;
        }
      case SLAVE_CMD_MODIFY_SLTP:
        {
         SlaveModifyCmd cmd;
         if(Json_ParseModify(json, cmd)) Api_ExecuteModify(cmd);
         break;
        }
      case SLAVE_CMD_HEARTBEAT:
         Api_SendHeartbeat();
         break;

      default:
         PrintFormat("EPCopyFlow_Slave | Mensagem ignorada → '%s'", json);
         break;
     }
  }

#endif // EPCOPYFLOW_SLAVE_API_MQH
