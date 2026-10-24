#!/usr/bin/env bash
# Register a Making Things self-hosted GitHub Actions runner for Godot CI/e2e.
#
# Required env:
#   RUNNER_TOKEN  — registration token from
#                   Repo → Settings → Actions → Runners → New self-hosted runner
# Optional env:
#   REPO_URL      — default https://github.com/Tzeke000/CC-experments
#   RUNNER_NAME   — default $(hostname)-mt-godot
#   RUNNER_LABELS — default self-hosted,making-things,godot
#   RUNNER_DIR    — default $HOME/actions-runner
#   INSTALL_GODOT — default 1 (download Godot 4.7.2 + xvfb)
#   GODOT_VERSION — default 4.7.2-stable
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Tzeke000/CC-experments}"
RUNNER_NAME="${RUNNER_NAME:-$(hostname)-mt-godot}"
RUNNER_LABELS="${RUNNER_LABELS:-self-hosted,making-things,godot}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"
INSTALL_GODOT="${INSTALL_GODOT:-1}"
GODOT_VERSION="${GODOT_VERSION:-4.7.2-stable}"

if [[ -z "${RUNNER_TOKEN:-}" ]]; then
  cat >&2 <<'EOF'
RUNNER_TOKEN is required.

1. Open: Repo → Settings → Actions → Runners → New self-hosted runner (Linux x64)
2. Copy the token from the config script shown on that page
3. Re-run:
     export RUNNER_TOKEN='...'
     bash scripts/ci/setup-github-runner.sh
EOF
  exit 1
fi

echo "== Installing deps (curl, tar, libicu if needed) =="
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    curl tar libicu74 libicu-dev 2>/dev/null \
    || sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq curl tar libicu70 || true
  if [[ "$INSTALL_GODOT" == "1" ]]; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq xvfb unzip
  fi
fi

if [[ "$INSTALL_GODOT" == "1" ]]; then
  echo "== Godot ${GODOT_VERSION} =="
  DEST="${GODOT_INSTALL_DIR:-$HOME/godot}"
  mkdir -p "$DEST" /tmp/godot-dl
  cd /tmp/godot-dl
  asset="Godot_v${GODOT_VERSION}_linux.x86_64.zip"
  if [[ ! -x "$DEST/Godot_v${GODOT_VERSION}_linux.x86_64" ]]; then
    curl -fsSL -o "$asset" \
      "https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}/${asset}"
    unzip -o -q "$asset" -d "$DEST"
    chmod +x "$DEST/Godot_v${GODOT_VERSION}_linux.x86_64"
  fi
  mkdir -p /opt/godot 2>/dev/null || true
  if [[ -w /opt/godot ]] || sudo mkdir -p /opt/godot; then
    sudo ln -sfn "$DEST/Godot_v${GODOT_VERSION}_linux.x86_64" /opt/godot/godot || \
      ln -sfn "$DEST/Godot_v${GODOT_VERSION}_linux.x86_64" "$HOME/godot/godot"
  fi
  echo "Export GODOT_BIN=$DEST/Godot_v${GODOT_VERSION}_linux.x86_64 (or set repo var GODOT_BIN=/opt/godot/godot)"
fi

echo "== GitHub Actions runner → $RUNNER_DIR =="
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"
# Latest stable runner release (pin bump as needed)
RUNNER_VER="${ACTIONS_RUNNER_VERSION:-2.328.0}"
if [[ ! -f ./config.sh ]]; then
  curl -fsSL -o actions-runner-linux-x64.tar.gz \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VER}/actions-runner-linux-x64-${RUNNER_VER}.tar.gz"
  tar xzf actions-runner-linux-x64.tar.gz
fi

if [[ ! -f .runner ]]; then
  ./config.sh --unattended \
    --url "$REPO_URL" \
    --token "$RUNNER_TOKEN" \
    --name "$RUNNER_NAME" \
    --labels "$RUNNER_LABELS" \
    --work "_work" \
    --replace
fi

echo "== Next steps =="
cat <<EOF
1. Start the runner (foreground):
     cd $RUNNER_DIR && ./run.sh

   Or install as a service:
     cd $RUNNER_DIR && sudo ./svc.sh install && sudo ./svc.sh start

2. In GitHub → Settings → Actions → Variables, set:
     MT_CI_RUNS_ON  = ["self-hosted","making-things","godot"]
     MT_E2E_RUNS_ON = ["self-hosted","making-things","godot"]
     GODOT_BIN      = /opt/godot/godot   # if the symlink was created

3. Leave those variables UNSET to keep using ubuntu-latest (safe default).

4. Dispatch workflow "ci" or "e2e" and confirm the job runs on: $RUNNER_NAME
EOF
