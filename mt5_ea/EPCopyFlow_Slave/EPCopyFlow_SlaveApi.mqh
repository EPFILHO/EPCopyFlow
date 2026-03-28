//+------------------------------------------------------------------+
//| EPCopyFlow_SlaveApi.mqh                                          |
//| Executa os comandos recebidos pelo Slave no MT5                  |
//| EPCopyFlow - EPFilho                                             |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_SLAVEAPI_MQH
#define EPCOPYFLOW_SLAVEAPI_MQH

#include "EPCopyFlow_SlaveEvents.mqh"
#include <Trade\Trade.mqh>

CTrade g_trade;

//+------------------------------------------------------------------+
//| Helper: reconstroi preco absoluto a partir de pontos             |
//| open_price : preco de abertura real do Slave                     |
//| points     : distancia em pontos (0 = sem nivel)                 |
//| is_buy     : true = BUY, false = SELL                            |
//| is_sl      : true = Stop Loss, false = Take Profit               |
//+------------------------------------------------------------------+
double _SA_PointsToPrice(const string symbol,
                          double       open_price,
                          long         points,
                          bool         is_buy,
                          bool         is_sl)
{
   if(points <= 0) return 0.0;

   double point   = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int    digits  = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   double dist    = points * point;

   double level = 0.0;
   if(is_buy)
      level = is_sl ? (open_price - dist) : (open_price + dist);
   else
      level = is_sl ? (open_price + dist) : (open_price - dist);

   return NormalizeDouble(level, digits);
}

//+------------------------------------------------------------------+
//| Executa abertura de posicao                                      |
//+------------------------------------------------------------------+
bool Api_ExecuteOpen(const SlaveOpenCmd &cmd,
                      ulong             &slave_ticket_out)
{
   slave_ticket_out = 0;

   // Ajusta magic e comment do trade
   g_trade.SetExpertMagicNumber((ulong)cmd.magic);

   // Determina preco de execucao (0 = preco de mercado)
   double price  = cmd.price;
   bool   is_buy = (cmd.order_type == ORDER_TYPE_BUY);

   // Usa o preco que o Slave vai realmente abrir para calcular SL/TP
   // Se price == 0 (mercado), captura o bid/ask atual
   if(price <= 0.0)
      price = is_buy ? SymbolInfoDouble(cmd.symbol, SYMBOL_ASK)
                     : SymbolInfoDouble(cmd.symbol, SYMBOL_BID);

   // Reconstroi SL e TP em preco local usando o open_price do Slave
   double slave_sl = _SA_PointsToPrice(cmd.symbol, price, cmd.sl_points, is_buy, true);
   double slave_tp = _SA_PointsToPrice(cmd.symbol, price, cmd.tp_points, is_buy, false);

   bool result = false;
   if(is_buy)
      result = g_trade.Buy(cmd.volume, cmd.symbol, 0, slave_sl, slave_tp, cmd.comment);
   else
      result = g_trade.Sell(cmd.volume, cmd.symbol, 0, slave_sl, slave_tp, cmd.comment);

   if(result)
   {
      slave_ticket_out = g_trade.ResultOrder();
      PrintFormat("[SlaveApi] OPEN OK | master=%I64u slave=%I64u sym=%s sl=%.5f tp=%.5f",
                  cmd.master_ticket, slave_ticket_out,
                  cmd.symbol, slave_sl, slave_tp);
   }
   else
   {
      PrintFormat("[SlaveApi] OPEN ERRO | retcode=%d desc=%s",
                  g_trade.ResultRetcode(),
                  g_trade.ResultRetcodeDescription());
   }

   return result;
}

//+------------------------------------------------------------------+
//| Executa modificacao de SL/TP                                     |
//+------------------------------------------------------------------+
bool Api_ExecuteModify(const SlaveModifyCmd &cmd, ulong slave_ticket)
{
   if(!PositionSelectByTicket(slave_ticket))
   {
      PrintFormat("[SlaveApi] MODIFY ERRO | ticket %I64u nao encontrado", slave_ticket);
      return false;
   }

   double slave_open  = PositionGetDouble(POSITION_PRICE_OPEN);
   bool   is_buy      = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY);
   string symbol      = PositionGetString(POSITION_SYMBOL);

   // Reconstroi SL e TP usando o open_price real da posicao do Slave
   double slave_sl = _SA_PointsToPrice(symbol, slave_open, cmd.sl_points, is_buy, true);
   double slave_tp = _SA_PointsToPrice(symbol, slave_open, cmd.tp_points, is_buy, false);

   bool result = g_trade.PositionModify(slave_ticket, slave_sl, slave_tp);

   if(result)
      PrintFormat("[SlaveApi] MODIFY OK | ticket=%I64u sl=%.5f tp=%.5f",
                  slave_ticket, slave_sl, slave_tp);
   else
      PrintFormat("[SlaveApi] MODIFY ERRO | retcode=%d desc=%s",
                  g_trade.ResultRetcode(),
                  g_trade.ResultRetcodeDescription());

   return result;
}

//+------------------------------------------------------------------+
//| Executa fechamento de posicao                                    |
//+------------------------------------------------------------------+
bool Api_ExecuteClose(const SlaveCloseCmd &cmd, ulong slave_ticket)
{
   if(!PositionSelectByTicket(slave_ticket))
   {
      PrintFormat("[SlaveApi] CLOSE ERRO | ticket %I64u nao encontrado", slave_ticket);
      return false;
   }

   double total_vol = PositionGetDouble(POSITION_VOLUME);
   double close_vol = NormalizeDouble(total_vol * cmd.volume_pct, 2);
   if(close_vol <= 0.0) close_vol = total_vol;

   bool result;
   if(close_vol >= total_vol)
      result = g_trade.PositionClose(slave_ticket);
   else
      result = g_trade.PositionClosePartial(slave_ticket, close_vol);

   if(result)
      PrintFormat("[SlaveApi] CLOSE OK | ticket=%I64u vol=%.2f reason=%s",
                  slave_ticket, close_vol, cmd.reason);
   else
      PrintFormat("[SlaveApi] CLOSE ERRO | retcode=%d desc=%s",
                  g_trade.ResultRetcode(),
                  g_trade.ResultRetcodeDescription());

   return result;
}

#endif // EPCOPYFLOW_SLAVEAPI_MQH
//+------------------------------------------------------------------+
