#!/usr/bin/env bash
#
# deploy/install.sh — Instalador guiado do Sistema de Controle de Saídas
# =======================================================================
#
# Sobe o projeto do zero numa VM Ubuntu/Debian: pacotes do sistema,
# usuário dedicado, código, venv, banco de dados, systemd, Nginx e
# certificado HTTPS gratuito (Let's Encrypt) — sem precisar editar nada
# na mão.
#
# Uso:
#   sudo bash deploy/install.sh
#
# Também aceita flags para pular as perguntas (útil em automação/CI):
#   sudo bash deploy/install.sh --dir /opt/projeto_saida --user projeto_saida \
#       --repo https://github.com/Gerson-if/projeto_saida.git \
#       --domain saida.exemplo.com.br --email voce@exemplo.com \
#       --db mariadb --workers 2 --yes
#
# Rodar de novo é seguro (idempotente na maior parte dos passos) — útil
# se algo falhar no meio e você quiser continuar de onde parou.
#
set -euo pipefail

# ── Aparência ────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    C_RESET="\033[0m"; C_BOLD="\033[1m"; C_GREEN="\033[32m"
    C_YELLOW="\033[33m"; C_RED="\033[31m"; C_BLUE="\033[34m"
else
    C_RESET=""; C_BOLD=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BLUE=""
fi

log()  { echo -e "${C_BLUE}${C_BOLD}==>${C_RESET} $*"; }
ok()   { echo -e "${C_GREEN}✔${C_RESET} $*"; }
warn() { echo -e "${C_YELLOW}⚠${C_RESET}  $*"; }
err()  { echo -e "${C_RED}✘ $*${C_RESET}" >&2; }
die()  { err "$*"; exit 1; }

# ── Valores padrão (sobrescrevíveis por flag ou pergunta interativa) ─────
INSTALL_DIR="/opt/projeto_saida"
SYS_USER="projeto_saida"
REPO_URL="https://github.com/Gerson-if/projeto_saida.git"
DOMAIN=""
EMAIL=""
DB_BACKEND=""            # sqlite | mariadb
DB_NAME="projeto_saida"
DB_USER="projeto_saida"
DB_PASS=""
WORKERS="1"
ADMIN_NOME=""
ADMIN_CPF=""
ADMIN_SENHA=""
ASSUME_YES="0"
NON_INTERACTIVE="0"
SKIP_SSL="0"

usage() {
    grep -E '^#( |$)' "${BASH_SOURCE[0]}" | sed -E 's/^# ?//' | head -n 20
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dir) INSTALL_DIR="$2"; shift 2 ;;
        --user) SYS_USER="$2"; shift 2 ;;
        --repo) REPO_URL="$2"; shift 2 ;;
        --domain) DOMAIN="$2"; shift 2 ;;
        --email) EMAIL="$2"; shift 2 ;;
        --db) DB_BACKEND="$2"; shift 2 ;;
        --workers) WORKERS="$2"; shift 2 ;;
        --admin-nome) ADMIN_NOME="$2"; shift 2 ;;
        --admin-cpf) ADMIN_CPF="$2"; shift 2 ;;
        --admin-senha) ADMIN_SENHA="$2"; shift 2 ;;
        --skip-ssl) SKIP_SSL="1"; shift ;;
        --yes|-y) ASSUME_YES="1"; NON_INTERACTIVE="1"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Opção desconhecida: $1 (use --help)" ;;
    esac
done

[ "$(id -u)" -eq 0 ] || die "Rode como root (ex: sudo bash deploy/install.sh)."

# ── Helpers de pergunta interativa ───────────────────────────────────────
ask() {
    # ask "pergunta" "padrão" -> imprime resposta em $REPLY_VAL
    local pergunta="$1" padrao="${2:-}"
    if [ "$NON_INTERACTIVE" = "1" ]; then
        REPLY_VAL="$padrao"
        return
    fi
    local resp
    if [ -n "$padrao" ]; then
        read -r -p "$(echo -e "${C_BOLD}${pergunta}${C_RESET} [${padrao}]: ")" resp || true
    else
        read -r -p "$(echo -e "${C_BOLD}${pergunta}${C_RESET}: ")" resp || true
    fi
    REPLY_VAL="${resp:-$padrao}"
}

