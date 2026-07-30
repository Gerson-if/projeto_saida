"""
context_processors.py — Variáveis globais injetadas em todos os templates.

Disponível em todos os templates:
  config_sistema              →  dict com as configurações dinâmicas do banco
  now                         →  datetime.now() para exibir data/hora atual
  solicitacoes_pendentes_count →  nº de solicitações de posto/graduação
                                   aguardando aprovação (só calculado para o
                                   super-usuário logado — é a "notificação"
                                   de que há alterações pedidas por militares)
  max_content_length_mb       →  limite de upload (MAX_CONTENT_LENGTH) em MB,
                                   para telas com formulário de upload
                                   validarem no navegador ANTES de enviar —
                                   evita que o usuário só descubra que
                                   passou do limite depois de esperar o
                                   upload inteiro (e, sem isso, poderia
                                   nem ver mensagem nenhuma, caso o Nginx
                                   rejeitasse antes do Flask responder).
"""

from datetime import datetime

from flask_login import current_user

from app import db
from app.models import ConfigSistema, SolicitacaoPostoGraduacao


def register_context_processors(app) -> None:
    @app.context_processor
    def inject_globals() -> dict:
        try:
            configs = {c.chave: c.valor for c in ConfigSistema.query.all()}
        except Exception:
            # Banco ainda não inicializado (ex: primeiro boot) ou erro
            # transitório (ex: lock momentâneo). Além de cair no valor
            # padrão, é ESSENCIAL desfazer a transação aqui: sem o
            # rollback, a sessão do SQLAlchemy fica marcada como
            # "precisa de rollback" e qualquer consulta seguinte na MESMA
            # requisição (ex: dentro da própria rota) falharia com um erro
            # totalmente não relacionado ("PendingRollbackError"), como se
            # o sistema tivesse quebrado do nada.
            try:
                db.session.rollback()
            except Exception:
                pass
            app.logger.warning("Falha ao carregar config_sistema no context processor.", exc_info=True)
            configs = {}

        pendentes = 0
        try:
            if current_user.is_authenticated and current_user.is_admin:
                pendentes = SolicitacaoPostoGraduacao.contar_pendentes()
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            pendentes = 0

        return {
            "config_sistema": configs,
            "now": datetime.now(),
            "solicitacoes_pendentes_count": pendentes,
            "max_content_length_mb": app.config.get("MAX_CONTENT_LENGTH", 0) / (1024 * 1024),
        }
