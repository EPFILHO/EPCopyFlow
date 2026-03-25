# EPCopyFlow Master EA

## Descrição

EA Master do sistema EPCopyFlow - detecta eventos de posição (abertura, modificação SL/TP e fechamento) e publica via ZMQ PUB para replicação automática nas contas Slaves.

## Arquitetura

### Estrutura de Arquivos

```
EPCopyFlow_Master/
├── EPCopyFlow_Master.mq5          # EA principal com eventos OnInit/OnDeinit/OnTimer/OnTradeTransaction/OnTrade
├── EPCopyFlow_MasterApi.mqh       # API pública: Master_Init(), Master_OnPositionOpened(), etc.
├── EPCopyFlow_MasterContext.mqh   # Leitura do config.ini e struct MasterContext
├── EPCopyFlow_MasterEvents.mqh    # Structs dos eventos (Open, ModifySLTP, Close, Heartbeat)
├── EPCopyFlow_MasterJson.mqh      # Serialização JSON dos eventos
└── EPCopyFlow_MasterZmq.mqh       # Wrapper ZMQ PUB (bind no endereço configurado)
```

### Protocolo de Comunicação

**Padrão ZMQ:** PUB/SUB unidirecional
- **Master:** Usa socket PUB (bind) para publicar eventos
- **Python:** Usa socket DEALER para receber eventos do Master
- **Formato:** JSON em UTF-8
- **Porta:** Lida do arquivo `config.ini` (campo `MasterPort`)

### Tipos de Eventos

#### 1. OPEN - Posição Aberta
```json
{
  "protocol_version": "1.0",
  "event_type": "OPEN",
  "master_id": "MASTER_1",
  "master_ticket": 12345,
  "symbol": "EURUSD",
  "order_type": "BUY",
  "volume": 1.0,
  "open_price": 1.12345,
  "sl": 1.12000,
  "tp": 1.13000,
  "magic": 0,
  "comment": "",
  "timestamp": 1735689600
}
```

#### 2. MODIFY_SLTP - SL/TP Modificados
```json
{
  "protocol_version": "1.0",
  "event_type": "MODIFY_SLTP",
  "master_id": "MASTER_1",
  "master_ticket": 12345,
  "symbol": "EURUSD",
  "sl": 1.12100,
  "tp": 1.13000,
  "timestamp": 1735689700
}
```

#### 3. CLOSE - Posição Fechada
```json
{
  "protocol_version": "1.0",
  "event_type": "CLOSE",
  "master_id": "MASTER_1",
  "master_ticket": 12345,
  "symbol": "EURUSD",
  "volume_closed": 1.0,
  "close_price": 1.12800,
  "reason": "MANUAL",
  "timestamp": 1735689800
}
```
**Reasons:** `MANUAL`, `SL`, `TP`, `PARTIAL`

#### 4. HEARTBEAT - Sinal de Vida
```json
{
  "protocol_version": "1.0",
  "event_type": "HEARTBEAT",
  "master_id": "MASTER_1",
  "timestamp": 1735689900
}
```

## Configuração

### Arquivo config.ini

Deve estar em: `<MT5_DATA>\MQL5\Files\config.ini`

```ini
[EPCopyFlow]
MasterID=MASTER_1
ProtocolVersion=1.0

[Ports]
MasterPort=5555
```

### Parâmetros do EA

- **InpDebugLog** (bool): Ativar logs detalhados no Experts (default: true)
- **InpHeartbeatSec** (int): Intervalo de heartbeat em segundos (default: 5)

## Instalação

1. Copie todos os arquivos `.mqh` e `.mq5` para `<MT5>\MQL5\Experts\EPCopyFlow_Master\`
2. Compile o EA `EPCopyFlow_Master.mq5` no MetaEditor
3. Crie o arquivo `config.ini` em `<MT5_DATA>\MQL5\Files\` com a configuração acima
4. Adicione o EA no gráfico do MT5

## Dependências

- **mql5-zmq library:** Biblioteca ZMQ para MQL5 (deve estar em `<MT5>\MQL5\Include\Zmq\`)
  - Disponível em: https://github.com/dingmaotu/mql-zmq

## Funcionamento

### Detecção de Eventos

1. **OnTradeTransaction:** Captura DEAL_ENTRY_IN (abertura) e DEAL_ENTRY_OUT (fechamento)
2. **OnTrade:** Monitora mudanças em SL/TP comparando estado atual vs anterior
3. **OnTimer:** Envia heartbeat periódico para o Python

### Fluxo de Publicação

```
Evento MT5 → Struct do evento → Serialização JSON → ZMQ PUB → Python Bridge
```

## API Interna (para desenvolvedores)

### Funções Principais

```cpp
// Inicialização
bool Master_Init(bool debug_log = true);
void Master_Shutdown();

// Eventos de posição
void Master_OnPositionOpened(const ulong position_ticket);
void Master_OnPositionModified(const ulong position_ticket);
void Master_OnPositionClosed(const ulong position_ticket, 
                             const double volume_closed,
                             const double close_price,
                             const string reason = "MANUAL");

// Heartbeat
void Master_SendHeartbeat();

// ZMQ (uso interno)
bool Master_ZmqConnect(const string address);
void Master_ZmqDisconnect();
bool Master_ZmqSend(const string &payload);
```

## Logs e Debug

Quando `InpDebugLog = true`, o EA registra:
- Conexão ZMQ (endereço e porta)
- Todos os eventos publicados (OPEN, MODIFY_SLTP, CLOSE, HEARTBEAT)
- Erros de serialização ou envio

Ver em: MT5 → Caixa de Ferramentas → Experts

## Tratamento de Erros

- Se `config.ini` não for encontrado: EA não inicializa (INIT_PARAMETERS_INCORRECT)
- Se porta ZMQ inválida ou ocupada: EA não inicializa (INIT_FAILED)
- Falha de envio ZMQ: registrada no log, mas EA continua operando

## Limitações Conhecidas

- Apenas posições do próprio EA são monitoradas (baseado em tickets)
- Fechamento parcial detectado como evento PARTIAL, mas não rastreia histórico completo
- Heartbeat é periódico (timer), não event-driven

## Roadmap

- [ ] Suporte para ordens pendentes (LIMIT, STOP)
- [ ] Filtro por magic number
- [ ] Filtro por símbolo
- [ ] Compressão de eventos (batch send)

## Licença

EPCopyFlow - EPFilho  
Versão 1.00
