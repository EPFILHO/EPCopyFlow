# EPCopyFlow Slave EA

## Descrição
EA Slave do sistema EPCopyFlow - recebe comandos de replicação via ZMQ do Python
middleware, executa as ordens proporcionalmente e envia heartbeat com estado das
posições abertas para reconciliação automática.

## Arquitetura

### Estrutura de Arquivos
EPCopyFlow_Slave/
├── EPCopyFlow_Slave.mq5 # EA principal: OnInit/OnDeinit/OnTimer/OnTradeTransaction/OnTrade
├── EPCopyFlow_SlaveApi.mqh # API pública: execução de ordens + heartbeat
├── EPCopyFlow_SlaveContext.mqh # Leitura do config.ini e struct SlaveContext
├── EPCopyFlow_SlaveEvents.mqh # Structs dos comandos recebidos e heartbeat
├── EPCopyFlow_SlaveJson.mqh # Deserialização JSON dos comandos + serialização heartbeat
└── EPCopyFlow_SlaveZmq.mqh # Wrapper ZMQ SUB (recebe) + PUB (envia heartbeat)

text

### Protocolo de Comunicação
**Padrão ZMQ:** SUB/PUB bidirecional
- **Python:** Faz `bind` em ambas as portas (TradePort e HeartbeatPort)
- **Slave:** Faz `connect` como SUB no TradePort e PUB no HeartbeatPort
- **Formato:** JSON em UTF-8
- **Portas:** Lidas do arquivo `epcopyflow.cfg`

### Comandos Recebidos do Python

#### 1. OPEN — Abrir posição
```json
{
  "protocol_version": "1.0",
  "event_type": "OPEN",
  "slave_id": "SLAVE_ABC",
  "master_id": "MASTER_1",
  "master_ticket": 123456789,
  "symbol": "XAUUSD",
  "order_type": "BUY",
  "volume": 0.02,
  "price": 0.0,
  "sl": 1900.00,
  "tp": 1950.00,
  "comment": "EPSlave|MT#123456789"
}
2. CLOSE — Fechar posição
json
{
  "protocol_version": "1.0",
  "event_type": "CLOSE",
  "slave_id": "SLAVE_ABC",
  "master_id": "MASTER_1",
  "master_ticket": 123456789,
  "symbol": "XAUUSD"
}
3. PARTIAL_CLOSE — Fechamento parcial
json
{
  "protocol_version": "1.0",
  "event_type": "PARTIAL_CLOSE",
  "slave_id": "SLAVE_ABC",
  "master_id": "MASTER_1",
  "master_ticket": 123456789,
  "symbol": "XAUUSD",
  "close_volume": 0.01
}
4. MODIFY_SLTP — Modificar SL/TP
json
{
  "protocol_version": "1.0",
  "event_type": "MODIFY_SLTP",
  "slave_id": "SLAVE_ABC",
  "master_id": "MASTER_1",
  "master_ticket": 123456789,
  "symbol": "XAUUSD",
  "sl": 1910.00,
  "tp": 1950.00
}
Heartbeat Enviado ao Python
json
{
  "protocol_version": "1.0",
  "event_type": "HEARTBEAT",
  "slave_id": "SLAVE_ABC",
  "master_id": "MASTER_1",
  "timestamp": 1735689900,
  "positions_count": 2,
  "positions": [
    {
      "ticket": 987654321,
      "symbol": "XAUUSD",
      "type": 0,
      "volume": 0.02,
      "open_price": 1920.50,
      "sl": 1900.00,
      "tp": 1950.00,
      "profit": 12.40,
      "master_ticket": 123456789,
      "comment": "EPSlave|MT#123456789"
    }
  ]
}
Configuração
Arquivo epcopyflow.cfg
Deve estar em: \MQL5\Files\epcopyflow.cfg

text
SlaveId=SLAVE_ABC
MasterId=MASTER_1
TradePort=5556
HeartbeatPort=5557
ProtocolVersion=1.0
Parâmetros do EA
InpHeartbeatSec (int): Intervalo do heartbeat em segundos (default: 5)

Instalação
Copie todos os arquivos .mqh e .mq5 para \MQL5\Experts\EPCopyFlow_Slave\

Compile o EA EPCopyFlow_Slave.mq5 no MetaEditor

Crie o arquivo epcopyflow.cfg em \MQL5\Files\ com a configuração acima

Adicione o EA no gráfico do MT5

Dependências
mql5-zmq library: Biblioteca ZMQ para MQL5 (deve estar em \MQL5\Include\Zmq\)

Disponível em: https://github.com/dingmaotu/mql-zmq

Funcionamento
Rastreamento de Posições
O Slave grava o master_ticket no comment de cada posição aberta no formato:

text
EPSlave|MT#123456789
Isso permite localizar a posição correta ao receber comandos de CLOSE,
PARTIAL_CLOSE ou MODIFY_SLTP sem depender de magic number.

Fluxo de Execução
text
Python PUB → ZMQ SUB → Json_ParseXxx() → Api_ExecuteXxx() → CTrade → MT5
Fluxo de Heartbeat
text
OnTimer / OnTradeTransaction / OnTrade → Api_SendHeartbeat() → Json_BuildHeartbeat() → ZMQ PUB → Python
Tratamento de Erros
Se epcopyflow.cfg não for encontrado: EA não inicializa (INIT_FAILED)

Campos obrigatórios ausentes no config: EA não inicializa com log descritivo

Posição não encontrada pelo master_ticket: operação ignorada com log de WARN

Falha de execução de trade: retcode e descrição registrados no log

Limitações Conhecidas
Volume recebido do Python já deve estar normalizado para o broker

Não executa ordens pendentes (LIMIT/STOP) — apenas ordens a mercado

master_ticket é extraído do comment — não altere o comment manualmente

Roadmap
 Filtro por magic number

 Suporte a ordens pendentes

 Confirmação de execução enviada de volta ao Python

 Painel visual no gráfico com status da conexão

Licença
EPCopyFlow - EPFilho
Versão 1.00
