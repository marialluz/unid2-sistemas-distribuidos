import os
import time
import threading
import requests
import socket
import json
from flask import Flask, request, jsonify
from functools import cmp_to_key

app = Flask(__name__)

# --- CONFIGURAÇÕES ---
# Pega o nome do pod (ex: multicast-app-0)
HOSTNAME = socket.gethostname()
# Extrai o ID do final do nome (0, 1 ou 2)
MY_ID = int(HOSTNAME.split('-')[-1]) if '-' in HOSTNAME else 0

# Lista de todos os peers no cluster (nomes DNS estáveis do StatefulSet)
APP_NAME = os.getenv("APP_NAME", "dist-app")
SERVICE_NAME = os.getenv("SERVICE_NAME", "dist-service")
TOTAL_PROCESSOS = int(os.getenv("TOTAL_PROCESSOS", "3"))

PEERS = [f"{APP_NAME}-{i}.{SERVICE_NAME}" for i in range(TOTAL_PROCESSOS)]


# --- ESTADO GLOBAL (Lamport) ---
relogio_logico = 0
fila_prioridade = [] # Lista de dicionários: [{'clock': 1, 'pid': 0, 'msg': '...', 'acks': 0}]
lock_clock = threading.Lock()
lock_q1 = threading.Lock()
lock_q2 = threading.Lock()


# Simulação de atraso
ATRASO_ACK = False

# --- FUNÇÕES AUXILIARES ---

def incrementar_relogio():
    global relogio_logico
    with lock_clock:
        relogio_logico += 1
    return relogio_logico

def atualizar_relogio(timestamp_recebido):
    global relogio_logico
    with lock_clock:
        relogio_logico = max(relogio_logico, timestamp_recebido) + 1
    return relogio_logico

# Critério de ordenação: (Timestamp, ID do Processo)
def comparar_mensagens(msg1, msg2):
    if msg1['clock'] < msg2['clock']: return -1
    if msg1['clock'] > msg2['clock']: return 1
    # Desempate pelo ID do processo
    if msg1['pid'] < msg2['pid']: return -1
    return 1

# Thread que monitora a fila para processar mensagens
def processador_de_mensagens():
    while True:
        with lock_q1:
            if fila_prioridade:
                print(f"🔄 Fila de prioridade: {fila_prioridade}") 
                # Ordena a fila (Ordenação Total)
                fila_prioridade.sort(key=cmp_to_key(comparar_mensagens))

                msg_topo = fila_prioridade[0]
                
                print(f"🔄 Verificando se a mensagem {msg_topo['uuid']} pode ser processada...")
                
                if msg_topo['acks'] >= TOTAL_PROCESSOS:
                    # Processa a mensagem
                    print(f"✅ PROCESSANDO: '{msg_topo['msg']}' [Clock: {msg_topo['clock']}, PID: {msg_topo['pid']}]")
                    fila_prioridade.pop(0)
                else:
                    print(f"🔴 Esperando mais ACKs para {msg_topo['uuid']} - ACKs necessários: {TOTAL_PROCESSOS - msg_topo['acks']}")
        time.sleep(0.5)

threading.Thread(target=processador_de_mensagens, daemon=True).start()

# --- ENDPOINTS (API) ---

@app.route('/iniciar_msg', methods=['POST'])
def iniciar_envio():
    """Endpoint que o USUÁRIO chama para disparar uma mensagem"""
    data = request.json
    msg_conteudo = data.get('msg', 'Olá')
    
    # 1. Incrementa relógio local
    ts = incrementar_relogio()
    
    msg_struct = {
        'uuid': f"{MY_ID}-{ts}", # Identificador único da msg
        'pid': MY_ID,
        'clock': ts,
        'msg': msg_conteudo
    }

    # 2. Multicast para TODOS (incluindo a si mesmo)
    print(f"📢 Enviando Multicast: {msg_conteudo} (TS: {ts})")
    
    def broadcast():
        for peer in PEERS:
            try:
                # Tenta conectar no DNS do pod
                url = f"http://{peer}:5000/receber_msg"
                requests.post(url, json=msg_struct, timeout=5)
            except Exception as e:
                print(f"Erro ao contatar {peer}: {e}")

    threading.Thread(target=broadcast).start()
    return jsonify({"status": "Multicast iniciado", "msg": msg_struct})