ask_secret() {
    local pergunta="$1"
    if [ "$NON_INTERACTIVE" = "1" ]; then
        REPLY_VAL=""
        return
    fi
    local resp
    read -r -s -p "$(echo -e "${C_BOLD}${pergunta}${C_RESET}: ")" resp || true
    echo
    REPLY_VAL="$resp"
}

yesno() {
    # yesno "pergunta" "s|n(padrão)" -> retorna 0 se sim
    local pergunta="$1" padrao="${2:-s}"
    if [ "$ASSUME_YES" = "1" ]; then
        [ "$padrao" = "s" ] && return 0 || return 1
    fi
    local resp
    read -r -p "$(echo -e "${C_BOLD}${pergunta}${C_RESET} [s/n] (${padrao}): ")" resp || true
    resp="${resp:-$padrao}"
    [[ "$resp" =~ ^[sSyY] ]]
}

rand_hex() { python3 -c "import secrets; print(secrets.token_hex(${1:-16}))"; }
rand_pass() { python3 -c "import secrets,string; a=string.ascii_letters+string.digits; print(''.join(secrets.choice(a) for _ in range(${1:-20})))"; }

echo
echo -e "${C_BOLD}Sistema de Controle de Saídas — instalador guiado${C_RESET}"
echo "Este script prepara Ubuntu/Debian com Gunicorn + Nginx + HTTPS grátis."
echo

# ─────────────────────────────────────────────────────────────────────────
# 1. Detecção de SO
# ─────────────────────────────────────────────────────────────────────────
log "Verificando sistema operacional"
if [ -r /etc/os-release ]; then
    . /etc/os-release
    case "${ID:-}" in
        ubuntu|debian) ok "Detectado $PRETTY_NAME" ;;
        *) warn "SO '$PRETTY_NAME' não testado oficialmente (feito para Ubuntu/Debian). Continuando mesmo assim." ;;
    esac
else
    warn "Não foi possível detectar o SO. Continuando mesmo assim."
fi

# ─────────────────────────────────────────────────────────────────────────
# 2. Perguntas (puladas se --yes / flags já preenchidas)
# ─────────────────────────────────────────────────────────────────────────
if [ "$NON_INTERACTIVE" != "1" ]; then
    ask "Diretório de instalação" "$INSTALL_DIR"; INSTALL_DIR="$REPLY_VAL"
    ask "Usuário de sistema para rodar o app" "$SYS_USER"; SYS_USER="$REPLY_VAL"
    ask "URL do repositório git" "$REPO_URL"; REPO_URL="$REPLY_VAL"
fi

# Domínio / IP + HTTPS
PUBLIC_IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || true)"
if [ -z "$DOMAIN" ] && [ "$NON_INTERACTIVE" != "1" ]; then
    echo
    echo "Para HTTPS gratuito (Let's Encrypt) é preciso um nome de domínio"
    echo "que resolva para o IP desta VM — Let's Encrypt NÃO emite certificado"
    echo "para IP puro (ex: https://${PUBLIC_IP:-1.2.3.4})."
    if [ -n "$PUBLIC_IP" ]; then
        echo "IP público detectado desta VM: ${C_BOLD}${PUBLIC_IP}${C_RESET}"
    fi
    if yesno "Você já tem um domínio/subdomínio apontando para este IP?" "n"; then
        ask "Domínio (ex: saida.suaorganizacao.com.br)" ""
        DOMAIN="$REPLY_VAL"
    else
        if [ -n "$PUBLIC_IP" ]; then
            SUGESTAO="${PUBLIC_IP}.sslip.io"
            echo
            echo "Sem domínio próprio, dá pra usar um serviço de DNS público que"
            echo "resolve automaticamente para o IP embutido no nome — sem precisar"
            echo "configurar nada em lugar nenhum:"
            echo "   ${C_BOLD}${SUGESTAO}${C_RESET}  →  aponta para ${PUBLIC_IP}"
            if yesno "Usar '${SUGESTAO}' como domínio (permite HTTPS de verdade grátis)?" "s"; then
                DOMAIN="$SUGESTAO"
            fi
        fi
        if [ -z "$DOMAIN" ]; then
            warn "Sem domínio, vou gerar um certificado autoassinado — o navegador"
            warn "vai mostrar aviso de 'conexão não segura' até você configurar um"
            warn "domínio de verdade e rodar 'sudo certbot --nginx -d seu-dominio'."
            SKIP_SSL="1"
        fi
    fi
