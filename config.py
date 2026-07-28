"""
config.py — Configurações da aplicação.

Hierarquia:
  DevelopmentConfig  →  usa SQLite local, DEBUG=True
  ProductionConfig   →  lê DATABASE_URL do ambiente, DEBUG=False
  TestingConfig      →  banco em memória, TESTING=True

Para selecionar: FLASK_ENV=production  (ou passe a classe diretamente).
"""

import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # ── Segurança ──────────────────────────────────────────────────────────
    SECRET_KEY: str = os.environ.get(
        "SECRET_KEY", "troque-esta-chave-em-producao-use-uma-muito-longa"
    )

    # ── Banco de dados ─────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(basedir, 'instance', 'sistema_saida.db')}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        # Reconecta automaticamente após idle de conexão (importante para MariaDB)
        "pool_recycle": 280,
        "pool_pre_ping": True,
    }

    # ── Upload de arquivos ─────────────────────────────────────────────────
    # IMPORTANTE: esta lista é apenas informativa/legado. A validação real do
    # arquivo é feita pelo conteúdo (Pillow), não pela extensão — ver
    # app/uploads.py::FORMATOS_ACEITOS, que é a fonte de verdade.
    UPLOAD_FOLDER: str = os.path.join(basedir, "app", "static", "uploads")
    MAX_CONTENT_LENGTH: int = 5 * 1024 * 1024          # 5 MB (limite global do Flask)
    ALLOWED_EXTENSIONS: set = {"png", "jpg", "jpeg", "gif", "webp", "ico"}

    # ── Relatórios (PDF) ───────────────────────────────────────────────────
    RELATORIO_FOLDER: str = os.path.join(basedir, "app", "static", "relatorios")

    # ── Identidade visual (fallback; o admin pode sobrescrever via DB) ─────
    SISTEMA_NOME: str = os.environ.get(
        "SISTEMA_NOME", "Sistema de Controle de Saídas"
    )
    SISTEMA_SUBTITULO: str = os.environ.get(
        "SISTEMA_SUBTITULO", "Gestão de Saídas de Guarnição"
    )
    SISTEMA_ORGANIZACAO: str = os.environ.get(
        "SISTEMA_ORGANIZACAO", "Organização Militar"
    )

    # ── Regras de negócio ──────────────────────────────────────────────────
    # Limite de caracteres para o campo "motivo" no formulário de saída
    MOTIVO_MAX_LENGTH: int = 300

    # Motivos pré-definidos exibidos como sugestão no formulário
    MOTIVOS_SUGERIDOS: list = [
        "Férias anuais",
        "Licença médica / Tratamento de saúde",
        "Visita familiar",
        "Curso / Capacitação",
        "Missão oficial",
        "Licença especial",
        "Outro",
    ]

    # ── Agendador de status ────────────────────────────────────────────────
    # Intervalo (em minutos) em que o job de atualização automática roda
    SCHEDULER_STATUS_INTERVAL_MINUTES: int = int(
        os.environ.get("SCHEDULER_STATUS_INTERVAL_MINUTES", 10)
    )


class DevelopmentConfig(Config):
    DEBUG: bool = True


class ProductionConfig(Config):
    DEBUG: bool = False

    @classmethod
    def validate(cls) -> None:
        """Garante que variáveis críticas estejam definidas em produção."""
        missing = []
        if cls.SECRET_KEY == "troque-esta-chave-em-producao-use-uma-muito-longa":
            missing.append("SECRET_KEY")
        if not os.environ.get("DATABASE_URL"):
            missing.append("DATABASE_URL")
        if missing:
            raise RuntimeError(
                f"Variáveis de ambiente obrigatórias não configuradas: {missing}"
            )


class TestingConfig(Config):
    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"
    WTF_CSRF_ENABLED: bool = False


# Mapa de nomes → classes (usado em create_app e FLASK_ENV)
config: dict = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
