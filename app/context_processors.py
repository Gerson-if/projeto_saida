"""
context_processors.py — Variáveis globais injetadas em todos os templates.

Disponível em todos os templates:
  config_sistema  →  dict com as configurações dinâmicas do banco
  now             →  datetime.now() para exibir data/hora atual
"""

from datetime import datetime

from app.models import ConfigSistema


def register_context_processors(app) -> None:
    @app.context_processor
    def inject_globals() -> dict:
        try:
            configs = {c.chave: c.valor for c in ConfigSistema.query.all()}
        except Exception:
            # Banco ainda não inicializado (ex: primeiro boot)
            configs = {}
        return {
            "config_sistema": configs,
            "now": datetime.now(),
        }
