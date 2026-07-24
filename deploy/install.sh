#!/usr/bin/env bash
#
# deploy/install.sh — Instalador guiado do Sistema de Controle de Saídas
# =======================================================================
#
# Sobe/mantém o projeto numa VM Ubuntu: pacotes do sistema, usuário
# dedicado, código, venv, banco de dados, systemd, Nginx, certificado
# HTTPS gratuito (Let's Encrypt) e backup automático — sem precisar
# editar nada na mão.
#
# Uso interativo (mostra um menu):
#   sudo bash deploy/install.sh
#
# Uso direto por flags (pula o menu, útil em automação/CI):
#   sudo bash deploy/install.sh --action install \
#       --dir /opt/projeto_saida --user projeto_saida \
#       --repo https://github.com/Gerson-if/projeto_saida.git \
#       --domain saida.exemplo.com.br --email voce@exemplo.com \
#       --db mariadb --workers 2 --yes
#
# Ações disponíveis (--action):
#   install       Instalação completa (pacotes, venv, banco, systemd, Nginx, HTTPS)
#   ssl           Emite/renova o certificado HTTPS de uma instalação já existente
#   backup        Configura backup automático diário (banco + uploads)
#   update        Atualiza uma instalação existente (git pull + migrações + restart)
#   diagnostico   Roda verificações de saúde da instalação
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
ACTION=""
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
BACKUP_RETENCAO_DIAS="14"
BACKUP_HORA="03:00"
ASSUME_YES="0"
NON_INTERACTIVE="0"
SKIP_SSL="0"
FLAGS_INFORMADAS="0"     # vira 1 se qualquer flag de configuração foi passada

usage() {
    awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --action) ACTION="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --dir) INSTALL_DIR="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --user) SYS_USER="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --repo) REPO_URL="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --domain) DOMAIN="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --email) EMAIL="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --db) DB_BACKEND="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --workers) WORKERS="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --admin-nome) ADMIN_NOME="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --admin-cpf) ADMIN_CPF="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --admin-senha) ADMIN_SENHA="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --backup-dias) BACKUP_RETENCAO_DIAS="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --backup-hora) BACKUP_HORA="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --skip-ssl) SKIP_SSL="1"; FLAGS_INFORMADAS="1"; shift ;;
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

rand_hex()  { python3 -c "import secrets; print(secrets.token_hex(${1:-16}))"; }
rand_pass() { python3 -c "import secrets,string; a=string.ascii_letters+string.digits; print(''.join(secrets.choice(a) for _ in range(${1:-20})))"; }

