//+------------------------------------------------------------------+
//| EPCopyFlow_SlaveEvents.mqh                                       |
//| Structs de comandos recebidos pelo EA Slave.                     |
//| EPCopyFlow - EPFilho                                             |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_SLAVEEVENTS_MQH
#define EPCOPYFLOW_SLAVEEVENTS_MQH

//--- Mapeamento de tickets: master_ticket -> slave_ticket
struct SlaveTicketMap
{
   ulong    master_ticket;
   ulong    slave_ticket;
};

//--- Comando OPEN: abrir posicao no Slave
struct SlaveOpenCmd
{
   ulong            master_ticket;
   string           symbol;
   ENUM_ORDER_TYPE  order_type;    // ORDER_TYPE_BUY ou ORDER_TYPE_SELL
   double           volume;
   double           price;         // preco sugerido (0 = mercado)
   long             sl_points;     // distancia do SL em pontos a partir do preco de abertura
   long             tp_points;     // distancia do TP em pontos a partir do preco de abertura
   long             magic;
   string           comment;
   datetime         timestamp;
};

//--- Comando MODIFY_SLTP: modificar SL/TP no Slave
struct SlaveModifyCmd
{
   ulong    master_ticket;
   string   symbol;
   long     sl_points;     // novo SL em pontos a partir do open_price da posicao
   long     tp_points;     // novo TP em pontos a partir do open_price da posicao
   datetime timestamp;
};

//--- Comando CLOSE: fechar posicao no Slave
struct SlaveCloseCmd
{
   ulong    master_ticket;
   string   symbol;
   double   volume_pct;    // percentual do volume a fechar (1.0 = total)
   string   reason;        // "MANUAL", "SL", "TP", "PARTIAL"
   datetime timestamp;
};

//--- Comando HEARTBEAT: verificar conexao
struct SlaveHeartbeatCmd
{
   datetime timestamp;
};

#endif // EPCOPYFLOW_SLAVEEVENTS_MQH
//+------------------------------------------------------------------+
