#!/usr/bin/env bash
#
# pm-shell installer.
#
# One script, three jobs:
#   1. Make sure uv (and a compatible Python) are available.
#   2. Install the `pm` CLI globally from this checkout. The source is copied
#      into uv's tool environment, so `pm` keeps working from any directory
#      even if this repo is later moved or deleted. Pass --dev to install in
#      editable mode instead (useful when hacking on pm-shell itself).
#   3. Prompt for your Jira credentials and write them to
#      $XDG_CONFIG_HOME/pm-shell/secrets.json (default: ~/.config/pm-shell/).
#
# Safe to re-run: an existing pm install is refreshed in place, and the
# secrets file is only rewritten if you confirm.

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/pm-shell"
readonly SECRETS_FILE="$CONFIG_DIR/secrets.json"
readonly PYTHON_CONSTRAINT=">=3.11"
readonly UV_INSTALLER_URL="https://astral.sh/uv/install.sh"
readonly TOKEN_HELP_URL="https://id.atlassian.com/manage-profile/security/api-tokens"

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

if [[ -t 1 ]]; then
    BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'
    GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BLUE=$'\033[34m'
    RESET=$'\033[0m'
else
    BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; BLUE=""; RESET=""
fi

step() { printf '\n%s==>%s %s%s%s\n'    "$BLUE"   "$RESET" "$BOLD" "$*" "$RESET"; }
ok()   { printf   '  %s✓%s %s\n'        "$GREEN"  "$RESET" "$*"; }
warn() { printf   '  %s!%s %s\n'        "$YELLOW" "$RESET" "$*"; }
note() { printf   '  %s%s%s\n'          "$DIM"    "$*"     "$RESET"; }
die()  { printf '\n%s✗%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }

confirm() {
    # confirm "Prompt text" [default=N]
    local prompt=$1 default=${2:-N} reply suffix
    suffix=$([[ "$default" =~ ^[Yy]$ ]] && echo "[Y/n]" || echo "[y/N]")
    printf '  %s %s ' "$prompt" "$suffix"
    IFS= read -r reply || reply=""
    reply=${reply:-$default}
    [[ "$reply" =~ ^[Yy]$ ]]
}

# ---------------------------------------------------------------------------
# 1. Toolchain
# ---------------------------------------------------------------------------

ensure_uv() {
    step "Checking for uv"
    if command -v uv >/dev/null 2>&1; then
        ok "uv $(uv --version | awk '{print $2}')"
        return
    fi

    warn "uv is not installed."
    note "uv is the Python toolchain manager pm-shell uses to install \`pm\`."
    if ! confirm "Install it now from $UV_INSTALLER_URL?"; then
        die "uv is required. Install it manually, then re-run ./install.sh"
    fi

    curl -LsSf "$UV_INSTALLER_URL" | sh

    # The installer drops uv into ~/.local/bin (or ~/.cargo/bin on some setups)
    # and updates shell rc files — but the current shell hasn't been reloaded.
    # Probe the well-known locations so we can keep going in this session.
    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [[ -x "$candidate" ]]; then
            export PATH="$(dirname "$candidate"):$PATH"
            break
        fi
    done

    command -v uv >/dev/null 2>&1 \
        || die "uv installed but not on PATH. Open a new terminal and re-run ./install.sh"
    ok "uv $(uv --version | awk '{print $2}') installed"
}

ensure_python() {
    step "Checking for Python $PYTHON_CONSTRAINT"
    local py
    py=$(uv python find "$PYTHON_CONSTRAINT" 2>/dev/null || true)
    if [[ -z "$py" ]]; then
        note "No matching Python found. Asking uv to download one…"
        uv python install 3.11
        py=$(uv python find "$PYTHON_CONSTRAINT")
    fi
    ok "Python $("$py" --version 2>&1 | awk '{print $2}') ($py)"
}

# ---------------------------------------------------------------------------
# 2. Install pm globally
# ---------------------------------------------------------------------------

install_cli() {
    local mode_label="standalone (repo-independent)"
    local install_args=("--force")
    if [[ "$EDITABLE_INSTALL" == "1" ]]; then
        mode_label="editable (live-tracks $SCRIPT_DIR)"
        install_args+=("--editable")
    fi

    step "Installing the pm CLI — $mode_label"
    (cd "$SCRIPT_DIR" && uv tool install "${install_args[@]}" .)

    if command -v pm >/dev/null 2>&1; then
        ok "pm is on PATH at $(command -v pm)"
    else
        warn "pm was installed but isn't on your PATH yet."
        note "Run 'uv tool update-shell' and open a new terminal to fix it."
    fi

    if [[ "$EDITABLE_INSTALL" != "1" ]]; then
        note "Source copied to uv's tool env — this repo can be moved or deleted."
    fi
}

# ---------------------------------------------------------------------------
# 3. Credentials
# ---------------------------------------------------------------------------

prompt_value() {
    # prompt_value VAR_NAME "Label" ["default value"]
    local var=$1 label=$2 default=${3:-} reply
    if [[ -n "$default" ]]; then
        printf '  %s%s%s [%s]: ' "$BOLD" "$label" "$RESET" "$default"
    else
        printf '  %s%s%s: ' "$BOLD" "$label" "$RESET"
    fi
    IFS= read -r reply || reply=""
    reply=${reply:-$default}
    [[ -n "$reply" ]] || die "$label is required."
    printf -v "$var" '%s' "$reply"
}

prompt_secret() {
    # prompt_secret VAR_NAME "Label"
    local var=$1 label=$2 reply
    printf '  %s%s%s (hidden): ' "$BOLD" "$label" "$RESET"
    IFS= read -rs reply || reply=""
    printf '\n'
    [[ -n "$reply" ]] || die "$label is required."
    printf -v "$var" '%s' "$reply"
}

read_existing_field() {
    # read_existing_field FIELD — returns empty if the file or field is missing.
    local field=$1
    [[ -f "$SECRETS_FILE" ]] || return 0
    python3 - "$SECRETS_FILE" "$field" <<'PY' 2>/dev/null || true
import json, sys
try:
    print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))