# ─────────────────────────────────────────────────────────────────────────
# Validadores — cada um recebe o valor em $1 e retorna 0 (válido) / 1 (inválido)
# ─────────────────────────────────────────────────────────────────────────
validate_nao_vazio()   { [ -n "${1:-}" ]; }
validate_path()        { [[ "$1" =~ ^/[A-Za-z0-9_./-]+$ ]] && [ "$1" != "/" ]; }
validate_username()    { [[ "$1" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; }
validate_repo_url()    { [[ "$1" =~ ^(https?://|git@) ]]; }
validate_domain()      { [[ "$1" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$ ]]; }
validate_email()       { [[ "$1" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; }
validate_inteiro_pos() { [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ]; }
validate_workers()     { validate_inteiro_pos "$1" && [ "$1" -le 32 ]; }
validate_hora_hhmm()   { [[ "$1" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; }
validate_nome_pessoa() { [ -n "$1" ] && [ "${#1}" -le 120 ]; }
validate_senha_admin() { [ "${#1}" -ge 4 ] && [ "${#1}" -le 72 ]; }

# Mesma regra usada pelo próprio app em app/validators.py::validar_cpf_ou_identificacao:
# aceita um CPF numericamente válido (11 dígitos + dígitos verificadores) OU
# um identificador alfanumérico simples de 3-14 caracteres com ao menos uma letra
# (para permitir contas especiais como "admin").
validate_cpf_ou_id() {
    python3 - "$1" <<'PYEOF' >/dev/null 2>&1
import re, sys
bruto = sys.argv[1].strip()
if not bruto:
    sys.exit(1)
sem_pont = re.sub(r"[.\-\s]", "", bruto)
if sem_pont.isdigit():
    d = sem_pont
    if len(d) != 11 or d == d[0] * 11:
        sys.exit(1)
    def dv(parcial, peso_inicial):
        soma = sum(int(c) * p for c, p in zip(parcial, range(peso_inicial, 1, -1)))
        r = (soma * 10) % 11
        return 0 if r == 10 else r
    d1 = dv(d[:9], 10)
    d2 = dv(d[:9] + str(d1), 11)
    sys.exit(0 if d[-2:] == f"{d1}{d2}" else 1)
else:
    if re.fullmatch(r"[A-Za-z0-9._-]{3,14}", bruto) and re.search(r"[A-Za-z]", bruto):
        sys.exit(0)
    sys.exit(1)
PYEOF
}

# ask_valid "pergunta" "padrão" validador "mensagem de erro" -> preenche $REPLY_VAL
ask_valid() {
    local pergunta="$1" padrao="$2" validador="$3" msg_erro="$4"
    while true; do
        ask "$pergunta" "$padrao"
        if "$validador" "$REPLY_VAL"; then
            return 0
        fi
        warn "$msg_erro (valor recebido: '${REPLY_VAL}')"
        if [ "$NON_INTERACTIVE" = "1" ]; then
            die "$pergunta: valor inválido em modo não interativo. Ajuste a flag correspondente."
        fi
    done
}

# ask_valid_secret_confirm "pergunta" -> preenche $REPLY_VAL, pedindo confirmação
ask_valid_secret_confirm() {
    local pergunta="$1" senha1
    while true; do
        ask_secret "$pergunta"
        senha1="$REPLY_VAL"
        if [ "$NON_INTERACTIVE" = "1" ]; then
            return 0
        fi
        if ! validate_senha_admin "$senha1"; then
            warn "A senha deve ter entre 4 e 72 caracteres."
            continue
        fi
        ask_secret "Confirme a senha"
        if [ "$senha1" != "$REPLY_VAL" ]; then
            warn "As senhas não conferem — tente de novo."
            continue
        fi
        REPLY_VAL="$senha1"
        return 0
    done
}

banner() {
    echo
    echo -e "${C_BOLD}=======================================================${C_RESET}"
    echo -e "${C_BOLD} Sistema de Controle de Saídas — instalador guiado${C_RESET}"
    echo -e "${C_BOLD}=======================================================${C_RESET}"
}

# ─────────────────────────────────────────────────────────────────────────
# Detecção de SO — este instalador foi desenhado e testado só para Ubuntu
# ─────────────────────────────────────────────────────────────────────────
detect_os() {
    log "Verificando sistema operacional"
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        case "${ID:-}" in
            ubuntu)
                ok "Detectado $PRETTY_NAME"
                ;;
            *)
                warn "Este instalador foi desenhado e testado APENAS para Ubuntu"
                warn "(22.04/24.04 LTS). SO detectado: '${PRETTY_NAME:-desconhecido}'."
                warn "Em outras distros (Debian, CentOS, etc.) os nomes de pacotes"
                warn "e caminhos mudam e o script pode falhar no meio ou deixar o"
                warn "sistema mal configurado."
                if ! yesno "Ainda assim, quer tentar continuar por sua conta e risco?" "n"; then
                    die "Instalação cancelada. Recomendado: use uma VM Ubuntu 22.04 ou 24.04 LTS."
                fi
                ;;
        esac
    else
        warn "Não foi possível detectar o SO (/etc/os-release ausente)."
        if ! yesno "Continuar mesmo assim?" "n"; then
            die "Instalação cancelada."
        fi
    fi
}

# ─────────────────────────────────────────────────────────────────────────
# Menu principal
# ─────────────────────────────────────────────────────────────────────────
show_menu() {
    banner
    cat <<EOF

O que você quer fazer?

  1) Instalação completa (servidor novo)
  2) Emitir/renovar certificado HTTPS (Let's Encrypt)
  3) Configurar backup automático diário
  4) Atualizar uma instalação existente (git pull + migrações)
  5) Diagnóstico (verifica se está tudo saudável)
  6) Sair

EOF
    while true; do
        ask "Escolha uma opção (1-6)" "1"
        case "$REPLY_VAL" in
            1) ACTION="install"; return ;;
            2) ACTION="ssl"; return ;;
            3) ACTION="backup"; return ;;
            4) ACTION="update"; return ;;
            5) ACTION="diagnostico"; return ;;
            6) ACTION="sair"; return ;;
            *) warn "Opção inválida — digite um número de 1 a 6." ;;
        esac
    done
}

# ─────────────────────────────────────────────────────────────────────────
# Detecta IP público (usado no fallback de domínio via sslip.io)
# ─────────────────────────────────────────────────────────────────────────
detect_public_ip() {
    curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null \
        || hostname -I 2>/dev/null | awk '{print $1}' \
        || true
}

