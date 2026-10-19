#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! /usr/bin/python3 -c 'import pygame; from pygame._sdl2 import controller' >/dev/null 2>&1; then
  echo 'Install the Ubuntu dependencies first:'
  echo '  sudo apt update'
  echo '  sudo apt install python3 python3-pygame'
  exit 1
fi
exec /usr/bin/python3 controller_hub.py "$@"