@app.route('/receber_msg', methods=['POST'])
def receber_msg():
    """Recebe mensagem de um par"""
    data = request.json
    atualizar_relogio(data['clock'])
    
    item = data.copy()
    item['acks'] = 1
    with lock_q1:
        if not any(m['uuid'] == data['uuid'] for m in fila_prioridade):
            fila_prioridade.append(item)
    
    def enviar_acks():
        if ATRASO_ACK and "ATRASAR" in data['msg']:
            print(f"😴 [Simulação] Atrasando ACK por 10s...")
            time.sleep(10)

        ack = {'uuid': data['uuid'], 'from_pid': MY_ID}
        for peer in PEERS:
            try:
                requests.post(f"http://{peer}:5000/receber_ack", json=ack, timeout=5)
            except: pass
            
    threading.Thread(target=enviar_acks).start()
    
    return jsonify({"status": "Recebido"})

@app.route('/receber_ack', methods=['POST'])
def receber_ack():
    data = request.json
    uuid_alvo = data['uuid']
    
    with lock_q1:
        for msg in fila_prioridade:
            if msg['uuid'] == uuid_alvo:
                msg['acks'] += 1
                print(f"✅ ACK recebido de {data['from_pid']} para msg {uuid_alvo}. Total: {msg['acks']}")

                # Checar se já podemos processar a mensagem
                if msg['acks'] >= TOTAL_PROCESSOS:
                    print(f"🔄 Mensagem {uuid_alvo} pronta para processamento (ACKs suficientes).")
                break
                
    return jsonify({"status": "ACK contabilizado"})

@app.route('/config/atraso', methods=['POST'])
def config_atraso():
    """Endpoint para ligar/desligar o modo de atraso (Requisito da tarefa)"""
    global ATRASO_ACK
    ATRASO_ACK = not ATRASO_ACK
    return jsonify({"status": f"Modo Atraso: {ATRASO_ACK}"})

# =========================
# Q2: Exclusão Mútua Distribuída — Ricart–Agrawala
# =========================

# Estado do mutex
q2_requesting = False
q2_in_cs = False
q2_req_ts = None

q2_awaiting_replies = set()   # pids de quem ainda falta REPLY
q2_deferred = set()           
q2_enter_thread = None
Q2_CS_DURATION_SEC = float(os.getenv("Q2_CS_DURATION_SEC", "2"))

Q2_DELAY_REPLY_MS = int(os.getenv("Q2_DELAY_REPLY_MS", "0"))
Q2_DELAY_REPLY_FROM_PID = int(os.getenv("Q2_DELAY_REPLY_FROM_PID", "-1"))


def q2_has_priority_over(other_ts, other_pid):
    """Meu REQUEST tem prioridade se (ts menor) ou (ts igual e pid menor)."""
    global q2_req_ts
    if q2_req_ts is None:
        return False
    if q2_req_ts < other_ts:
        return True
    if q2_req_ts > other_ts:
        return False
    return MY_ID < other_pid


def q2_send_reply(to_pid):
    """Envia REPLY para o processo to_pid."""
    ts = incrementar_relogio()
    payload = {"from_pid": MY_ID, "ts": ts}
    url = f"http://{PEERS[to_pid]}:5000/q2/reply"
    try:
        requests.post(url, json=payload, timeout=5)
        print(f"✅ [Q2] REPLY -> p{to_pid} (ts={ts})")
    except Exception as e:
        print(f"⚠️ [Q2] Falha ao enviar REPLY para p{to_pid}: {e}")


def q2_broadcast_request(req_ts):
    payload = {"from_pid": MY_ID, "ts": req_ts}
    for pid, peer in enumerate(PEERS):
        if pid == MY_ID:
            continue
        url = f"http://{peer}:5000/q2/request"
        try:
            requests.post(url, json=payload, timeout=5)
            print(f"📩 [Q2] REQUEST -> p{pid} (ts={req_ts})")
        except Exception as e:
            print(f"⚠️ [Q2] Falha ao enviar REQUEST para p{pid}: {e}")


