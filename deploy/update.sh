#!/usr/bin/env bash
#
# deploy/update.sh — Atalho para atualizar uma instalação já feita
#
# Equivale a: sudo bash deploy/install.sh --action update [--dir DIR] [--user USER]
# Mantido como comando curto porque é a operação mais comum no dia a dia.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/install.sh" --action update "$@"
