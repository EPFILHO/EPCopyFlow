//+------------------------------------------------------------------+
//|                                     EPCopyFlow_SlaveEvents.mqh  |
//|                                         EP Filho © 2026         |
//|                          https://github.com/EPFILHO/EPCopyFlow  |
//+------------------------------------------------------------------+
#ifndef EPCOPYFLOW_SLAVE_EVENTS_MQH
#define EPCOPYFLOW_SLAVE_EVENTS_MQH

//+------------------------------------------------------------------+
//| Tipos de comando recebidos do Python                             |
//+------------------------------------------------------------------+
enum ENUM_SLAVE_CMD
  {
   SLAVE_CMD_UNKNOWN       = 0,
   SLAVE_CMD_OPEN          = 1,
   SLAVE_CMD_CLOSE         = 2,
   SLAVE_CMD_PARTIAL_CLOSE = 3,
   SLAVE_CMD_MODIFY_SLTP   = 4,
   SLAVE_CMD_HEARTBEAT     = 5,
  };

//+------------------------------------------------------------------+
//| Comando OPEN                                                     |
//+------------------------------------------------------------------+
struct SlaveOpenCmd
  {
   string            slave_id;
   string            master_id;
   long              master_ticket;
   string            symbol;
   ENUM_ORDER_TYPE   order_type;
   double            volume;
   double            price;
   double            sl;
   double            tp;
   string            comment;
   string            protocol_version;
  };

//+------------------------------------------------------------------+
//| Comando CLOSE                                                     |
//+------------------------------------------------------------------+
struct SlaveCloseCmd
  {
   string            slave_id;
   string            master_id;
   long              master_ticket;
   string            symbol;
   string            protocol_version;
  };

//+------------------------------------------------------------------+
//| Comando PARTIAL_CLOSE                                            |
//+------------------------------------------------------------------+
struct SlavePartialCloseCmd
  {
   string            slave_id;
   string            master_id;
   long              master_ticket;
   string            symbol;
   double            close_volume;
   string            protocol_version;
  };

//+------------------------------------------------------------------+
//| Comando MODIFY_SLTP                                              |
//+------------------------------------------------------------------+
struct SlaveModifyCmd
  {
   string            slave_id;
   string            master_id;
   long              master_ticket;
   string            symbol;
   double            sl;
   double            tp;
   string            protocol_version;
  };

//+------------------------------------------------------------------+
//| Posição aberta — usada no heartbeat                              |
//+------------------------------------------------------------------+
struct SlavePosition
  {
   long              ticket;
   string            symbol;
   ENUM_POSITION_TYPE type;
   double            volume;
   double            open_price;
   double            sl;
   double            tp;
   double            profit;
   long              master_ticket;
   string            comment;
  };

//+------------------------------------------------------------------+
//| Heartbeat enviado ao Python                                      |
//+------------------------------------------------------------------+
struct SlaveHeartbeat
  {
   string            protocol_version;
   string            event_type;
   string            slave_id;
   string            master_id;
   datetime          timestamp;
   int               positions_count;
   SlavePosition     positions[];
  };

#endif // EPCOPYFLOW_SLAVE_EVENTS_MQH
