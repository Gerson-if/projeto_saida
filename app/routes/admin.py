"""
routes/admin.py — Rotas do painel administrativo.
"""

from datetime import date, datetime, timedelta
from functools import wraps

from flask import (
    Blueprint, current_app, flash, redirect,
    render_template, request, url_for,
)
from flask_login import current_user, login_required

from app import db
from app.models import ConfigSistema, Registro, StatusSaida, Subunidade, TipoUsuario, Usuario
from app.uploads import validar_e_salvar_imagem, remover_upload_seguro
from app.validators import (
    validar_nome,
    validar_cpf_ou_identificacao,
    validar_texto_livre,
    validar_cor_hex,
    validar_data,
    parse_int_seguro,
    sanitizar_texto,
)

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    """Decorador: exige que o usuário logado seja administrador."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Acesso restrito ao administrador.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def _save_upload(field_name: str, prefix: str) -> tuple[str | None, str | None]:
    """
    Valida e salva um upload de imagem.
    Retorna (nome_arquivo, erro). Se nenhum arquivo foi enviado, retorna
    (None, None) — a rota deve então manter o valor anterior, se houver.
    """
    file = request.files.get(field_name)
    resultado = validar_e_salvar_imagem(
        file,
        destino_dir=current_app.config["UPLOAD_FOLDER"],
        prefixo=prefix,
    )
    if not resultado.ok:
        return None, resultado.erro
    return resultado.nome_arquivo, None


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

    em_transito = Registro.query.filter_by(status=StatusSaida.EM_TRANSITO).count()
    agendadas   = Registro.query.filter_by(status=StatusSaida.AGENDADA).count()

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

    dicas = [
        (ConfigSistema.get(f"dica_{i}", "") or "").strip()
        for i in range(1, 5)
    ]
    dicas = [d for d in dicas if d]
    if not dicas:
        dicas = [
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
    busca = sanitizar_texto(request.args.get("busca", ""), max_len=100)
    subunidade_id = request.args.get("subunidade", "")
    query = Usuario.query
    if busca:
        query = query.filter(
            (Usuario.nome.ilike(f"%{busca}%")) | (Usuario.cpf.ilike(f"%{busca}%"))
        )
    sub_id_valido = parse_int_seguro(subunidade_id, minimo=1)
    if sub_id_valido is not None:
        query = query.filter_by(subunidade_id=sub_id_valido)
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
        nome_raw = request.form.get("nome", "")
        cpf_raw  = request.form.get("cpf", "")
        senha    = (request.form.get("senha", "") or "")[:255]
        tipo     = sanitizar_texto(request.form.get("tipo", TipoUsuario.USUARIO), max_len=20)
        sub_id   = request.form.get("subunidade_id", "")

        nome, erros_nome = validar_nome(nome_raw, campo="nome")
        cpf, erros_cpf   = validar_cpf_ou_identificacao(cpf_raw)

        errors = [*erros_nome, *erros_cpf]
        if not senha.strip() or len(senha.strip()) < 4:
            errors.append("A senha deve ter no mínimo 4 caracteres.")
        if len(senha) > 72:
            errors.append("A senha deve ter no máximo 72 caracteres.")
        if tipo not in TipoUsuario.TODOS:
            errors.append("Tipo de usuário inválido.")
        if not errors and cpf and Usuario.query.filter_by(cpf=cpf).first():
            errors.append("Este CPF já está cadastrado.")

        subunidade_id_valida = _validar_subunidade(sub_id, errors)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("admin/form_usuario.html", acao="novo", subunidades=subunidades)

        usuario = Usuario(nome=nome, cpf=cpf, tipo=tipo)
        usuario.set_senha(senha.strip())
        usuario.subunidade_id = subunidade_id_valida

        try:
            db.session.add(usuario)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Não foi possível cadastrar o usuário. Verifique os dados e tente novamente.", "danger")
            return render_template("admin/form_usuario.html", acao="novo", subunidades=subunidades)

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
        nome_raw   = request.form.get("nome", "")
        cpf_raw    = request.form.get("cpf", "")
        tipo       = sanitizar_texto(request.form.get("tipo", TipoUsuario.USUARIO), max_len=20)
        nova_senha = (request.form.get("nova_senha", "") or "")[:255]
        ativo      = request.form.get("ativo") == "on"
        sub_id     = request.form.get("subunidade_id", "")

        nome, erros_nome = validar_nome(nome_raw, campo="nome")
        cpf, erros_cpf   = validar_cpf_ou_identificacao(cpf_raw)

        errors = [*erros_nome, *erros_cpf]
        if tipo not in TipoUsuario.TODOS:
            errors.append("Tipo de usuário inválido.")
        if cpf and Usuario.query.filter(Usuario.cpf == cpf, Usuario.id != id).first():
            errors.append("Este CPF já pertence a outro usuário.")
        if nova_senha.strip() and len(nova_senha.strip()) > 72:
            errors.append("A senha deve ter no máximo 72 caracteres.")

        subunidade_id_valida = _validar_subunidade(sub_id, errors)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "admin/form_usuario.html", usuario=usuario,
                acao="editar", subunidades=subunidades,
            )

        usuario.nome          = nome
        usuario.cpf           = cpf
        usuario.tipo          = tipo
        usuario.ativo         = ativo
        usuario.subunidade_id = subunidade_id_valida

        if nova_senha.strip():
            if len(nova_senha.strip()) >= 4:
                usuario.set_senha(nova_senha.strip())
            else:
                flash("Senha não alterada: deve ter no mínimo 4 caracteres.", "warning")

        if request.form.get("remover_foto") == "1":
            if usuario.foto:
                remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], usuario.foto)
            usuario.foto = None
        else:
            foto, erro_foto = _save_upload("foto", f"user_{id}")
            if erro_foto:
                flash(erro_foto, "danger")
                return render_template(
                    "admin/form_usuario.html", usuario=usuario,
                    acao="editar", subunidades=subunidades,
                )
            if foto:
                foto_antiga = usuario.foto
                usuario.foto = foto
                remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], foto_antiga)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Não foi possível salvar as alterações. Verifique os dados e tente novamente.", "danger")
            return render_template(
                "admin/form_usuario.html", usuario=usuario,
                acao="editar", subunidades=subunidades,
            )

        flash(f"Usuário {nome} atualizado com sucesso!", "success")
        return redirect(url_for("admin.listar_usuarios"))

    return render_template(
        "admin/form_usuario.html", usuario=usuario,
        acao="editar", subunidades=subunidades,
    )


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

    nome      = usuario.nome
    foto_antiga = usuario.foto
    try:
        db.session.delete(usuario)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Não foi possível excluir o usuário. Ele pode possuir registros vinculados.", "danger")
        return redirect(url_for("admin.listar_usuarios"))

    remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], foto_antiga)
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
        nome, erros_nome = validar_texto_livre(
            request.form.get("nome", ""), campo="nome da subunidade",
            max_len=100, min_len=2, obrigatorio=True,
        )
        sigla, erros_sigla = validar_texto_livre(
            request.form.get("sigla", ""), campo="sigla",
            max_len=20, obrigatorio=False,
        )

        errors = [*erros_nome, *erros_sigla]
        if not errors and Subunidade.query.filter_by(nome=nome).first():
            errors.append("Já existe uma subunidade com este nome.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("admin/form_subunidade.html", acao="nova")

        sub = Subunidade(nome=nome, sigla=sigla or None)
        try:
            db.session.add(sub)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Não foi possível criar a subunidade. Tente novamente.", "danger")
            return render_template("admin/form_subunidade.html", acao="nova")

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
        nome, erros_nome = validar_texto_livre(
            request.form.get("nome", ""), campo="nome da subunidade",
            max_len=100, min_len=2, obrigatorio=True,
        )
        sigla, erros_sigla = validar_texto_livre(
            request.form.get("sigla", ""), campo="sigla",
            max_len=20, obrigatorio=False,
        )
        ativa = request.form.get("ativa") == "on"

        errors = [*erros_nome, *erros_sigla]
        if not errors:
            duplicado = Subunidade.query.filter(
                Subunidade.nome == nome, Subunidade.id != id
            ).first()
            if duplicado:
                errors.append("Já existe uma subunidade com este nome.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("admin/form_subunidade.html", sub=sub, acao="editar")

        sub.nome  = nome
        sub.sigla = sigla or None
        sub.ativa = ativa
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Não foi possível salvar as alterações. Tente novamente.", "danger")
            return render_template("admin/form_subunidade.html", sub=sub, acao="editar")

        flash(f"Subunidade '{nome}' atualizada.", "success")
        return redirect(url_for("admin.listar_subunidades"))

    return render_template("admin/form_subunidade.html", sub=sub, acao="editar")


@admin_bp.route("/subunidades/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_subunidade(id):
    """
    Exclui uma subunidade.

    Estratégia de desassociação:
    - Se a subunidade tiver usuários vinculados, eles são desvinculados
      (subunidade_id -> NULL) ANTES da exclusão, para não violar a FK.
    - O comportamento é transparente para o admin: a operação sempre
      conclui com sucesso, e uma mensagem informa quantos usuários
      foram desvinculados.
    """
    sub = db.session.get(Subunidade, id)
    if not sub:
        flash("Subunidade não encontrada.", "danger")
        return redirect(url_for("admin.listar_subunidades"))

    nome = sub.nome
    usuarios_vinculados = Usuario.query.filter_by(subunidade_id=id).all()
    qtd_desvinculados = len(usuarios_vinculados)

    try:
        # Desvincula todos os usuários antes de excluir a subunidade
        for u in usuarios_vinculados:
            u.subunidade_id = None

        db.session.delete(sub)
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Não foi possível remover a subunidade. Tente novamente.", "danger")
        return redirect(url_for("admin.listar_subunidades"))

    if qtd_desvinculados:
        flash(
            f"Subunidade '{nome}' removida. "
            f"{qtd_desvinculados} usuário(s) foram desvinculados.",
            "warning",
        )
    else:
        flash(f"Subunidade '{nome}' removida com sucesso.", "success")

    return redirect(url_for("admin.listar_subunidades"))


# ─────────────────────────────────────────────────────────────────────────────
# Saídas
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/saidas")
@login_required
@admin_required
def listar_saidas():
    busca         = sanitizar_texto(request.args.get("busca", ""), max_len=100)
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

    sub_id_valida = parse_int_seguro(subunidade_id, minimo=1)
    if sub_id_valida is not None:
        query = query.filter(Usuario.subunidade_id == sub_id_valida)

    data_inicio_dt, _ = validar_data(data_inicio, campo="data de início")
    if data_inicio_dt:
        query = query.filter(Registro.data_saida >= data_inicio_dt)

    data_fim_dt, _ = validar_data(data_fim, campo="data de fim")
    if data_fim_dt:
        query = query.filter(Registro.data_saida <= data_fim_dt)

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
        campos_texto_max = {
            "nome_sistema": 100,
            "subtitulo":    150,
            "organizacao":  150,
            "rodape":       255,
            "dica_1":       200,
            "dica_2":       200,
            "dica_3":       200,
            "dica_4":       200,
        }
        erros_config = []
        for campo, max_len in campos_texto_max.items():
            valor, erros = validar_texto_livre(
                request.form.get(campo, ""), campo=campo,
                max_len=max_len, obrigatorio=False, permitir_emoji=True,
            )
            erros_config.extend(erros)
            ConfigSistema.set(campo, valor)

        for campo_cor in ["cor_primaria", "cor_secundaria"]:
            cor_atual = ConfigSistema.get(campo_cor, "#1a3a5c") or "#1a3a5c"
            cor, erros_cor = validar_cor_hex(
                request.form.get(campo_cor, ""), default=cor_atual
            )
            erros_config.extend(erros_cor)
            ConfigSistema.set(campo_cor, cor)

        if erros_config:
            for e in erros_config:
                flash(e, "warning")

        for campo_img in ["logo", "logo_relatorio", "brasao", "favicon"]:
            if request.form.get(f"remover_{campo_img}") == "1":
                valor_atual = ConfigSistema.get(campo_img)
                remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], valor_atual)
                ConfigSistema.set(campo_img, "")
                continue

            nome_arquivo, erro_upload = _save_upload(campo_img, campo_img)
            if erro_upload:
                flash(f"{campo_img}: {erro_upload}", "danger")
                continue
            if nome_arquivo:
                valor_antigo = ConfigSistema.get(campo_img)
                ConfigSistema.set(campo_img, nome_arquivo)
                remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], valor_antigo)

        flash("Configurações salvas com sucesso!", "success")
        return redirect(url_for("admin.configuracoes"))

    configs = {c.chave: c.valor for c in ConfigSistema.query.all()}
    return render_template("admin/configuracoes.html", configs=configs)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _validar_subunidade(sub_id: str, errors: list) -> int | None:
    """
    Valida o ID de subunidade vindo do formulário.
    Adiciona mensagem em `errors` se inválido.
    Retorna o ID válido ou None.
    """
    if not sub_id:
        return None
    subunidade_id_valida = parse_int_seguro(sub_id, minimo=1)
    if subunidade_id_valida is None:
        errors.append("Subunidade inválida.")
        return None
    if not db.session.get(Subunidade, subunidade_id_valida):
        errors.append("Subunidade não encontrada.")
        return None
    return subunidade_id_valida
