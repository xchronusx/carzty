#!/usr/bin/env bash
##xchronusx
# ==============================================================================
#  carzty.install.zw.sh - one-line Carzty installer for Linux and macOS
#
#  Synopsis:
#    curl -fsSL https://raw.githubusercontent.com/xchronusx/carzty/main/scripts/linux/carzty.install.zw.sh | bash
#
#  Description:
#    1. downloads Carzty to ~/carzty (or $CARZTY_DIR). does a git pull instead if it's a checkout
#    2. builds a venv and installs the requirements
#    3. runs the setup wizard: token (checked with Discord), timezone, tone, invite link
#    4. Linux + systemd: offers to install a user service so it runs in the background and
#       comes back after reboots. no root needed for the service itself
#    Run it again any time to update. .env, data and logs are left alone.
#
#  Notes:
#    Author:       Zachary Wright (xchronusx)
#    Project:      Carzty - https://github.com/xchronusx/carzty
#    License:      MIT
#    Disclaimer:   provided as-is, no warranty. read scripts before you pipe them into bash. yes, this one too.
#    Requirements: python 3.10+ with venv (debian/ubuntu: sudo apt install python3 python3-venv), curl or git
#    Env knobs:    CARZTY_DIR        install folder (default ~/carzty)
#                  CARZTY_BRANCH     branch to grab (default main)
#                  CARZTY_TOKEN      bot token, for fully unattended installs (skips the questions)
#                  CARZTY_NO_SERVICE set to 1 to skip the systemd question
#                  CARZTY_SRC        copy from this local folder instead of downloading (offline / testing)
# ==============================================================================

set -euo pipefail

REPO="xchronusx/carzty"

#region HELPERS

if [ -t 1 ]; then
  C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_DIM=$'\033[2m'; C_HI=$'\033[36m'; C_OFF=$'\033[0m'
else
  C_OK=""; C_WARN=""; C_ERR=""; C_DIM=""; C_HI=""; C_OFF=""
fi

say()  { printf '%s\n' "  $*"; }
ok()   { printf '%s\n' "  ${C_OK}ok${C_OFF}  $*"; }
warn() { printf '%s\n' "  ${C_WARN}!!${C_OFF}  $*"; }
die()  { printf '%s\n' "  ${C_ERR}xx${C_OFF}  $*" >&2; exit 1; }

# piped into bash means stdin is the script, so questions have to come from the terminal
have_tty() { [ -r /dev/tty ] && { : </dev/tty; } 2>/dev/null; }

ask_yes() {
  # ask_yes "question" [default y|n]
  local q="$1" def="${2:-y}" hint answer
  if [ "$def" = "y" ]; then hint="[Y/n]"; else hint="[y/N]"; fi
  if ! have_tty || [ -n "${CARZTY_TOKEN:-}" ]; then [ "$def" = "y" ]; return; fi
  while true; do
    printf '  %s %s ' "$q" "$hint" >/dev/tty
    read -r answer </dev/tty || answer=""
    answer="$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')"
    case "$answer" in
      "") [ "$def" = "y" ]; return ;;
      y|yes) return 0 ;;
      n|no) return 1 ;;
      *) say "y or n. it's not a trick question." ;;
    esac
  done
}

#endregion

#region STEPS

find_python() {
  local cand
  for cand in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$cand" >/dev/null 2>&1 \
      && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      command -v "$cand"
      return 0
    fi
  done
  return 1
}

get_code() {
  local dir="$1" branch="$2"
  if [ -n "${CARZTY_SRC:-}" ]; then
    say "copying from $CARZTY_SRC"
    mkdir -p "$dir"
    (cd "$CARZTY_SRC" && tar cf - --exclude=.venv --exclude=.git --exclude=data --exclude=logs --exclude=.env .) | (cd "$dir" && tar xf -)
    return
  fi
  if [ -d "$dir/.git" ] && command -v git >/dev/null 2>&1; then
    say "found a git checkout, pulling the latest"
    git -C "$dir" pull --ff-only || die "git pull failed. sort out your local changes and run this again"
    return
  fi

  local url="https://github.com/$REPO/archive/refs/heads/$branch.tar.gz"
  say "downloading $url"
  mkdir -p "$dir"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" | tar xz -C "$dir" --strip-components=1
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$url" | tar xz -C "$dir" --strip-components=1
  else
    die "need curl or wget to download. or git. something."
  fi
}

