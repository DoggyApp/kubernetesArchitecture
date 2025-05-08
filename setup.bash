#!/bin/bash


aws update-kubeconfig --region us-east-1 --name doggy-app-eks-cluster-0 --profile eks-cluster-admin

kubectl apply -f pods.yaml 
kubectl apply -f services.yaml 
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/examples/2048/ingress.yaml

curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

kubectl create namespace monitoring

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack --namespace monitoring


helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm install loki grafana/loki-stack --namespace monitoring
