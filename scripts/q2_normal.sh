#!/usr/bin/env bash
set -euo pipefail

kubectl exec coord-node-0 -- curl -sS -X POST http://127.0.0.1:5000/q2/reset >/dev/null || true
kubectl exec coord-node-1 -- curl -sS -X POST http://127.0.0.1:5000/q2/reset >/dev/null || true
kubectl exec coord-node-2 -- curl -sS -X POST http://127.0.0.1:5000/q2/reset >/dev/null || true

kubectl exec coord-node-0 -- curl -sS -X POST http://127.0.0.1:5000/q2/enter; echo
kubectl exec coord-node-1 -- curl -sS -X POST http://127.0.0.1:5000/q2/enter; echo

sleep 1

kubectl exec coord-node-0 -- sh -lc 'curl -sS --max-time 2 http://127.0.0.1:5000/q2/state; echo'
kubectl exec coord-node-1 -- sh -lc 'curl -sS --max-time 2 http://127.0.0.1:5000/q2/state; echo'
kubectl exec coord-node-2 -- sh -lc 'curl -sS --max-time 2 http://127.0.0.1:5000/q2/state; echo'
