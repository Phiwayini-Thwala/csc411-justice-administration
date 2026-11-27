#!/usr/bin/env bash
# Starts the three services in the background (logs in ./logs), Ctrl+C stops all three.
# First time only:  pip install -r police-service/requirements.txt -r judiciary-service/requirements.txt -r correctional-service/requirements.txt
set -e
cd "$(dirname "$0")"
export JWT_SECRET="${JWT_SECRET:-dev-only-shared-secret-change-me-32chars}"   # same value in all three
mkdir -p logs
pids=()
for entry in police-service:8001 judiciary-service:8002 correctional-service:8003; do
  dir="${entry%%:*}"; port="${entry##*:}"
  (cd "$dir" && exec python -m uvicorn main:app --port "$port") > "logs/$dir.log" 2>&1 &
  pids+=($!)
done
trap 'kill "${pids[@]}" 2>/dev/null' INT TERM EXIT
echo "Police       http://localhost:8001/ui"
echo "Judiciary    http://localhost:8002/ui"
echo "Correctional http://localhost:8003/ui"
echo "Portal       frontend/index.html     (Ctrl+C stops all three services)"
wait
