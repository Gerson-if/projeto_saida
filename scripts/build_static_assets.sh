#!/usr/bin/env bash
#
# scripts/build_static_assets.sh — Compilação estática dos assets de terceiros
# =============================================================================
#
# Baixa versões fixas do Bootstrap, Bootstrap Icons, Chart.js e da fonte Inter
# e organiza tudo dentro de app/static/vendor/, para a aplicação servir esses
# arquivos localmente em vez de depender de CDNs externos em tempo de
# execução. Isso deixa o carregamento das páginas mais rápido (sem handshake
# TLS extra para 2-3 domínios diferentes, sem esperar CDN responder) e faz a
# aplicação continuar funcionando mesmo se o CDN de terceiros sair do ar ou a
# VM não tiver acesso à internet depois de instalada.
#
# Quem chama este script:
#   - setup_dev.sh, no ambiente de desenvolvimento;
#   - deploy/install.sh, durante a instalação e a cada atualização em produção.
#
# Uso:
#   bash scripts/build_static_assets.sh            # só baixa o que estiver faltando/desatualizado
#   bash scripts/build_static_assets.sh --force     # ignora o cache e baixa tudo de novo
#
# Não precisa de Node/npm — os pacotes são baixados diretamente do registro
# do npm (registry.npmjs.org) como tarballs, só com curl e tar.
#
set -euo pipefail

BOOTSTRAP_VERSION="5.3.2"
BOOTSTRAP_ICONS_VERSION="1.11.3"
CHARTJS_VERSION="4.4.0"
INTER_VERSION="5.3.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENDOR_DIR="$REPO_ROOT/app/static/vendor"
MARKER="$VENDOR_DIR/.build_versions"
VERSOES_ATUAIS="bootstrap=$BOOTSTRAP_VERSION;bootstrap-icons=$BOOTSTRAP_ICONS_VERSION;chartjs=$CHARTJS_VERSION;inter=$INTER_VERSION"

FORCE="0"
[ "${1:-}" = "--force" ] && FORCE="1"

log()  { echo "==> $*"; }
err()  { echo "✘ $*" >&2; }
die()  { err "$*"; exit 1; }

command -v curl >/dev/null 2>&1 || die "curl não encontrado — instale curl e rode de novo."
command -v tar  >/dev/null 2>&1 || die "tar não encontrado — instale tar e rode de novo."

if [ -f "$MARKER" ] && [ "$FORCE" != "1" ] && [ "$(cat "$MARKER" 2>/dev/null)" = "$VERSOES_ATUAIS" ]; then
    log "Assets estáticos já compilados nas versões atuais — nada a fazer (use --force para refazer)."
    exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

baixar() {
    # baixar <url> <destino> — 3 tentativas, por instabilidade de rede transitória.
    local url="$1" destino="$2" tentativa=1
    until curl -fsSL --max-time 60 -o "$destino" "$url" 2>"$TMP/curl.err"; do
        if [ "$tentativa" -ge 3 ]; then
            err "Falha ao baixar $url depois de 3 tentativas:"
            cat "$TMP/curl.err" >&2 2>/dev/null || true
            return 1
        fi
        tentativa=$((tentativa + 1))
        sleep 2
    done
}

log "Preparando app/static/vendor/"
rm -rf "$VENDOR_DIR"
mkdir -p "$VENDOR_DIR"

log "Bootstrap $BOOTSTRAP_VERSION"
baixar "https://registry.npmjs.org/bootstrap/-/bootstrap-${BOOTSTRAP_VERSION}.tgz" "$TMP/bootstrap.tgz" \
    || die "Não consegui baixar o Bootstrap. Confira a conexão com registry.npmjs.org."
mkdir -p "$TMP/bootstrap"
tar xzf "$TMP/bootstrap.tgz" -C "$TMP/bootstrap"
mkdir -p "$VENDOR_DIR/bootstrap/css" "$VENDOR_DIR/bootstrap/js"
cp "$TMP/bootstrap/package/dist/css/bootstrap.min.css" "$VENDOR_DIR/bootstrap/css/bootstrap.min.css"
cp "$TMP/bootstrap/package/dist/js/bootstrap.bundle.min.js" "$VENDOR_DIR/bootstrap/js/bootstrap.bundle.min.js"

