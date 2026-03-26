//+------------------------------------------------------------------+
//|                                      EPCopyFlow_MasterZmq.mqh   |
//|                 Wrapper ZMQ PUSH unidirecional para o EA Master  |
//|         Reutiliza padrao da lib Zmq/Zmq.mqh (mql5-zmq)          |
//|                                       EPCopyFlow - EPFilho       |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_MASTERZMQ_MQH
#define EPCOPYFLOW_MASTERZMQ_MQH

#include <Zmq/Zmq.mqh>

//--- Variaveis de estado do socket ZMQ do Master
Context g_zmq_ctx;
Socket  g_zmq_push(g_zmq_ctx, ZMQ_PUSH); // PUSH: envia eventos para o Python
bool    g_zmq_connected  = false;
string  g_zmq_bound_addr = "";

//+------------------------------------------------------------------+
//| Conecta o socket PUSH ao endereco do Python (connect)            |
//| address: ex "tcp://127.0.0.1:15560"                              |
//+------------------------------------------------------------------+
bool Master_ZmqConnect(const string address)
  {
   if(g_zmq_connected)
     {
      Print("EPCopyFlow_Master ZMQ: ja conectado em ", g_zmq_bound_addr);
      return true;
     }

   // PUSH faz connect() — o Python (PULL) faz bind() e fica sempre de pe
   if(!g_zmq_push.connect(address))
     {
      PrintFormat("EPCopyFlow_Master ZMQ: Falha ao connect em %s, erro=%d",
                  address, GetLastError());
      return false;
     }

   g_zmq_connected  = true;
   g_zmq_bound_addr = address;
   PrintFormat("EPCopyFlow_Master ZMQ: PUSH socket connect OK em %s", address);
   return true;
  }

//+------------------------------------------------------------------+
//| Desconecta o socket PUSH                                         |
//+------------------------------------------------------------------+
void Master_ZmqDisconnect()
  {
   if(!g_zmq_connected) return;
   g_zmq_push.disconnect(g_zmq_bound_addr);
   g_zmq_connected  = false;
   g_zmq_bound_addr = "";
   Print("EPCopyFlow_Master ZMQ: desconectado");
  }

//+------------------------------------------------------------------+
//| Envia payload JSON pelo socket PUSH                              |
//+------------------------------------------------------------------+
bool Master_ZmqSend(const string &payload)
  {
   if(!g_zmq_connected)
     {
      Print("EPCopyFlow_Master ZMQ: tentativa de envio sem conexao");
      return false;
     }
   ZmqMsg msg(payload);
   if(!g_zmq_push.send(msg))
     {
      PrintFormat("EPCopyFlow_Master ZMQ: falha ao enviar msg, erro=%d", GetLastError());
      return false;
     }
   return true;
  }

#endif // EPCOPYFLOW_MASTERZMQ_MQH
//+------------------------------------------------------------------+
