//+------------------------------------------------------------------+
//| EPCopyFlow_MasterApi.mqh                                         |
//| API publica do EA Master: Init, eventos de posicao, heartbeat   |
//| EPCopyFlow - EPFilho                                             |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_MASTERAPI_MQH
#define EPCOPYFLOW_MASTERAPI_MQH

#include "EPCopyFlow_MasterContext.mqh"
#include "EPCopyFlow_MasterJson.mqh"
#include "EPCopyFlow_MasterZmq.mqh"

//--- Contexto global do Master (preenchido em Master_Init)
MasterContext g_master_ctx;
bool          g_master_debug = true;

//+------------------------------------------------------------------+
//| Master_Init: carrega config, conecta ZMQ                         |
//+------------------------------------------------------------------+
bool Master_Init(bool debug_log = true)
  {
   g_master_debug = debug_log;

   if(!Master_LoadConfig(g_master_ctx))
     {
      Alert("EPCopyFlow_Master: Falha ao carregar config.ini");
      return false;
     }

   if(!Master_ZmqConnect(g_master_ctx.zmq_address))
     {
      Alert("EPCopyFlow_Master: Falha ao conectar ZMQ em ", g_master_ctx.zmq_address);
      return false;
     }

   PrintFormat("EPCopyFlow_Master: Iniciado. ID=%s Proto=%s ZMQ=%s",
               g_master_ctx.master_id,
               g_master_ctx.protocol_version,
               g_master_ctx.zmq_address);
   return true;
  }

//+------------------------------------------------------------------+
//| Master_Shutdown: desconecta ZMQ                                  |
//+------------------------------------------------------------------+
void Master_Shutdown()
  {
   Master_ZmqDisconnect();
   Print("EPCopyFlow_Master: Shutdown.");
  }

//+------------------------------------------------------------------+
//| Master_SendHeartbeat: envia HEARTBEAT periodico                  |
//+------------------------------------------------------------------+
void Master_SendHeartbeat()
  {
   MasterEventHeartbeat hb;
   hb.timestamp = TimeCurrent();
   string json = Master_SerializeHeartbeat(g_master_ctx, hb);
   if(!Master_ZmqSend(json))
      Print("EPCopyFlow_Master: Falha ao enviar HEARTBEAT");
   else if(g_master_debug)
      PrintFormat("EPCopyFlow_Master: HEARTBEAT enviado ts=%d", (long)hb.timestamp);
  }

//+------------------------------------------------------------------+
//| Master_OnPositionOpened: chamado quando posicao e aberta         |
//+------------------------------------------------------------------+
void Master_OnPositionOpened(const ulong position_ticket)
  {
   if(!PositionSelectByTicket(position_ticket))
     {
      PrintFormat("EPCopyFlow_Master: PositionSelectByTicket falhou para ticket=%llu", position_ticket);
      return;
     }

   MasterEventOpen evt;
   evt.master_ticket = position_ticket;
   evt.symbol        = PositionGetString(POSITION_SYMBOL);
   evt.order_type    = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
                       ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   evt.volume        = PositionGetDouble(POSITION_VOLUME);
   evt.open_price    = PositionGetDouble(POSITION_PRICE_OPEN);
   evt.sl            = PositionGetDouble(POSITION_SL);
   evt.tp            = PositionGetDouble(POSITION_TP);
   evt.magic         = PositionGetInteger(POSITION_MAGIC);
   evt.comment       = PositionGetString(POSITION_COMMENT);
   evt.timestamp     = (datetime)PositionGetInteger(POSITION_TIME);

   string json = Master_SerializeOpen(g_master_ctx, evt);
   if(!Master_ZmqSend(json))
      PrintFormat("EPCopyFlow_Master: Falha ao enviar OPEN ticket=%llu", position_ticket);
   else if(g_master_debug)
      PrintFormat("EPCopyFlow_Master: OPEN enviado ticket=%llu sym=%s vol=%.2f",
                  position_ticket, evt.symbol, evt.volume);
  }

//+------------------------------------------------------------------+
//| Master_OnPositionModified: chamado quando SL/TP e alterado       |
//+------------------------------------------------------------------+
void Master_OnPositionModified(const ulong position_ticket)
  {
   if(!PositionSelectByTicket(position_ticket))
     {
      PrintFormat("EPCopyFlow_Master: PositionSelectByTicket falhou para ticket=%llu", position_ticket);
      return;
     }

   MasterEventModifySLTP evt;
   evt.master_ticket = position_ticket;
   evt.symbol        = PositionGetString(POSITION_SYMBOL);
   evt.sl            = PositionGetDouble(POSITION_SL);
   evt.tp            = PositionGetDouble(POSITION_TP);
   evt.timestamp     = TimeCurrent();

   string json = Master_SerializeModifySLTP(g_master_ctx, evt);
   if(!Master_ZmqSend(json))
      PrintFormat("EPCopyFlow_Master: Falha ao enviar MODIFY_SLTP ticket=%llu", position_ticket);
   else if(g_master_debug)
      PrintFormat("EPCopyFlow_Master: MODIFY_SLTP enviado ticket=%llu sl=%.5f tp=%.5f",
                  position_ticket, evt.sl, evt.tp);
  }

//+------------------------------------------------------------------+
//| Master_OnPositionClosed: chamado quando posicao e fechada        |
//| volume_closed e close_price vem do deal de saida                 |
//| reason: "MANUAL", "SL", "TP", "PARTIAL"                         |
//+------------------------------------------------------------------+
void Master_OnPositionClosed(const ulong position_ticket,
                             const double volume_closed,
                             const double close_price,
                             const string reason = "MANUAL")
  {
   //--- tenta pegar o symbol ainda da posicao aberta, senao usa o historico
   string symbol = "";
   if(PositionSelectByTicket(position_ticket))
      symbol = PositionGetString(POSITION_SYMBOL);
   else
     {
      // posicao ja fechada: busca no historico de deals
      if(HistorySelectByPosition(position_ticket))
        {
         int n = HistoryDealsTotal();
         if(n > 0)
           {
            ulong deal_ticket = HistoryDealGetTicket(0);
            symbol = HistoryDealGetString(deal_ticket, DEAL_SYMBOL);
           }
        }
     }

   MasterEventClose evt;
   evt.master_ticket = position_ticket;
   evt.symbol        = symbol;
   evt.volume_closed = volume_closed;
   evt.close_price   = close_price;
   evt.reason        = reason;
   evt.timestamp     = TimeCurrent();

   string json = Master_SerializeClose(g_master_ctx, evt);
   if(!Master_ZmqSend(json))
      PrintFormat("EPCopyFlow_Master: Falha ao enviar CLOSE ticket=%llu", position_ticket);
   else if(g_master_debug)
      PrintFormat("EPCopyFlow_Master: CLOSE enviado ticket=%llu vol=%.2f px=%.5f reason=%s",
                  position_ticket, volume_closed, close_price, reason);
  }

#endif // EPCOPYFLOW_MASTERAPI_MQH
//+------------------------------------------------------------------+
