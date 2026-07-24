#!/usr/bin/env bash
#
# deploy/update.sh — Atualiza uma instalação já feita pelo install.sh
#
# Uso:
#   sudo bash deploy/update.sh [--dir /opt/projeto_saida] [--user projeto_saida]
#
set -euo pipefail

INSTALL_DIR="/opt/projeto_saida"
SYS_USER="projeto_saida"

while [ $# -gt 0 ]; do
    case "$1" in
        --dir) INSTALL_DIR="$2"; shift 2 ;;
        --user) SYS_USER="$2"; shift 2 ;;
        -h|--help)
            echo "Uso: sudo bash deploy/update.sh [--dir DIR] [--user USER]"
            exit 0 ;;
        *) echo "Opção desconhecida: $1" >&2; exit 1 ;;
    esac
done

[ "$(id -u)" -eq 0 ] || { echo "Rode como root (sudo)." >&2; exit 1; }
[ -d "$INSTALL_DIR/.git" ] || { echo "$INSTALL_DIR não parece uma instalação válida (sem .git)." >&2; exit 1; }

echo "==> Baixando última versão"
sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git pull"

echo "==> Atualizando dependências Python"
sudo -u "$SYS_USER" -H bash -c "
    cd '$INSTALL_DIR'
    source venv/bin/activate
    pip install -r requirements.txt -q
"

echo "==> Aplicando migrações de banco pendentes (se houver)"
sudo -u "$SYS_USER" -H bash -c "
    set -a; source '$INSTALL_DIR/.env'; set +a
    cd '$INSTALL_DIR'
    source venv/bin/activate
    flask db upgrade
"

echo "==> Reiniciando serviço"
systemctl restart projeto-saida
systemctl --no-pager --lines=5 status projeto-saida

echo
echo "Atualização concluída. Logs: journalctl -u projeto-saida -f"
