# mql-zmq Library

## Sobre

Biblioteca ZMQ para MQL5 (MetaTrader 5) - Cópia dos arquivos necessários do repositório original.

**Repositório Original:** https://github.com/dingmaotu/mql-zmq  
**Licença:** Apache License 2.0  
**Copyright:** 2016-2017 Li Ding <dingmaotu@hotmail.com>

## Motivo da Cópia

Esta cópia foi criada para garantir a disponibilidade contínua dos arquivos necessários ao projeto EPCopyFlow, evitando dependências externas que possam ser alteradas ou removidas pelo autor original.

## Arquivos Incluídos

### Include/Zmq/ (Arquivos .mqh)

Os seguintes arquivos estão disponíveis em `Include/Zmq/`:

- [x] **Zmq.mqh** - Arquivo principal já copiado
- [ ] **AtomicCounter.mqh**
- [ ] **Context.mqh**
- [ ] **Errno.mqh**
- [ ] **Socket.mqh**
- [ ] **SocketOptions.mqh**
- [ ] **Z85.mqh**
- [ ] **ZmqMsg.mqh**

### Library/MT5/ (DLLs)

DLLs necessárias para MT5 (64-bit):

- [ ] **libsodium.dll**
- [ ] **libzmq.dll**

## Instalação Manual

Para instalar os arquivos restantes manualmente:

### 1. Baixar Arquivos .mqh

Acesse o repositório original e baixe os arquivos da pasta `Include/Zmq/`:

https://github.com/dingmaotu/mql-zmq/tree/master/Include/Zmq

Copie os arquivos para: `<MT5>\MQL5\Include\Zmq\`

### 2. Baixar DLLs

Acesse a pasta de DLLs para MT5:

https://github.com/dingmaotu/mql-zmq/tree/master/Library/MT5

Baixe:
- `libsodium.dll`
- `libzmq.dll`

Copie para: `<MT5>\MQL5\Libraries\`

## Uso no EPCopyFlow

No código MQL5, inclua a biblioteca:

```cpp
#include <Zmq/Zmq.mqh>
```

Exemplo de uso:

```cpp
Context context;
Socket socket(context, ZMQ_PUB);
socket.bind("tcp://127.0.0.1:5555");

string message = "{\"event\":\"HEARTBEAT\"}";
ZmqMsg msg(message);
socket.send(msg);
```

## Documentação Original

Para documentação completa e exemplos, consulte o repositório original:

https://github.com/dingmaotu/mql-zmq

## Licença

Este código está licenciado sob a Apache License 2.0, conforme o repositório original.

Texto completo da licença: http://www.apache.org/licenses/LICENSE-2.0

```
Copyright 2016-2017 Li Ding

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

## Créditos

Todos os créditos ao autor original:
- **Autor:** Li Ding (dingmaotu)
- **Email:** dingmaotu@hotmail.com
- **GitHub:** https://github.com/dingmaotu/mql-zmq
