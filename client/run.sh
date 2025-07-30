#!/bin/bash

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# Check if authenticated
echo "🔑 Checking OCI authentication..."
if ! oci session validate --profile DEFAULT --auth security_token &>/dev/null; then
    echo "❌ Not authenticated. Run:"
    echo "oci session authenticate --profile-name DEFAULT --region us-chicago-1"
    exit 1
fi

echo "✅ Authentication OK"

# Go back to server directory and run client
cd ..
source .venv/bin/activate
python client/oracle_mcp_client.py