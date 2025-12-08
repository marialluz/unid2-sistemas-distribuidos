
# Q1: Multicast com Ordenação Total (Relógio de Lamport)

Implementação de um sistema distribuído utilizando **Kubernetes** e **Python** para demonstrar o algoritmo de Multicast com Ordenação Total baseada em Relógios Lógicos de Lamport.

## 📋 Requisitos do Projeto
- **API Rest** para comunicação entre processos.
- **Relógio Lógico de Lamport** para timestamp das mensagens.
- **Fila de Prioridade** para ordenação das mensagens.
- **Controle de ACKs**: A mensagem só é processada quando confirmada por todos os nós.
- **Simulação de Atraso**: Capacidade de atrasar propositalmente um ACK para demonstrar o bloqueio da fila e a garantia da ordem total.

---
## 🚀 Como Executar

### 1. Pré-requisitos
Certifique-se de ter instalado:
- Minikube
- Docker
- Kubectl

### 2. Inicialização do Ambiente
Inicie o Minikube (caso não esteja rodando):
```bash
minikube start --driver=docker
```

### 3\. Build e Deploy

Como estamos usando o Minikube, é necessário construir a imagem docker dentro do ambiente do cluster:

```bash
# 1. Construir a imagem localmente (Tag v3)
docker build -t multicast-img:v3 .

# 2. Carregar a imagem para o Minikube
minikube image load multicast-img:v3

# 3. Aplicar os manifestos Kubernetes (Service + StatefulSet)
kubectl apply -f k8s-deployment.yaml
```

Verifique se os 3 pods estão rodando:

```bash
kubectl get pods -o wide
```

*(Aguarde até que o status de todos seja `Running`)*

-----

## 🧪 Como Testar

Para visualizar o funcionamento do algoritmo, abra 3 terminais separados para monitorar os logs de cada processo:

  * **Terminal 1:** `kubectl logs -f multicast-app-0`
  * **Terminal 2:** `kubectl logs -f multicast-app-1`
  * **Terminal 3:** `kubectl logs -f multicast-app-2`

### Cenário 1: Envio Normal (Sincronia)

Envie uma mensagem a partir do Pod 0. Todos os nós devem receber, trocar ACKs e processar a mensagem quase simultaneamente.

**Comando:**

```bash
kubectl exec multicast-app-0 -- curl -X POST http://localhost:5000/iniciar_msg \
-H "Content-Type: application/json" \
-d '{"msg": "Ola Mundo Distribuido"}'
```

**Resultado esperado nos logs:**
Todos os pods imprimem: `✅ PROCESSANDO: 'Ola Mundo Distribuido' ...`

### Cenário 2: Simulação de Atraso (Prova da Ordenação Total)

Este teste demonstra que se um nó demorar a responder (atraso no ACK), **nenhum** outro nó processa a mensagem até que a confirmação chegue, garantindo a consistência do sistema distribuído.

**Passo 1: Ative o modo de atraso no Pod 1**

```bash
kubectl exec multicast-app-1 -- curl -X POST http://localhost:5000/config/atraso
```

**Passo 2: Envie uma mensagem que ativa o gatilho de atraso**

```bash
kubectl exec multicast-app-0 -- curl -X POST http://localhost:5000/iniciar_msg \
-H "Content-Type: application/json" \
-d '{"msg": "Esta mensagem vai ATRASAR"}'
```

**Resultado esperado:**

1.  Todos os logs mostram o recebimento da mensagem.
2.  **PAUSA DE 10 SEGUNDOS**: Ninguém imprime "PROCESSANDO". A fila fica bloqueada aguardando o Pod 1.
3.  Após 10s, o Pod 1 envia o ACK e **todos** processam a mensagem simultaneamente.

-----

## 🛠️ Detalhes Técnicos da Implementação

  * **Linguagem:** Python 3.9
  * **Comunicação:** API Rest (Flask) rodando na porta 5000.
  * **Infraestrutura:** Kubernetes StatefulSet.
      * Garante nomes de rede estáveis: `multicast-app-0`, `multicast-app-1`, `multicast-app-2`.
  * **Service Discovery:** Headless Service (`clusterIP: None`) permite que os pods resolvam os IPs uns dos outros diretamente pelo DNS.

### Estrutura da Mensagem (JSON)

```json
{
  "uuid": "0-15",       // ID único (ID Processo - Timestamp)
  "pid": 0,             // ID do processo remetente
  "clock": 15,          // Relógio Lógico de Lamport no momento do envio
  "msg": "Conteúdo",
  "acks": 0             // Contador interno de confirmações recebidas
}
```