# Confirma que $INSTALL_DIR/$SYS_USER correspondem a uma instalação válida
# feita anteriormente por este script (usado pelas ações ssl/backup/update/diagnostico).
require_existing_install() {
    if [ "$NON_INTERACTIVE" != "1" ] && [ "$FLAGS_INFORMADAS" != "1" ]; then
        ask_valid "Diretório da instalação" "$INSTALL_DIR" validate_path \
            "Informe um caminho absoluto (ex: /opt/projeto_saida)."
        INSTALL_DIR="$REPLY_VAL"
        ask_valid "Usuário de sistema do app" "$SYS_USER" validate_username \
            "Nome de usuário Linux inválido."
        SYS_USER="$REPLY_VAL"
    fi
    [ -f "$INSTALL_DIR/.env" ] && [ -x "$INSTALL_DIR/venv/bin/python" ] \
        || die "Não encontrei uma instalação válida em '$INSTALL_DIR' (faltam .env ou venv/). Rode a ação 'install' primeiro."
    id "$SYS_USER" >/dev/null 2>&1 \
        || die "Usuário de sistema '$SYS_USER' não existe."
}

run_as_app_user() {
    # run_as_app_user "comando shell" -- roda com o .env carregado, dentro do venv
    sudo -u "$SYS_USER" -H bash -c "
        set -a; source '$INSTALL_DIR/.env'; set +a
        cd '$INSTALL_DIR'
        source venv/bin/activate
        $1
    "
}

