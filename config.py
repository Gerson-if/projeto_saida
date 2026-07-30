"""
config.py — Configurações da aplicação.

Hierarquia:
  DevelopmentConfig  →  usa SQLite local em instance/, DEBUG=True
  ProductionConfig   →  lê DATABASE_URL do ambiente (sempre MariaDB/MySQL —
                         SQLite é rejeitado por validate(), veja abaixo),
                         DEBUG=False
  TestingConfig      →  banco em memória, TESTING=True

SQLite é só para desenvolvimento local (setup_dev.sh). Em produção,
deploy/install.sh sempre configura MariaDB — não há suporte a SQLite em
produção porque um arquivo único não aguenta bem escrita concorrente de
vários usuários/workers Gunicorn ao mesmo tempo.

Para selecionar: export FLASK_ENV=production  (ou passe a classe diretamente).
"""

import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

# Pasta instance/ para o SQLite — criada em runtime pelo __init__.py
INSTANCE_DIR = os.path.join(basedir, "instance")

# Valor de fallback antigo. Se alguém ainda tiver isso no .env, tratamos como
# "não configurado" — porque essa string está escrita no código-fonte público
# do projeto. Qualquer pessoa que leia o repositório conhece essa chave, e
# quem conhece a SECRET_KEY consegue *forjar* um cookie de sessão válido para
# qualquer usuário (inclusive admin) sem nunca ter feito login. Isso é o tipo
# de bug que se manifesta como "essa aba apareceu logada sozinha": não é a
# aba que herdou a sessão, é que qualquer cookie assinado com essa chave
# conhecida é aceito pelo servidor como legítimo.
_CHAVE_INSEGURA_LEGADA = "troque-esta-chave-em-producao-use-uma-muito-longa"

# Preenchido por _obter_secret_key(): True se a chave veio de uma variável de
# ambiente explícita (o esperado em produção); False se foi autogerada em
# instance/secret_key (aceitável em dev, mas ProductionConfig.validate()
# deve recusar subir assim).
_secret_key_veio_do_ambiente = False


