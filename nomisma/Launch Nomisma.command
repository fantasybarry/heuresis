#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
if ! python3 -B launch.py; then
  read -r "?Press Return to close."
  exit 1
fi
