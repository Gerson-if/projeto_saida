"""
models/__init__.py — Modelos SQLAlchemy do sistema.

Modelos:
  Usuario        →  militares e administradores
  Registro       →  controle de saídas (com status automático)
  ConfigSistema  →  configurações dinâmicas via painel admin
"""

from __future__ import annotations

from datetime import date, datetime

from flask_login import UserMixin

from app import bcrypt, db, login_manager


# ─────────────────────────────────────────────────────────────────────────────
# Loader do Flask-Login
# ─────────────────────────────────────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id: str) -> "Usuario | None":
    return db.session.get(Usuario, int(user_id))


# ─────────────────────────────────────────────────────────────────────────────
# Enums como constantes (evita depender de Enum do Python + SQL)
# ─────────────────────────────────────────────────────────────────────────────

class TipoUsuario:
    ADMIN = "admin"
    USUARIO = "usuario"
    TODOS = [ADMIN, USUARIO]


class StatusSaida:
    AGENDADA = "agendada"       # Saída registrada, ainda não começou
    EM_TRANSITO = "em_transito" # Saída em andamento (data_saida <= hoje)
    RETORNADO = "retornado"     # Data de retorno expirou (automático)
    CANCELADO = "cancelado"     # Cancelado pelo usuário

    TODOS = [AGENDADA, EM_TRANSITO, RETORNADO, CANCELADO]

    # Exibição amigável
    LABELS = {
        AGENDADA:    "Agendada",
        EM_TRANSITO: "Em Trânsito",
        RETORNADO:   "Retornado",
        CANCELADO:   "Cancelado",
    }

    # Classes Bootstrap para os badges
    BADGES = {
        AGENDADA:    "warning",
        EM_TRANSITO: "primary",
        RETORNADO:   "success",
        CANCELADO:   "secondary",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Modelo: Usuario
# ─────────────────────────────────────────────────────────────────────────────

class Usuario(UserMixin, db.Model):
    """Representa um militar ou administrador do sistema."""

    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    cpf = db.Column(db.String(14), unique=True, nullable=False, index=True)
    nome = db.Column(db.String(100), nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    tipo = db.Column(
        db.Enum(*TipoUsuario.TODOS, name="tipo_usuario"),
        nullable=False,
        default=TipoUsuario.USUARIO,
    )
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    foto = db.Column(db.String(255), nullable=True)

    # Relacionamento com registros de saída
    registros = db.relationship(
        "Registro",
        backref="usuario",
        lazy="dynamic",
        foreign_keys="Registro.cpf_usuario",
        primaryjoin="Usuario.cpf == Registro.cpf_usuario",
        cascade="all, delete-orphan",
    )

    # ── Senha ──────────────────────────────────────────────────────────────

    def set_senha(self, senha: str) -> None:
        self.senha_hash = bcrypt.generate_password_hash(senha).decode("utf-8")

    def check_senha(self, senha: str) -> bool:
        return bcrypt.check_password_hash(self.senha_hash, senha)

    # ── Propriedades ───────────────────────────────────────────────────────

    @property
    def is_admin(self) -> bool:
        return self.tipo == TipoUsuario.ADMIN

    @property
    def saidas_ativas(self) -> int:
        """Quantidade de saídas atualmente em trânsito."""
        return self.registros.filter_by(status=StatusSaida.EM_TRANSITO).count()

    def __repr__(self) -> str:
        return f"<Usuario {self.nome} ({self.cpf})>"


# ─────────────────────────────────────────────────────────────────────────────
# Modelo: Registro (saída)
# ─────────────────────────────────────────────────────────────────────────────

class Registro(db.Model):
    """Registra uma saída de militar com controle automático de status."""

    __tablename__ = "registros"

    id = db.Column(db.Integer, primary_key=True)
    cpf_usuario = db.Column(
        db.String(14),
        db.ForeignKey("usuarios.cpf", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    local = db.Column(db.String(255), nullable=False)
    motivo = db.Column(db.String(300), nullable=False)   # limitado a 300 chars
    data_saida = db.Column(db.DateTime, nullable=False, index=True)
    data_retorno = db.Column(db.DateTime, nullable=True, index=True)
    telefone_contato = db.Column(db.String(20), nullable=True)
    endereco_destino = db.Column(db.Text, nullable=True)
    data_registro = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(
        db.Enum(*StatusSaida.TODOS, name="status_saida"),
        default=StatusSaida.AGENDADA,
        nullable=False,
        index=True,
    )
    # Audit: quando o status foi alterado pela última vez (manual ou automático)
    status_atualizado_em = db.Column(db.DateTime, nullable=True)

    # ── Propriedades de exibição ───────────────────────────────────────────

    @property
    def status_badge(self) -> str:
        return StatusSaida.BADGES.get(self.status, "info")

    @property
    def status_label(self) -> str:
        return StatusSaida.LABELS.get(self.status, self.status)

    # ── Lógica de status automático ────────────────────────────────────────

    def atualizar_status_automatico(self) -> bool:
        """
        Avalia as datas e ajusta o status sem intervenção humana.

        Regras:
          agendada     → em_transito  quando data_saida <= hoje
          em_transito  → retornado    quando data_retorno < hoje
          retornado / cancelado → imutável por esta função

        Retorna True se o status foi alterado.
        """
        if self.status in (StatusSaida.RETORNADO, StatusSaida.CANCELADO):
            return False

        hoje = date.today()
        novo_status = self.status

        if self.status == StatusSaida.AGENDADA:
            if self.data_saida.date() <= hoje:
                novo_status = StatusSaida.EM_TRANSITO

        if self.status == StatusSaida.EM_TRANSITO:
            if self.data_retorno and self.data_retorno.date() < hoje:
                novo_status = StatusSaida.RETORNADO

        if novo_status != self.status:
            self.status = novo_status
            self.status_atualizado_em = datetime.utcnow()
            return True

        return False

    def __repr__(self) -> str:
        return f"<Registro #{self.id} {self.local} [{self.status}]>"


# ─────────────────────────────────────────────────────────────────────────────
# Modelo: ConfigSistema
# ─────────────────────────────────────────────────────────────────────────────

class ConfigSistema(db.Model):
    """
    Armazena configurações dinâmicas editáveis pelo super admin.

    Tipos suportados: 'texto', 'imagem', 'booleano'.
    Acesso via ConfigSistema.get(chave) / ConfigSistema.set(chave, valor).
    """

    __tablename__ = "config_sistema"

    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(100), unique=True, nullable=False)
    valor = db.Column(db.Text, nullable=True)
    descricao = db.Column(db.String(255), nullable=True)
    tipo = db.Column(db.String(20), default="texto")

    @staticmethod
    def get(chave: str, default: str | None = None) -> str | None:
        config = ConfigSistema.query.filter_by(chave=chave).first()
        return config.valor if config else default

    @staticmethod
    def set(chave: str, valor: str) -> None:
        config = ConfigSistema.query.filter_by(chave=chave).first()
        if config:
            config.valor = valor
        else:
            db.session.add(ConfigSistema(chave=chave, valor=valor))
        db.session.commit()

    def __repr__(self) -> str:
        return f"<Config {self.chave}={self.valor!r}>"