def _obter_secret_key() -> str:
    """
    Resolve a SECRET_KEY com a seguinte prioridade:

    1. Variável de ambiente SECRET_KEY, desde que não seja o valor
       inseguro conhecido publicamente no código.
    2. Um arquivo `instance/secret_key` gerado automaticamente na primeira
       execução (uma chave aleatória por instalação, nunca versionada).

    Isso garante que, mesmo em dev/sem configurar nada, cada instalação do
    sistema tem uma chave própria e imprevisível — sessões de uma instalação
    nunca são aceitas por outra, e ninguém consegue forjar cookies só por
    ter lido o código-fonte no GitHub.
    """
    global _secret_key_veio_do_ambiente

    env_key = os.environ.get("SECRET_KEY")
    if env_key and env_key != _CHAVE_INSEGURA_LEGADA:
        _secret_key_veio_do_ambiente = True
        return env_key

    os.makedirs(INSTANCE_DIR, exist_ok=True)
    caminho_chave = os.path.join(INSTANCE_DIR, "secret_key")

    if os.path.exists(caminho_chave):
        with open(caminho_chave, "r", encoding="utf-8") as f:
            chave = f.read().strip()
            if chave:
                return chave

    nova_chave = secrets.token_hex(32)
    # Grava com permissão restrita (somente o dono lê/escreve), quando o SO
    # suportar (Windows ignora o modo silenciosamente).
    fd = os.open(caminho_chave, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(nova_chave)
    return nova_chave


class Config:
    # ── Segurança ──────────────────────────────────────────────────────────
    SECRET_KEY: str = _obter_secret_key()

    # ── Cookies de sessão ──────────────────────────────────────────────────
    # Nome próprio evita colisão com outra aplicação Flask rodando no mesmo
    # domínio/porta (ex: outro projeto local na 5000) que use o nome padrão
    # "session" — dois apps diferentes no mesmo host podem, sem isso,
    # sobrescrever o cookie um do outro.
    SESSION_COOKIE_NAME: str = "saida_session"
    SESSION_COOKIE_HTTPONLY: bool = True        # JS não pode ler o cookie
    SESSION_COOKIE_SAMESITE: str = "Lax"        # bloqueia envio cross-site
    SESSION_COOKIE_SECURE: bool = False         # ligado em produção (abaixo)
    PERMANENT_SESSION_LIFETIME: timedelta = timedelta(
        minutes=int(os.environ.get("SESSION_LIFETIME_MINUTES", 480))  # 8h
    )
    SESSION_REFRESH_EACH_REQUEST: bool = True

    # "Lembrar-me" — cookie de longa duração do Flask-Login. Também precisa
    # das mesmas travas, senão vira a forma mais fraca de manter sessão.
    REMEMBER_COOKIE_DURATION: timedelta = timedelta(
        days=int(os.environ.get("REMEMBER_COOKIE_DAYS", 14))
    )
    REMEMBER_COOKIE_HTTPONLY: bool = True
    REMEMBER_COOKIE_SAMESITE: str = "Lax"
    REMEMBER_COOKIE_SECURE: bool = False        # ligado em produção (abaixo)

    # ── Banco de dados ─────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(INSTANCE_DIR, 'sistema_saida.db')}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # pool_recycle e pool_pre_ping causam problemas com SQLite puro.
    # Em produção com MariaDB/MySQL, sobrescrevemos com os valores adequados.
    SQLALCHEMY_ENGINE_OPTIONS: dict = {}

    # ── Upload de arquivos ─────────────────────────────────────────────────
    UPLOAD_FOLDER: str = os.path.join(basedir, "app", "static", "uploads")
    # Limite global do Flask — precisa cobrir o PIOR CASO de uma única
    # requisição, não um upload isolado. A tela de Configurações envia até
    # 5 campos de imagem (logo, logo_relatorio, brasao, favicon,
    # login_bg_imagem — máx. 10MB cada, ver app/uploads.py) MAIS o vídeo de
    # fundo do login (máx. 20MB) no mesmo POST: 5×10 + 20 = 70MB no limite
    # teórico. 90MB dá uma margem confortável sem abrir mão da defesa.
    #
    # IMPORTANTE: se mudar este valor, mude também `client_max_body_size`
    # em deploy/nginx.conf — o Nginx rejeita a requisição ANTES dela
    # sequer chegar ao Flask se o valor de lá for menor. De propósito, o
    # Nginx é configurado um pouco ACIMA deste valor (hoje 100M lá contra
    # 90M aqui): assim, na prática, é quase sempre o Flask quem recusa
    # primeiro — com uma mensagem amigável por campo — em vez do Nginx,
    # que devolveria a página genérica dele (ver
    # deploy/static-error-pages/413.html para quando isso acontece mesmo
    # assim). `flask diagnosticar` avisa se os dois ficarem dessincronizados
    # numa instalação em produção.
    MAX_CONTENT_LENGTH: int = 90 * 1024 * 1024
    ALLOWED_EXTENSIONS: set = {"png", "jpg", "jpeg", "gif", "webp", "ico"}
    ALLOWED_VIDEO_EXTENSIONS: set = {"mp4", "webm", "ogg"}

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
    MOTIVO_MAX_LENGTH: int = 300

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
    SCHEDULER_STATUS_INTERVAL_MINUTES: int = int(
        os.environ.get("SCHEDULER_STATUS_INTERVAL_MINUTES", 10)
    )
    # Em produção com múltiplos workers Gunicorn, CADA worker é um processo
    # separado — se o agendador ficar ligado, o job de atualização de status
    # roda uma vez POR worker (duplicado). Duas opções em produção:
    #   1) 1 worker (--workers 1 --threads N): pode deixar ligado (padrão).
    #   2) Vários workers: defina SCHEDULER_ENABLED=false no ambiente e
    #      agende `flask atualizar-status` via cron/systemd timer em vez
    #      disso (veja deploy/DEPLOY.md).
    SCHEDULER_ENABLED: bool = os.environ.get("SCHEDULER_ENABLED", "true").lower() not in (
        "false", "0", "no",
    )

    # ── Proxy reverso (Nginx/Cloudflare/etc.) ───────────────────────────────
    # Quando o Flask roda atrás de um proxy que já termina o TLS, ele não
    # vê o IP real do cliente nem o esquema (https) sem essa camada —
    # o que quebra geração de URL externa correta e deixa os logs com o
    # IP do proxy em vez do cliente. Ligado por padrão (é o caso comum de
    # produção); desligue com BEHIND_PROXY=false se expuser o Flask direto.
    BEHIND_PROXY: bool = os.environ.get("BEHIND_PROXY", "true").lower() not in (
        "false", "0", "no",
    )

    # ── Proteção contra força bruta no login ───────────────────────────────
    LOGIN_MAX_TENTATIVAS: int = int(os.environ.get("LOGIN_MAX_TENTATIVAS", 5))
    LOGIN_BLOQUEIO_MINUTOS: int = int(os.environ.get("LOGIN_BLOQUEIO_MINUTOS", 15))

    # ── Concorrência / SQLite ───────────────────────────────────────────────
    # Quantas vezes tentamos novamente um commit que falhou por
    # "database is locked" antes de desistir e reportar erro ao usuário.
    DB_COMMIT_MAX_TENTATIVAS: int = int(os.environ.get("DB_COMMIT_MAX_TENTATIVAS", 3))
    # Tempo (ms) que o SQLite espera por um lock antes de levantar
    # OperationalError — evita que acessos simultâneos "cheguem atrasados
    # por um milissegundo" e falhem sem necessidade.
    SQLITE_BUSY_TIMEOUT_MS: int = int(os.environ.get("SQLITE_BUSY_TIMEOUT_MS", 8000))


class DevelopmentConfig(Config):
    DEBUG: bool = True
    # SQLite: sem pool (StaticPool gerenciado pelo SQLAlchemy)
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "connect_args": {"check_same_thread": False},
    }


