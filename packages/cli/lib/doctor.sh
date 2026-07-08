# shellcheck shell=bash
# doctor.sh — check corral's dependencies and update it to the latest main.

doctor_usage() {
  cat <<'EOF'
corral doctor — check that corral is healthy and up to date.

Verifies the runtime dependencies (herdr, jq, git) are installed, reports
on the herdr server and config file, then fast-forwards the corral
installation to the latest main from its origin remote.

The update step only ever fast-forwards a clean checkout that is on main;
a dev checkout (other branch, or local changes) is left alone with a note.

Usage:
  corral doctor [options]

Options:
  --no-update    Run the checks only; never touch the installation.

Exit status: 0 when every required dependency is present and the update
step succeeded (or was safely skipped), 1 otherwise.

Examples:
  corral doctor
  corral doctor --no-update
EOF
}

# First line of `<dep> --version`, or nothing — purely cosmetic.
_doctor_version_of() {
  "$1" --version 2>/dev/null | head -n1 || true
}

# Fast-forward the corral checkout at $1 to origin/main. Prints its findings;
# returns 1 only on a real failure (fetch/pull error), 0 when up to date,
# updated, or safely skipped.
_doctor_update() {
  local root="$1"

  if ! git -C "$root" rev-parse --git-dir >/dev/null 2>&1; then
    warn "install at $root is not a git checkout — cannot self-update"
    info "  reinstall with: curl -fsSL https://raw.githubusercontent.com/jsutter909/corral/main/install.sh | bash"
    return 0
  fi

  local branch
  branch="$(git -C "$root" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  if [ "$branch" != "main" ]; then
    warn "skipping update: checkout is on '${branch:-?}', not main (dev checkout?)"
    return 0
  fi
  if [ -n "$(git -C "$root" status --porcelain 2>/dev/null)" ]; then
    warn "skipping update: checkout at $root has local changes"
    return 0
  fi

  info "fetching origin main"
  if ! git -C "$root" fetch --quiet origin main; then
    warn "could not fetch origin main (offline? no remote?)"
    return 1
  fi

  if git -C "$root" merge-base --is-ancestor origin/main HEAD 2>/dev/null; then
    ok "corral is up to date (v$CORRAL_VERSION, $(git -C "$root" rev-parse --short HEAD))"
    return 0
  fi

  if ! git -C "$root" merge-base --is-ancestor HEAD origin/main 2>/dev/null; then
    warn "skipping update: local main has diverged from origin/main"
    return 0
  fi

  if ! git -C "$root" pull --quiet --ff-only origin main; then
    warn "fast-forward to origin/main failed"
    return 1
  fi

  # Report the freshly pulled version, not the one this process loaded.
  local newver
  newver="$(sed -n 's/^CORRAL_VERSION="\(.*\)"$/\1/p' "$root/packages/cli/lib/common.sh" 2>/dev/null || true)"
  ok "updated corral to latest main (v${newver:-?}, $(git -C "$root" rev-parse --short HEAD))"
}

cmd_doctor() {
  local do_update=1
  while [ $# -gt 0 ]; do
    case "$1" in
      -h|--help)   doctor_usage; return 0 ;;
      --no-update) do_update=0; shift ;;
      -*) die "unknown option: $1 (try 'corral doctor --help')" ;;
      *)  die "unexpected argument: $1" ;;
    esac
  done

  local failed=0

  # --- required dependencies (unlike require_deps, report every one) --------
  info "dependencies"
  local dep ver
  for dep in herdr jq git; do
    if command -v "$dep" >/dev/null 2>&1; then
      ver="$(_doctor_version_of "$dep")"
      ok "$dep — $(command -v "$dep")${ver:+ ($ver)}"
    else
      warn "$dep — not found on PATH"
      failed=1
    fi
  done
  if [ "$failed" -ne 0 ]; then
    info "  corral needs herdr, jq, and git. herdr: https://herdr.dev"
  fi

  # --- environment (informational; never fails the doctor) ------------------
  info "environment"
  if command -v herdr >/dev/null 2>&1; then
    if herdr status server >/dev/null 2>&1; then
      ok "herdr server is reachable"
    else
      warn "herdr server is not reachable (spawn/ls/close need one running)"
    fi
  fi
  if [ -f "$CORRAL_CONFIG" ]; then
    ok "config: $CORRAL_CONFIG"
  else
    info "  no config file at $CORRAL_CONFIG (defaults in effect — that's fine)"
  fi

  # --- self-update to the latest main ----------------------------------------
  local root
  root="$(cd -P "$CORRAL_LIB_DIR/../../.." >/dev/null 2>&1 && pwd)"
  if [ "$do_update" -eq 1 ]; then
    info "update"
    if command -v git >/dev/null 2>&1; then
      _doctor_update "$root" || failed=1
    else
      warn "skipping update: git is not installed"
    fi
  fi

  if [ "$failed" -ne 0 ]; then
    die "doctor found problems (see above)"
  fi
  ok "corral is healthy"
}