except Exception:
    pass
PY
}

write_secrets_file() {
    # write_secrets_file BASE_URL EMAIL TOKEN
    mkdir -p "$CONFIG_DIR"
    PM_BASE_URL=$1 PM_EMAIL=$2 PM_TOKEN=$3 python3 - "$SECRETS_FILE" <<'PY'
import json, os, sys
payload = {
    "baseUrl":  os.environ["PM_BASE_URL"],
    "email":    os.environ["PM_EMAIL"],
    "apiToken": os.environ["PM_TOKEN"],
}
with open(sys.argv[1], "w") as f:
    json.dump(payload, f, indent=2)
    f.write("\n")
PY
    chmod 600 "$SECRETS_FILE"
}

configure_credentials() {
    step "Configuring credentials at $SECRETS_FILE"

    local existing_base existing_email
    existing_base=$(read_existing_field baseUrl)
    existing_email=$(read_existing_field email)

    if [[ -f "$SECRETS_FILE" ]]; then
        note "Existing credentials found:"
        note "  baseUrl: ${existing_base:-(unset)}"
        note "  email:   ${existing_email:-(unset)}"
        note "  apiToken: (hidden)"
        if ! confirm "Overwrite them?"; then
            ok "Keeping existing $SECRETS_FILE"
            return
        fi
    fi

    note "Get an API token at $TOKEN_HELP_URL"
    local base_url email token
    prompt_value  base_url "Jira base URL (e.g. https://acme.atlassian.net)" "$existing_base"
    prompt_value  email    "Atlassian account email"                          "$existing_email"
    prompt_secret token    "API token"

    write_secrets_file "$base_url" "$email" "$token"
    ok "Wrote $SECRETS_FILE (chmod 600)"
}

# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: ./install.sh [--dev] [-h|--help]

Installs the pm CLI globally and writes Jira credentials to
$SECRETS_FILE.

Options:
  --dev       Install editable (pm tracks changes in this checkout).
              Default is a standalone install so the repo can be deleted.
  -h, --help  Show this message.
EOF
}

EDITABLE_INSTALL=0

parse_args() {
    while (($#)); do
        case "$1" in
            --dev)        EDITABLE_INSTALL=1 ;;
            -h|--help)    usage; exit 0 ;;
            *)            usage >&2; die "Unknown argument: $1" ;;
        esac
        shift
    done
}

main() {
    parse_args "$@"

    printf '%spm-shell installer%s\n' "$BOLD" "$RESET"
    printf '%sRepo: %s%s\n' "$DIM" "$SCRIPT_DIR" "$RESET"

    ensure_uv
    ensure_python
    install_cli
    configure_credentials

    step "Done"
    ok "Run 'pm --help' to get started."
    note "Next: 'pm create' to register a Jira project, then 'pm clone --space <name>' in any directory."
}

main "$@"