# ─────────────────────────────────────────────────────────────────────────
# AÇÃO: install — instalação completa
# ─────────────────────────────────────────────────────────────────────────
cmd_install() {
    banner
    echo "Este modo prepara a VM do zero: pacotes, usuário dedicado, venv,"
    echo "banco de dados, systemd, Nginx e HTTPS grátis — sem edição manual."
    echo

    detect_os

    if [ "$NON_INTERACTIVE" != "1" ]; then
        ask_valid "Diretório de instalação" "$INSTALL_DIR" validate_path \
            "Informe um caminho absoluto, sem espaços (ex: /opt/projeto_saida)."
        INSTALL_DIR="$REPLY_VAL"

        ask_valid "Usuário de sistema para rodar o app" "$SYS_USER" validate_username \
            "Use só letras minúsculas, números, '_' ou '-', começando por letra/underscore."
        SYS_USER="$REPLY_VAL"

        ask_valid "URL do repositório git" "$REPO_URL" validate_repo_url \
            "Informe uma URL git válida (https://... ou git@...)."
        REPO_URL="$REPLY_VAL"
    fi

    # ── Domínio / IP + HTTPS ──────────────────────────────────────────────
    PUBLIC_IP="$(detect_public_ip)"
    if [ -n "$DOMAIN" ] && ! validate_domain "$DOMAIN"; then
        die "--domain '$DOMAIN' não parece um domínio válido (ex: saida.exemplo.com.br)."
    fi
    if [ -z "$DOMAIN" ] && [ "$NON_INTERACTIVE" != "1" ]; then
        echo
        echo "Para HTTPS gratuito (Let's Encrypt) é preciso um nome de domínio"
        echo "que resolva para o IP desta VM — Let's Encrypt NÃO emite certificado"
        echo "para IP puro (ex: https://${PUBLIC_IP:-1.2.3.4})."
        if [ -n "$PUBLIC_IP" ]; then
            echo -e "IP público detectado desta VM: ${C_BOLD}${PUBLIC_IP}${C_RESET}"
        fi
        if yesno "Você já tem um domínio/subdomínio apontando para este IP?" "n"; then
            ask_valid "Domínio (ex: saida.suaorganizacao.com.br)" "" validate_domain \
                "Domínio inválido — use um nome como saida.exemplo.com.br."
            DOMAIN="$REPLY_VAL"
        else
            if [ -n "$PUBLIC_IP" ]; then
                SUGESTAO="${PUBLIC_IP}.sslip.io"
                echo
                echo "Sem domínio próprio, dá pra usar um serviço de DNS público que"
                echo "resolve automaticamente para o IP embutido no nome — sem precisar"
                echo "configurar nada em lugar nenhum:"
                echo -e "   ${C_BOLD}${SUGESTAO}${C_RESET}  →  aponta para ${PUBLIC_IP}"
                if yesno "Usar '${SUGESTAO}' como domínio (permite HTTPS de verdade grátis)?" "s"; then
                    DOMAIN="$SUGESTAO"
                fi
            fi
            if [ -z "$DOMAIN" ]; then
                warn "Sem domínio, vou gerar um certificado autoassinado — o navegador"
                warn "vai mostrar aviso de 'conexão não segura' até você configurar um"
                warn "domínio de verdade (rode depois a ação 'ssl' deste mesmo script)."
                SKIP_SSL="1"
            fi
        fi
    fi

    if [ -n "$DOMAIN" ] && [ -z "$EMAIL" ] && [ "$NON_INTERACTIVE" != "1" ] && [ "$SKIP_SSL" != "1" ]; then
        ask_valid "E-mail para avisos de expiração do certificado (Let's Encrypt)" "" validate_email \
            "E-mail inválido — use o formato nome@dominio.com."
        EMAIL="$REPLY_VAL"
    fi
    if [ -n "$EMAIL" ] && ! validate_email "$EMAIL"; then
        die "--email '$EMAIL' não é um e-mail válido."
    fi
    [ -z "$DOMAIN" ] && DOMAIN="${PUBLIC_IP:-_}"

    # ── Banco de dados ────────────────────────────────────────────────────
    if [ -z "$DB_BACKEND" ]; then
        if [ "$NON_INTERACTIVE" = "1" ]; then
            DB_BACKEND="sqlite"
        else
            echo
            echo "Banco de dados:"
            echo "  1) SQLite   — mais simples, ótimo para times pequenos/uso único (padrão)"
            echo "  2) MariaDB  — recomendado se esperar mais carga/usuários simultâneos"
            while true; do
                ask "Escolha (1/2)" "1"
                case "$REPLY_VAL" in
                    1) DB_BACKEND="sqlite"; break ;;
                    2) DB_BACKEND="mariadb"; break ;;
                    *) warn "Digite 1 ou 2." ;;
                esac
            done
        fi
    elif [ "$DB_BACKEND" != "sqlite" ] && [ "$DB_BACKEND" != "mariadb" ]; then
        die "--db deve ser 'sqlite' ou 'mariadb' (recebido: '$DB_BACKEND')."
    fi
    [ "$DB_BACKEND" = "mariadb" ] && [ -z "$DB_PASS" ] && DB_PASS="$(rand_pass 24)"

    if [ "$NON_INTERACTIVE" != "1" ]; then
        echo
        echo "Quantos workers do Gunicorn? Com 1 worker o agendador de status roda"
        echo "dentro do próprio processo (mais simples). Com mais de 1, o script"
        echo "desliga o agendador interno e usa um timer systemd equivalente."
        ask_valid "Número de workers Gunicorn" "$WORKERS" validate_workers \
            "Informe um número inteiro entre 1 e 32."
        WORKERS="$REPLY_VAL"
    elif ! validate_workers "$WORKERS"; then
        die "--workers deve ser um número inteiro entre 1 e 32 (recebido: '$WORKERS')."
    fi

    # ── Administrador inicial ────────────────────────────────────────────
    if [ "$NON_INTERACTIVE" != "1" ]; then
        echo
        echo "Vamos criar o primeiro administrador do sistema."
        ask_valid "Nome completo do administrador" "${ADMIN_NOME:-Administrador}" validate_nome_pessoa \
            "Nome não pode ficar vazio (máx. 120 caracteres)."
        ADMIN_NOME="$REPLY_VAL"

        ask_valid "CPF do administrador (11 dígitos) ou identificador (ex: admin)" "${ADMIN_CPF:-admin}" validate_cpf_ou_id \
            "Use um CPF válido de 11 dígitos ou um identificador de 3-14 caracteres (com ao menos 1 letra)."
        ADMIN_CPF="$REPLY_VAL"

        ask_valid_secret_confirm "Senha do administrador (4-72 caracteres, não aparece na tela)"
        ADMIN_SENHA="$REPLY_VAL"
    else
        ADMIN_NOME="${ADMIN_NOME:-Administrador}"
        ADMIN_CPF="${ADMIN_CPF:-admin}"
        validate_nome_pessoa "$ADMIN_NOME" || die "--admin-nome inválido."
        validate_cpf_ou_id "$ADMIN_CPF" || die "--admin-cpf inválido: use um CPF de 11 dígitos ou identificador de 3-14 caracteres com letra."
        ADMIN_SENHA="${ADMIN_SENHA:-$(rand_pass 16)}"
        validate_senha_admin "$ADMIN_SENHA" || die "--admin-senha deve ter entre 4 e 72 caracteres."
    fi

    # ── Backup automático (opcional, já configurado aqui mesmo) ─────────
    QUER_BACKUP="n"
    if [ "$NON_INTERACTIVE" != "1" ]; then
        echo
        if yesno "Configurar backup automático diário (banco + uploads) agora?" "s"; then
            QUER_BACKUP="s"
            ask_valid "Quantos dias de backup manter" "$BACKUP_RETENCAO_DIAS" validate_inteiro_pos \
                "Informe um número inteiro de dias (ex: 14)."
            BACKUP_RETENCAO_DIAS="$REPLY_VAL"
            ask_valid "Horário do backup diário (HH:MM)" "$BACKUP_HORA" validate_hora_hhmm \
                "Use o formato HH:MM, 24h (ex: 03:00)."
            BACKUP_HORA="$REPLY_VAL"
        fi
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
  Admin inicial ....... $ADMIN_NOME (cpf/id: $ADMIN_CPF)
  Backup automático ... $([ "$QUER_BACKUP" = "s" ] && echo "sim, diário às $BACKUP_HORA, retendo $BACKUP_RETENCAO_DIAS dias" || echo "não (pode configurar depois pela ação 'backup')")
