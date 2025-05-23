#!/bin/bash


aws eks update-kubeconfig --region us-east-1 --name doggy-app-eks-cluster-0 --profile eks-cluster-admin


export OIDC_URL=$(aws eks describe-cluster \
  --name doggy-app-eks-cluster-0 \
  --query "cluster.identity.oidc.issuer" \
  --output text | sed 's|https://||')

envsubst < /home/ec2-user/kubernetesArchitecture/autoscaler/cf-autoscaler-role.yaml > /home/ec2-user/cf-autoscaler-role-up.yaml

aws cloudformation deploy \
  --template-file /home/ec2-user/cf-autoscaler-role-up.yaml \
  --stack-name cluster-autoscaler-iam-role \
  --capabilities CAPABILITY_NAMED_IAM

export AUTOSC_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name cluster-autoscaler-iam-role \
  --query "Stacks[0].Outputs[?OutputKey=='ClusterAutoscalerRoleArn'].OutputValue" \
  --output text)

envsubst < /home/ec2-user/kubernetesArchitecture/autoscaler/autoscaler-values.yaml > /home/ec2-user/autoscaler-values-up.yaml

kubectl apply -f /home/ec2-user/kubernetesArchitecture/pods.yaml 

kubectl create namespace ingress-nginx

kubectl apply -f /home/ec2-user/kubernetesArchitecture/services.yaml 

kubectl apply -k /home/ec2-user/kubernetesArchitecture/ingress/

curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

helm repo add autoscaler https://kubernetes.github.io/autoscaler
helm repo update

helm upgrade --install cluster-autoscaler autoscaler/cluster-autoscaler \
  --namespace kube-system \
  --create-namespace \
  -f /home/ec2-user//autoscaler-values-up.yaml

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

kubectl create namespace monitoring

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f /home/ec2-user/kubernetesArchitecture/logging/prometheus/prometheus-values.yaml


helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm upgrade --install loki grafana/loki \
  -n monitoring \
  -f /home/ec2-user/kubernetesArchitecture/logging/loki-values.yaml

helm upgrade --install promtail grafana/promtail \
  --namespace monitoring \
  --create-namespace \
  -f /home/ec2-user/kubernetesArchitecture/logging/promtail-values.yaml

helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring \
  -f /home/ec2-user/kubernetesArchitecture/logging/prometheus/grafana-values.yaml \
  --reuse-values

sudo yum install python3 -y
pip3 install flask requests

export BASTION_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
envsubst < /home/ec2-user/kubernetesArchitecture/alerting/alert-manager-values.yaml > /home/ec2-user/alert-manager-value-up.yaml

pip install boto3

export OPENAI_API_KEY=your_openai_api_key
export LOKI_URL=http://loki-gateway.monitoring.svc.cluster.local/loki/api/v1/query_range
python3 prometheus_webhook.py

helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set-file alertmanager.config=/home/ec2-user/alert-manager-value-up.yaml

# kubectl get secret -n monitoring kube-prometheus-stack-grafana -o jsonpath="{.data.admin-password}" | base64 --decode

# kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80

# aws ssm start-session --target i-0020efb79913823b0 --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
