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
PEERS = [f"multicast-app-{i}.multicast-service" for i in range(3)]
TOTAL_PROCESSOS = 3

# --- ESTADO GLOBAL (Lamport) ---
relogio_logico = 0
fila_prioridade = [] # Lista de dicionários: [{'clock': 1, 'pid': 0, 'msg': '...', 'acks': 0}]
lock = threading.Lock()

# Simulação de atraso (Dica da tarefa)
ATRASO_ACK = False

# --- FUNÇÕES AUXILIARES ---

def incrementar_relogio():
    global relogio_logico
    with lock:
        relogio_logico += 1
    return relogio_logico

def atualizar_relogio(timestamp_recebido):
    global relogio_logico
    with lock:
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
        with lock:
            if fila_prioridade:
                # Ordena a fila (Ordenação Total)
                fila_prioridade.sort(key=cmp_to_key(comparar_mensagens))
                
                # Regra de Lamport: 
                # 1. Mensagem está no topo da fila
                # 2. Recebeu ACKs de TODOS os processos
                msg_topo = fila_prioridade[0]
                
                if msg_topo['acks'] >= TOTAL_PROCESSOS:
                    # Processa a mensagem
                    print(f"✅ PROCESSANDO: '{msg_topo['msg']}' [Clock: {msg_topo['clock']}, PID: {msg_topo['pid']}]")
                    # Remove da fila
                    fila_prioridade.pop(0)
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
    item['acks'] = 0
    with lock:
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
    """Contabiliza os ACKs recebidos"""
    data = request.json
    uuid_alvo = data['uuid']
    
    with lock:
        for msg in fila_prioridade:
            if msg['uuid'] == uuid_alvo:
                msg['acks'] += 1
                print(f"ACK recebido de {data['from_pid']} para msg {uuid_alvo}. Total: {msg['acks']}")
                break
                
    return jsonify({"status": "ACK contabilizado"})

@app.route('/config/atraso', methods=['POST'])
def config_atraso():
    """Endpoint para ligar/desligar o modo de atraso (Requisito da tarefa)"""
    global ATRASO_ACK
    ATRASO_ACK = not ATRASO_ACK
    return jsonify({"status": f"Modo Atraso: {ATRASO_ACK}"})

if __name__ == '__main__':
    print(f"🚀 Iniciando Pod ID: {MY_ID} na porta 5000")
    app.run(host='0.0.0.0', port=5000)