EOF
    echo
    if ! yesno "Confirma e inicia a instalação?" "s"; then
        die "Instalação cancelada pelo usuário."
    fi

    # ── 1. Pacotes do sistema ─────────────────────────────────────────────
    log "Atualizando pacotes e instalando dependências do sistema"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    PKGS=(python3 python3-venv python3-pip git nginx build-essential pkg-config curl ufw openssl cron)
    [ "$SKIP_SSL" != "1" ] && PKGS+=(certbot python3-certbot-nginx)
    [ "$DB_BACKEND" = "mariadb" ] && PKGS+=(mariadb-server mariadb-client libmariadb-dev)
    apt-get install -y "${PKGS[@]}"
    ok "Pacotes instalados"

    # ── 2. Firewall ────────────────────────────────────────────────────────
    log "Configurando firewall (ufw)"
    ufw allow OpenSSH >/dev/null 2>&1 || true
    ufw allow 'Nginx Full' >/dev/null 2>&1 || true
    ufw status | grep -q "Status: active" || ufw --force enable
    ok "Firewall ativo — só 22/80/443 liberadas; Gunicorn continua só em 127.0.0.1"

    # ── 3. Usuário de sistema ─────────────────────────────────────────────
    log "Criando usuário de sistema '$SYS_USER' (sem login) e diretório $INSTALL_DIR"
    id "$SYS_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$SYS_USER"
    mkdir -p "$INSTALL_DIR"
    chown "$SYS_USER:$SYS_USER" "$INSTALL_DIR"
    ok "Usuário e diretório prontos"

    # ── 4. Código da aplicação ────────────────────────────────────────────
    log "Obtendo código da aplicação"
    if [ -d "$INSTALL_DIR/.git" ]; then
        warn "Repositório já existe em $INSTALL_DIR — atualizando com 'git pull'."
        sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git pull"
    elif [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
        die "$INSTALL_DIR já existe e não é um repositório git. Esvazie a pasta ou escolha outro diretório."
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

    # ── 5. Banco de dados ─────────────────────────────────────────────────
    DATABASE_URL=""
    if [ "$DB_BACKEND" = "mariadb" ]; then
        log "Configurando MariaDB"
        systemctl enable --now mariadb >/dev/null 2>&1 || systemctl enable --now mysql
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

    # ── 6. Arquivo .env ────────────────────────────────────────────────────
    log "Gerando .env de produção"
    ENV_FILE="$INSTALL_DIR/.env"
    if [ -f "$ENV_FILE" ]; then
        warn ".env já existe — mantendo o existente sem sobrescrever (backup em .env.bak.<timestamp>)."
        cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%s)"
    else
        SECRET_KEY="$(rand_hex 32)"
        {
            echo "FLASK_ENV=production"
            echo "SECRET_KEY=$SECRET_KEY"
            [ -n "$DATABASE_URL" ] && echo "DATABASE_URL=$DATABASE_URL"
            echo "BEHIND_PROXY=true"
            if [ "$WORKERS" -gt 1 ]; then
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

    # ── 7. Inicializa banco + admin ────────────────────────────────────────
    log "Inicializando tabelas e criando administrador"
    run_as_app_user "flask init-db"
    if run_as_app_user "flask create-admin '$ADMIN_NOME' '$ADMIN_CPF' '$ADMIN_SENHA'" 2>/tmp/create_admin.err; then
        ok "Administrador '$ADMIN_CPF' criado"
    else
        warn "Não foi possível criar o administrador (talvez já exista): $(tail -n1 /tmp/create_admin.err 2>/dev/null)"
    fi

    # ── 8. systemd — serviço web (Gunicorn) ────────────────────────────────
    log "Configurando serviço systemd do app"
    sed \
        -e "s#/opt/projeto_saida#$INSTALL_DIR#g" \
        -e "s#User=projeto_saida#User=$SYS_USER#g" \
        -e "s#Group=projeto_saida#Group=$SYS_USER#g" \
        "$INSTALL_DIR/deploy/projeto-saida.service" > /etc/systemd/system/projeto-saida.service
    systemctl daemon-reload
    systemctl enable --now projeto-saida
    ok "Serviço 'projeto-saida' ativo (journalctl -u projeto-saida -f para logs)"

    if [ "$WORKERS" -gt 1 ]; then
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

    # ── 9. Nginx ───────────────────────────────────────────────────────────
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

    # ── 10. HTTPS ──────────────────────────────────────────────────────────
    if [ "$SKIP_SSL" = "1" ]; then
        emit_selfsigned_cert
    else
        emit_letsencrypt_cert
    fi

    # ── 11. Backup automático (se escolhido) ───────────────────────────────
    if [ "$QUER_BACKUP" = "s" ]; then
        setup_backup
    fi

    # ── 12. Diagnóstico final ───────────────────────────────────────────────
    log "Rodando diagnóstico interno do app"
    run_as_app_user "flask diagnosticar" || warn "flask diagnosticar retornou avisos — revise acima."

    echo
    echo -e "${C_GREEN}${C_BOLD}Instalação concluída.${C_RESET}"
    cat <<EOF

  URL ................ $([ "$SKIP_SSL" = "1" ] && echo "https://$DOMAIN (autoassinado) / http://$DOMAIN" || echo "https://$DOMAIN")
  Admin CPF/ID ....... $ADMIN_CPF
  Admin senha ........ ${ADMIN_SENHA} (ANOTE E GUARDE — não fica salva em nenhum arquivo)
  Diretório .......... $INSTALL_DIR
  .env ............... $ENV_FILE (permissão 600, só root/$SYS_USER leem)
  Serviço ............ systemctl status projeto-saida
  Logs systemd ....... journalctl -u projeto-saida -f
  Log da aplicação ... $INSTALL_DIR/instance/logs/app.log
  Atualizar depois ... sudo bash $INSTALL_DIR/deploy/install.sh --action update
  Backup automático .. $([ "$QUER_BACKUP" = "s" ] && echo "configurado (sudo bash deploy/install.sh --action backup para ajustar)" || echo "não configurado — rode: sudo bash deploy/install.sh --action backup")

Único passo que este script NÃO consegue automatizar: se sua VM estiver
atrás de um firewall do provedor de nuvem (grupo de segurança AWS/GCP/
Azure/etc.), libere as portas 80 e 443 lá também — isso fica fora da VM.
EOF
}

