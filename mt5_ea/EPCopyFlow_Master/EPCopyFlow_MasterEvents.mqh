//+------------------------------------------------------------------+
//| EPCopyFlow_MasterEvents.mqh                                      |
//| Structs de contexto e eventos do EA Master                       |
//| EPCopyFlow - EPFilho                                             |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_MASTEREVENTS_MQH
#define EPCOPYFLOW_MASTEREVENTS_MQH

//--- Contexto geral do Master (lido do config.ini)
struct MasterContext
{
   string   master_id;          // ex: "MASTER_1"
   string   protocol_version;   // ex: "1.0"
   string   zmq_address;        // ex: "tcp://127.0.0.1:5555"
};

//--- Evento OPEN: posicao aberta no Master
struct MasterEventOpen
{
   ulong            master_ticket;
   string           symbol;
   ENUM_ORDER_TYPE  order_type;   // ORDER_TYPE_BUY ou ORDER_TYPE_SELL
   double           volume;
   double           open_price;
   double           sl;
   double           tp;
   long             magic;
   string           comment;
   datetime         timestamp;
};

//--- Evento MODIFY_SLTP: SL/TP da posicao alterados
struct MasterEventModifySLTP
{
   ulong            master_ticket;
   string           symbol;
   double           open_price;    // preco de abertura da posicao (para calculo de pontos)
   ENUM_ORDER_TYPE  order_type;    // BUY ou SELL (necessario para calcular direcao dos pontos)
   double           sl;
   double           tp;
   datetime         timestamp;
};

//--- Evento CLOSE: posicao fechada (total ou parcial)
struct MasterEventClose
{
   ulong    master_ticket;
   string   symbol;
   double   volume_closed;   // volume efetivamente fechado
   double   close_price;
   string   reason;          // "MANUAL", "SL", "TP", "PARTIAL"
   datetime timestamp;
};

//--- Evento HEARTBEAT: sinal de vida do Master
struct MasterEventHeartbeat
{
   datetime timestamp;
};

#endif // EPCOPYFLOW_MASTEREVENTS_MQH
//+------------------------------------------------------------------+