def q2_enter_worker():
    global q2_requesting, q2_in_cs, q2_req_ts, q2_awaiting_replies

    with lock_q2:
        if q2_in_cs or q2_requesting:
            print("ℹ️ [Q2] Já estou na CS ou já solicitei.")
            return

        req_ts = incrementar_relogio()
        q2_requesting = True
        q2_req_ts = req_ts
        q2_awaiting_replies = set([i for i in range(TOTAL_PROCESSOS) if i != MY_ID])

    print(f"🚪 [Q2] Pedindo CS (req_ts={req_ts}) aguardando REPLY de: {sorted(list(q2_awaiting_replies))}")

    # manda REQUEST pra todos
    q2_broadcast_request(req_ts)

    # espera replies
    while True:
        with lock_q2:
            if len(q2_awaiting_replies) == 0:
                q2_in_cs = True
                break
        time.sleep(0.05)

    print(f"🔒 [Q2] >>> ENTROU NA SEÇÃO CRÍTICA (req_ts={q2_req_ts})")

    # simula "trabalho" na CS
    time.sleep(Q2_CS_DURATION_SEC)

    # auto-leave: sai da CS e envia REPLY para quem ficou deferido
    with lock_q2:
        print("🔓 [Q2] <<< SAINDO DA SEÇÃO CRÍTICA (auto)")
        q2_in_cs = False
        q2_requesting = False
        q2_req_ts = None

        to_reply = list(q2_deferred)
        q2_deferred.clear()

    for pid in to_reply:
        q2_send_reply(pid)

    print(f"✅ [Q2] auto-leave concluído. replies enviados para: {sorted(to_reply)}")



@app.route("/q2/enter", methods=["POST"])
def q2_enter():
    """Dispara o pedido de CS em thread (não bloqueia HTTP)."""
    global q2_enter_thread
    if q2_enter_thread and q2_enter_thread.is_alive():
        return jsonify({"status": "já existe pedido em andamento", "pid": MY_ID}), 409

    q2_enter_thread = threading.Thread(target=q2_enter_worker, daemon=True)
    q2_enter_thread.start()
    return jsonify({"status": "pedido CS iniciado", "pid": MY_ID})


@app.route("/q2/leave", methods=["POST"])
def q2_leave():
    """Sai da CS e responde os REQUESTs deferidos."""
    global q2_requesting, q2_in_cs, q2_req_ts, q2_deferred

    with lock_q2:
        if not q2_in_cs:
            return jsonify({"status": "não estou na CS", "pid": MY_ID}), 409

        print("🔓 [Q2] <<< SAINDO DA SEÇÃO CRÍTICA")
        q2_in_cs = False
        q2_requesting = False
        q2_req_ts = None

        to_reply = list(q2_deferred)
        q2_deferred.clear()

    # responde fora do lock
    for pid in to_reply:
        q2_send_reply(pid)

    return jsonify({"status": "liberado", "pid": MY_ID, "replies_enviados": sorted(to_reply)})


@app.route("/q2/request", methods=["POST"])
def q2_on_request():
    """Recebe REQUEST e decide responder agora ou deferir."""
    global q2_deferred

    data = request.json
    from_pid = int(data["from_pid"])
    other_ts = int(data["ts"])

    atualizar_relogio(other_ts)

    with lock_q2:
        should_defer = (
            q2_in_cs or
            (q2_requesting and q2_has_priority_over(other_ts, from_pid))
        )

    if should_defer:
        with lock_q2:
            q2_deferred.add(from_pid)
        print(f"⏸️ [Q2] REQUEST de p{from_pid} (ts={other_ts}) -> DEFER (meu_req_ts={q2_req_ts}, in_cs={q2_in_cs})")
        return jsonify({"status": "deferido"})

    if Q2_DELAY_REPLY_MS > 0 and from_pid == Q2_DELAY_REPLY_FROM_PID:
        print(f"😴 [Q2] Atrasando REPLY para p{from_pid} por {Q2_DELAY_REPLY_MS}ms")
        time.sleep(Q2_DELAY_REPLY_MS / 1000.0)

    print(f"✅ [Q2] REQUEST de p{from_pid} (ts={other_ts}) -> REPLY agora")
    q2_send_reply(from_pid)
    return jsonify({"status": "reply_enviado"})


@app.route("/q2/reply", methods=["POST"])
def q2_on_reply():
    """Recebe REPLY e marca que aquele pid respondeu."""
    data = request.json
    from_pid = int(data["from_pid"])
    ts = int(data["ts"])

    atualizar_relogio(ts)

    removed = False
    with lock_q2:
        if from_pid in q2_awaiting_replies:
            q2_awaiting_replies.remove(from_pid)
            removed = True

    if removed:
        print(f"📬 [Q2] REPLY recebido de p{from_pid}. faltam: {sorted(list(q2_awaiting_replies))}")
    else:
        print(f"ℹ️ [Q2] REPLY de p{from_pid} ignorado (não aguardava).")

    return jsonify({"status": "ok"})


