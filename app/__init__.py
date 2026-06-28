"""
app/__init__.py — Application Factory do Flask.

Uso:
    from app import create_app
    app = create_app()           # usa DevelopmentConfig
    app = create_app("production")
"""

import os

from flask import Flask
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
    from config import config as config_map

    app = Flask(__name__, instance_relative_config=False)

    # ── Seleciona a configuração ───────────────────────────────────────────
    env = config_name or os.environ.get("FLASK_ENV", "default")
    cfg_class = config_map.get(env, config_map["default"])
    app.config.from_object(cfg_class)

    # Valida variáveis críticas em produção
    if hasattr(cfg_class, "validate"):
        cfg_class.validate()

    # ── Garante diretórios necessários ────────────────────────────────────
    for folder in (app.config["UPLOAD_FOLDER"], app.config["RELATORIO_FOLDER"]):
        os.makedirs(folder, exist_ok=True)

    # ── Inicializa extensões ───────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Por favor, faça login para acessar esta página."
    login_manager.login_message_category = "warning"

    # ── Registra context processors ────────────────────────────────────────
    from app.context_processors import register_context_processors
    register_context_processors(app)

    # ── Registra tratadores de erro (páginas amigáveis para 400/403/404/413/500...)
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


def _init_scheduler(app: Flask) -> None:
    """
    Registra job APScheduler para atualizar status de saídas automaticamente.
    O job roda em background a cada N minutos (configurável via SCHEDULER_STATUS_INTERVAL_MINUTES).
    """
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
    Função executada pelo scheduler.
    Roda dentro do application context para ter acesso ao banco.
    """
    with app.app_context():
        from app.models import Registro, StatusSaida
        try:
            pendentes = Registro.query.filter(
                Registro.status.in_([StatusSaida.AGENDADA, StatusSaida.EM_TRANSITO])
            ).all()

            atualizados = 0
            for registro in pendentes:
                if registro.atualizar_status_automatico():
                    atualizados += 1

            if atualizados:
                db.session.commit()
                app.logger.info(f"[scheduler] {atualizados} saída(s) atualizada(s) automaticamente.")
        except Exception:
            db.session.rollback()
            app.logger.exception("[scheduler] Falha ao atualizar status automático de saídas.")
