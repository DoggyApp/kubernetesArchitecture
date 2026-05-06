#!/bin/bash
cat >> ~/.aws/config << 'EOF'

[sso-session doggy-session]
sso_start_url = https://d-90660d7b78.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access

[profile doggy-admin]
sso_session = doggy-session
sso_account_id = 109798190983
sso_role_name = AdministratorAccess
region = us-east-1
output = json
EOF

echo "SSO config appended. Logging in..."
aws sso login --profile doggy-admin