fi

if [ -n "$DOMAIN" ] && [ -z "$EMAIL" ] && [ "$NON_INTERACTIVE" != "1" ] && [ "$SKIP_SSL" != "1" ]; then
    ask "E-mail para avisos de expiração do certificado (Let's Encrypt)" ""
    EMAIL="$REPLY_VAL"
fi
[ -z "$DOMAIN" ] && DOMAIN="${PUBLIC_IP:-_}"

# Banco de dados
if [ -z "$DB_BACKEND" ]; then
    if [ "$NON_INTERACTIVE" = "1" ]; then
        DB_BACKEND="sqlite"
    else
        echo
        echo "Banco de dados:"
        echo "  1) SQLite   — mais simples, ótimo para times pequenos/uso único (padrão)"
        echo "  2) MariaDB  — recomendado se esperar mais carga/usuários simultâneos"
        ask "Escolha (1/2)" "1"
        [ "$REPLY_VAL" = "2" ] && DB_BACKEND="mariadb" || DB_BACKEND="sqlite"
    fi
fi

if [ "$DB_BACKEND" = "mariadb" ] && [ -z "$DB_PASS" ]; then
    DB_PASS="$(rand_pass 24)"
fi

if [ "$NON_INTERACTIVE" != "1" ]; then
    echo
    echo "Quantos workers do Gunicorn? Com 1 worker o agendador de status roda"
    echo "dentro do próprio processo (mais simples). Com mais de 1, o script"
    echo "desliga o agendador interno e usa um timer systemd equivalente."
    ask "Número de workers Gunicorn" "$WORKERS"
    WORKERS="$REPLY_VAL"
fi

# Admin inicial
if [ "$NON_INTERACTIVE" != "1" ]; then
    echo
    echo "Vamos criar o primeiro administrador do sistema."
    ask "Nome completo do administrador" "Administrador"
    ADMIN_NOME="$REPLY_VAL"
    ask "CPF do administrador (somente números)" "admin"
    ADMIN_CPF="$REPLY_VAL"
    while [ -z "$ADMIN_SENHA" ]; do
        ask_secret "Senha do administrador (não aparece na tela)"
        ADMIN_SENHA="$REPLY_VAL"
        [ -z "$ADMIN_SENHA" ] && warn "Senha não pode ficar vazia."
    done
else
    ADMIN_NOME="${ADMIN_NOME:-Administrador}"
    ADMIN_CPF="${ADMIN_CPF:-admin}"
    ADMIN_SENHA="${ADMIN_SENHA:-$(rand_pass 16)}"
fi

