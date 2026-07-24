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
SKIP_SSL="0"             # legado: --skip-ssl equivale a --https-mode selfsigned
HTTPS_MODE=""            # letsencrypt | selfsigned | none
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
        --https-mode) HTTPS_MODE="$2"; FLAGS_INFORMADAS="1"; shift 2 ;;
        --skip-ssl) SKIP_SSL="1"; FLAGS_INFORMADAS="1"; shift ;;   # legado, use --https-mode selfsigned
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

# retry_cmd <tentativas> <comando...> — repete um comando com espera crescente
# entre tentativas. Usado em operações de rede (apt, pip, git) que falham por
# instabilidade transitória e não por erro real de configuração.
retry_cmd() {
    local tentativas="$1" tentativa=1 espera=5
    shift
    until "$@"; do
        if [ "$tentativa" -ge "$tentativas" ]; then
            return 1
        fi
        warn "Tentativa $tentativa/$tentativas falhou (\"$*\") — tentando de novo em ${espera}s..."
        sleep "$espera"
        tentativa=$((tentativa + 1))
        espera=$((espera * 2))
    done
    return 0
}

# ─────────────────────────────────────────────────────────────────────────
# Pré-checagens — tentam pegar problemas óbvios ANTES de mexer no sistema
# ─────────────────────────────────────────────────────────────────────────
preflight_checks() {
    log "Checagens antes de começar"
    local problemas=0

    if ! retry_cmd 3 curl -fsS --max-time 5 -o /dev/null https://deb.debian.org 2>/dev/null \
       && ! retry_cmd 1 curl -fsS --max-time 5 -o /dev/null http://archive.ubuntu.com 2>/dev/null; then
        warn "Não consegui confirmar acesso à internet (necessário para apt/pip/certbot)."
        problemas=$((problemas + 1))
    else
        ok "Conectividade de rede OK"
    fi

    local disp_kb
    disp_kb="$(df -Pk / 2>/dev/null | awk 'NR==2{print $4}')"
    if [ -n "$disp_kb" ] && [ "$disp_kb" -lt 1048576 ]; then
        warn "Menos de 1 GB livre em / (disponível: $((disp_kb / 1024)) MB) — a instalação pode falhar por falta de espaço."
        problemas=$((problemas + 1))
    else
        ok "Espaço em disco OK"
    fi

    if command -v ss >/dev/null 2>&1; then
        if ss -ltn 2>/dev/null | grep -qE ':80\s|:443\s'; then
            warn "Já existe algo escutando na porta 80 e/ou 443 (outro Nginx/Apache?)."
            warn "O instalador vai sobrescrever a config do site 'projeto-saida', mas"
            warn "se for outro serviço além do Nginx, pode haver conflito de porta."
            problemas=$((problemas + 1))
        fi
    fi

    if [ "$problemas" -gt 0 ] && [ "$NON_INTERACTIVE" != "1" ]; then
        if ! yesno "Foram encontrados $problemas aviso(s) acima. Continuar mesmo assim?" "n"; then
            die "Instalação cancelada — resolva os avisos acima e rode de novo."
        fi
    elif [ "$problemas" -gt 0 ]; then
        warn "$problemas aviso(s) de pré-checagem ignorado(s) por rodar em modo não interativo."
    fi
}

# wait_for_service_ativo <unidade> <timeout_seg> — espera um serviço systemd
# ficar "active (running)", em vez de confiar cegamente no "enable --now".
wait_for_service_ativo() {
    local unidade="$1" timeout="${2:-15}" decorrido=0
    while [ "$decorrido" -lt "$timeout" ]; do
        systemctl is-active --quiet "$unidade" && return 0
        sleep 1
        decorrido=$((decorrido + 1))
    done
    systemctl is-active --quiet "$unidade"
}

# wait_for_http <url> <timeout_seg> — espera um endpoint HTTP responder
# qualquer coisa (mesmo 302/401/500) — só não pode ser "conexão recusada".
wait_for_http() {
    # Sem -f: qualquer status HTTP (mesmo 404/500) conta como "respondeu".
    # Só falha em erro de conexão (recusada, timeout) — é só isso que
    # realmente indica que o serviço não está de pé.
    local url="$1" timeout="${2:-15}" decorrido=0
    while [ "$decorrido" -lt "$timeout" ]; do
        curl -sS -o /dev/null --max-time 3 "$url" 2>/dev/null && return 0
        sleep 1
        decorrido=$((decorrido + 1))
    done
    return 1
}

