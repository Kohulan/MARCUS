#!/bin/bash
# Task D5: rerun Safe (security v2, fake-engine mode) and Responsive (S3, S5) plus a Robust smoke
# (robustness_v2.py) on v2-backend HEAD bdcc6c5, shipping GPU settings, judge-stack per-IP raises incl. nginx (R25).
. ~/Project_MARCUS/v2-test/v2_lib.sh
export JUDGE_V2_BUILD="d5-bdcc6c5"
L=~/Project_MARCUS/v2-test/logs
J="uv run python"
JD=~/Project_MARCUS/v2-test/judges
prod_check() {
  echo "-- prod: marcus-backend $(docker inspect -f '{{.State.Status}} restart={{.HostConfig.RestartPolicy.Name}}' marcus-backend)," \
       "marcus-frontend $(docker inspect -f '{{.State.Status}}' marcus-frontend)," \
       "maintenance 8080=$(curl -s -o /dev/null -w %{http_code} -m 5 http://127.0.0.1:8080/) 9000=$(curl -s -o /dev/null -w %{http_code} -m 5 http://127.0.0.1:9000/health)"
}
stack_checks() {
  echo "== [$(ts)] $1"; docker compose -p marcus-v2-test ps -a --format "{{.Name}} {{.Image}} {{.Status}}"
  echo "-- nginx edge: $(docker logs marcus-v2-test-nginx-1 2>&1 | grep -E 'limit_conn perip|real_ip' | sed 's/^.*25-marcus-edge.sh: //' | tr '\n' ';')"
  docker exec marcus-v2-test-nginx-1 sh -c 'cat /tmp/nginx/limits.conf; grep -n client_max_body_size /etc/nginx/nginx.conf'
  echo "-- api limits: $(docker exec marcus-v2-test-api-1 env | grep -E '^MARCUS_(IP_|RATE_LIMIT_IP)' | sort | tr '\n' ' ')"
  echo "-- mem/tmpfs: api $(docker inspect -f '{{.HostConfig.Memory}} {{json .HostConfig.Tmpfs}}' marcus-v2-test-api-1); nginx $(docker inspect -f '{{.HostConfig.Memory}} {{json .HostConfig.Tmpfs}}' marcus-v2-test-nginx-1)"
}
gpu_checks() {
  nvidia-smi --query-compute-apps=pid,used_memory --format=csv
  docker exec marcus-v2-test-dispatcher-1 python -c "from marcus.core.queues import SLOTS; print('SLOTS', SLOTS)"
  for c in $(docker ps --filter label=com.docker.compose.project=marcus-v2-test --format "{{.Names}}" | grep -E "worker-(segment|decimer|molnextr|molscribe)"); do
    echo "-- $c env: $(docker exec $c env | grep -E '^MARCUS_(GPU_MEM_MB|TORCH_MEM_FRACTION|MOLSCRIBE_DEVICE)' | tr '\n' ' ') cmd: $(docker inspect -f '{{join .Config.Cmd " "}}' $c | grep -oE '(-c [0-9]+|--max-tasks-per-child [0-9]+)' | tr '\n' ' ')"
    docker logs $c 2>&1 | grep -E "limited to|skipping|loaded|device|cuda" | grep -v Warning | cut -c1-220 | head -6
  done
}
echo "[$(ts)] D5 start"; prod_check
cd $B
echo "[$(ts)] wipe any old v2-test containers and volumes"
$G down -v --remove-orphans 2>&1 | tail -2; $S down -v --remove-orphans 2>&1 | tail -2
echo "-- v2-test volumes left: [$(docker volume ls -q --filter label=com.docker.compose.project=marcus-v2-test | tr '\n' ' ')]"

# ---------------- Safe: security v2 suite (fake engines; the suite uploads with engine "fake")
echo "[$(ts)] security mode up"; $S up -d 2>&1 | tail -3
wait_ready || { docker compose -p marcus-v2-test ps -a; exit 1; }
stack_checks "security mode" > $L/d5_security_stack.log 2>&1
cd $JD
MARCUS_BACKEND_URL=$URL MARCUS_FS_PROBE=docker:marcus-v2-test-api-1 uv run pytest security/v2 -v -rs -p no:cacheprovider \
   --junitxml=load/results/jarvis_v2_SECURITY_$(date +%Y%m%dT%H%M%S)_d5.xml > $L/d5_security.log 2>&1
echo "SECURITY_RC=$?"; tail -3 $L/d5_security.log
cd $B && $S down -v 2>&1 | tail -2
prod_check

# ---------------- GPU mode, shipping configuration: Responsive (S3, S5) and the Robust smoke
echo "[$(ts)] GPU mode up (shipping config)"; $G up -d 2>&1 | tail -2
wait_ready || { docker compose -p marcus-v2-test ps -a; exit 1; }
sleep 15
( while true; do echo "$(ts),$(nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader,nounits)"; sleep 2; done ) > $L/d5_gpu.csv 2>&1 &
GPUPID=$!
{ stack_checks "GPU mode"; gpu_checks; } > $L/d5_gpu_checks.log 2>&1
cd $JD
A="--target jarvis --client v2 --base-url $URL --prod-stopped --cache-pg-container $PG"
for s in S3 S5; do echo "[$(ts)] $s"; $J load/scenarios.py $A --scenarios $s --tag d5; echo "${s}_RC=$?"; done
echo "[$(ts)] robustness"
$J load/robustness_v2.py --target jarvis --prod-stopped --base-url $URL --project marcus-v2-test
echo "ROBUST_RC=$?"
cd $B
{ echo "== [$(ts)] after runs"; gpu_checks
  echo "-- restart counts:"; for c in $(docker ps -a --filter label=com.docker.compose.project=marcus-v2-test --format "{{.Names}}"); do echo "$c $(docker inspect -f '{{.RestartCount}} {{.State.Status}} oom={{.State.OOMKilled}}' $c)"; done
  echo "-- steps by kind/status/attempts:"
  docker exec $PG psql -U marcus -d marcus -c "select kind, status, max(attempts) max_attempts, count(*) from steps group by 1,2 order by 1,2"
  echo "-- failed steps:"
  docker exec $PG psql -U marcus -d marcus -c "select p.display_name, s.kind, s.page, s.error_class, left(s.error,120) error from steps s left join papers p on p.id=s.paper_id where s.status='failed' order by 1,2,3"
  echo "-- OOM / ResourceExhausted lines in worker logs: $(for c in segment decimer molnextr molscribe; do docker logs marcus-v2-test-worker-$c-1 2>&1 | grep -ciE 'ResourceExhausted|out of memory'; done | tr '\n' ' ')"
} > $L/d5_after.log 2>&1
kill $GPUPID
echo "[$(ts)] stack down"; $G down -v 2>&1 | tail -2
echo "-- v2-test volumes left: [$(docker volume ls -q --filter label=com.docker.compose.project=marcus-v2-test | tr '\n' ' ')]"
nvidia-smi --query-gpu=memory.used,compute_mode --format=csv,noheader
prod_check
echo "ALL DONE $(ts)"
