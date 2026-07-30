"""
app/__init__.py — Application Factory do Flask.

Uso:
    from app import create_app
    app = create_app()           # usa DevelopmentConfig
    app = create_app("production")
"""

import os
import time
import uuid

from flask import Flask, request
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# Extensões inicializadas sem app (pattern Application Factory)
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
bcrypt = Bcrypt()


def create_app(config_name: str | None = None) -> Flask:
    """
    Cria e configura a instância Flask.

    Args:
        config_name: Chave do dict `config` em config.py
                     ('development', 'production', 'testing').
                     Se None, usa FLASK_ENV ou 'default'.
    """
    from config import config as config_map, INSTANCE_DIR

    app = Flask(__name__, instance_relative_config=False)

    # ── Seleciona a configuração ───────────────────────────────────────────
    env = config_name or os.environ.get("FLASK_ENV", "default")
    cfg_class = config_map.get(env, config_map["default"])
    app.config.from_object(cfg_class)

    # Valida variáveis críticas em produção
    if hasattr(cfg_class, "validate"):
        cfg_class.validate()

    # ── Garante diretórios necessários ─────────────────────────────────────
    # instance/ precisa existir antes de criar o banco SQLite
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    for folder in (app.config["UPLOAD_FOLDER"], app.config["RELATORIO_FOLDER"]):
        os.makedirs(folder, exist_ok=True)

    # ── Proxy reverso (Nginx, etc.) ─────────────────────────────────────────
    # Sem isso, atrás de um proxy reverso o Flask vê toda requisição como
    # vinda de 127.0.0.1 e sempre em HTTP (mesmo com HTTPS ativo no proxy),
    # o que quebra url_for(..., _external=True) e corrompe o IP nos logs.
    if app.config.get("BEHIND_PROXY", True):
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # ── Inicializa extensões ───────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Por favor, faça login para acessar esta página."
    login_manager.login_message_category = "warning"
    # "strong": se o IP ou o User-Agent do navegador mudar no meio de uma
    # sessão marcada como "lembrar-me", o Flask-Login invalida a sessão e
    # exige login novamente. É a defesa mais direta contra uma sessão sendo
    # aceita fora do navegador/contexto onde ela foi criada.
    login_manager.session_protection = "strong"

    with app.app_context():
        from app.db_utils import configurar_sqlite
        configurar_sqlite(app, db)

    # ── Logging em arquivo (facilita debug em produção e em dev) ──────────
    _init_logging(app)

    # ── Cabeçalhos de resposta (cache + segurança básica) ──────────────────
    _init_response_headers(app)

    # ── Registra context processors ────────────────────────────────────────
    from app.context_processors import register_context_processors
    register_context_processors(app)

    # ── Registra tratadores de erro ────────────────────────────────────────
    from app.error_handlers import register_error_handlers
    register_error_handlers(app)

    # ── Registra comandos CLI ──────────────────────────────────────────────
    from app.commands import register_commands
    register_commands(app)

    # ── Registra blueprints ────────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.user import user_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(user_bp, url_prefix="/usuario")
    app.register_blueprint(reports_bp, url_prefix="/relatorios")

    # ── Agendador de status automático ────────────────────────────────────
    _init_scheduler(app)

    return app


def _init_logging(app: Flask) -> None:
    """
    Configura log em arquivo rotativo, além do console.

    Antes desta mudança, muitos `except Exception: db.session.rollback()`
    espalhados pelas rotas engoliam o erro real sem registrar nada — o único
    sinal era um flash genérico pro usuário. Isso torna impossível investigar
    problemas depois (inclusive os de concorrência). Com isso aqui, qualquer
    `current_app.logger.exception(...)` (usado em app/db_utils.py e nos
    handlers de erro) grava o traceback completo em
    instance/logs/app.log.

    Cada linha também ganha um "req=<id>" de correlação (o mesmo em todas as
    linhas de uma mesma requisição, inclusive um eventual traceback), além de
    IP, usuário, método e caminho — sem isso, investigar um problema relatado
    por um usuário significava vasculhar o log inteiro tentando adivinhar
    qual linha era dela pelo horário aproximado. Esse mesmo id também vai no
    cabeçalho de resposta "X-Request-ID", então dá pra pedir pro usuário
    olhar as ferramentas de desenvolvedor do navegador e já saber
    exatamente qual linha procurar no log.

    IMPORTANTE (lição de uma investigação real de "413 Request Entity Too
    Large" que levou várias rodadas para resolver): quando é o Nginx quem
    recusa a requisição (ex.: limite de upload excedido ANTES de chegar ao
    Flask), nada disso aparece aqui — o Flask nunca chega a rodar. Esses
    casos só aparecem em /var/log/nginx/projeto-saida.error.log (veja a
    ação 'logs' do instalador, que já mostra os dois lados).
    """
    import logging
    from logging.handlers import RotatingFileHandler

    if app.testing:
        return

    from config import INSTANCE_DIR
    log_dir = os.path.join(INSTANCE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)

    class _ContextoRequisicaoFilter(logging.Filter):
        """Anexa dados da requisição em andamento a cada LogRecord (ou um
        "-" em cada campo quando o log acontece fora de uma requisição,
        como no agendador de status em background)."""

        def filter(self, record: logging.LogRecord) -> bool:
            from flask import g, has_request_context

            if has_request_context():
                record.request_id = getattr(g, "request_id", "-")
                record.remote_addr = request.remote_addr or "-"
                record.metodo = request.method
                record.caminho = request.path
                try:
                    from flask_login import current_user
                    record.usuario = (
                        current_user.cpf if current_user.is_authenticated else "anon"
                    )
                except Exception:
                    record.usuario = "-"
            else:
                record.request_id = "-"
                record.remote_addr = "-"
                record.metodo = "-"
                record.caminho = "-"
                record.usuario = "-"
            return True

    handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=2_000_000,
        backupCount=8,
        encoding="utf-8",
    )
    handler.addFilter(_ContextoRequisicaoFilter())
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] "
        "req=%(request_id)s ip=%(remote_addr)s usuario=%(usuario)s "
        "%(metodo)s %(caminho)s :: %(message)s"
    ))
    nivel = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    handler.setLevel(nivel)

    if not any(isinstance(h, RotatingFileHandler) for h in app.logger.handlers):
        app.logger.addHandler(handler)
    app.logger.setLevel(nivel)

    # ── Id de correlação por requisição + log-resumo de cada requisição ────
    @app.before_request
    def _marcar_inicio_requisicao():
        from flask import g
        g.request_id = uuid.uuid4().hex[:12]
        g._inicio_requisicao_monotonico = time.monotonic()

    @app.after_request
    def _registrar_requisicao_concluida(response):
        from flask import g
        response.headers["X-Request-ID"] = getattr(g, "request_id", "-")
        # Não registra estático: em produção o Nginx serve /static/ direto
        # (nem passa pelo Flask); em dev ainda passaria, mas só geraria
        # ruído sem ajudar a diagnosticar nada.
        if not request.path.startswith("/static/"):
            inicio = getattr(g, "_inicio_requisicao_monotonico", None)
            duracao_ms = int((time.monotonic() - inicio) * 1000) if inicio is not None else -1
            app.logger.info("requisição concluída: status=%s duracao_ms=%s",
                             response.status_code, duracao_ms)
        return response


