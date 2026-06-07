#!/bin/bash
LOG=/var/log/asx-predictions.log
echo "--- $(date) ---" >> $LOG

# Step 1: Get a fresh admin token (JSON body)
TOKEN=$(curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"asxscreener@gmail.com","password":"Password@1234!"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "ERROR: Could not obtain admin token" >> $LOG
  exit 1
fi

# Step 2: Trigger predictions
RESULT=$(curl -s -X POST "http://localhost:8000/api/v1/predictions/trigger?top_n=1000" \
  -H "Authorization: Bearer $TOKEN")

echo "Result: $RESULT" >> $LOG
