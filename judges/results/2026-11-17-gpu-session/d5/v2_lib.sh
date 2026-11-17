# shared helpers for the D4 v2 runs on jarvis
cd ~/Project_MARCUS/v2-test && . ./env.sh
B=~/Project_MARCUS/v2-test/backend-v2
G="docker compose -p marcus-v2-test -f docker-compose.yml -f docker-compose.gpu.yml -f ../judges/stack/docker-compose.v2-jarvis.yml"
S="docker compose -p marcus-v2-test -f docker-compose.yml -f docker-compose.fake.yml -f ../judges/stack/docker-compose.v2-jarvis.yml"
URL=http://127.0.0.1:18090
PG=marcus-v2-test-postgres-1
ts() { date -u +%FT%TZ; }
wait_ready() { for i in $(seq 1 180); do c=$(curl -s -o /dev/null -w "%{http_code}" -m 10 $URL/api/v2/ready); [ "$c" = 200 ] && { echo "[$(ts)] ready after ${i}x5s"; return 0; }; sleep 5; done; echo "[$(ts)] NOT READY ($c)"; return 1; }