# ─────────────────────────────────────────────────────────────────────────
# Emissão de certificado — autoassinado (fallback sem domínio)
# ─────────────────────────────────────────────────────────────────────────
emit_selfsigned_cert() {
    warn "Sem Let's Encrypt: gerando certificado autoassinado só para não"
    warn "deixar a porta 443 sem nada — o navegador vai avisar que não confia nele."
    mkdir -p /etc/ssl/projeto-saida
    if [ ! -f /etc/ssl/projeto-saida/selfsigned.crt ]; then
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout /etc/ssl/projeto-saida/selfsigned.key \
            -out /etc/ssl/projeto-saida/selfsigned.crt \
            -subj "/CN=$DOMAIN" >/dev/null 2>&1
    fi
    if ! grep -q "listen 443 ssl" /etc/nginx/sites-available/projeto-saida 2>/dev/null; then
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
    fi
    nginx -t && systemctl reload nginx
    echo
    warn "Assim que tiver um domínio de verdade apontando para este IP, rode:"
    warn "  sudo bash deploy/install.sh --action ssl --domain SEU-DOMINIO --email SEU-EMAIL"
}

# ─────────────────────────────────────────────────────────────────────────
# Emissão de certificado — Let's Encrypt, com checagem de DNS e retentativa
# ─────────────────────────────────────────────────────────────────────────
dns_resolve() {
    python3 - "$1" <<'PYEOF' 2>/dev/null
import socket, sys
try:
    print(socket.gethostbyname(sys.argv[1]))
except Exception:
    pass
PYEOF
}

emit_letsencrypt_cert() {
    local ip_esperado resolvido tentativas=0

    # sslip.io/IP puro resolve instantaneamente — não precisa checar propagação.
    if [[ "$DOMAIN" != *.sslip.io ]]; then
        ip_esperado="${PUBLIC_IP:-$(detect_public_ip)}"
        log "Conferindo se '$DOMAIN' já resolve para este servidor ($ip_esperado)"
        while [ "$tentativas" -lt 6 ]; do
            resolvido="$(dns_resolve "$DOMAIN")"
            if [ -n "$resolvido" ] && [ "$resolvido" = "$ip_esperado" ]; then
                ok "DNS de '$DOMAIN' já aponta para $ip_esperado"
                break
            fi
            tentativas=$((tentativas + 1))
            if [ "$tentativas" -ge 6 ]; then
                warn "DNS de '$DOMAIN' resolve para '${resolvido:-nada ainda}', não para '$ip_esperado'."
                warn "Pode ser propagação de DNS ainda em andamento. Vou tentar o Certbot"
                warn "mesmo assim; se falhar, rode de novo mais tarde:"
                warn "  sudo bash deploy/install.sh --action ssl --domain $DOMAIN --email ${EMAIL:-SEU-EMAIL}"
                break
            fi
            [ "$NON_INTERACTIVE" = "1" ] && break
            echo -n "."
            sleep 10
        done
    fi

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
        warn "O site continua acessível em http://$DOMAIN. Rode depois:"
        warn "  sudo bash deploy/install.sh --action ssl --domain $DOMAIN --email ${EMAIL:-SEU-EMAIL}"
    fi
}

