//+------------------------------------------------------------------+
//| EPCopyFlow_MasterZmq.mqh                                         |
//| Wrapper ZMQ PUB unidirecional para o EA Master                   |
//| Reutiliza padrao da lib Zmq/Zmq.mqh (mql5-zmq)                  |
//| EPCopyFlow - EPFilho                                             |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_MASTERZMQ_MQH
#define EPCOPYFLOW_MASTERZMQ_MQH

#include <Zmq/Zmq.mqh>

//--- Variaveis de estado do socket ZMQ do Master
Context  g_zmq_ctx;
Socket   g_zmq_pub(g_zmq_ctx, ZMQ_PUB);  // PUB: envia eventos para Slaves
bool     g_zmq_connected = false;
string   g_zmq_bound_addr = "";

//+------------------------------------------------------------------+
//| Conecta o socket PUB ao endereco (bind)                          |
//| address: ex "tcp://127.0.0.1:5555" ou "tcp://*:5555"            |
//+------------------------------------------------------------------+
bool Master_ZmqConnect(const string address)
  {
   if(g_zmq_connected)
     {
      Print("EPCopyFlow_Master ZMQ: ja conectado em ", g_zmq_bound_addr);
      return true;
     }

   // Para PUB no Master fazemos bind (o Master eh o publisher)
   // Se o address vier com IP especifico (127.0.0.1) convertemos para wildcard
   // para bindar corretamente; mantenha como veio do config.
   if(!g_zmq_pub.bind(address))
     {
      PrintFormat("EPCopyFlow_Master ZMQ: Falha ao bind em %s, erro=%d",
                  address, GetLastError());
      return false;
     }

   g_zmq_connected  = true;
   g_zmq_bound_addr = address;
   PrintFormat("EPCopyFlow_Master ZMQ: PUB socket bind OK em %s", address);
   return true;
  }

//+------------------------------------------------------------------+
//| Desconecta o socket PUB                                          |
//+------------------------------------------------------------------+
void Master_ZmqDisconnect()
  {
   if(!g_zmq_connected) return;
   g_zmq_pub.unbind(g_zmq_bound_addr);
   g_zmq_connected  = false;
   g_zmq_bound_addr = "";
   Print("EPCopyFlow_Master ZMQ: desconectado");
  }

//+------------------------------------------------------------------+
//| Envia payload JSON pelo socket PUB                               |
//+------------------------------------------------------------------+
bool Master_ZmqSend(const string &payload)
  {
   if(!g_zmq_connected)
     {
      Print("EPCopyFlow_Master ZMQ: tentativa de envio sem conexao");
      return false;
     }

   ZmqMsg msg(payload);
   if(!g_zmq_pub.send(msg))
     {
      PrintFormat("EPCopyFlow_Master ZMQ: falha ao enviar msg, erro=%d", GetLastError());
      return false;
     }
   return true;
  }

#endif // EPCOPYFLOW_MASTERZMQ_MQH
//+------------------------------------------------------------------+
