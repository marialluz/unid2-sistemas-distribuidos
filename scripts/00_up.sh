#!/usr/bin/env bash
set -euo pipefail

minikube start --driver=docker >/dev/null || true

echo "==> build image"
docker build --no-cache -t algoritmos-coordenacao:v6 .

echo "==> load image into minikube"
minikube image load algoritmos-coordenacao:v6

echo "==> apply k8s"
kubectl apply -f k8s-deployment.yaml

echo "==> restart statefulset"
kubectl rollout restart statefulset/coord-node
kubectl rollout status statefulset/coord-node --timeout=180s

echo "==> wait pods ready"
kubectl wait --for=condition=ready pod/coord-node-0 --timeout=120s
kubectl wait --for=condition=ready pod/coord-node-1 --timeout=120s
kubectl wait --for=condition=ready pod/coord-node-2 --timeout=120s

kubectl get pods -o wide