@app.route("/q2/state", methods=["GET"])
def q2_state():
    with lock_q2:
        return jsonify({
            "pid": MY_ID,
            "clock": relogio_logico,
            "requesting": q2_requesting,
            "in_cs": q2_in_cs,
            "req_ts": q2_req_ts,
            "awaiting_replies": sorted(list(q2_awaiting_replies)),
            "deferred": sorted(list(q2_deferred)),
            "delay": {"ms": Q2_DELAY_REPLY_MS, "from_pid": Q2_DELAY_REPLY_FROM_PID}
        })

@app.route("/q2/reset", methods=["POST"])
def q2_reset():
    global q2_requesting, q2_in_cs, q2_req_ts, q2_awaiting_replies, q2_deferred, q2_enter_thread
    with lock_q2:
        q2_requesting = False
        q2_in_cs = False
        q2_req_ts = None
        q2_awaiting_replies = set()
        q2_deferred = set()
    q2_enter_thread = None
    return jsonify({"status": "reset_ok", "pid": MY_ID})


# =========================
# Q3: Eleição de Líder — Bully (Valentão)
# =========================

q3_leader_id = None
q3_election_in_progress = False
q3_failed = False  # simula processo "morto" (não responde)

q3_got_answer = False
q3_wait_coordinator_until = 0.0

Q3_ANSWER_TIMEOUT_SEC = float(os.getenv("Q3_ANSWER_TIMEOUT_SEC", "1.5"))
Q3_COORD_TIMEOUT_SEC = float(os.getenv("Q3_COORD_TIMEOUT_SEC", "2.5"))


def q3_broadcast_coordinator(new_leader_id: int):
    """Envia COORDINATOR para todos."""
    payload = {"leader_id": new_leader_id, "from_pid": MY_ID}
    for pid, peer in enumerate(PEERS):
        if pid == MY_ID:
            continue
        url = f"http://{peer}:5000/q3/coordinator"
        try:
            requests.post(url, json=payload, timeout=2)
        except Exception as e:
            print(f"⚠️ [Q3] Falha ao enviar COORDINATOR para p{pid}: {repr(e)}")


def q3_become_leader():
    """Assume liderança e notifica todo mundo."""
    global q3_leader_id, q3_election_in_progress, q3_got_answer

    with lock_q2: 
        q3_leader_id = MY_ID
        q3_election_in_progress = False
        q3_got_answer = False

    print(f"👑 [Q3] >>> EU (p{MY_ID}) SOU O NOVO LÍDER <<<")
    q3_broadcast_coordinator(MY_ID)


def q3_send_election(to_pid: int):
    """Envia ELECTION para processo com ID maior."""
    payload = {"from_pid": MY_ID}
    url = f"http://{PEERS[to_pid]}:5000/q3/election"
    try:
        requests.post(url, json=payload, timeout=2)
        print(f"📨 [Q3] ELECTION -> p{to_pid}")
        return True
    except Exception as e:
        print(f"⚠️ [Q3] Falha ELECTION -> p{to_pid}: {repr(e)}")
        return False


def q3_send_answer(to_pid: int):
    """Responde ANSWER para processo menor."""
    payload = {"from_pid": MY_ID}
    url = f"http://{PEERS[to_pid]}:5000/q3/answer"
    try:
        requests.post(url, json=payload, timeout=2)
        print(f"✅ [Q3] ANSWER -> p{to_pid}")
        return True
    except Exception as e:
        print(f"⚠️ [Q3] Falha ANSWER -> p{to_pid}: {repr(e)}")
        return False


def q3_start_election_worker():
    """
    Bully:
    - envia ELECTION para todos com pid maior
    - se ninguém responder -> vira líder
    - se alguém responder (ANSWER) -> espera COORDINATOR; se não vier, tenta de novo
    """
    global q3_election_in_progress, q3_got_answer, q3_wait_coordinator_until

    with lock_q2:
        if q3_failed:
            print("💀 [Q3] Estou em modo FAIL: não inicio eleição.")
            q3_election_in_progress = False
            return
        if q3_election_in_progress:
            print("ℹ️ [Q3] Eleição já em andamento.")
            return
        q3_election_in_progress = True
        q3_got_answer = False

    print(f"🚨 [Q3] Iniciando eleição (p{MY_ID})...")

    higher = [pid for pid in range(TOTAL_PROCESSOS) if pid > MY_ID]
    any_sent = False

    # envia election pros maiores
    for pid in higher:
        ok = q3_send_election(pid)
        any_sent = any_sent or ok

    # Se não existe ninguém maior, vira líder direto
    if not higher:
        q3_become_leader()
        return

    # Espera ANSWER por um tempo
    deadline = time.time() + Q3_ANSWER_TIMEOUT_SEC
    while time.time() < deadline:
        with lock_q2:
            if q3_got_answer:
                break
        time.sleep(0.05)

    with lock_q2:
        got = q3_got_answer

    if not got:
        # ninguém respondeu -> eu sou o maior vivo
        q3_become_leader()
        return

    print(f"⏳ [Q3] Recebi ANSWER. Aguardando COORDINATOR...")

    with lock_q2:
        q3_wait_coordinator_until = time.time() + Q3_COORD_TIMEOUT_SEC

    # espera coordenador
    while True:
        with lock_q2:
            if not q3_election_in_progress:
                # recebeu coordinator
                return
            if time.time() > q3_wait_coordinator_until:
                break
        time.sleep(0.05)

    print("🔁 [Q3] Timeout esperando COORDINATOR. Reiniciando eleição...")
    with lock_q2:
        q3_election_in_progress = False
    # reinicia eleição
    q3_start_election_worker()