# ─────────────────────────────────────────────────────────────────────────
# Validadores — cada um recebe o valor em $1 e retorna 0 (válido) / 1 (inválido)
# ─────────────────────────────────────────────────────────────────────────
validate_nao_vazio()   { [ -n "${1:-}" ]; }
validate_path()        { [[ "$1" =~ ^/[A-Za-z0-9_./-]+$ ]] && [ "$1" != "/" ]; }
validate_username()    { [[ "$1" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; }
validate_repo_url()    { [[ "$1" =~ ^(https?://|git@) ]]; }
validate_domain()      { [[ "$1" =~ ^([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$ ]]; }
validate_ipv4() {
    local ip="$1" o
    [[ "$ip" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]] || return 1
    for o in "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${BASH_REMATCH[4]}"; do
        [ "$o" -le 255 ] || return 1
    done
    return 0
}
validate_domain_ou_ip() { validate_domain "$1" || validate_ipv4 "$1"; }
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
    preflight_checks

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

    # ── Domínio ou IP + modo de HTTPS ─────────────────────────────────────
    PUBLIC_IP="$(detect_public_ip)"
    if [ -n "$DOMAIN" ] && ! validate_domain "$DOMAIN" && ! validate_ipv4 "$DOMAIN"; then
        die "--domain '$DOMAIN' não é um domínio nem um IPv4 válido (ex: saida.exemplo.com.br ou 203.0.113.10)."
    fi
    if [ -n "$HTTPS_MODE" ] && [ "$HTTPS_MODE" != "letsencrypt" ] && [ "$HTTPS_MODE" != "selfsigned" ] && [ "$HTTPS_MODE" != "none" ]; then
        die "--https-mode deve ser 'letsencrypt', 'selfsigned' ou 'none' (recebido: '$HTTPS_MODE')."
    fi

    if [ -z "$HTTPS_MODE" ] && [ "$NON_INTERACTIVE" != "1" ]; then
        echo
        echo "Como você quer expor o sistema para os usuários?"
        if [ -n "$PUBLIC_IP" ]; then
            echo -e "IP público detectado desta VM/VPS: ${C_BOLD}${PUBLIC_IP}${C_RESET}"
        fi
        cat <<EOF
  1) Tenho um domínio próprio apontando para este servidor (HTTPS real, Let's Encrypt)
  2) Não tenho domínio, mas quero HTTPS real do mesmo jeito (usa o IP via sslip.io)
  3) Usar o IP da VM/VPS direto, com certificado autoassinado (navegador avisa "não seguro")
  4) Só HTTP por enquanto, sem certificado (não recomendado, ex: ambiente de teste)
EOF
        while true; do
            ask "Escolha (1-4)" "1"
            case "$REPLY_VAL" in
                1)
                    ask_valid "Domínio (ex: saida.suaorganizacao.com.br)" "" validate_domain \
                        "Domínio inválido — use um nome como saida.exemplo.com.br."
                    DOMAIN="$REPLY_VAL"
                    HTTPS_MODE="letsencrypt"
                    break
                    ;;
                2)
                    [ -z "$PUBLIC_IP" ] && { warn "Não consegui detectar o IP público desta VM — escolha outra opção."; continue; }
                    DOMAIN="${PUBLIC_IP}.sslip.io"
                    ok "Vou usar '${DOMAIN}' (resolve automaticamente para ${PUBLIC_IP}, sem configurar nada em DNS)."
                    HTTPS_MODE="letsencrypt"
                    break
                    ;;
                3)
                    DOMAIN="${PUBLIC_IP:-}"
                    if [ -z "$DOMAIN" ]; then
                        ask_valid "Não detectei o IP automaticamente — informe o IP da VM/VPS" "" validate_ipv4 \
                            "Informe um IPv4 válido (ex: 203.0.113.10)."
                        DOMAIN="$REPLY_VAL"
                    fi
                    warn "Certificado autoassinado para IP '$DOMAIN': o navegador vai avisar"
                    warn "'conexão não é segura' na primeira visita — isso é esperado, não é erro."
                    HTTPS_MODE="selfsigned"
                    break
                    ;;
                4)
                    DOMAIN="${PUBLIC_IP:-_}"
                    warn "Seguindo sem HTTPS — dados (inclusive senhas) trafegam sem criptografia."
                    HTTPS_MODE="none"
                    break
                    ;;
                *) warn "Digite um número de 1 a 4." ;;
            esac
        done
    elif [ -z "$HTTPS_MODE" ]; then
        # Modo não interativo sem --https-mode explícito: mantém compatibilidade
        # com versões anteriores (Let's Encrypt se houver domínio, senão autoassinado).
        HTTPS_MODE="letsencrypt"
        [ -z "$DOMAIN" ] && { DOMAIN="${PUBLIC_IP:-_}"; HTTPS_MODE="selfsigned"; }
    fi
    [ -z "$DOMAIN" ] && DOMAIN="${PUBLIC_IP:-_}"

    if [ "$HTTPS_MODE" = "letsencrypt" ] && [ -z "$EMAIL" ] && [ "$NON_INTERACTIVE" != "1" ]; then
        ask_valid "E-mail para avisos de expiração do certificado (Let's Encrypt)" "" validate_email \
            "E-mail inválido — use o formato nome@dominio.com."
        EMAIL="$REPLY_VAL"
    fi
    if [ -n "$EMAIL" ] && ! validate_email "$EMAIL"; then
        die "--email '$EMAIL' não é um e-mail válido."
    fi
    # SKIP_SSL é mantido só por compatibilidade com versões anteriores do script.
    [ "$SKIP_SSL" = "1" ] && HTTPS_MODE="selfsigned"

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
  HTTPS ............... $(case "$HTTPS_MODE" in
                            letsencrypt) echo "Let's Encrypt (certificado real, grátis)" ;;
                            selfsigned)  echo "autoassinado (navegador vai avisar 'não seguro')" ;;
                            none)        echo "nenhum — apenas HTTP (não recomendado)" ;;
                          esac)
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
    retry_cmd 3 apt-get update -y \
        || die "apt-get update falhou depois de 3 tentativas — confira a conexão da VM com a internet."
    # Inclui bibliotecas de compilação para o caso raro de o pip precisar
    # compilar 'cryptography'/'Pillow' na hora (sem wheel pronta pra essa arch).
    PKGS=(python3 python3-venv python3-pip git nginx build-essential pkg-config curl ufw \
          openssl cron libssl-dev libffi-dev python3-dev zlib1g-dev libjpeg-dev)
    [ "$HTTPS_MODE" = "letsencrypt" ] && PKGS+=(certbot python3-certbot-nginx)
    [ "$DB_BACKEND" = "mariadb" ] && PKGS+=(mariadb-server mariadb-client libmariadb-dev)
    retry_cmd 3 apt-get install -y "${PKGS[@]}" \
        || die "Falha ao instalar pacotes do sistema depois de 3 tentativas. Rode 'apt-get install ${PKGS[*]}' manualmente para ver o erro completo."
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
    log "Conferindo se o repositório é acessível"
    retry_cmd 3 git ls-remote "$REPO_URL" HEAD >/dev/null 2>&1 \
        || die "Não consegui acessar '$REPO_URL' (URL errada? repositório privado sem credenciais? sem internet?)."

    log "Obtendo código da aplicação"
    if [ -d "$INSTALL_DIR/.git" ]; then
        warn "Repositório já existe em $INSTALL_DIR — atualizando com 'git pull'."
        retry_cmd 3 sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git pull" \
            || die "git pull falhou em $INSTALL_DIR. Verifique se há alterações locais conflitantes (git status)."
    elif [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
        die "$INSTALL_DIR já existe e não é um repositório git. Esvazie a pasta ou escolha outro diretório."
    else
        retry_cmd 3 sudo -u "$SYS_USER" -H git clone "$REPO_URL" "$INSTALL_DIR" \
            || die "git clone de '$REPO_URL' falhou depois de 3 tentativas."
    fi
    ok "Código em $INSTALL_DIR"

    log "Criando ambiente virtual e instalando dependências Python"
    if ! sudo -u "$SYS_USER" -H bash -c "
        set -e
        cd '$INSTALL_DIR'
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip -q
        pip install -r requirements.txt -q
        pip install gunicorn -q
        if [ '$DB_BACKEND' = 'mariadb' ]; then
            pip install pymysql cryptography -q
        fi
    " > /tmp/pip_install.log 2>&1; then
        warn "Primeira tentativa de instalar dependências Python falhou — tentando de novo"
        warn "(bibliotecas de compilação já foram instaladas no passo 1, pode ter sido rede)."
        if ! sudo -u "$SYS_USER" -H bash -c "
            cd '$INSTALL_DIR'
            source venv/bin/activate
            pip install -r requirements.txt -q
            pip install gunicorn -q
            if [ '$DB_BACKEND' = 'mariadb' ]; then
                pip install pymysql cryptography -q
            fi
        " > /tmp/pip_install.log 2>&1; then
            err "Falha ao instalar dependências Python. Últimas linhas do log:"
            tail -n 30 /tmp/pip_install.log >&2
            die "Log completo em /tmp/pip_install.log."
        fi
    fi
    ok "Dependências instaladas"

    # ── 5. Banco de dados ─────────────────────────────────────────────────
    DATABASE_URL=""
    if [ "$DB_BACKEND" = "mariadb" ]; then
        log "Configurando MariaDB"
        systemctl enable --now mariadb >/dev/null 2>&1 || systemctl enable --now mysql
        sleep 2
        if ! systemctl is-active --quiet mariadb 2>/dev/null && ! systemctl is-active --quiet mysql 2>/dev/null; then
            die "O serviço MariaDB não iniciou. Veja: journalctl -u mariadb --no-pager -n 50"
        fi

        # Padrão do Ubuntu: root do MariaDB autentica via socket Unix (sem
        # senha) quando 'mysql' é chamado como root do sistema — funciona na
        # maioria das instalações. Se não funcionar (root com senha definida
        # manualmente antes), pedimos a senha em vez de falhar sem explicação.
        MYSQL_ROOT_CMD=(mysql -u root)
        if ! "${MYSQL_ROOT_CMD[@]}" -e "SELECT 1" >/dev/null 2>&1; then
            warn "Não consegui autenticar no MariaDB como root via socket (padrão do Ubuntu)."
            if [ "$NON_INTERACTIVE" != "1" ]; then
                ask_secret "Senha do root do MariaDB (deixe em branco para tentar sem senha de novo)"
                if [ -n "$REPLY_VAL" ]; then
                    MYSQL_ROOT_CMD=(mysql -u root -p"$REPLY_VAL")
                fi
            fi
            "${MYSQL_ROOT_CMD[@]}" -e "SELECT 1" >/dev/null 2>&1 \
                || die "Não foi possível autenticar no MariaDB como root. Configure o acesso manualmente e rode de novo."
        fi

        if ! "${MYSQL_ROOT_CMD[@]}" -e "USE $DB_NAME" >/dev/null 2>&1; then
            if ! "${MYSQL_ROOT_CMD[@]}" <<SQL
CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';
GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
SQL
            then
                die "Falha ao criar banco/usuário no MariaDB. Rode manualmente para ver o erro: sudo mysql -u root"
            fi
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

    if ! wait_for_service_ativo projeto-saida 15; then
        err "O serviço 'projeto-saida' não subiu corretamente. Últimas linhas do log:"
        journalctl -u projeto-saida --no-pager -n 40 >&2 || true
        die "Corrija o erro acima (causas comuns: porta 8000 ocupada, erro no .env, dependência faltando) e rode a instalação de novo."
    fi

    log "Conferindo se a aplicação responde em 127.0.0.1:8000"
    if wait_for_http "http://127.0.0.1:8000/" 15; then
        ok "Serviço 'projeto-saida' ativo e respondendo (journalctl -u projeto-saida -f para logs)"
    else
        err "O processo do Gunicorn está de pé, mas não respondeu em http://127.0.0.1:8000/ a tempo."
        journalctl -u projeto-saida --no-pager -n 40 >&2 || true
        die "Revise o log acima antes de continuar — sem isso, Nginx/HTTPS não vão ter o que servir."
    fi

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
    if ! nginx -t 2>/tmp/nginx_test.log; then
        err "Nginx recusou a configuração gerada:"
        tail -n 20 /tmp/nginx_test.log >&2
        die "Corrija /etc/nginx/sites-available/projeto-saida e rode 'nginx -t' manualmente para validar."
    fi
    systemctl reload nginx
    if wait_for_http "http://127.0.0.1/" 10; then
        ok "Nginx servindo http://$DOMAIN (proxy para Gunicorn em 127.0.0.1:8000)"
    else
        warn "Nginx recarregou, mas http://127.0.0.1/ não respondeu a tempo — confira 'nginx -t' e os logs em /var/log/nginx/."
    fi

    # ── 10. HTTPS ──────────────────────────────────────────────────────────
    case "$HTTPS_MODE" in
        selfsigned) emit_selfsigned_cert ;;
        letsencrypt) emit_letsencrypt_cert ;;
        none) ok "Seguindo sem HTTPS, conforme escolhido (só http://$DOMAIN)." ;;
    esac

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

  URL ................ $(case "$HTTPS_MODE" in
                            letsencrypt) echo "https://$DOMAIN" ;;
                            selfsigned)  echo "https://$DOMAIN (autoassinado) — aceite o aviso do navegador" ;;
                            none)        echo "http://$DOMAIN (sem HTTPS)" ;;
                          esac)
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
    log "Gerando certificado autoassinado para '$DOMAIN'"
    warn "O navegador vai avisar 'conexão não é segura' na primeira visita —"
    warn "isso é esperado para um certificado autoassinado, não é um erro."

    mkdir -p /etc/ssl/projeto-saida

    # SAN correto (IP ou DNS) é obrigatório — navegadores modernos (Chrome,
    # Firefox) ignoram o campo CN sozinho desde 2017 e rejeitam o certificado
    # como malformado se faltar o SAN, mesmo sendo autoassinado.
    local san
    if validate_ipv4 "$DOMAIN"; then
        san="subjectAltName=IP:$DOMAIN"
    else
        san="subjectAltName=DNS:$DOMAIN"
    fi

    # Sempre regera: garante que o SAN acompanha o domínio/IP atual, mesmo
    # que a VM tenha trocado de IP público desde a última execução.
    if ! openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
            -keyout /etc/ssl/projeto-saida/selfsigned.key \
            -out /etc/ssl/projeto-saida/selfsigned.crt \
            -subj "/CN=$DOMAIN" \
            -addext "$san" >/tmp/openssl_selfsigned.log 2>&1
    then
        err "Falha ao gerar o certificado autoassinado:"
        tail -n 20 /tmp/openssl_selfsigned.log >&2
        die "Não foi possível gerar o certificado. Veja /tmp/openssl_selfsigned.log."
    fi
    chmod 640 /etc/ssl/projeto-saida/selfsigned.key
    ok "Certificado autoassinado gerado (válido por ~2 anos, SAN=$DOMAIN)"

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

    if ! nginx -t 2>/tmp/nginx_test.log; then
        err "Nginx recusou a configuração com o certificado autoassinado:"
        tail -n 20 /tmp/nginx_test.log >&2
        die "Corrija /etc/nginx/sites-available/projeto-saida e rode 'nginx -t' de novo."
    fi
    systemctl reload nginx
    ok "HTTPS autoassinado ativo em https://$DOMAIN"
    echo
    warn "Assim que tiver um domínio de verdade apontando para este servidor, rode:"
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
    echo "Por padrão emite Let's Encrypt; use --https-mode selfsigned para"
    echo "gerar (ou trocar para) um certificado autoassinado com IP/domínio."
    echo
    require_existing_install

    [ -f /etc/nginx/sites-available/projeto-saida ] \
        || die "Não encontrei /etc/nginx/sites-available/projeto-saida. Rode a ação 'install' primeiro."

    [ -z "$HTTPS_MODE" ] && HTTPS_MODE="letsencrypt"
    if [ "$HTTPS_MODE" != "letsencrypt" ] && [ "$HTTPS_MODE" != "selfsigned" ]; then
        die "--https-mode aqui só aceita 'letsencrypt' ou 'selfsigned' (recebido: '$HTTPS_MODE')."
    fi

    PUBLIC_IP="$(detect_public_ip)"
    if [ -z "$DOMAIN" ]; then
        if [ "$HTTPS_MODE" = "selfsigned" ]; then
            ask_valid "Domínio ou IP para o certificado" "${PUBLIC_IP:-}" validate_domain_ou_ip \
                "Informe um domínio válido (ex: saida.exemplo.com.br) ou um IPv4."
        else
            ask_valid "Domínio (ex: saida.suaorganizacao.com.br)" "" validate_domain \
                "Domínio inválido — use um nome como saida.exemplo.com.br."
        fi
        DOMAIN="$REPLY_VAL"
    elif [ "$HTTPS_MODE" = "selfsigned" ] && ! validate_domain_ou_ip "$DOMAIN"; then
        die "--domain '$DOMAIN' não é um domínio nem um IPv4 válido."
    elif [ "$HTTPS_MODE" = "letsencrypt" ] && ! validate_domain "$DOMAIN"; then
        die "--domain '$DOMAIN' não parece um domínio válido (Let's Encrypt não emite para IP puro)."
    fi

    if [ "$HTTPS_MODE" = "letsencrypt" ] && [ -z "$EMAIL" ] && [ "$NON_INTERACTIVE" != "1" ]; then
        ask_valid "E-mail para avisos de expiração" "" validate_email \
            "E-mail inválido — use o formato nome@dominio.com."
        EMAIL="$REPLY_VAL"
    fi

    if [ "$HTTPS_MODE" = "selfsigned" ]; then
        emit_selfsigned_cert
    else
        command -v certbot >/dev/null 2>&1 || {
            log "Instalando Certbot"
            export DEBIAN_FRONTEND=noninteractive
            apt-get update -y && apt-get install -y certbot python3-certbot-nginx
        }
        emit_letsencrypt_cert
    fi
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
    echo "Atualiza código, dependências e banco de uma instalação existente,"
    echo "com backup automático antes e rollback automático se algo falhar."
    echo
    require_existing_install

    [ -d "$INSTALL_DIR/.git" ] || die "$INSTALL_DIR não parece um checkout git (sem .git)."

    local db_engine="sqlite"
    grep -q '^DATABASE_URL=mysql' "$INSTALL_DIR/.env" 2>/dev/null && db_engine="mariadb"

    log "Verificando se há alterações locais não commitadas em $INSTALL_DIR"
    if [ -n "$(sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git status --porcelain -- . ':!.env*'" 2>/dev/null)" ]; then
        warn "Há arquivos modificados localmente em $INSTALL_DIR (fora de .env)."
        warn "Isso normalmente não deveria acontecer numa instalação de produção."
        if ! yesno "Continuar mesmo assim (git pull pode falhar ou descartar essas mudanças)?" "n"; then
            die "Atualização cancelada. Revise 'git status' em $INSTALL_DIR antes de tentar de novo."
        fi
    fi

    local before_commit
    before_commit="$(sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git rev-parse HEAD")"

    log "Verificando se há uma versão nova"
    retry_cmd 3 sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git fetch --quiet" \
        || die "git fetch falhou depois de 3 tentativas — confira a conectividade da VM."
    local remote_commit branch
    branch="$(sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git rev-parse --abbrev-ref HEAD")"
    remote_commit="$(sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git rev-parse '@{u}'" 2>/dev/null || echo "$before_commit")"
    if [ "$before_commit" = "$remote_commit" ]; then
        ok "Já está na última versão (branch '$branch', commit ${before_commit:0:8}). Nada a fazer."
        return 0
    fi

    log "Fazendo backup de segurança antes de atualizar"
    local backup_stamp backup_pre_dir
    backup_stamp="$(date +%Y%m%d_%H%M%S)"
    backup_pre_dir="$INSTALL_DIR/instance/backups/pre-update-$backup_stamp"
    mkdir -p "$backup_pre_dir"
    cp "$INSTALL_DIR/.env" "$backup_pre_dir/.env.bak" 2>/dev/null || true
    if [ "$db_engine" = "mariadb" ]; then
        local db_url db_user_b db_pass_b db_name_b
        db_url="$(grep '^DATABASE_URL=' "$INSTALL_DIR/.env" | cut -d= -f2-)"
        db_user_b="$(echo "$db_url" | sed -E 's#mysql\+pymysql://([^:]+):.*#\1#')"
        db_pass_b="$(echo "$db_url" | sed -E 's#mysql\+pymysql://[^:]+:([^@]+)@.*#\1#')"
        db_name_b="$(echo "$db_url" | sed -E 's#.*/([^/?]+)$#\1#')"
        if ! mysqldump -u "$db_user_b" -p"$db_pass_b" "$db_name_b" 2>/tmp/mysqldump_update.log | gzip > "$backup_pre_dir/db.sql.gz"; then
            err "Falha ao fazer o backup do MariaDB antes de atualizar:"
            tail -n 20 /tmp/mysqldump_update.log >&2
            die "Atualização cancelada por segurança — sem backup, não sigo. Log em /tmp/mysqldump_update.log."
        fi
    else
        find "$INSTALL_DIR/instance" -maxdepth 1 -name "*.db" -exec cp {} "$backup_pre_dir/" \; 2>/dev/null || true
    fi
    chown -R "$SYS_USER:$SYS_USER" "$backup_pre_dir"
    ok "Backup pré-atualização salvo em $backup_pre_dir"

    # rollback_update — restaura código e banco ao estado anterior a esta atualização.
    rollback_update() {
        err "Revertendo para o commit anterior (${before_commit:0:8}) e restaurando o backup..."
        sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git reset --hard '$before_commit'" || true
        sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && source venv/bin/activate && pip install -r requirements.txt -q" \
            || warn "Não consegui reinstalar as dependências da versão anterior — revise o venv manualmente."
        if [ "$db_engine" = "mariadb" ] && [ -f "$backup_pre_dir/db.sql.gz" ]; then
            local db_url db_user_b db_pass_b db_name_b
            db_url="$(grep '^DATABASE_URL=' "$INSTALL_DIR/.env" | cut -d= -f2-)"
            db_user_b="$(echo "$db_url" | sed -E 's#mysql\+pymysql://([^:]+):.*#\1#')"
            db_pass_b="$(echo "$db_url" | sed -E 's#mysql\+pymysql://[^:]+:([^@]+)@.*#\1#')"
            db_name_b="$(echo "$db_url" | sed -E 's#.*/([^/?]+)$#\1#')"
            gunzip -c "$backup_pre_dir/db.sql.gz" | mysql -u "$db_user_b" -p"$db_pass_b" "$db_name_b" \
                || warn "Não consegui restaurar o dump do MariaDB automaticamente — restaure na mão a partir de $backup_pre_dir/db.sql.gz"
        elif [ "$db_engine" = "sqlite" ]; then
            local bkp
            bkp="$(find "$backup_pre_dir" -maxdepth 1 -name "*.db" | head -n1)"
            if [ -n "$bkp" ]; then
                cp "$bkp" "$INSTALL_DIR/instance/$(basename "$bkp")"
                chown "$SYS_USER:$SYS_USER" "$INSTALL_DIR/instance/$(basename "$bkp")"
            fi
        fi
        systemctl restart projeto-saida 2>/dev/null || true
        err "Reversão concluída. A instalação deve estar de volta ao estado anterior à atualização."
        err "Backup preservado em $backup_pre_dir para investigação."
    }

    log "Baixando última versão (fast-forward only)"
    if ! sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git merge --ff-only '@{u}'"; then
        die "git pull (fast-forward) falhou — provavelmente há divergência local. Nada foi alterado; investigue com 'git status' em $INSTALL_DIR."
    fi

    log "Atualizando dependências Python"
    if ! sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && source venv/bin/activate && pip install -r requirements.txt -q" > /tmp/pip_update.log 2>&1; then
        err "Falha ao instalar dependências da nova versão:"
        tail -n 30 /tmp/pip_update.log >&2
        rollback_update
        die "Atualização revertida. Log completo em /tmp/pip_update.log."
    fi

    log "Aplicando migrações de banco pendentes (se houver)"
    if ! run_as_app_user "flask db upgrade" > /tmp/flask_db_upgrade.log 2>&1; then
        err "Falha ao aplicar migrações de banco:"
        tail -n 30 /tmp/flask_db_upgrade.log >&2
        rollback_update
        die "Atualização revertida. Log completo em /tmp/flask_db_upgrade.log."
    fi

    log "Reiniciando serviço"
    systemctl restart projeto-saida

    if ! wait_for_service_ativo projeto-saida 15 || ! wait_for_http "http://127.0.0.1:8000/" 15; then
        err "O serviço não voltou saudável depois da atualização."
        journalctl -u projeto-saida --no-pager -n 40 >&2 || true
        rollback_update
        die "Atualização revertida por falha no health-check pós-restart."
    fi

    local after_commit
    after_commit="$(sudo -u "$SYS_USER" -H bash -c "cd '$INSTALL_DIR' && git rev-parse HEAD")"
    ok "Atualização concluída com sucesso: ${before_commit:0:8} → ${after_commit:0:8}"
    echo "  Backup pré-atualização: $backup_pre_dir"
    echo "  Logs: journalctl -u projeto-saida -f"
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