echo
log "Resumo da instalação"
cat <<EOF
  Diretório .......... $INSTALL_DIR
  Usuário de sistema .. $SYS_USER
  Repositório ......... $REPO_URL
  Domínio/host ........ $DOMAIN
  HTTPS (Let's Encrypt) $([ "$SKIP_SSL" = "1" ] && echo "não (certificado autoassinado)" || echo "sim")
  Banco de dados ...... $DB_BACKEND
  Workers Gunicorn .... $WORKERS
  Admin inicial ....... $ADMIN_NOME (cpf: $ADMIN_CPF)
EOF
echo
if ! yesno "Confirma e inicia a instalação?" "s"; then
    die "Instalação cancelada pelo usuário."
fi

# ─────────────────────────────────────────────────────────────────────────
# 3. Pacotes do sistema
# ─────────────────────────────────────────────────────────────────────────
log "Atualizando pacotes e instalando dependências do sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
PKGS=(python3 python3-venv python3-pip git nginx build-essential pkg-config curl ufw)
[ "$SKIP_SSL" != "1" ] && PKGS+=(certbot python3-certbot-nginx)
if [ "$DB_BACKEND" = "mariadb" ]; then
    PKGS+=(mariadb-server mariadb-client libmariadb-dev)
fi
apt-get install -y "${PKGS[@]}"
ok "Pacotes instalados"

# ─────────────────────────────────────────────────────────────────────────
# 4. Firewall
# ─────────────────────────────────────────────────────────────────────────
log "Configurando firewall (ufw)"
ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow 'Nginx Full' >/dev/null 2>&1 || true
if ! ufw status | grep -q "Status: active"; then
    ufw --force enable
fi
ok "Firewall ativo — só 22/80/443 liberadas; Gunicorn continua só em 127.0.0.1"

# ─────────────────────────────────────────────────────────────────────────
# 5. Usuário de sistema
# ─────────────────────────────────────────────────────────────────────────
log "Criando usuário de sistema '$SYS_USER' (sem login) e diretório $INSTALL_DIR"
if ! id "$SYS_USER" >/dev/null 2>&1; then
    useradd --system --create-home --shell /usr/sbin/nologin "$SYS_USER"
fi
mkdir -p "$INSTALL_DIR"
chown "$SYS_USER:$SYS_USER" "$INSTALL_DIR"
ok "Usuário e diretório prontos"

# ─────────────────────────────────────────────────────────────────────────
# 6. Código da aplicação
# ─────────────────────────────────────────────────────────────────────────
log "Obtendo código da aplicação"
if [ -d "$INSTALL_DIR/.git" ]; then
    warn "Repositório já existe em $INSTALL_DIR — atualizando com 'git pull'."
    sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git pull"
elif [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ] && [ ! -d "$INSTALL_DIR/.git" ]; then
    die "$INSTALL_DIR já existe e não é um repositório git. Esvazie a pasta ou escolha outro --dir."
else
    sudo -u "$SYS_USER" -H git clone "$REPO_URL" "$INSTALL_DIR"
fi
ok "Código em $INSTALL_DIR"

log "Criando ambiente virtual e instalando dependências Python"
sudo -u "$SYS_USER" -H bash -c "
    cd '$INSTALL_DIR'
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    pip install gunicorn -q
    if [ '$DB_BACKEND' = 'mariadb' ]; then
        pip install pymysql cryptography -q
    fi
"
ok "Dependências instaladas"

# ─────────────────────────────────────────────────────────────────────────
# 7. Banco de dados
# ─────────────────────────────────────────────────────────────────────────
DATABASE_URL=""
if [ "$DB_BACKEND" = "mariadb" ]; then
    log "Configurando MariaDB"
    systemctl enable --now mariadb >/dev/null 2>&1 || systemctl enable --now mysql
    # Idempotente: recria usuário/senha só se ainda não existir o banco.
    if ! mysql -u root -e "USE $DB_NAME" >/dev/null 2>&1; then
        mysql -u root <<SQL
CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';
GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
SQL
        ok "Banco '$DB_NAME' e usuário '$DB_USER' criados"
    else
        warn "Banco '$DB_NAME' já existe — mantendo como está."
    fi
    DATABASE_URL="mysql+pymysql://${DB_USER}:${DB_PASS}@localhost/${DB_NAME}"
else
    ok "Usando SQLite (criado automaticamente em instance/ na primeira execução)"
fi

# ─────────────────────────────────────────────────────────────────────────
# 8. Arquivo .env
# ─────────────────────────────────────────────────────────────────────────
log "Gerando .env de produção"
ENV_FILE="$INSTALL_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    warn ".env já existe — mantendo o existente sem sobrescrever (backup em .env.bak)."
    cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%s)"
