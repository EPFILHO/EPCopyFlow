# mql-zmq Library

## Sobre

Biblioteca ZMQ para MQL5 (MetaTrader 5) - Cópia dos arquivos necessários do repositório original.

**Repositório Original:** https://github.com/dingmaotu/mql-zmq  
**Licença:** Apache License 2.0  
**Copyright:** 2016-2017 Li Ding <dingmaotu@hotmail.com>  
**Localização:** `mt5_ea/mql-zmq/` (mantida junto com os EAs)

## Motivo da Cópia

Esta cópia foi criada para:
- Garantir disponibilidade contínua dos arquivos necessários ao EPCopyFlow
- Evitar dependências externas que possam ser alteradas pelo autor original
- Manter as dependências MT5 separadas do código Python

## Arquivos no Projeto

### ✅ Já Disponíveis

**Include/Zmq/**
- [x] **Zmq.mqh** - Arquivo principal (incluindo Context, Socket, ZmqMsg)

**DLLs** (em `../../dlls/`)  
- [x] **libsodium.dll** - Já presente na pasta dlls do projeto
- [x] **libzmq.dll** - Já presente na pasta dlls do projeto

### ⚠️ Arquivos Complementares (Opcional)

Os seguintes arquivos .mqh podem ser baixados caso necessário:
- [ ] AtomicCounter.mqh
- [ ] Context.mqh
- [ ] Errno.mqh
- [ ] Socket.mqh
- [ ] SocketOptions.mqh
- [ ] Z85.mqh
- [ ] ZmqMsg.mqh

Acesse: https://github.com/dingmaotu/mql-zmq/tree/master/Include/Zmq

## Uso no EPCopyFlow

O arquivo `Zmq.mqh` já inclui automaticamente os módulos principais (Context, Socket, ZmqMsg). 

### No código MQL5:

```cpp
#include <Zmq/Zmq.mqh>
```

### Exemplo de uso (EA Master):

```cpp
// Criar contexto e socket PUB
Context context;
Socket socket(context, ZMQ_PUB);
socket.bind("tcp://127.0.0.1:5555");

// Enviar mensagem JSON
string json = "{\"event\":\"OPEN\", \"symbol\":\"EURUSD\"}";
ZmqMsg msg(json);
socket.send(msg);
```

## Estrutura de Diretórios

```
EPCopyFlow/
├── mt5_ea/
│   ├── EPCopyFlow_Master/
│   │   ├── EPCopyFlow_Master.mq5
│   │   ├── EPCopyFlow_MasterZmq.mqh      // Usa Zmq.mqh
│   │   └── ...
│   └── mql-zmq/
│       ├── Include/Zmq/
│       │   └── Zmq.mqh                    // Biblioteca principal
│       └── README.md
└── dlls/
    ├── libsodium.dll                       // DLL já presente
    └── libzmq.dll                          // DLL já presente
```

## Instalação no MT5

### 1. Copiar Arquivos .mqh

Copie a pasta `Include/Zmq` para:  
`<MT5_INSTANCE>\MQL5\Include\Zmq\`

Ou crie um link simbólico da pasta mql-zmq.

### 2. DLLs (Já Incluídas)

As DLLs `libsodium.dll` e `libzmq.dll` já estão na pasta `dlls/` do projeto.  
O `broker_manager.py` as copia automaticamente para cada instância MT5.

**Destino automático:**  
`<INSTANCES_DIR>/<BROKER_KEY>/MQL5/Libraries/`

### 3. Permitir DLL no MT5

No MetaEditor:
- Propriedades do EA → **Permitir importação de DLL** ☑️

## Documentação Original

Para documentação completa, exemplos e código-fonte:

https://github.com/dingmaotu/mql-zmq

## Licença

Este código está licenciado sob a **Apache License 2.0**.  
Texto completo: http://www.apache.org/licenses/LICENSE-2.0

```
Copyright 2016-2017 Li Ding <dingmaotu@hotmail.com>

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
- **Projeto Original:** https://github.com/dingmaotu/mql-zmq

---

## Como Completar a Cópia dos Arquivos ZMQ

Alguns arquivos do mql-zmq são muito grandes para adicionar via interface web do GitHub.
Para completar a cópia, siga os passos abaixo no VSCode:

### Via Terminal no VSCode

```bash
# 1. Navegue até a pasta mt5_ea/mql-zmq
cd mt5_ea/mql-zmq

# 2. Crie um diretório temporário
mkdir temp_zmq
cd temp_zmq

# 3. Clone o repositório original
git clone https://github.com/dingmaotu/mql-zmq.git .

# 4. Copie os arquivos faltantes
cp Include/Zmq/Context.mqh ../Include/Zmq/
cp Include/Zmq/Errno.mqh ../Include/Zmq/
cp Include/Zmq/SocketOptions.mqh ../Include/Zmq/
cp Include/Zmq/ZmqMsg.mqh ../Include/Zmq/

# 5. Volte para a pasta raiz e remova o temp
cd ..
rm -rf temp_zmq

# 6. Adicione e commite os novos arquivos
git add Include/Zmq/
git commit -m "feat: add remaining zmq library files (Context, Errno, SocketOptions, ZmqMsg)"
git push
```

### Alternativa: Download Manual

Se preferir, você pode baixar os arquivos diretamente:

1. **Context.mqh**: https://raw.githubusercontent.com/dingmaotu/mql-zmq/master/Include/Zmq/Context.mqh
2. **Errno.mqh**: https://raw.githubusercontent.com/dingmaotu/mql-zmq/master/Include/Zmq/Errno.mqh  
3. **SocketOptions.mqh**: https://raw.githubusercontent.com/dingmaotu/mql-zmq/master/Include/Zmq/SocketOptions.mqh
4. **ZmqMsg.mqh**: https://raw.githubusercontent.com/dingmaotu/mql-zmq/master/Include/Zmq/ZmqMsg.mqh

Depois salve-os na pasta `mt5_ea/mql-zmq/Include/Zmq/` e faça commit via VSCode.

---

**EPCopyFlow** - Sistema de replicação de trades via ZMQ