install_service() {
  local dir="$1" unit_dir="$HOME/.config/systemd/user"
  mkdir -p "$unit_dir"
  cat >"$unit_dir/carzty.service" <<EOF
##xchronusx
# written by carzty.install.zw.sh. rerun the installer to regenerate it.
[Unit]
Description=Carzty - Discord bot that nags you until you do the thing

[Service]
Type=simple
WorkingDirectory=$dir
ExecStart=$dir/.venv/bin/python -m carzty
Restart=on-failure
RestartSec=10
# exit 1 = bad config, 2 = bad token. restarting fixes neither
RestartPreventExitStatus=1 2

[Install]
WantedBy=default.target
##xchronusx
EOF
  systemctl --user daemon-reload
  systemctl --user enable carzty >/dev/null 2>&1
  systemctl --user restart carzty
  ok "service installed and running"

  # without linger, user services die when you log out and don't start at boot
  if [ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || echo no)" != "yes" ]; then
    say "To keep it running after you log out (and start at boot), 'linger' needs to be on for your user."
    if ask_yes "Turn it on now? (might ask for your sudo password)" y; then
      loginctl enable-linger "$USER" 2>/dev/null || sudo loginctl enable-linger "$USER" \
        || warn "couldn't turn on linger. run: sudo loginctl enable-linger $USER"
    fi
  fi
}

#endregion

main() {
  local dir="${CARZTY_DIR:-$HOME/carzty}" branch="${CARZTY_BRANCH:-main}" py venv_py

  printf '\n  %sCarzty installer%s\n  %sa Discord bot that nags you until you do the thing%s\n\n' "$C_HI" "$C_OFF" "$C_DIM" "$C_OFF"
  say "installing to $dir"

  #region 1. PYTHON
  py="$(find_python)" || {
    case "$(uname -s)" in
      Darwin) die "need python 3.10+. easiest: brew install python@3.12  (or grab it from python.org)" ;;
      *) die "need python 3.10+. debian/ubuntu: sudo apt install python3 python3-venv | fedora: sudo dnf install python3" ;;
    esac
  }
  ok "python: $py ($("$py" -c 'import platform; print(platform.python_version())'))"
  "$py" -c 'import venv, ensurepip' 2>/dev/null \
    || die "python's venv module is missing. debian/ubuntu: sudo apt install python3-venv"
  #endregion

  #region 2. CODE
  get_code "$dir" "$branch"
  [ -f "$dir/requirements.txt" ] || die "download looks broken, no requirements.txt in $dir"
  ok "code's in place"
  #endregion

  #region 3. VENV
  if [ ! -x "$dir/.venv/bin/python" ]; then
    say "building the venv"
    "$py" -m venv "$dir/.venv"
  fi
  venv_py="$dir/.venv/bin/python"
  "$venv_py" -m pip install --quiet --disable-pip-version-check --upgrade pip
  "$venv_py" -m pip install --quiet --disable-pip-version-check -r "$dir/requirements.txt"
  ok "packages installed"
  #endregion

  #region 4. WIZARD
  if [ -n "${CARZTY_TOKEN:-}" ]; then
    (cd "$dir" && "$venv_py" -m carzty setup --token "$CARZTY_TOKEN" --yes)
  elif [ -f "$dir/.env" ] && ! have_tty; then
    say ".env already there and no terminal to ask questions on, keeping it"
  elif have_tty; then
    (cd "$dir" && "$venv_py" -m carzty setup </dev/tty)
  else
    die "no terminal to ask questions on. rerun with CARZTY_TOKEN=your-token set"
  fi
  (cd "$dir" && "$venv_py" -m carzty check >/dev/null) || die "config check failed. run: cd $dir && .venv/bin/python -m carzty setup"
  ok "config checks out"
  #endregion

  #region 5. SERVICE
  local service=no
  if [ "$(uname -s)" = "Linux" ] && [ -z "${CARZTY_NO_SERVICE:-}" ] && command -v systemctl >/dev/null 2>&1 \
    && systemctl --user show-environment >/dev/null 2>&1; then
    if [ -f "$HOME/.config/systemd/user/carzty.service" ] || ask_yes "Run Carzty in the background and start it automatically?" y; then
      install_service "$dir"
      service=yes
    fi
  fi
  #endregion

  printf '\n'
  say "${C_HI}Carzty lives in:${C_OFF} $dir"
  if [ "$service" = "yes" ]; then
    say "logs:      journalctl --user -u carzty -f"
    say "stop/start: systemctl --user stop carzty / systemctl --user start carzty"
    say "uninstall: systemctl --user disable --now carzty && rm -rf $dir ~/.config/systemd/user/carzty.service"
  else
    say "run it:    cd $dir && .venv/bin/python -m carzty"
    say "           (in tmux/screen if you want it to survive closing the terminal, or use Docker)"
    say "uninstall: rm -rf $dir"
  fi
  say "settings:  cd $dir && .venv/bin/python -m carzty setup"
  say "update:    run this same one-liner again"
  printf '\n'
}

# everything's inside main() so a half-downloaded script can't run half its commands
main "$@"
##xchronusx
