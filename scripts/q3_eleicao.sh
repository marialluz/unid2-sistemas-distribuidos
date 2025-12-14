#!/usr/bin/env bash
set -euo pipefail

# reset em todos
for i in 0 1 2; do
  kubectl exec "coord-node-$i" -- curl -sS -X POST http://127.0.0.1:5000/q3/reset >/dev/null || true
done

echo "==> Iniciando eleição a partir do p0 (esperado: p2 líder)"
kubectl exec coord-node-0 -- curl -sS -X POST http://127.0.0.1:5000/q3/start; echo

sleep 2

echo "==> estados"
for i in 0 1 2; do
  echo "-- p$i --"
  kubectl exec "coord-node-$i" -- curl -sS http://127.0.0.1:5000/q3/state; echo
done

echo
echo "==> Simulando p2 FAIL (líder cai). Esperado: p1 vira líder."
kubectl exec coord-node-2 -- curl -sS -X POST http://127.0.0.1:5000/q3/fail; echo

echo "==> eleição a partir do p0"
kubectl exec coord-node-0 -- curl -sS -X POST http://127.0.0.1:5000/q3/start; echo

sleep 3

echo "==> estados"
for i in 0 1 2; do
  echo "-- p$i --"
  kubectl exec "coord-node-$i" -- curl -sS http://127.0.0.1:5000/q3/state; echo
done