else
    SECRET_KEY="$(rand_hex 32)"
    {
        echo "FLASK_ENV=production"
        echo "SECRET_KEY=$SECRET_KEY"
        [ -n "$DATABASE_URL" ] && echo "DATABASE_URL=$DATABASE_URL"
        echo "BEHIND_PROXY=true"
        if [ "$WORKERS" -gt 1 ] 2>/dev/null; then
            echo "SCHEDULER_ENABLED=false"
            echo "WEB_CONCURRENCY=$WORKERS"
        else
            echo "SCHEDULER_ENABLED=true"
            echo "WEB_CONCURRENCY=1"
        fi
    } > "$ENV_FILE"
    chown "$SYS_USER:$SYS_USER" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    ok ".env criado com SECRET_KEY própria desta instalação"
fi

# ─────────────────────────────────────────────────────────────────────────
# 9. Inicializa banco + admin
# ─────────────────────────────────────────────────────────────────────────
log "Inicializando tabelas e criando administrador"
sudo -u "$SYS_USER" -H bash -c "
    set -a; source '$ENV_FILE'; set +a
    cd '$INSTALL_DIR'
    source venv/bin/activate
    flask init-db
"
# create-admin falha se o cpf já existir — não tratamos como erro fatal.
if sudo -u "$SYS_USER" -H bash -c "
    set -a; source '$ENV_FILE'; set +a
    cd '$INSTALL_DIR'
    source venv/bin/activate
    flask create-admin '$ADMIN_NOME' '$ADMIN_CPF' '$ADMIN_SENHA'
" 2>/tmp/create_admin.err; then
    ok "Administrador '$ADMIN_CPF' criado"
else
    warn "Não foi possível criar o administrador (talvez já exista): $(tail -n1 /tmp/create_admin.err 2>/dev/null)"
fi

# ─────────────────────────────────────────────────────────────────────────
# 10. systemd — serviço web (Gunicorn)
# ─────────────────────────────────────────────────────────────────────────
log "Configurando serviço systemd do app"
sed \
    -e "s#/opt/projeto_saida#$INSTALL_DIR#g" \
    -e "s#User=projeto_saida#User=$SYS_USER#g" \
    -e "s#Group=projeto_saida#Group=$SYS_USER#g" \
    "$INSTALL_DIR/deploy/projeto-saida.service" > /etc/systemd/system/projeto-saida.service
systemctl daemon-reload
systemctl enable --now projeto-saida
ok "Serviço 'projeto-saida' ativo (journalctl -u projeto-saida -f para logs)"

if [ "$WORKERS" -gt 1 ] 2>/dev/null; then
    log "Mais de 1 worker: ativando timer systemd para status (evita job duplicado)"
    sed \
        -e "s#/opt/projeto_saida#$INSTALL_DIR#g" \
        -e "s#User=projeto_saida#User=$SYS_USER#g" \
        -e "s#Group=projeto_saida#Group=$SYS_USER#g" \
        "$INSTALL_DIR/deploy/projeto-saida-status.service" > /etc/systemd/system/projeto-saida-status.service
    cp "$INSTALL_DIR/deploy/projeto-saida-status.timer" /etc/systemd/system/projeto-saida-status.timer
    systemctl daemon-reload
    systemctl enable --now projeto-saida-status.timer
    ok "Timer de status ativo a cada 10min"
fi

# ─────────────────────────────────────────────────────────────────────────
# 11. Nginx
# ─────────────────────────────────────────────────────────────────────────
log "Configurando Nginx"
sed \
    -e "s#seu-dominio.com.br#$DOMAIN#g" \
    -e "s#/opt/projeto_saida#$INSTALL_DIR#g" \
    "$INSTALL_DIR/deploy/nginx.conf" > /etc/nginx/sites-available/projeto-saida
ln -sf /etc/nginx/sites-available/projeto-saida /etc/nginx/sites-enabled/projeto-saida
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
ok "Nginx servindo http://$DOMAIN (proxy para Gunicorn em 127.0.0.1:8000)"

