"""
context_processors.py — Variáveis globais injetadas em todos os templates.

Disponível em todos os templates:
  config_sistema              →  dict com as configurações dinâmicas do banco
  now                         →  datetime.now() para exibir data/hora atual
  solicitacoes_pendentes_count →  nº de solicitações de posto/graduação
                                   aguardando aprovação (só calculado para o
                                   super-usuário logado — é a "notificação"
                                   de que há alterações pedidas por militares)
"""

from datetime import datetime

from flask_login import current_user

from app.models import ConfigSistema, SolicitacaoPostoGraduacao


def register_context_processors(app) -> None:
    @app.context_processor
    def inject_globals() -> dict:
        try:
            configs = {c.chave: c.valor for c in ConfigSistema.query.all()}
        except Exception:
            # Banco ainda não inicializado (ex: primeiro boot)
            configs = {}

        pendentes = 0
        try:
            if current_user.is_authenticated and current_user.is_admin:
                pendentes = SolicitacaoPostoGraduacao.contar_pendentes()
        except Exception:
            pendentes = 0

        return {
            "config_sistema": configs,
            "now": datetime.now(),
            "solicitacoes_pendentes_count": pendentes,
        }
