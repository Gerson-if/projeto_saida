"""
routes/admin.py — Rotas do painel administrativo.
"""

import os
from datetime import date, datetime, timedelta

from flask import (
    Blueprint, current_app, flash, redirect,
    render_template, request, url_for,
)
from flask_login import current_user, login_required
from functools import wraps
from werkzeug.utils import secure_filename

from app import db
from app.models import ConfigSistema, Registro, StatusSaida, Subunidade, TipoUsuario, Usuario

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Acesso restrito ao administrador.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def _allowed_file(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in current_app.config["ALLOWED_EXTENSIONS"]
    )


def _save_upload(field_name: str, prefix: str) -> str | None:
    file = request.files.get(field_name)
    if not file or not file.filename or not _allowed_file(file.filename):
        return None
    filename = secure_filename(f"{prefix}_{file.filename}")
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file.save(path)
    return filename


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    hoje = date.today()

    total_militares = Usuario.query.filter_by(tipo=TipoUsuario.USUARIO).count()
    total_admins    = Usuario.query.filter_by(tipo=TipoUsuario.ADMIN).count()
    total_saidas    = Registro.query.count()

    em_transito     = Registro.query.filter_by(status=StatusSaida.EM_TRANSITO).count()
    agendadas       = Registro.query.filter_by(status=StatusSaida.AGENDADA).count()

    retornados_hoje = Registro.query.filter(
        Registro.status.in_([StatusSaida.RETORNADO, StatusSaida.FINALIZADO]),
        db.func.date(Registro.status_atualizado_em) == hoje,
    ).count()

    saidas_hoje = Registro.query.filter(
        db.func.date(Registro.data_saida) == hoje
    ).count()

    militares_presentes = total_militares - Registro.query.filter(
        Registro.status == StatusSaida.EM_TRANSITO
    ).with_entities(Registro.cpf_usuario).distinct().count()

    proximas_saidas = (
        Registro.query
        .filter(
            Registro.status == StatusSaida.AGENDADA,
            Registro.data_saida >= datetime.now(),
            Registro.data_saida <= datetime.now() + timedelta(days=7),
        )
        .order_by(Registro.data_saida)
        .limit(5)
        .all()
    )

    # Apenas 4 últimas saídas no dashboard
    ultimas_saidas = (
        Registro.query
        .order_by(Registro.data_registro.desc())
        .limit(4)
        .all()
    )
    total_registros = Registro.query.count()

    usuarios = Usuario.query.order_by(Usuario.nome).all()

    grafico_status = {
        StatusSaida.AGENDADA:    agendadas,
        StatusSaida.EM_TRANSITO: em_transito,
        StatusSaida.RETORNADO:   Registro.query.filter_by(status=StatusSaida.RETORNADO).count(),
        StatusSaida.CANCELADO:   Registro.query.filter_by(status=StatusSaida.CANCELADO).count(),
        StatusSaida.FINALIZADO:  Registro.query.filter_by(status=StatusSaida.FINALIZADO).count(),
    }

    # Dicas de viagem configuráveis
    dicas_raw = ConfigSistema.get("dicas_viagem", "")
    dicas = [d.strip() for d in dicas_raw.split("\n") if d.strip()] if dicas_raw else [
        "Verifique documentos e comunicação antes de sair.",
        "Mantenha contato com a unidade durante a viagem.",
        "Respeite os horários de retorno estabelecidos.",
        "Em caso de imprevisto, comunique imediatamente a unidade.",
    ]

    return render_template(
        "admin/dashboard.html",
        total_militares=total_militares,
        total_admins=total_admins,
        total_saidas=total_saidas,
        em_transito=em_transito,
        agendadas=agendadas,
        retornados_hoje=retornados_hoje,
        saidas_hoje=saidas_hoje,
        militares_presentes=militares_presentes,
        ultimas_saidas=ultimas_saidas,
        total_registros=total_registros,
        proximas_saidas=proximas_saidas,
        usuarios=usuarios,
        grafico_status=grafico_status,
        dicas=dicas,
        StatusSaida=StatusSaida,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Usuários
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/usuarios")
@login_required
@admin_required
def listar_usuarios():
    busca = request.args.get("busca", "").strip()
    subunidade_id = request.args.get("subunidade", "")
    query = Usuario.query
    if busca:
        query = query.filter(
            (Usuario.nome.ilike(f"%{busca}%")) | (Usuario.cpf.ilike(f"%{busca}%"))
        )
    if subunidade_id:
        try:
            query = query.filter_by(subunidade_id=int(subunidade_id))
        except (ValueError, TypeError):
            pass
    usuarios = query.order_by(Usuario.nome).all()
    subunidades = Subunidade.query.filter_by(ativa=True).order_by(Subunidade.nome).all()
    return render_template(
        "admin/usuarios.html",
        usuarios=usuarios,
        busca=busca,
        subunidades=subunidades,
        subunidade_id=subunidade_id,
    )


@admin_bp.route("/usuarios/novo", methods=["GET", "POST"])
@login_required
@admin_required
def novo_usuario():
    subunidades = Subunidade.query.filter_by(ativa=True).order_by(Subunidade.nome).all()
    if request.method == "POST":
        nome  = request.form.get("nome", "").strip()
        cpf   = request.form.get("cpf", "").strip()
        senha = request.form.get("senha", "").strip()
        tipo  = request.form.get("tipo", TipoUsuario.USUARIO)
        sub_id = request.form.get("subunidade_id", "")

        errors = []
        if not nome:
            errors.append("O nome é obrigatório.")
        if not cpf:
            errors.append("O CPF é obrigatório.")
        if not senha or len(senha) < 4:
            errors.append("A senha deve ter no mínimo 4 caracteres.")
        if tipo not in TipoUsuario.TODOS:
            errors.append("Tipo de usuário inválido.")
        if not errors and Usuario.query.filter_by(cpf=cpf).first():
            errors.append("Este CPF já está cadastrado.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("admin/form_usuario.html", acao="novo", subunidades=subunidades)

        usuario = Usuario(nome=nome, cpf=cpf, tipo=tipo)
        usuario.set_senha(senha)
        if sub_id:
            try:
                usuario.subunidade_id = int(sub_id)
            except (ValueError, TypeError):
                pass
        db.session.add(usuario)
        db.session.commit()
        flash(f"Usuário {nome} cadastrado com sucesso!", "success")
        return redirect(url_for("admin.listar_usuarios"))

    return render_template("admin/form_usuario.html", acao="novo", subunidades=subunidades)


@admin_bp.route("/usuarios/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_usuario(id):
    usuario = db.session.get(Usuario, id)
    if not usuario:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for("admin.listar_usuarios"))

    subunidades = Subunidade.query.filter_by(ativa=True).order_by(Subunidade.nome).all()

    if request.method == "POST":
        nome       = request.form.get("nome", "").strip()
        cpf        = request.form.get("cpf", "").strip()
        tipo       = request.form.get("tipo", TipoUsuario.USUARIO)
        nova_senha = request.form.get("nova_senha", "").strip()
        ativo      = request.form.get("ativo") == "on"
        sub_id     = request.form.get("subunidade_id", "")

        errors = []
        if not nome:
            errors.append("O nome é obrigatório.")
        if not cpf:
            errors.append("O CPF é obrigatório.")
        if tipo not in TipoUsuario.TODOS:
            errors.append("Tipo de usuário inválido.")
        if Usuario.query.filter(Usuario.cpf == cpf, Usuario.id != id).first():
            errors.append("Este CPF já pertence a outro usuário.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("admin/form_usuario.html", usuario=usuario, acao="editar", subunidades=subunidades)

        usuario.nome  = nome
        usuario.cpf   = cpf
        usuario.tipo  = tipo
        usuario.ativo = ativo
        usuario.subunidade_id = int(sub_id) if sub_id else None

        if nova_senha:
            if len(nova_senha) >= 4:
                usuario.set_senha(nova_senha)
            else:
                flash("Senha não alterada: deve ter no mínimo 4 caracteres.", "warning")

        if request.form.get("remover_foto") == "1":
            if usuario.foto:
                try:
                    caminho = os.path.join(current_app.config["UPLOAD_FOLDER"], usuario.foto)
                    if os.path.exists(caminho):
                        os.remove(caminho)
                except Exception:
                    pass
            usuario.foto = None
        else:
            foto = _save_upload("foto", f"user_{id}")
            if foto:
                usuario.foto = foto

        db.session.commit()
        flash(f"Usuário {nome} atualizado com sucesso!", "success")
        return redirect(url_for("admin.listar_usuarios"))

    return render_template("admin/form_usuario.html", usuario=usuario, acao="editar", subunidades=subunidades)


@admin_bp.route("/usuarios/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_usuario(id):
    usuario = db.session.get(Usuario, id)
    if not usuario:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for("admin.listar_usuarios"))
    if usuario.id == current_user.id:
        flash("Você não pode excluir sua própria conta.", "danger")
        return redirect(url_for("admin.listar_usuarios"))

    nome = usuario.nome
    db.session.delete(usuario)
    db.session.commit()
    flash(f"Usuário {nome} excluído com sucesso.", "success")
    return redirect(url_for("admin.listar_usuarios"))


# ─────────────────────────────────────────────────────────────────────────────
# Subunidades
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/subunidades")
@login_required
@admin_required
def listar_subunidades():
    subunidades = Subunidade.query.order_by(Subunidade.nome).all()
    return render_template("admin/subunidades.html", subunidades=subunidades)


@admin_bp.route("/subunidades/nova", methods=["GET", "POST"])
@login_required
@admin_required
def nova_subunidade():
    if request.method == "POST":
        nome  = request.form.get("nome", "").strip()
        sigla = request.form.get("sigla", "").strip()
        if not nome:
            flash("O nome da subunidade é obrigatório.", "danger")
            return render_template("admin/form_subunidade.html", acao="nova")
        if Subunidade.query.filter_by(nome=nome).first():
            flash("Já existe uma subunidade com este nome.", "danger")
            return render_template("admin/form_subunidade.html", acao="nova")
        sub = Subunidade(nome=nome, sigla=sigla or None)
        db.session.add(sub)
        db.session.commit()
        flash(f"Subunidade '{nome}' criada com sucesso!", "success")
        return redirect(url_for("admin.listar_subunidades"))
    return render_template("admin/form_subunidade.html", acao="nova")


@admin_bp.route("/subunidades/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_subunidade(id):
    sub = db.session.get(Subunidade, id)
    if not sub:
        flash("Subunidade não encontrada.", "danger")
        return redirect(url_for("admin.listar_subunidades"))

    if request.method == "POST":
        nome  = request.form.get("nome", "").strip()
        sigla = request.form.get("sigla", "").strip()
        ativa = request.form.get("ativa") == "on"
        if not nome:
            flash("O nome é obrigatório.", "danger")
            return render_template("admin/form_subunidade.html", sub=sub, acao="editar")
        duplicado = Subunidade.query.filter(Subunidade.nome == nome, Subunidade.id != id).first()
        if duplicado:
            flash("Já existe uma subunidade com este nome.", "danger")
            return render_template("admin/form_subunidade.html", sub=sub, acao="editar")
        sub.nome  = nome
        sub.sigla = sigla or None
        sub.ativa = ativa
        db.session.commit()
        flash(f"Subunidade '{nome}' atualizada.", "success")
        return redirect(url_for("admin.listar_subunidades"))

    return render_template("admin/form_subunidade.html", sub=sub, acao="editar")


@admin_bp.route("/subunidades/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_subunidade(id):
    sub = db.session.get(Subunidade, id)
    if not sub:
        flash("Subunidade não encontrada.", "danger")
        return redirect(url_for("admin.listar_subunidades"))
    nome = sub.nome
    db.session.delete(sub)
    db.session.commit()
    flash(f"Subunidade '{nome}' removida.", "success")
    return redirect(url_for("admin.listar_subunidades"))


# ─────────────────────────────────────────────────────────────────────────────
# Saídas
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/saidas")
@login_required
@admin_required
def listar_saidas():
    busca         = request.args.get("busca", "").strip()
    status_filtro = request.args.get("status", "")
    data_inicio   = request.args.get("data_inicio", "")
    data_fim      = request.args.get("data_fim", "")
    subunidade_id = request.args.get("subunidade", "")

    query = Registro.query.join(Usuario, Registro.cpf_usuario == Usuario.cpf)

    if busca:
        query = query.filter(
            (Usuario.nome.ilike(f"%{busca}%"))
            | (Registro.local.ilike(f"%{busca}%"))
            | (Registro.motivo.ilike(f"%{busca}%"))
        )
    if status_filtro and status_filtro in StatusSaida.TODOS:
        query = query.filter(Registro.status == status_filtro)
    if subunidade_id:
        try:
            query = query.filter(Usuario.subunidade_id == int(subunidade_id))
        except (ValueError, TypeError):
            pass
    if data_inicio:
        try:
            query = query.filter(
                Registro.data_saida >= datetime.strptime(data_inicio, "%Y-%m-%d")
            )
        except ValueError:
            pass
    if data_fim:
        try:
            query = query.filter(
                Registro.data_saida <= datetime.strptime(data_fim, "%Y-%m-%d")
            )
        except ValueError:
            pass

    saidas = query.order_by(Registro.data_registro.desc()).all()
    subunidades = Subunidade.query.filter_by(ativa=True).order_by(Subunidade.nome).all()
    return render_template(
        "admin/saidas.html",
        saidas=saidas,
        busca=busca,
        status_filtro=status_filtro,
        data_inicio=data_inicio,
        data_fim=data_fim,
        subunidades=subunidades,
        subunidade_id=subunidade_id,
        StatusSaida=StatusSaida,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Configurações
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/configuracoes", methods=["GET", "POST"])
@login_required
@admin_required
def configuracoes():
    if request.method == "POST":
        campos_texto = [
            "nome_sistema", "subtitulo", "organizacao",
            "rodape", "cor_primaria", "cor_secundaria",
            "dica_1", "dica_2", "dica_3", "dica_4",
        ]
        for campo in campos_texto:
            valor = request.form.get(campo, "").strip()
            ConfigSistema.set(campo, valor)

        for campo_img in ["logo", "logo_relatorio", "brasao", "favicon"]:
            # Verificar remoção
            if request.form.get(f"remover_{campo_img}") == "1":
                valor_atual = ConfigSistema.get(campo_img)
                if valor_atual:
                    try:
                        caminho = os.path.join(current_app.config["UPLOAD_FOLDER"], valor_atual)
                        if os.path.exists(caminho):
                            os.remove(caminho)
                    except Exception:
                        pass
                ConfigSistema.set(campo_img, "")
                continue

            # Upload de nova imagem
            nome_arquivo = _save_upload(campo_img, campo_img)
            if nome_arquivo:
                ConfigSistema.set(campo_img, nome_arquivo)

        flash("Configurações salvas com sucesso!", "success")
        return redirect(url_for("admin.configuracoes"))

    configs = {c.chave: c.valor for c in ConfigSistema.query.all()}
    return render_template("admin/configuracoes.html", configs=configs)
