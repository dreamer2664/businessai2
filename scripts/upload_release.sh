#!/bin/sh
# Upload release/kdr-brain-lite, release/brain.kdr and release/packs/*.kdw to the GitHub Release tagged "latest".
#   sh scripts/upload_release.sh        (reads .secrets/env: GH_OWNER, GITHUB_TOKEN)
set -e
cd "$(dirname "$0")/.."
[ -f .secrets/env ] && { set -a; . ./.secrets/env; set +a; }
GH_TOKEN="${GH_TOKEN:-$GITHUB_TOKEN}"; : "${GH_OWNER:?}"; : "${GH_TOKEN:?}"; GH_REPO="${GH_REPO:-businessai2}"; TAG="${TAG:-latest}"
API="https://api.github.com/repos/$GH_OWNER/$GH_REPO"
auth() { curl -sS -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/vnd.github+json" "$@"; }
rel=$(auth "$API/releases/tags/$TAG" || true)
id=$(printf '%s' "$rel" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null || true)
if [ -z "$id" ]; then
  rel=$(auth -X POST "$API/releases" -d "{\"tag_name\":\"$TAG\",\"name\":\"businessai $TAG\",\"body\":\"Brain assets: kdr-brain-lite (engine), brain.kdr (retriever+reader models), *.kdw knowledge packs. Fetch with scripts/get_brain.sh\"}")
  id=$(printf '%s' "$rel" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
fi
echo "release id $id"
for f in ${FILES:-release/kdr-brain-lite release/brain.kdr release/packs/*.kdw release/llm/llama-server-static}; do
  [ -s "$f" ] || continue; name=$(basename "$f")
  # delete an existing asset with the same name
  aid=$(auth "$API/releases/$id/assets" | python3 -c "import json,sys; print(next((a['id'] for a in json.load(sys.stdin) if a['name']=='$name'),''))")
  [ -n "$aid" ] && auth -X DELETE "$API/releases/assets/$aid" >/dev/null
  echo "uploading $name ($(stat -c %s "$f") bytes)"
  curl -sS -H "Authorization: Bearer $GH_TOKEN" -H "Content-Type: application/octet-stream" -T "$f" \
       "https://uploads.github.com/repos/$GH_OWNER/$GH_REPO/releases/$id/assets?name=$name" -o /dev/null -w "  -> HTTP %{http_code}\n"
done
echo "done: https://github.com/$GH_OWNER/$GH_REPO/releases/tag/$TAG"
