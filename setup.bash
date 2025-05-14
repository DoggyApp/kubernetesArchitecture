#!/bin/bash


aws eks update-kubeconfig --region us-east-1 --name doggy-app-eks-cluster-0 --profile eks-cluster-admin

kubectl apply -f /home/ec2-user/kubernetesArchitecture/pods.yaml 
kubectl apply -f /home/ec2-user/kubernetesArchitecture/services.yaml 

kubectl create namespace ingress-nginx
kubectl apply -f /home/ec2-user/kubernetesArchitecture/ingress.yaml -n ingress-nginx
kubectl apply -f https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.13.0/docs/examples/2048/2048_full.yaml # check here https://github.com/kubernetes-sigs/aws-load-balancer-controller/blob/main/version-stable.txt for latest ersion 

curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

kubectl create namespace monitoring

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack --namespace monitoring


helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm install loki grafana/loki-stack --namespace monitoring
