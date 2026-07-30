"""
models/__init__.py — Modelos SQLAlchemy do sistema.
"""

from __future__ import annotations

from datetime import date, datetime

from flask_login import UserMixin

from app import bcrypt, db, login_manager


@login_manager.user_loader
def load_user(user_id: str) -> "Usuario | None":
    try:
        return db.session.get(Usuario, int(user_id))
    except (ValueError, TypeError):
        return None


class TipoUsuario:
    ADMIN   = "admin"
    USUARIO = "usuario"
    TODOS   = [ADMIN, USUARIO]


class StatusSaida:
    AGENDADA    = "agendada"
    EM_TRANSITO = "em_transito"
    RETORNADO   = "retornado"
    CANCELADO   = "cancelado"
    FINALIZADO  = "finalizado"

    TODOS = [AGENDADA, EM_TRANSITO, RETORNADO, CANCELADO, FINALIZADO]

    LABELS = {
        AGENDADA:    "Agendada",
        EM_TRANSITO: "Em Trânsito",
        RETORNADO:   "Retornado",
        CANCELADO:   "Cancelado",
        FINALIZADO:  "Finalizado",
    }

    BADGES = {
        AGENDADA:    "warning",
        EM_TRANSITO: "primary",
        RETORNADO:   "success",
        CANCELADO:   "secondary",
        FINALIZADO:  "dark",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Modelo: Subunidade
# ─────────────────────────────────────────────────────────────────────────────

class Subunidade(db.Model):
    """Subunidades organizacionais (ex: 1º BO, 2ª BIA, BC)."""

    __tablename__ = "subunidades"

    id           = db.Column(db.Integer, primary_key=True)
    nome         = db.Column(db.String(100), unique=True, nullable=False)
    sigla        = db.Column(db.String(20), nullable=True)
    ativa        = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    usuarios = db.relationship("Usuario", backref="subunidade", lazy="select")

    @property
    def total_usuarios(self) -> int:
        return len(self.usuarios)

    def __repr__(self) -> str:
        return f"<Subunidade {self.nome}>"


# ─────────────────────────────────────────────────────────────────────────────
# Modelo: MotivoCancelamento
# ─────────────────────────────────────────────────────────────────────────────

class MotivoCancelamento(db.Model):
    """Motivos de cancelamento configuráveis pelo super-usuário/admin."""

    __tablename__ = "motivos_cancelamento"

    id     = db.Column(db.Integer, primary_key=True)
    texto  = db.Column(db.String(150), nullable=False)
    ativo  = db.Column(db.Boolean, default=True, nullable=False)
    ordem  = db.Column(db.Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<MotivoCancelamento {self.texto!r}>"

    @staticmethod
    def listar_ativos():
        return MotivoCancelamento.query.filter_by(ativo=True).order_by(
            MotivoCancelamento.ordem, MotivoCancelamento.id
        ).all()


# ─────────────────────────────────────────────────────────────────────────────
# Modelo: Usuario
# ─────────────────────────────────────────────────────────────────────────────

class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id            = db.Column(db.Integer, primary_key=True)
    cpf           = db.Column(db.String(14), unique=True, nullable=False, index=True)
    nome          = db.Column(db.String(100), nullable=False)
    senha_hash    = db.Column(db.String(255), nullable=False)
    tipo          = db.Column(
        db.Enum(*TipoUsuario.TODOS, name="tipo_usuario"),
        nullable=False,
        default=TipoUsuario.USUARIO,
    )
    ativo         = db.Column(db.Boolean, default=True, nullable=False)
    data_criacao  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    foto          = db.Column(db.String(255), nullable=True)
    subunidade_id = db.Column(
        db.Integer,
        db.ForeignKey("subunidades.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Dados não-críticos editáveis pelo próprio usuário
    telefone      = db.Column(db.String(20), nullable=True)
    email         = db.Column(db.String(120), nullable=True)

    registros = db.relationship(
        "Registro",
        backref="usuario",
        lazy="dynamic",
        foreign_keys="Registro.cpf_usuario",
        primaryjoin="Usuario.cpf == Registro.cpf_usuario",
        cascade="all, delete-orphan",
    )

    def set_senha(self, senha: str) -> None:
        self.senha_hash = bcrypt.generate_password_hash(senha).decode("utf-8")

    def check_senha(self, senha: str) -> bool:
        return bcrypt.check_password_hash(self.senha_hash, senha)

    @property
    def is_admin(self) -> bool:
        return self.tipo == TipoUsuario.ADMIN

    @property
    def saidas_ativas(self) -> int:
        return self.registros.filter_by(status=StatusSaida.EM_TRANSITO).count()

    def __repr__(self) -> str:
        return f"<Usuario {self.nome} ({self.cpf})>"


# ─────────────────────────────────────────────────────────────────────────────
# Modelo: Registro (saída)
# ─────────────────────────────────────────────────────────────────────────────

class Registro(db.Model):
    __tablename__ = "registros"

    id                   = db.Column(db.Integer, primary_key=True)
    cpf_usuario          = db.Column(
        db.String(14),
        db.ForeignKey("usuarios.cpf", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    local                = db.Column(db.String(255), nullable=False)
    motivo               = db.Column(db.String(300), nullable=False)
    data_saida           = db.Column(db.DateTime, nullable=False, index=True)
    data_retorno         = db.Column(db.DateTime, nullable=True, index=True)
    telefone_contato     = db.Column(db.String(20), nullable=True)
    endereco_destino     = db.Column(db.Text, nullable=True)
    data_registro        = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status               = db.Column(
        db.Enum(*StatusSaida.TODOS, name="status_saida"),
        default=StatusSaida.AGENDADA,
        nullable=False,
        index=True,
    )
    status_atualizado_em = db.Column(db.DateTime, nullable=True)

    # Campos de cancelamento — motivo agora é selecionado de uma lista
    motivo_cancelamento  = db.Column(db.String(150), nullable=True)   # texto do motivo selecionado
    obs_cancelamento     = db.Column(db.String(200), nullable=True)   # observação opcional curta
    data_cancelamento    = db.Column(db.DateTime, nullable=True)

    @property
    def status_badge(self) -> str:
        return StatusSaida.BADGES.get(self.status, "info")

    @property
    def status_label(self) -> str:
        return StatusSaida.LABELS.get(self.status, self.status)

    @property
    def editavel(self) -> bool:
        if self.status in (StatusSaida.CANCELADO, StatusSaida.FINALIZADO):
            return False
        if self.data_retorno and self.data_retorno.date() < date.today():
            return False
        return True

    def atualizar_status_automatico(self) -> bool:
        if self.status in (StatusSaida.CANCELADO, StatusSaida.FINALIZADO):
            return False

        hoje = date.today()
        novo_status = self.status

        if self.status == StatusSaida.AGENDADA:
            if self.data_saida.date() <= hoje:
                novo_status = StatusSaida.EM_TRANSITO

        if self.status in (StatusSaida.AGENDADA, StatusSaida.EM_TRANSITO):
            if self.data_retorno and self.data_retorno.date() < hoje:
                novo_status = StatusSaida.FINALIZADO

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
    __tablename__ = "config_sistema"

    id        = db.Column(db.Integer, primary_key=True)
    chave     = db.Column(db.String(100), unique=True, nullable=False)
    valor     = db.Column(db.Text, nullable=True)
    descricao = db.Column(db.String(255), nullable=True)
    tipo      = db.Column(db.String(20), default="texto")

    @staticmethod
    def get(chave: str, default: str | None = None) -> str | None:
        try:
            config = ConfigSistema.query.filter_by(chave=chave).first()
            return config.valor if config else default
        except Exception:
            return default

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
