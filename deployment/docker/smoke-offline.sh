#!/bin/bash
# Offline smoke test for a ChaCC image: module packages survive restarts and
# recreated containers without network, also in a custom MODULE_PACKAGES_DIR.
#
#   docker build -f deployment/docker/Dockerfile.local -t chacc-api:local .
#   IMAGE=chacc-api:local deployment/docker/smoke-offline.sh
#
# Needs network for steps 1 and 4 (installs tomli-w from PyPI), port 8097 free, and
# uses throwaway volumes named smoke_*.
set -u
IMAGE=${IMAGE:-chacc-api:local}
NAME=chacc-smoke
WORK=$(mktemp -d)
trap 'rm -f "$WORK/t5_probe.chacc"; rmdir "$WORK"' EXIT
PROBE=$WORK/t5_probe.chacc
python3 - "$PROBE" <<'PY'
import json, sys, zipfile
meta = {"name": "t5_probe", "version": "1.0.0", "entry_point": "probe_src.main:setup_plugin",
        "base_path_prefix": "/probe", "module_dependencies": {"required": [], "optional": []}}
main = """from fastapi import APIRouter
import tomli_w

async def setup_plugin(context=None):
    router = APIRouter()

    @router.get("/where")
    async def where():
        return {"tomli_w": tomli_w.__file__}

    return router
"""
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("module_meta.json", json.dumps(meta))
    z.writestr("requirements.txt", "tomli-w==1.2.0\n")
    z.writestr("probe_src/__init__.py", "")
    z.writestr("probe_src/main.py", main)
PY
COMMON=(-e SECRET_KEY=smoke-secret-key-for-testing-only-0123456789 -e DATABASE_ENGINE=sqlite
        -e SQLITE_DATABASE_PATH=/app/.chacc_cache
        --mount type=volume,src=smoke_modules,dst=/app/.modules_installed,volume-nocopy
        --mount type=volume,src=smoke_cache,dst=/app/.chacc_cache)
PASS=0; FAIL=0
ok()   { echo "  PASS $*"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL $*"; FAIL=$((FAIL+1)); }
check(){ if [ "$1" = "$2" ]; then ok "$3"; else bad "$3 (got '$1', want '$2')"; fi; }

inside() {  # GET a URL from inside the container (works with --network none)
    docker exec "$NAME" python -c "import urllib.request,sys
try:
    r=urllib.request.urlopen('http://localhost:8085$1',timeout=5); print(r.status, r.read().decode())
except urllib.error.HTTPError as e: print(e.code)
except Exception as e: print('DOWN')" 2>/dev/null
}
wait_up() {
    for _ in $(seq 1 180); do
        case "$(inside /api/health)" in 200*) return 0;; esac
        docker ps -q --filter name=$NAME --filter status=running | grep -q . || { echo "  container exited"; docker logs $NAME 2>&1 | tail -20; return 1; }
        sleep 1
    done
    return 1
}
start() {  # start [extra docker args...]
    docker rm -f $NAME >/dev/null 2>&1
    docker run -d --name $NAME "${COMMON[@]}" "$@" "$IMAGE" >/dev/null
    local t=$(date +%s); wait_up; echo "  (up in $(( $(date +%s)-t ))s)"
}
probe_path() { inside /api/probe/where | sed -n 's/^200 {"tomli_w":"\(.*\)"}$/\1/p'; }

docker rm -f $NAME >/dev/null 2>&1
docker volume rm smoke_modules smoke_cache smoke_packages smoke_custom >/dev/null 2>&1

echo "== Image"
check "$(docker run --rm --entrypoint python $IMAGE -c 'import sys;print(sys.version.split()[0])')" "3.15.2" "Python 3.15.2"
check "$(docker run --rm --entrypoint sh $IMAGE -c 'ls -A /app/.modules_installed | wc -l')" "0" "no module archives baked into the image"

echo "== 1. Upload a module that needs a new package (network on)"
start -p 8097:8085 --mount type=volume,src=smoke_packages,dst=/app/.chacc_packages
code=$(curl -s -o /tmp/smoke_upload.json -w '%{http_code}' -F "file=@$PROBE" localhost:8097/api/modules/)
check "$code" "200" "upload accepted"
check "$(docker exec $NAME sh -c 'ls /app/.chacc_packages | grep -c tomli_w')" "2" "tomli-w installed into /app/.chacc_packages"
check "$(docker exec $NAME sh -c 'test -e /app/.local && echo yes || echo no')" "no" "no user-site fallback (/app/.local)"

echo "== 2. In-container restart (console / API)"
curl -s -X POST localhost:8097/api/system/restart >/dev/null
sleep 3; wait_up
check "$(probe_path)" "/app/.chacc_packages/tomli_w/__init__.py" "module loads after restart"

echo "== 3. Recreate the container WITHOUT network"
start --network none --mount type=volume,src=smoke_packages,dst=/app/.chacc_packages
check "$(probe_path)" "/app/.chacc_packages/tomli_w/__init__.py" "module loads offline after recreate"
check "$(docker logs $NAME 2>&1 | grep -ciE 'Installing|pip install|Could not')" "0" "no pip activity at boot"
check "$(docker exec $NAME python -c "import json;print(json.load(open('/app/.chacc_cache/deps_status.json'))['ok'])")" "True" "boot check ok"

echo "== 4. Custom MODULE_PACKAGES_DIR outside /app (empty volume, network on)"
start -p 8097:8085 -e MODULE_PACKAGES_DIR=/srv/chacc/packages \
      --mount type=volume,src=smoke_custom,dst=/srv/chacc/packages
check "$(probe_path)" "/srv/chacc/packages/tomli_w/__init__.py" "boot installed missing packages into the custom dir"
check "$(docker exec $NAME stat -c %U /srv/chacc/packages)" "chacc" "custom dir owned by the server user"
check "$(docker exec $NAME sh -c 'cat $(python -c "import site;print(site.getsitepackages()[0])")/chacc_modules.pth')" "/srv/chacc/packages" ".pth points at the custom dir"
check "$(docker exec -u chacc $NAME python -c 'import tomli_w;print(tomli_w.__file__)')" "/srv/chacc/packages/tomli_w/__init__.py" "plain python sees the custom dir"

echo "== 5. Recreate WITHOUT network, custom dir"
start --network none -e MODULE_PACKAGES_DIR=/srv/chacc/packages \
      --mount type=volume,src=smoke_custom,dst=/srv/chacc/packages
check "$(probe_path)" "/srv/chacc/packages/tomli_w/__init__.py" "module loads offline from the custom dir"

echo "== 6. Packages lost and no network: server still starts, only that module is skipped"
docker rm -f $NAME >/dev/null
docker volume rm smoke_custom >/dev/null
start --network none -e MODULE_PACKAGES_DIR=/srv/chacc/packages \
      --mount type=volume,src=smoke_custom,dst=/srv/chacc/packages
check "$(inside /api/health | cut -c1-3)" "200" "server is up"
check "$(inside /api/probe/where | cut -c1-3)" "404" "module skipped"
check "$(inside /api/modules/graph | grep -c 'Python packages not installed')" "1" "graph explains why"

docker rm -f $NAME >/dev/null 2>&1
docker volume rm smoke_modules smoke_cache smoke_packages smoke_custom >/dev/null 2>&1
echo; echo "passed: $PASS  failed: $FAIL"
[ "$FAIL" -eq 0 ]
