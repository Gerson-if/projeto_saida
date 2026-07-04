"""
deploy/gunicorn_conf.py — Configuração do Gunicorn para produção.

Uso:
    gunicorn -c deploy/gunicorn_conf.py "run:app"

Ajuste as variáveis de ambiente abaixo (ou edite os valores padrão aqui)
conforme o tamanho da VM. Veja deploy/DEPLOY.md para o racional de cada
escolha, especialmente a relação entre WEB_CONCURRENCY e SCHEDULER_ENABLED.
"""

import multiprocessing
import os

# ── Endereço/porta ───────────────────────────────────────────────────────
# 127.0.0.1: só o Nginx (na mesma máquina) acessa o Gunicorn diretamente.
# A aplicação nunca fica exposta direto na internet.
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")

# ── Workers ──────────────────────────────────────────────────────────────
# Padrão simples e seguro para a maioria das VMs pequenas/médias: 1 worker
# com várias threads (bom para I/O-bound como este app, e evita duplicar
# o agendador de status em processos diferentes — veja SCHEDULER_ENABLED
# em config.py se decidir usar vários workers).
#
# Para escalar horizontalmente, defina WEB_CONCURRENCY > 1 no ambiente E
# SCHEDULER_ENABLED=false (para não rodar o job de status N vezes) — nesse
# caso, agende `flask atualizar-status` via systemd timer/cron.
workers = int(os.environ.get("WEB_CONCURRENCY", 1))
threads = int(os.environ.get("GUNICORN_THREADS", 4))
worker_class = "gthread"

# ── Timeouts ─────────────────────────────────────────────────────────────
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 60))
graceful_timeout = 30
keepalive = 5

# ── Logs — vão para o journal do systemd (stdout/stderr) ────────────────
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")

# ── Robustez ─────────────────────────────────────────────────────────────
# Recicla workers periodicamente (higiene contra vazamento de memória de
# longa duração) com jitter para não reciclar todos ao mesmo tempo.
max_requests = 2000
max_requests_jitter = 200

# Nome do processo — facilita achar em `ps aux` / `htop`
proc_name = "projeto_saida"