# ─────────────────────────────────────────────────────────────────────────
# AÇÃO: ssl — emitir/renovar certificado numa instalação já existente
# ─────────────────────────────────────────────────────────────────────────
cmd_ssl() {
    banner
    echo "Emitir ou renovar o certificado HTTPS de uma instalação já feita."
    echo
    require_existing_install

    command -v certbot >/dev/null 2>&1 || {
        log "Instalando Certbot"
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -y && apt-get install -y certbot python3-certbot-nginx
    }

    [ -f /etc/nginx/sites-available/projeto-saida ] \
        || die "Não encontrei /etc/nginx/sites-available/projeto-saida. Rode a ação 'install' primeiro."

    PUBLIC_IP="$(detect_public_ip)"
    if [ -z "$DOMAIN" ]; then
        ask_valid "Domínio (ex: saida.suaorganizacao.com.br)" "" validate_domain \
            "Domínio inválido — use um nome como saida.exemplo.com.br."
        DOMAIN="$REPLY_VAL"
    elif ! validate_domain "$DOMAIN"; then
        die "--domain '$DOMAIN' não parece um domínio válido."
    fi
    if [ -z "$EMAIL" ] && [ "$NON_INTERACTIVE" != "1" ]; then
        ask_valid "E-mail para avisos de expiração" "" validate_email \
            "E-mail inválido — use o formato nome@dominio.com."
        EMAIL="$REPLY_VAL"
    fi

    SKIP_SSL="0"
    emit_letsencrypt_cert
}

# ─────────────────────────────────────────────────────────────────────────
# AÇÃO: backup — configura backup automático diário
# ─────────────────────────────────────────────────────────────────────────
setup_backup() {
    log "Configurando backup automático diário"

    if ! command -v crontab >/dev/null 2>&1; then
        log "Pacote 'cron' ausente — instalando"
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -y && apt-get install -y cron
        systemctl enable --now cron 2>/dev/null || true
    fi

    local backup_dir="$INSTALL_DIR/instance/backups"
    mkdir -p "$backup_dir"
    chown "$SYS_USER:$SYS_USER" "$backup_dir"

    local backup_script="$INSTALL_DIR/deploy/backup.sh"
    {
        echo "#!/usr/bin/env bash"
        echo "# Gerado automaticamente por deploy/install.sh — backup diário."
        echo "set -euo pipefail"
        echo "DATA=\$(date +%F_%H%M)"
        echo "DEST='$backup_dir'"
        echo "mkdir -p \"\$DEST\""
        echo "set -a; source '$INSTALL_DIR/.env'; set +a"
        echo
        if [ "$DB_BACKEND" = "mariadb" ] || grep -q '^DATABASE_URL=mysql' "$INSTALL_DIR/.env" 2>/dev/null; then
            cat <<'BKSCRIPT'
DB_URL="${DATABASE_URL:-}"
DB_USER_B=$(echo "$DB_URL" | sed -E 's#mysql\+pymysql://([^:]+):.*#\1#')
DB_PASS_B=$(echo "$DB_URL" | sed -E 's#mysql\+pymysql://[^:]+:([^@]+)@.*#\1#')
DB_NAME_B=$(echo "$DB_URL" | sed -E 's#.*/([^/?]+)$#\1#')
mysqldump -u "$DB_USER_B" -p"$DB_PASS_B" "$DB_NAME_B" | gzip > "$DEST/db-$DATA.sql.gz"
BKSCRIPT
        else
            echo 'find "'"$INSTALL_DIR"'/instance" -maxdepth 1 -name "*.db" -exec cp {} "$DEST/db-$DATA.db" \; 2>/dev/null || true'
            echo '[ -f "$DEST/db-$DATA.db" ] && gzip -f "$DEST/db-$DATA.db"'
        fi
        echo
        echo "tar -czf \"\$DEST/uploads-\$DATA.tar.gz\" -C '$INSTALL_DIR/app/static' uploads 2>/dev/null || true"
        echo
        echo "# Remove backups mais antigos que a retenção configurada"
        echo "find \"\$DEST\" -type f -mtime +${BACKUP_RETENCAO_DIAS} -delete"
    } > "$backup_script"
    chown "$SYS_USER:$SYS_USER" "$backup_script"
    chmod 750 "$backup_script"
    ok "Script de backup criado em $backup_script"

    local marcador="# projeto_saida-backup-automatico"
    local hora="${BACKUP_HORA%%:*}" minuto="${BACKUP_HORA##*:}"
    local nova_linha="${minuto} ${hora} * * * $backup_script >> $INSTALL_DIR/instance/logs/backup.log 2>&1 ${marcador}"
    ( crontab -u "$SYS_USER" -l 2>/dev/null | grep -vF "$marcador" ; echo "$nova_linha" ) | crontab -u "$SYS_USER" -
    ok "Cron configurado: backup diário às ${BACKUP_HORA}, retendo ${BACKUP_RETENCAO_DIAS} dias em $backup_dir"
}