log "Bootstrap Icons $BOOTSTRAP_ICONS_VERSION"
baixar "https://registry.npmjs.org/bootstrap-icons/-/bootstrap-icons-${BOOTSTRAP_ICONS_VERSION}.tgz" "$TMP/bsicons.tgz" \
    || die "Não consegui baixar o Bootstrap Icons."
mkdir -p "$TMP/bsicons"
tar xzf "$TMP/bsicons.tgz" -C "$TMP/bsicons"
mkdir -p "$VENDOR_DIR/bootstrap-icons/fonts"
cp "$TMP/bsicons/package/font/bootstrap-icons.min.css" "$VENDOR_DIR/bootstrap-icons/bootstrap-icons.min.css"
cp "$TMP/bsicons/package/font/fonts/bootstrap-icons.woff2" "$VENDOR_DIR/bootstrap-icons/fonts/bootstrap-icons.woff2"
cp "$TMP/bsicons/package/font/fonts/bootstrap-icons.woff" "$VENDOR_DIR/bootstrap-icons/fonts/bootstrap-icons.woff"

log "Chart.js $CHARTJS_VERSION"
baixar "https://registry.npmjs.org/chart.js/-/chart.js-${CHARTJS_VERSION}.tgz" "$TMP/chartjs.tgz" \
    || die "Não consegui baixar o Chart.js."
mkdir -p "$TMP/chartjs"
tar xzf "$TMP/chartjs.tgz" -C "$TMP/chartjs"
mkdir -p "$VENDOR_DIR/chartjs"
cp "$TMP/chartjs/package/dist/chart.umd.js" "$VENDOR_DIR/chartjs/chart.umd.js"

log "Fonte Inter (variável, $INTER_VERSION — subconjuntos latin/latin-ext, cobre acentuação do português)"
baixar "https://registry.npmjs.org/@fontsource-variable/inter/-/inter-${INTER_VERSION}.tgz" "$TMP/inter.tgz" \
    || die "Não consegui baixar a fonte Inter."
mkdir -p "$TMP/inter"
tar xzf "$TMP/inter.tgz" -C "$TMP/inter"
mkdir -p "$VENDOR_DIR/fonts/inter/files"
cp "$TMP/inter/package/files/inter-latin-wght-normal.woff2" "$VENDOR_DIR/fonts/inter/files/inter-latin-wght-normal.woff2"
cp "$TMP/inter/package/files/inter-latin-ext-wght-normal.woff2" "$VENDOR_DIR/fonts/inter/files/inter-latin-ext-wght-normal.woff2"
cat > "$VENDOR_DIR/fonts/inter/inter.css" <<'CSSEOF'
/* Fonte Inter (peso variável 100-900), self-hosted.
 * Gerado por scripts/build_static_assets.sh a partir do pacote npm
 * @fontsource-variable/inter — só os subconjuntos latin + latin-ext
 * (cobre toda a acentuação do português: á ã â à ç é ê í ó õ ô ú ü, etc.).
 * Não editar à mão; rode o script de novo para atualizar.
 */
@font-face {
  font-family: 'Inter';
  font-style: normal;
  font-display: swap;
  font-weight: 100 900;
  src: url(./files/inter-latin-ext-wght-normal.woff2) format('woff2-variations');
  unicode-range: U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F,U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF;
}
@font-face {
  font-family: 'Inter';
  font-style: normal;
  font-display: swap;
  font-weight: 100 900;
  src: url(./files/inter-latin-wght-normal.woff2) format('woff2-variations');
  unicode-range: U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD;
}
CSSEOF

echo "$VERSOES_ATUAIS" > "$MARKER"

TAMANHO="$(du -sh "$VENDOR_DIR" 2>/dev/null | cut -f1)"
log "Assets estáticos compilados em app/static/vendor/ (${TAMANHO:-?}). A aplicação não depende mais de CDN externo."
