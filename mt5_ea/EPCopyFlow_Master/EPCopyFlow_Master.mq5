//+------------------------------------------------------------------+
//| EPCopyFlow_Master.mq5                                            |
//| EA Master do EPCopyFlow                                          |
//| Detecta eventos de posicao e publica via ZMQ PUB                |
//| para replicacao nos Slaves                                       |
//| EPCopyFlow - EPFilho                                             |
//+------------------------------------------------------------------+
#property copyright "EPFilho"
#property link      "epfilho73@gmail.com"
#property version   "1.00"
#property strict

//--- Inclui toda a API do Master (inclui os sub-modulos em cascata)
#include "EPCopyFlow_MasterApi.mqh"

//--- Parametros de entrada
input bool InpDebugLog         = true;  // Ativar logs detalhados
input int  InpHeartbeatSec     = 5;     // Intervalo do heartbeat (segundos)

//+------------------------------------------------------------------+
//| Inicializacao do EA                                              |
//+------------------------------------------------------------------+
int OnInit()
  {
   Print("EPCopyFlow_Master: Inicializando...");

   if(!Master_Init(InpDebugLog))
      return(INIT_PARAMETERS_INCORRECT);

   //--- timer para heartbeat
   if(!EventSetTimer(InpHeartbeatSec))
     {
      Print("EPCopyFlow_Master: Falha ao criar timer, erro=", GetLastError());
      return(INIT_FAILED);
     }

   Print("EPCopyFlow_Master: Pronto.");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| Finalizacao do EA                                                |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   EventKillTimer();
   Master_Shutdown();
   PrintFormat("EPCopyFlow_Master: Finalizado. Razao=%d", reason);
  }

//+------------------------------------------------------------------+
//| Timer: envia heartbeat periodico                                 |
//+------------------------------------------------------------------+
void OnTimer()
  {
   Master_SendHeartbeat();
  }

//+------------------------------------------------------------------+
//| Evento de transacao de trade                                     |
//| Aqui identificamos OPEN / MODIFY_SLTP / CLOSE                   |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest      &request,
                        const MqlTradeResult       &result)
  {
   //--- So processa deals (execucoes reais)
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD)
      return;

   ulong deal_ticket = trans.deal;
   if(deal_ticket == 0)
      return;

   //--- Seleciona o deal no historico
   if(!HistoryDealSelect(deal_ticket))
      return;

   ENUM_DEAL_TYPE  deal_type  = (ENUM_DEAL_TYPE)HistoryDealGetInteger(deal_ticket, DEAL_TYPE);
   ENUM_DEAL_ENTRY deal_entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);

   //--- Ignora deals que nao sao BUY/SELL (ex: balance, credit)
   if(deal_type != DEAL_TYPE_BUY && deal_type != DEAL_TYPE_SELL)
      return;

   ulong  position_ticket = trans.position;
   double deal_volume     = HistoryDealGetDouble(deal_ticket, DEAL_VOLUME);
   double deal_price      = HistoryDealGetDouble(deal_ticket, DEAL_PRICE);

   if(InpDebugLog)
      PrintFormat("EPCopyFlow_Master OnTradeTransaction: deal=%llu pos=%llu entry=%s vol=%.2f px=%.5f",
                  deal_ticket, position_ticket,
                  EnumToString(deal_entry), deal_volume, deal_price);

   //---
   //--- DEAL_ENTRY_IN: posicao aberta (nova ou adicional)
   //---
   if(deal_entry == DEAL_ENTRY_IN)
     {
      //--- Pequena espera para o MT5 consolidar a posicao
      Sleep(50);
      Master_OnPositionOpened(position_ticket);
      return;
     }

   //---
   //--- DEAL_ENTRY_OUT ou DEAL_ENTRY_OUT_BY: fechamento (total ou parcial)
   //---
   if(deal_entry == DEAL_ENTRY_OUT || deal_entry == DEAL_ENTRY_OUT_BY)
     {
      //--- Detecta reason do fechamento
      string reason = "MANUAL";
      long   deal_reason = HistoryDealGetInteger(deal_ticket, DEAL_REASON);
      if(deal_reason == DEAL_REASON_SL)       reason = "SL";
      else if(deal_reason == DEAL_REASON_TP)  reason = "TP";

      //--- Verifica se eh parcial (posicao ainda existe)
      if(PositionSelectByTicket(position_ticket))
         reason = "PARTIAL";

      Master_OnPositionClosed(position_ticket, deal_volume, deal_price, reason);
      return;
     }
  }

//+------------------------------------------------------------------+
//| Evento de mudanca de trade (captura modificacoes de SL/TP)       |
//+------------------------------------------------------------------+
void OnTrade()
  {
   //--- Varre todas as posicoes abertas e verifica se SL/TP mudou
   //--- Estrategia simples: comparamos o estado atual com o ultimo conhecido
   //--- usando um array estatico de tickets e SL/TP anteriores
   static ulong  s_tickets[];
   static double s_sl[];
   static double s_tp[];

   int total = PositionsTotal();

   //--- Redimensiona se necessario
   if(ArraySize(s_tickets) != total)
     {
      ArrayResize(s_tickets, total);
      ArrayResize(s_sl, total);
      ArrayResize(s_tp, total);

      //--- Inicializa com valores atuais (sem disparar evento na primeira passagem)
      for(int i = 0; i < total; i++)
        {
         ulong t = PositionGetTicket(i);
         if(PositionSelectByTicket(t))
           {
            s_tickets[i] = t;
            s_sl[i]      = PositionGetDouble(POSITION_SL);
            s_tp[i]      = PositionGetDouble(POSITION_TP);
           }
        }
      return;
     }

   //--- Compara SL/TP atual com o salvo
   for(int i = 0; i < total; i++)
     {
      ulong t = PositionGetTicket(i);
      if(!PositionSelectByTicket(t)) continue;

      double cur_sl = PositionGetDouble(POSITION_SL);
      double cur_tp = PositionGetDouble(POSITION_TP);

      //--- Verifica se eh o mesmo ticket na posicao i
      bool found = false;
      for(int j = 0; j < ArraySize(s_tickets); j++)
        {
         if(s_tickets[j] == t)
           {
            found = true;
            if(MathAbs(cur_sl - s_sl[j]) > 0.000001 ||
               MathAbs(cur_tp - s_tp[j]) > 0.000001)
              {
               //--- SL ou TP mudou -> envia MODIFY_SLTP
               Master_OnPositionModified(t);
               s_sl[j] = cur_sl;
               s_tp[j] = cur_tp;
              }
            break;
           }
        }

      if(!found)
        {
         //--- Novo ticket no array -> adiciona sem disparar evento
         ArrayResize(s_tickets, ArraySize(s_tickets) + 1);
         ArrayResize(s_sl,      ArraySize(s_sl)      + 1);
         ArrayResize(s_tp,      ArraySize(s_tp)      + 1);
         int last = ArraySize(s_tickets) - 1;
         s_tickets[last] = t;
         s_sl[last]      = cur_sl;
         s_tp[last]      = cur_tp;
        }
     }
  }
//+------------------------------------------------------------------+