cmd_backup() {
    banner
    echo "Configura backup automático diário do banco de dados e dos uploads"
    echo "(logos, fotos, vídeo de fundo do login) via cron."
    echo
    require_existing_install

    if grep -q '^DATABASE_URL=mysql' "$INSTALL_DIR/.env" 2>/dev/null; then
        DB_BACKEND="mariadb"
    else
        DB_BACKEND="sqlite"
    fi

    if [ "$NON_INTERACTIVE" != "1" ]; then
        ask_valid "Quantos dias de backup manter" "$BACKUP_RETENCAO_DIAS" validate_inteiro_pos \
            "Informe um número inteiro de dias (ex: 14)."
        BACKUP_RETENCAO_DIAS="$REPLY_VAL"
        ask_valid "Horário do backup diário (HH:MM)" "$BACKUP_HORA" validate_hora_hhmm \
            "Use o formato HH:MM, 24h (ex: 03:00)."
        BACKUP_HORA="$REPLY_VAL"
    else
        validate_inteiro_pos "$BACKUP_RETENCAO_DIAS" || die "--backup-dias inválido."
        validate_hora_hhmm "$BACKUP_HORA" || die "--backup-hora inválido (use HH:MM)."
    fi

    setup_backup
    echo
    ok "Backup automático configurado. Teste rodando agora:"
    echo "  sudo -u $SYS_USER bash $INSTALL_DIR/deploy/backup.sh"
}

# ─────────────────────────────────────────────────────────────────────────
# AÇÃO: update — atualiza uma instalação existente
# ─────────────────────────────────────────────────────────────────────────
cmd_update() {
    banner
    echo "Atualiza o código, dependências e o banco de uma instalação existente."
    echo
    require_existing_install

    [ -d "$INSTALL_DIR/.git" ] || die "$INSTALL_DIR não parece um checkout git (sem .git)."

    log "Baixando última versão"
    sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git pull"

    log "Atualizando dependências Python"
    sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && source venv/bin/activate && pip install -r requirements.txt -q"

    log "Aplicando migrações de banco pendentes (se houver)"
    run_as_app_user "flask db upgrade"

    log "Reiniciando serviço"
    systemctl restart projeto-saida
    systemctl --no-pager --lines=5 status projeto-saida || true

    ok "Atualização concluída. Logs: journalctl -u projeto-saida -f"
}

# ─────────────────────────────────────────────────────────────────────────
# AÇÃO: diagnostico — verifica saúde da instalação
# ─────────────────────────────────────────────────────────────────────────
cmd_diagnostico() {
    banner
    echo "Verificações de saúde da instalação."
    echo
    require_existing_install

    log "Diagnóstico interno da aplicação (flask diagnosticar)"
    run_as_app_user "flask diagnosticar" || warn "flask diagnosticar reportou avisos — revise acima."

    echo
    log "Serviço systemd"
    systemctl --no-pager --lines=5 status projeto-saida || warn "Serviço 'projeto-saida' não encontrado/ativo."

    echo
    log "Nginx"
    nginx -t 2>&1 || warn "Configuração do Nginx com problema."

    if command -v certbot >/dev/null 2>&1; then
        echo
        log "Certificados Let's Encrypt"
        certbot certificates 2>/dev/null || warn "Não há certificados Certbot configurados."
    fi

    echo
    log "Espaço em disco"
    df -h "$INSTALL_DIR"

    echo
    log "Memória"
    free -h

    echo
    ok "Diagnóstico concluído."
}

# ─────────────────────────────────────────────────────────────────────────
# Ponto de entrada
# ─────────────────────────────────────────────────────────────────────────
main() {
    if [ -z "$ACTION" ]; then
        if [ "$NON_INTERACTIVE" = "1" ] || [ "$FLAGS_INFORMADAS" = "1" ]; then
            ACTION="install"
        else
            show_menu
        fi
    fi

    case "$ACTION" in
        install|ssl|backup|update|diagnostico) ;;
        sair) echo "Até mais!"; exit 0 ;;
        *) die "Ação desconhecida: '$ACTION' (use install|ssl|backup|update|diagnostico)." ;;
    esac

    if ! ( set -e; "cmd_${ACTION}" ); then
        die "A ação '$ACTION' terminou com erro — revise as mensagens acima."
    fi
}

main