def _init_response_headers(app: Flask) -> None:
    """
    - Evita que páginas autenticadas sejam guardadas em cache por proxies ou
      pelo próprio navegador. Sem isso, em ambientes com proxy reverso
      cacheando por engano (ou botão "voltar" do navegador após logout),
      uma página com dados de outro usuário poderia ser reexibida.
    - Cabeçalhos básicos de hardening que não têm custo nenhum.
    """
    from flask_login import current_user

    @app.after_request
    def _sem_cache_para_paginas_autenticadas(response):
        try:
            autenticado = current_user.is_authenticated
        except Exception:
            autenticado = False

        if autenticado or request.path.startswith(("/admin", "/usuario", "/login", "/relatorios")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        return response


def _init_scheduler(app: Flask) -> None:
    """
    Registra job APScheduler para atualizar status de saídas automaticamente.

    Duas travas contra duplicação:
    1. Em dev, o Werkzeug reloader forka dois processos — só inicia no
       processo "filho" (WERKZEUG_RUN_MAIN=true).
    2. Em produção com múltiplos workers Gunicorn, cada worker é um processo
       separado — SCHEDULER_ENABLED=false desliga o agendador em todos eles,
       para usar `flask atualizar-status` via cron/systemd timer em vez
       disso (veja deploy/DEPLOY.md).
    """
    if not app.config.get("SCHEDULER_ENABLED", True):
        app.logger.info(
            "Agendador em processo desativado (SCHEDULER_ENABLED=false) — "
            "configure `flask atualizar-status` via cron/systemd timer."
        )
        return

    # Em dev, o Werkzeug reloader fork dois processos. Só inicia o scheduler
    # no processo "filho" (WERKZEUG_RUN_MAIN=true) ou em produção.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "false":
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        app.logger.warning(
            "APScheduler não instalado — atualização automática de status desativada."
        )
        return

    interval = app.config.get("SCHEDULER_STATUS_INTERVAL_MINUTES", 10)

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        func=_job_atualizar_status,
        trigger=IntervalTrigger(minutes=interval),
        args=[app],
        id="atualizar_status_saidas",
        name="Atualização automática de status de saídas",
        replace_existing=True,
    )
    scheduler.start()
    app.logger.info(
        f"Agendador iniciado — job de status a cada {interval} minuto(s)."
    )


def _job_atualizar_status(app: Flask) -> None:
    """
    Função executada pelo scheduler dentro do application context.
    """
    with app.app_context():
        from app.models import Registro, StatusSaida
        from app.db_utils import commit_seguro
        try:
            pendentes = Registro.query.filter(
                Registro.status.in_([StatusSaida.AGENDADA, StatusSaida.EM_TRANSITO])
            ).all()

            atualizados = 0
            for registro in pendentes:
                if registro.atualizar_status_automatico():
                    atualizados += 1

            if atualizados:
                # commit_seguro faz retry em caso de lock transitório (ex:
                # um usuário salvando algo bem nesse instante) e loga
                # qualquer falha real, em vez de deixar o job morrer
                # silenciosamente.
                ok, erro = commit_seguro(
                    db,
                    mensagem_erro="Falha ao atualizar status automático de saídas.",
                )
                if ok:
                    app.logger.info(
                        f"[scheduler] {atualizados} saída(s) atualizada(s) automaticamente."
                    )
                else:
                    app.logger.error(f"[scheduler] {erro}")
        except Exception:
            db.session.rollback()
            app.logger.exception(
                "[scheduler] Falha ao atualizar status automático de saídas."
            )