@app.route("/q3/start", methods=["POST"])
def q3_start():
    """Dispara eleição em thread."""
    threading.Thread(target=q3_start_election_worker, daemon=True).start()
    return jsonify({"status": "election_started", "pid": MY_ID})


@app.route("/q3/election", methods=["POST"])
def q3_on_election():
    """Recebe ELECTION de processo menor. Se eu sou maior e vivo, respondo ANSWER e inicio minha eleição."""
    global q3_election_in_progress

    if q3_failed:
        return jsonify({"status": "ignored_failed"}), 200

    data = request.json or {}
    from_pid = int(data.get("from_pid", -1))

    print(f"📩 [Q3] Recebi ELECTION de p{from_pid}")

    # se eu sou maior, respondo answer
    if MY_ID > from_pid:
        q3_send_answer(from_pid)

        # se não estou em eleição, começo a minha
        with lock_q2:
            already = q3_election_in_progress
        if not already:
            threading.Thread(target=q3_start_election_worker, daemon=True).start()

    return jsonify({"status": "ok"}), 200


@app.route("/q3/answer", methods=["POST"])
def q3_on_answer():
    """Recebe ANSWER: alguém maior está vivo."""
    global q3_got_answer

    if q3_failed:
        return jsonify({"status": "ignored_failed"}), 200

    data = request.json or {}
    from_pid = int(data.get("from_pid", -1))
    with lock_q2:
        q3_got_answer = True

    print(f"✅ [Q3] Recebi ANSWER de p{from_pid}")
    return jsonify({"status": "ok"}), 200


@app.route("/q3/coordinator", methods=["POST"])
def q3_on_coordinator():
    """Recebe COORDINATOR: atualiza líder."""
    global q3_leader_id, q3_election_in_progress, q3_got_answer

    if q3_failed:
        return jsonify({"status": "ignored_failed"}), 200

    data = request.json or {}
    leader_id = int(data.get("leader_id", -1))
    from_pid = int(data.get("from_pid", -1))

    with lock_q2:
        q3_leader_id = leader_id
        q3_election_in_progress = False
        q3_got_answer = False

    print(f"📣 [Q3] COORDINATOR recebido: líder = p{leader_id} (avisado por p{from_pid})")
    return jsonify({"status": "ok"}), 200


@app.route("/q3/state", methods=["GET"])
def q3_state():
    with lock_q2:
        return jsonify({
            "pid": MY_ID,
            "failed": q3_failed,
            "leader_id": q3_leader_id,
            "election_in_progress": q3_election_in_progress,
            "got_answer": q3_got_answer,
            "coord_wait_deadline": q3_wait_coordinator_until
        })


@app.route("/q3/reset", methods=["POST"])
def q3_reset():
    global q3_leader_id, q3_election_in_progress, q3_failed, q3_got_answer, q3_wait_coordinator_until
    with lock_q2:
        q3_leader_id = None
        q3_election_in_progress = False
        q3_got_answer = False
        q3_wait_coordinator_until = 0.0
        q3_failed = False
    return jsonify({"status": "reset_ok", "pid": MY_ID})


@app.route("/q3/fail", methods=["POST"])
def q3_fail_toggle():
    """Liga/desliga modo FAIL (processo para de responder Q3)."""
    global q3_failed
    with lock_q2:
        q3_failed = not q3_failed
    print(f"💀 [Q3] FAIL mode = {q3_failed}")
    return jsonify({"status": "ok", "pid": MY_ID, "failed": q3_failed})


if __name__ == '__main__':
    print(f"🚀 Iniciando Pod ID: {MY_ID} na porta 5000")
    app.run(host='0.0.0.0', port=5000, threaded=True, use_reloader=False)
