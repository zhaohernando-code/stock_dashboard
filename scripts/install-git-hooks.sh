#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
mkdir -p "$repo_root/../../.githooks"
shared_hooks="$(realpath "$repo_root/../../.githooks")"

git config core.hooksPath ../../.githooks

cat > "$shared_hooks/pre-push" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
project_hook="$repo_root/scripts/hooks/pre-push-stock-dashboard.sh"
if [ -x "$project_hook" ]; then
  exec "$project_hook"
fi
HOOK

chmod +x "$shared_hooks/pre-push"
chmod +x \
  "$repo_root/scripts/check-agent-constraints.sh" \
  "$repo_root/scripts/test-runtime-integration.sh" \
  "$repo_root/scripts/hooks/pre-push-stock-dashboard.sh"

echo "Installed stock_dashboard pre-push hook at $shared_hooks/pre-push"
