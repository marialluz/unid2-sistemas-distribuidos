#!/usr/bin/env bash
set -euo pipefail

MSG="${1:-Ola Mundo Distribuido}"

kubectl exec coord-node-0 -- curl -s -X POST http://localhost:5000/iniciar_msg \
  -H "Content-Type: application/json" \
  -d "{\"msg\": \"${MSG}\"}"
echo
