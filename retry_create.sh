#!/bin/bash
# Retry repo creation until the secondary rate limit clears, then push files.
GH=~/workspace/skills/github/bin/gh-api
for i in 1 2 3 4 5 6; do
  echo "--- attempt $i ($(date -u +%H:%M:%S) UTC) ---"
  OUT=$($GH POST /user/repos --params '{"name":"ghostapi","description":"Catch hallucinated and deprecated API usage: AST scan plus real importlib existence checks","private":false,"auto_init":false}' 2>&1)
  echo "$OUT" | head -3
  if echo "$OUT" | grep -q '"full_name"'; then
    echo "REPO CREATED"
    python3 ~/workspace/ghostapi/push_contents.py
    echo "PUSH DONE exit=$?"
    exit 0
  fi
  # 404 check: maybe it exists already
  CODE=$(curl -s -o /dev/null -w "%{http_code}" https://api.github.com/repos/hahahahahahahahah6/ghostapi)
  if [ "$CODE" = "200" ]; then
    echo "REPO EXISTS (200)"
    python3 ~/workspace/ghostapi/push_contents.py
    echo "PUSH DONE exit=$?"
    exit 0
  fi
  sleep 180
done
echo "STILL BLOCKED after 6 attempts"
exit 1
