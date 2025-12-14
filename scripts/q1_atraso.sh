#!/usr/bin/env bash
set -euo pipefail

echo "==> ligando atraso no pod 1"
kubectl exec coord-node-1 -- curl -s -X POST http://localhost:5000/config/atraso
echo

echo "==> enviando msg com gatilho ATRASAR"
kubectl exec coord-node-0 -- curl -s -X POST http://localhost:5000/iniciar_msg \
  -H "Content-Type: application/json" \
  -d '{"msg":"Esta mensagem vai ATRASAR"}'
echo
