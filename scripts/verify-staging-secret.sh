#!/usr/bin/env bash
# Verify that findmyjob/staging/app has all keys ECS expects. Does NOT print secret values.
# Run: ./scripts/verify-staging-secret.sh

set -e
REGION="${AWS_REGION:-ap-south-1}"

REQUIRED_KEYS=(
  MONGODB_URI
  MONGODB_DB_NAME
  REDIS_URL
  SECRET_KEY
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GMAIL_OAUTH_REDIRECT_URI
  TOKEN_ENCRYPTION_KEY
  RAZORPAY_KEY_ID
  RAZORPAY_KEY_SECRET
  RAZORPAY_WEBHOOK_SECRET
  OPENAI_API_KEY
  STORAGE_BACKEND
  CORS_ORIGINS
)

echo "Fetching secret key names (values are not printed)..."
SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id "findmyjob/staging/app" --region "$REGION" --query SecretString --output text)
KEYS_PRESENT=$(echo "$SECRET_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(' '.join(sorted(d.keys())))")
echo "Keys in secret: $KEYS_PRESENT"
echo ""

MISSING=()
for k in "${REQUIRED_KEYS[@]}"; do
  if echo "$SECRET_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if \"$k\" in d else 1)" 2>/dev/null; then
    echo "  [OK] $k"
  else
    echo "  [MISSING] $k"
    MISSING+=("$k")
  fi
done

echo ""
if [ ${#MISSING[@]} -eq 0 ]; then
  echo "All required keys are present."
else
  echo "Missing keys (add them in Secrets Manager): ${MISSING[*]}"
  exit 1
fi

# Value checks (length only, no content)
echo ""
echo "Quick value checks (length only):"
check_len() {
  local key=$1
  local min=$2
  local len
  len=$(echo "$SECRET_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); v=d.get('$key',''); print(len(v))" 2>/dev/null || echo "0")
  if [ "$len" -ge "$min" ] 2>/dev/null; then
    echo "  [OK] $key length >= $min"
  else
    echo "  [CHECK] $key length $len (expected >= $min)"
  fi
}
check_len SECRET_KEY 32
check_len MONGODB_URI 20
check_len REDIS_URL 10
check_len GOOGLE_CLIENT_ID 10
check_len GMAIL_OAUTH_REDIRECT_URI 10

echo ""
echo "REDIS_URL should look like: redis://<host>:6379/0"
echo "GMAIL_OAUTH_REDIRECT_URI should match exactly what you set in Google Cloud Console (e.g. https://api-staging.findmyjob.com/v1/gmail/oauth/callback)"
