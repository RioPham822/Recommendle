#!/bin/bash

BASE_URL="http://localhost:8015/api/game"

set -e

echo "Testing Decidio V2 game API"

echo "1) Start game"
GAME=$(curl -s -X POST "$BASE_URL/start" -H "Content-Type: application/json" -d '{"player_name":"API Test Player"}')
echo "$GAME" | jq '.'
GAME_ID=$(echo "$GAME" | jq -r '.id')

if [ -z "$GAME_ID" ] || [ "$GAME_ID" = "null" ]; then
  echo "Failed to create game"
  exit 1
fi

echo "2) Get onboarding pool"
ONBOARDING=$(curl -s "$BASE_URL/$GAME_ID/onboarding")
echo "$ONBOARDING" | jq '{game_id, pool_size, sample: (.products[0:3])}'
POOL_SIZE=$(echo "$ONBOARDING" | jq -r '.pool_size')
if [ "$POOL_SIZE" != "50" ]; then
  echo "Expected pool_size 50, got $POOL_SIZE"
  exit 1
fi

SELECTED_IDS=$(echo "$ONBOARDING" | jq -r '.products[0:10] | map(.id)')

echo "3) Submit onboarding"
SUBMIT=$(curl -s -X POST "$BASE_URL/$GAME_ID/onboarding/submit" \
  -H "Content-Type: application/json" \
  -d "{\"selected_product_ids\":$SELECTED_IDS,\"rating\":4}")
echo "$SUBMIT" | jq '.'
ACCEPTED=$(echo "$SUBMIT" | jq -r '.accepted')
if [ "$ACCEPTED" != "true" ]; then
  echo "Onboarding submit failed"
  exit 1
fi

echo "4) Start round 1"
ROUND1=$(curl -s -X POST "$BASE_URL/$GAME_ID/round/start")
echo "$ROUND1" | jq '{round_number, candidate_count: (.candidates|length), pre_round_metrics}'
ROUND_NUMBER=$(echo "$ROUND1" | jq -r '.round_number')
CANDIDATE_COUNT=$(echo "$ROUND1" | jq -r '.candidates | length')
if [ "$ROUND_NUMBER" != "1" ] || [ "$CANDIDATE_COUNT" != "10" ]; then
  echo "Round start failed"
  exit 1
fi

PICK_ID=$(echo "$ROUND1" | jq -r '.candidates[0].id')

echo "5) Submit pick"
RESULT1=$(curl -s -X POST "$BASE_URL/$GAME_ID/round/1/pick" \
  -H "Content-Type: application/json" \
  -d "{\"product_id\":\"$PICK_ID\"}")
echo "$RESULT1" | jq '{round_number, ai_correct, human_points, ai_points, total_human_score, total_ai_score, game_complete}'

echo "6) Status"
STATUS=$(curl -s "$BASE_URL/$GAME_ID/status")
echo "$STATUS" | jq '.'

echo "7) Leaderboard"
LEADERBOARD=$(curl -s "$BASE_URL/leaderboard")
echo "$LEADERBOARD" | jq '.'

echo "V2 API smoke test completed"
