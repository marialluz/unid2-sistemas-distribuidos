
# Sistemas Distribuídos — Algoritmos Clássicos (Q1, Q2 e Q3)

Este projeto implementa **três algoritmos fundamentais de Sistemas Distribuídos** utilizando **Python (Flask)**, **Docker** e **Kubernetes (Minikube)**, todos centralizados em um único serviço (`main.py`) executado em múltiplos pods.

## Algoritmos implementados

* **Q1** — Multicast com Ordenação Total (Relógio de Lamport)
* **Q2** — Exclusão Mútua Distribuída (Ricart–Agrawala)
* **Q3** — Eleição de Líder (Bully Algorithm)

---

## 🏗️ Arquitetura

* **Linguagem:** Python 3.9
* **Framework:** Flask (API REST)
* **Infraestrutura:** Kubernetes (Minikube)
* **Execução distribuída:** 3 pods (`coord-node-0`, `coord-node-1`, `coord-node-2`)
* **Comunicação:** HTTP entre pods via DNS estável

Cada pod conhece:

* Seu **ID de processo**
* O **total de processos**
* Os **endereços DNS dos peers**

---

## 📂 Estrutura do Projeto

```
.
├── Dockerfile
├── k8s-deployment.yaml
├── main.py
├── README.md
└── scripts/
    ├── 00_up.sh
    ├── q1_normal.sh
    ├── q1_atraso.sh
    ├── q2_normal.sh
    └── q3_eleicao.sh
```

---

## 🚀 Como Executar

### 1️⃣ Pré-requisitos

* Docker
* Minikube
* Kubectl

---

### 2️⃣ Subir o ambiente

O script abaixo **constrói a imagem, carrega no Minikube e aplica o deployment**:

```bash
./scripts/00_up.sh
```

Verifique se os pods estão rodando:

```bash
kubectl get pods
```

Esperado:

```
coord-node-0   Running
coord-node-1   Running
coord-node-2   Running
```

---

### 3️⃣ Acompanhar logs (recomendado)

Abra **3 terminais**, um para cada pod:

```bash
kubectl logs -f coord-node-0
kubectl logs -f coord-node-1
kubectl logs -f coord-node-2
```

---

# Q1 — Multicast com Ordenação Total (Lamport)

## Objetivo

Garantir que **todas as mensagens multicast sejam processadas na mesma ordem** em todos os processos, mesmo com atrasos de comunicação.

## Descrição

* Cada mensagem recebe um **timestamp de Lamport**
* Mensagens são armazenadas em uma **fila de prioridade**
* Uma mensagem só é processada quando:

  * Foi recebida por todos
  * Todos os **ACKs** foram contabilizados
* Existe um modo opcional de **atraso proposital de ACK**

---

## ▶️ Testes do Q1

### Cenário normal

```bash
./scripts/q1_normal.sh
```

**Esperado nos logs:**

```
PROCESSANDO: 'Mensagem X' [Clock: Y, PID: Z]
```

Mesma ordem em todos os pods.

---

### Cenário com atraso

```bash
./scripts/q1_atraso.sh
```

**Esperado:**

* A fila fica bloqueada
* Nenhum pod processa a mensagem
* Após o atraso, todos processam juntos

---

# Q2 — Exclusão Mútua Distribuída (Ricart–Agrawala)

## Objetivo

Garantir que **apenas um processo por vez** entre na **Seção Crítica (SC)**.

## Descrição

* Um processo envia `REQUEST` para todos os outros
* Os peers respondem com `REPLY` conforme prioridade:

  * Menor timestamp → maior prioridade
  * Empate → menor PID vence
* Ao receber todos os `REPLY`, o processo:

  * Entra na SC
  * Simula trabalho por tempo configurável
  * Sai automaticamente (`auto-leave`)
  * Envia replies deferidos

Não há liberação manual.

---

## ▶️ Teste do Q2

```bash
./scripts/q2_normal.sh
```

**Esperado nos logs:**

```
[Q2] Pedindo CS (req_ts=1)
[Q2] >>> ENTROU NA SEÇÃO CRÍTICA
[Q2] <<< SAINDO DA SEÇÃO CRÍTICA (auto)
```

Nunca existem dois pods na SC ao mesmo tempo.

---

# Q3 — Eleição de Líder (Bully Algorithm)

## Objetivo

Eleger dinamicamente um **líder**, sempre o processo com **maior ID ativo**.

## Descrição

* Um processo inicia eleição (`/q3/start`)
* Envia `ELECTION` para processos com PID maior
* Se ninguém responder, ele se torna líder
* O líder anuncia via `COORDINATOR`
* Falhas podem ser simuladas via `/q3/fail`

---

## ▶️ Teste do Q3

```bash
./scripts/q3_eleicao.sh
```

### Cenários testados automaticamente:

1. Eleição iniciada pelo p0 → p2 vira líder
2. Falha do líder p2 → nova eleição
3. p1 assume como novo líder

**Esperado nos logs:**

```
[Q3] >>> EU (p2) SOU O NOVO LÍDER <<<
[Q3] COORDINATOR recebido: líder = p2
```

---

## 🔎 Endpoints Principais

### Q1

* `POST /iniciar_msg`
* `POST /receber_msg`
* `POST /receber_ack`
* `POST /config/atraso`

### Q2

* `POST /q2/enter`
* `POST /q2/request`
* `POST /q2/reply`
* `GET  /q2/state`

### Q3

* `POST /q3/start`
* `POST /q3/election`
* `POST /q3/answer`
* `POST /q3/coordinator`
* `POST /q3/fail`
* `GET  /q3/state`

---

## ✅ Conclusão

Este projeto demonstra, de forma prática e observável via logs:

* **Consistência e ordenação total (Q1)**
* **Exclusão mútua correta sem coordenador central (Q2)**
* **Eleição dinâmica e tolerante a falhas (Q3)**

Tudo executando em **ambiente distribuído real com Kubernetes**, usando apenas **HTTP e relógios lógicos**.