class ProductionConfig(Config):
    DEBUG: bool = False
    # Para MariaDB/MySQL em produção: reconexão automática após idle
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
    }

    # Em produção assumimos HTTPS — cookies só trafegam em conexão segura.
    # Se o app estiver atrás de um proxy/load balancer que já termina TLS
    # (nginx, Cloudflare, etc.), configure ProxyFix no __init__.py para o
    # Flask enxergar o esquema corretamente.
    SESSION_COOKIE_SECURE: bool = True
    REMEMBER_COOKIE_SECURE: bool = True

    @classmethod
    def validate(cls) -> None:
        """Garante que variáveis críticas estejam definidas em produção."""
        missing = []
        # Em produção, a SECRET_KEY autogerada em disco NÃO é aceitável:
        # cada novo deploy/container geraria uma chave diferente, derrubando
        # a sessão de todo mundo a cada restart/deploy, e times com múltiplas
        # réplicas atrás de um load balancer teriam uma chave por réplica
        # (uma sessão criada numa réplica seria rejeitada por outra).
        if not _secret_key_veio_do_ambiente:
            missing.append("SECRET_KEY")
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            missing.append("DATABASE_URL")
        if missing:
            raise RuntimeError(
                f"Variáveis de ambiente obrigatórias não configuradas: {missing}"
            )
        # SQLite é só para desenvolvimento (arquivo único, sem suporte real a
        # escrita concorrente) — não é adequado para produção com múltiplos
        # usuários/workers Gunicorn gravando ao mesmo tempo. deploy/install.sh
        # já configura MariaDB automaticamente; se DATABASE_URL aponta para
        # SQLite mesmo assim, é sinal de configuração manual equivocada.
        if database_url.startswith("sqlite:"):
            raise RuntimeError(
                "DATABASE_URL aponta para SQLite, mas produção não suporta SQLite "
                "— use MariaDB/MySQL (ex: mysql+pymysql://usuario:senha@host/banco). "
                "Rode 'sudo bash deploy/install.sh' para configurar isso automaticamente."
            )


class TestingConfig(Config):
    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "connect_args": {"check_same_thread": False},
    }
    WTF_CSRF_ENABLED: bool = False


# Mapa de nomes → classes (usado em create_app e FLASK_ENV)
config: dict = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
