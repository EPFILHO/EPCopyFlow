//+------------------------------------------------------------------+
//|                                        EPCopyFlow_Slave.mq5      |
//|                                         EP Filho © 2026          |
//|                    https://github.com/EPFILHO/EPCopyFlow         |
//+------------------------------------------------------------------+
#property copyright "EP Filho © 2026"
#property link      "https://github.com/EPFILHO/EPCopyFlow"
#property version   "1.00"
#property strict

#include "EPCopyFlow_SlaveContext.mqh"
#include "EPCopyFlow_SlaveEvents.mqh"
#include "EPCopyFlow_SlaveJson.mqh"
#include "EPCopyFlow_SlaveZmq.mqh"
#include "EPCopyFlow_SlaveApi.mqh"

//--- Inputs
input int  InpHeartbeatSec = 5;   // Intervalo do heartbeat (segundos)

//--- Controle de tempo
uint g_last_heartbeat_tick = 0;
bool g_first_timer         = true;
uint g_last_hb_event_tick  = 0;   // [FIX] debounce heartbeat em rajada

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit()
  {
   if(!SlaveContext_Load())
      return INIT_FAILED;

   if(!SlaveZmq_Init())
      return INIT_FAILED;

   EventSetMillisecondTimer(500);

   PrintFormat("EPCopyFlow_Slave | Iniciado → SlaveId=%s | MasterId=%s | Aguardando ZMQ estabilizar...",
               g_ctx.slave_id, g_ctx.master_id);
   return INIT_SUCCEEDED;
  }

//+------------------------------------------------------------------+
//| OnDeinit                                                         |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   SlaveZmq_Deinit();
   PrintFormat("EPCopyFlow_Slave | Encerrado → SlaveId=%s | Reason=%d",
               g_ctx.slave_id, reason);
  }

//+------------------------------------------------------------------+
//| OnTimer — polling ZMQ + heartbeat periódico                      |
//+------------------------------------------------------------------+
void OnTimer()
  {
   //--- Primeiro timer: ZMQ já estabilizou, dispara heartbeat inicial
   if(g_first_timer)
     {
      g_first_timer          = false;
      g_last_heartbeat_tick  = GetTickCount();
      Api_SendHeartbeat();
      return;
     }

   //--- Drena todas as mensagens disponíveis no SUB
   string msg;
   while(SlaveZmq_Receive(msg))
      Api_ProcessMessage(msg);

   //--- Heartbeat periódico
   uint now = GetTickCount();
   if(now - g_last_heartbeat_tick >= (uint)(InpHeartbeatSec * 1000))
     {
      Api_SendHeartbeat();
      g_last_heartbeat_tick = now;
     }
  }

//+------------------------------------------------------------------+
//| OnTradeTransaction — loga deals e força heartbeat imediato       |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest     &request,   // [FIX] ordem correta
                        const MqlTradeResult      &result)    // [FIX] ordem correta
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;

   ulong deal = trans.deal;
   if(!HistoryDealSelect(deal)) return;

   long   ticket  = (long)HistoryDealGetInteger(deal, DEAL_POSITION_ID);
   string symbol  = HistoryDealGetString (deal, DEAL_SYMBOL);
   double volume  = HistoryDealGetDouble (deal, DEAL_VOLUME);
   double price   = HistoryDealGetDouble (deal, DEAL_PRICE);
   int    entry   = (int)HistoryDealGetInteger(deal, DEAL_ENTRY);
   string comment = HistoryDealGetString (deal, DEAL_COMMENT);

   string entry_str = (entry == DEAL_ENTRY_IN)    ? "IN"    :
                      (entry == DEAL_ENTRY_OUT)   ? "OUT"   :
                      (entry == DEAL_ENTRY_INOUT) ? "INOUT" : "OUT_BY";

   PrintFormat("EPCopyFlow_Slave | DEAL %s → ticket=%d | %s | vol=%.2f | price=%.5f | comment=%s",
               entry_str, ticket, symbol, volume, price, comment);

   //--- [FIX] Debounce: máximo 1 heartbeat de evento por segundo
   uint now = GetTickCount();
   if(now - g_last_hb_event_tick >= 1000)
     {
      g_last_hb_event_tick = now;
      Api_SendHeartbeat();
     }
  }

//+------------------------------------------------------------------+
//| OnTrade — modificações de posição → heartbeat imediato           |
//+------------------------------------------------------------------+
void OnTrade()
  {
   //--- [FIX] Debounce: máximo 1 heartbeat de evento por segundo
   uint now = GetTickCount();
   if(now - g_last_hb_event_tick >= 1000)
     {
      g_last_hb_event_tick = now;
      Api_SendHeartbeat();
     }
  }