# ─────────────────────────────────────────────────────────────────────────
# 12. HTTPS
# ─────────────────────────────────────────────────────────────────────────
if [ "$SKIP_SSL" = "1" ]; then
    warn "Pulando Let's Encrypt. Gerando certificado autoassinado só para não"
    warn "deixar a porta 443 sem nada — o navegador vai avisar que não confia nele."
    mkdir -p /etc/ssl/projeto-saida
    if [ ! -f /etc/ssl/projeto-saida/selfsigned.crt ]; then
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout /etc/ssl/projeto-saida/selfsigned.key \
            -out /etc/ssl/projeto-saida/selfsigned.crt \
            -subj "/CN=$DOMAIN" >/dev/null 2>&1
    fi
    cat >> /etc/nginx/sites-available/projeto-saida <<EOF

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name $DOMAIN;
    ssl_certificate     /etc/ssl/projeto-saida/selfsigned.crt;
    ssl_certificate_key /etc/ssl/projeto-saida/selfsigned.key;
    location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host \$host; }
}
EOF
    nginx -t && systemctl reload nginx
    echo
    warn "Assim que tiver um domínio de verdade apontando para este IP, rode:"
    warn "  sudo certbot --nginx -d SEU-DOMINIO -m SEU-EMAIL --agree-tos --redirect"
else
    log "Emitindo certificado HTTPS grátis via Let's Encrypt para $DOMAIN"
    CERTBOT_ARGS=(--nginx -d "$DOMAIN" --redirect --non-interactive --agree-tos)
    if [ -n "$EMAIL" ]; then
        CERTBOT_ARGS+=(-m "$EMAIL")
    else
        CERTBOT_ARGS+=(--register-unsafely-without-email)
    fi
    if certbot "${CERTBOT_ARGS[@]}"; then
        ok "HTTPS ativo em https://$DOMAIN — renovação automática já configurada"
        if certbot renew --dry-run >/tmp/certbot_dryrun.log 2>&1; then
            ok "Teste de renovação automática OK"
        else
            warn "Teste de renovação apresentou aviso — confira /tmp/certbot_dryrun.log"
        fi
    else
        warn "Certbot falhou (o domínio já resolve para este IP? porta 80 liberada?)."
        warn "O site continua acessível em http://$DOMAIN. Rode depois manualmente:"
        warn "  sudo certbot --nginx -d $DOMAIN"
    fi
fi

# ─────────────────────────────────────────────────────────────────────────
# 13. Diagnóstico final
# ─────────────────────────────────────────────────────────────────────────
log "Rodando diagnóstico interno do app"
sudo -u "$SYS_USER" -H bash -c "
    set -a; source '$ENV_FILE'; set +a
    cd '$INSTALL_DIR'
    source venv/bin/activate
    flask diagnosticar
" || warn "flask diagnosticar retornou avisos — revise acima."

echo
echo -e "${C_GREEN}${C_BOLD}Instalação concluída.${C_RESET}"
cat <<EOF

  URL ................ $([ "$SKIP_SSL" = "1" ] && echo "https://$DOMAIN (autoassinado) / http://$DOMAIN" || echo "https://$DOMAIN")
  Admin CPF .......... $ADMIN_CPF
  Admin senha ........ $([ -n "${ADMIN_SENHA:-}" ] && echo "$ADMIN_SENHA (ANOTE E GUARDE — não fica salva em nenhum arquivo)" )
  Diretório .......... $INSTALL_DIR
  .env ............... $ENV_FILE (permissão 600, só root/$SYS_USER leem)
  Serviço ............ systemctl status projeto-saida
  Logs systemd ....... journalctl -u projeto-saida -f
  Log da aplicação ... $INSTALL_DIR/instance/logs/app.log
  Atualizar depois ... sudo bash $INSTALL_DIR/deploy/update.sh

Próximos passos recomendados:
  - Configure backup do banco (veja deploy/DEPLOY.md, seção Backups).
  - Se usou domínio próprio, confirme o DNS antes de repetir --skip-ssl.
  - Guarde a senha do admin acima em um cofre de senhas.
EOF
