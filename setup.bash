#!/bin/bash


aws eks update-kubeconfig --region us-east-1 --name doggy-app-eks-cluster-0 --profile eks-cluster-admin

kubectl apply -f /home/ec2-user/kubernetesArchitecture/pods.yaml 

kubectl create namespace ingress-nginx
kubectl apply -f /home/ec2-user/kubernetesArchitecture/ingress.yaml -n ingress-nginx

kubectl apply -f /home/ec2-user/kubernetesArchitecture/services.yaml 

kubectl apply -k /home/ec2-user/kubernetesArchitecture/ingress/

curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

kubectl create namespace monitoring

helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack --namespace monitoring


helm repo add grafana https://grafana.github.io/helm-charts
helm repo update


helm install --values /home/ec2-user/kubernetesArchitecture/loki/values.yaml loki grafana/loki \
    --namespace monitoring \
    --create-namespace \
    -f /home/ec2-user/kubernetesArchitecture/logging/loki-values.yaml


helm upgrade --install promtail grafana/promtail \
    --namespace monitoring \
    --create-namespace \
    -f /home/ec2-user/kubernetesArchitecture/logging/promtail-values.yaml

helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
    -n monitoring \
    -f /home/ec2-user/kubernetesArchitecture/logging/grafana-values.yaml



# kubectl get secret -n monitoring kube-prometheus-stack-grafana -o jsonpath="{.data.admin-password}" | base64 --decode

# kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80

# aws ssm start-session --target i-0905bc6b077e8698f --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
