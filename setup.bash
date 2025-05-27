#!/bin/bash

# set env variables 
export CLUSTER_NAME="doggy-app-eks-cluster-0"
export NODEGROUP_NAME="doggy-app-eks-ng-monitoring"

aws eks update-kubeconfig --region us-east-1 --name $CLUSTER_NAME --profile eks-cluster-admin

# install helm 
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Call OIDC provider and create IAM role necessary for autoscaler 
export OIDC_URL=$(aws eks describe-cluster \
  --name $CLUSTER_NAME \
  --query "cluster.identity.oidc.issuer" \
  --output text | sed 's|https://||')

envsubst < /home/ec2-user/kubernetesArchitecture/autoscaler/cf-autoscaler-role.yaml > /home/ec2-user/cf-autoscaler-role-up.yaml

aws cloudformation deploy \
  --template-file /home/ec2-user/cf-autoscaler-role-up.yaml \
  --stack-name cluster-autoscaler-iam-role \
  --capabilities CAPABILITY_NAMED_IAM

# call AUTOSCALER role ARN and populate it into the autoscaler values config 
export AUTOSC_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name cluster-autoscaler-iam-role \
  --query "Stacks[0].Outputs[?OutputKey=='ClusterAutoscalerRoleArn'].OutputValue" \
  --output text)

envsubst < /home/ec2-user/kubernetesArchitecture/autoscaler/autoscaler-values.yaml > /home/ec2-user/autoscaler-values-up.yaml

# install the autoscaler repo and install the autoscaler 
helm repo add autoscaler https://kubernetes.github.io/autoscaler
helm repo update

helm upgrade --install cluster-autoscaler autoscaler/cluster-autoscaler \
  --namespace kube-system \
  --create-namespace \
  -f /home/ec2-user/autoscaler-values-up.yaml

# create ingress 
kubectl create namespace ingress-nginx
kubectl apply -k /home/ec2-user/kubernetesArchitecture/ingress/

# get host address and create a config map from it 
LB_HOST=$(kubectl get ingress doggy-ingress -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

kubectl create configmap frontend-config \
  --from-literal=LOAD_BALANCER_URL="http://$LB_HOST" \
  --dry-run=client -o yaml | kubectl apply -f - 

# create pods and services for application 
kubectl apply -f /home/ec2-user/kubernetesArchitecture/pods.yaml 
kubectl apply -f /home/ec2-user/kubernetesArchitecture/services.yaml 

# ==========================================================================

# start monitoring set up 
kubectl create namespace monitoring

# install prometheus 
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f /home/ec2-user/kubernetesArchitecture/logging/prometheus/prometheus-values.yaml

# install Loki and promtail 
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm upgrade --install loki grafana/loki \
  -n monitoring \
  -f /home/ec2-user/kubernetesArchitecture/logging/loki-values.yaml

helm upgrade --install promtail grafana/promtail \
  --namespace monitoring \
  --create-namespace \
  -f /home/ec2-user/kubernetesArchitecture/logging/promtail-values.yaml

# update grafana in the prometheus stack so that it adds the source for loki and grafana 
helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring \
  -f /home/ec2-user/kubernetesArchitecture/logging/prometheus/grafana-values.yaml \
  --reuse-values

# =================================================================================

# User previously Call OIDC provider and create IAM role necessary for alert analyzer 

envsubst < /home/ec2-user/kubernetesArchitecture/alerting/cf-alert-hook-role.yaml > /home/ec2-user/cf-alert-hook-role-up.yaml

aws cloudformation deploy \
  --template-file /home/ec2-user/cf-alert-hook-role-up.yaml \
  --stack-name alert-hook-iam-role \
  --capabilities CAPABILITY_NAMED_IAM

# call Alerter role ARN and populate it into the alert service account 
export ALERTER_ROLE_ARN=$(aws cloudformation describe-stacks \
  --stack-name alert-hook-iam-role \
  --query "Stacks[0].Outputs[?OutputKey=='ClusterAlerterRoleArn'].OutputValue" \
  --output text)

envsubst < /home/ec2-user/kubernetesArchitecture/alerting/alert-service-account.yaml > /home/ec2-user/alert-service-account-up.yaml

# Deply alerting pod 
kubectl apply -f /home/ec2-user/kubernetesArchitecture/alerting/alert-pod.yaml 


# update alert manager with needed config 
helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f /home/ec2-user/kubernetesArchitecture/alerting/alert-manager-values.yaml\
  --reuse-values


# kubectl get secret -n monitoring kube-prometheus-stack-grafana -o jsonpath="{.data.admin-password}" | base64 --decode

# kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80

# aws ssm start-session --target i-0a472ed38fb2b4698 --document-name AWS-StartPortForwardingSession --parameters '{"portNumber":["3000"],"localPortNumber":["3000"]}'
