"""
routes/admin.py — Rotas do painel administrativo.
"""

from datetime import date, datetime, timedelta
from functools import wraps

from flask import (
    Blueprint, current_app, flash, jsonify, redirect,
    render_template, request, url_for,
)
from flask_login import current_user, login_required

from app import db
from app.db_utils import commit_seguro
from app.models import (
    ConfigSistema, PostoGraduacao, Registro, SolicitacaoPostoGraduacao,
    StatusSaida, Subunidade, TipoUsuario, Usuario,
)
from app.uploads import (
    validar_e_salvar_imagem,
    validar_e_salvar_video,
    remover_upload_seguro,
)
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


def _save_video_upload(field_name: str, prefix: str) -> tuple[str | None, str | None]:
    """Mesmo contrato de `_save_upload`, mas para o vídeo curto opcional
    usado como plano de fundo da tela de login."""
    file = request.files.get(field_name)
    resultado = validar_e_salvar_video(
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
    posto_graduacao_id = request.args.get("posto_graduacao", "")

    postos_habilitados = ConfigSistema.get("postos_habilitados") == "1"

    query = Usuario.query
    if busca:
        query = query.filter(
            (Usuario.nome.ilike(f"%{busca}%")) | (Usuario.cpf.ilike(f"%{busca}%"))
        )
    sub_id_valido = parse_int_seguro(subunidade_id, minimo=1)
    if sub_id_valido is not None:
        query = query.filter_by(subunidade_id=sub_id_valido)

    # Filtro por nível de hierarquia (posto/graduação) — só faz sentido
    # quando o recurso está habilitado nas configurações do sistema.
    posto_id_valido = parse_int_seguro(posto_graduacao_id, minimo=1)
    if postos_habilitados and posto_id_valido is not None:
        query = query.filter_by(posto_graduacao_id=posto_id_valido)

    if postos_habilitados:
        # Ordena por nível de hierarquia (do mais alto para o mais baixo).
        # Usa outerjoin para não excluir usuários sem posto/graduação
        # vinculado — esses ficam agrupados ao final da listagem.
        query = query.outerjoin(
            PostoGraduacao, Usuario.posto_graduacao_id == PostoGraduacao.id
        )
        usuarios = query.order_by(
            PostoGraduacao.nivel.is_(None).asc(),
            PostoGraduacao.nivel.desc(),
            Usuario.nome,
        ).all()
    else:
        usuarios = query.order_by(Usuario.nome).all()

    subunidades = Subunidade.query.filter_by(ativa=True).order_by(Subunidade.nome).all()
    postos = PostoGraduacao.listar_ativos() if postos_habilitados else []

    return render_template(
        "admin/usuarios.html",
        usuarios=usuarios,
        busca=busca,
        subunidades=subunidades,
        subunidade_id=subunidade_id,
        postos=postos,
        posto_graduacao_id=posto_graduacao_id,
        postos_habilitados=postos_habilitados,
    )


@admin_bp.route("/usuarios/novo", methods=["GET", "POST"])
@login_required
@admin_required
def novo_usuario():
    subunidades = Subunidade.query.filter_by(ativa=True).order_by(Subunidade.nome).all()
    postos = PostoGraduacao.listar_ativos()
    if request.method == "POST":
        nome_raw = request.form.get("nome", "")
        cpf_raw  = request.form.get("cpf", "")
        senha    = (request.form.get("senha", "") or "")[:255]
        tipo     = sanitizar_texto(request.form.get("tipo", TipoUsuario.USUARIO), max_len=20)
        sub_id   = request.form.get("subunidade_id", "")
        posto_id = request.form.get("posto_graduacao_id", "")

        nome, erros_nome = validar_nome(nome_raw, campo="nome")
        cpf, erros_cpf   = validar_cpf_ou_identificacao(cpf_raw)

        errors = [*erros_nome, *erros_cpf]
        if not senha.strip() or len(senha.strip()) < 4:
            errors.append("A senha deve ter no mínimo 4 caracteres.")
        if len(senha.encode("utf-8")) > 72:
            # bcrypt limita a senha a 72 BYTES, não caracteres — com acentos
            # ou outros caracteres multibyte, len() em caracteres não é
            # suficiente para evitar o ValueError do bcrypt no set_senha().
            errors.append("A senha deve ter no máximo 72 caracteres.")
        if tipo not in TipoUsuario.TODOS:
            errors.append("Tipo de usuário inválido.")
        if not errors and cpf and Usuario.query.filter_by(cpf=cpf).first():
            errors.append("Este CPF já está cadastrado.")

        subunidade_id_valida = _validar_subunidade(sub_id, errors)
        posto_id_valido      = _validar_posto(posto_id, errors)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "admin/form_usuario.html", acao="novo",
                subunidades=subunidades, postos=postos,
            )

        # Foto (opcional na criação): valida e salva ANTES de criar o
        # registro do usuário — o próprio nome de arquivo não depende do ID
        # (é um UUID), então não há problema em salvar antes do INSERT. Se a
        # validação falhar (tamanho, tipo, dimensões), nada é criado.
        foto, erro_foto = _save_upload("foto", f"user_{cpf}")
        if erro_foto:
            flash(erro_foto, "danger")
            return render_template(
                "admin/form_usuario.html", acao="novo",
                subunidades=subunidades, postos=postos,
            )

        usuario = Usuario(nome=nome, cpf=cpf, tipo=tipo)
        usuario.set_senha(senha.strip())
        usuario.subunidade_id = subunidade_id_valida
        usuario.posto_graduacao_id = posto_id_valido
        if foto:
            usuario.foto = foto

        db.session.add(usuario)
        ok, erro = commit_seguro(
            db,
            mensagem_erro="Não foi possível cadastrar o usuário. Verifique os dados e tente novamente.",
            mensagem_duplicado="Este CPF já está cadastrado.",
        )
        if not ok:
            # Evita deixar um arquivo de foto órfão em disco se o usuário
            # acabou não sendo criado (ex.: CPF duplicado detectado só no
            # commit, por uma corrida entre duas requisições simultâneas).
            if foto:
                remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], foto)
            flash(erro, "danger")
            return render_template(
                "admin/form_usuario.html", acao="novo",
                subunidades=subunidades, postos=postos,
            )

        flash(f"Usuário {nome} cadastrado com sucesso!", "success")
        return redirect(url_for("admin.listar_usuarios"))

    return render_template(
        "admin/form_usuario.html", acao="novo",
        subunidades=subunidades, postos=postos,
    )


@admin_bp.route("/usuarios/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_usuario(id):
    usuario = db.session.get(Usuario, id)
    if not usuario:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for("admin.listar_usuarios"))

    subunidades = Subunidade.query.filter_by(ativa=True).order_by(Subunidade.nome).all()
    postos = PostoGraduacao.listar_ativos()

    if request.method == "POST":
        nome_raw   = request.form.get("nome", "")
        cpf_raw    = request.form.get("cpf", "")
        tipo       = sanitizar_texto(request.form.get("tipo", TipoUsuario.USUARIO), max_len=20)
        nova_senha = (request.form.get("nova_senha", "") or "")[:255]
        ativo      = request.form.get("ativo") == "on"
        sub_id     = request.form.get("subunidade_id", "")
        posto_id   = request.form.get("posto_graduacao_id", "")

        nome, erros_nome = validar_nome(nome_raw, campo="nome")
        cpf, erros_cpf   = validar_cpf_ou_identificacao(cpf_raw)

        errors = [*erros_nome, *erros_cpf]
        if tipo not in TipoUsuario.TODOS:
            errors.append("Tipo de usuário inválido.")
        if cpf and Usuario.query.filter(Usuario.cpf == cpf, Usuario.id != id).first():
            errors.append("Este CPF já pertence a outro usuário.")
        if nova_senha.strip() and len(nova_senha.strip().encode("utf-8")) > 72:
            errors.append("A senha deve ter no máximo 72 caracteres.")

        subunidade_id_valida = _validar_subunidade(sub_id, errors)
        posto_id_valido      = _validar_posto(posto_id, errors)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "admin/form_usuario.html", usuario=usuario,
                acao="editar", subunidades=subunidades, postos=postos,
            )

        cpf_anterior = usuario.cpf
        cpf_mudou = cpf != cpf_anterior

        if cpf_mudou:
            # O CPF é usado como chave estrangeira "natural" em registros.cpf_usuario
            # (ON DELETE CASCADE). Como não há ON UPDATE CASCADE configurado no
            # banco (SQLite não permite alterar essa cláusula sem recriar a
            # tabela), uma troca de CPF de um usuário que já possui saídas
            # registradas violaria a constraint de chave estrangeira e o
            # commit falharia com IntegrityError — por isso não era possível
            # editar o CPF de ninguém que já tivesse pelo menos um registro.
            #
            # A solução: dentro da MESMA transação, adiar a checagem de
            # chaves estrangeiras (SQLite) e atualizar em conjunto o usuário
            # e todos os registros que apontam para o CPF antigo, para que o
            # banco só valide a consistência no momento do commit, quando
            # tudo já está coerente.
            if db.engine.dialect.name == "sqlite":
                db.session.execute(db.text("PRAGMA defer_foreign_keys=ON"))
            Registro.query.filter_by(cpf_usuario=cpf_anterior).update(
                {Registro.cpf_usuario: cpf}, synchronize_session=False
            )

        usuario.nome               = nome
        usuario.cpf                = cpf
        usuario.tipo                = tipo
        usuario.ativo               = ativo
        usuario.subunidade_id       = subunidade_id_valida
        usuario.posto_graduacao_id  = posto_id_valido

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
                    acao="editar", subunidades=subunidades, postos=postos,
                )
            if foto:
                foto_antiga = usuario.foto
                usuario.foto = foto
                remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], foto_antiga)

        ok, erro = commit_seguro(
            db,
            mensagem_erro="Não foi possível salvar as alterações. Verifique os dados e tente novamente.",
            mensagem_duplicado="Este CPF já pertence a outro usuário.",
        )
        if not ok:
            flash(erro, "danger")
            return render_template(
                "admin/form_usuario.html", usuario=usuario,
                acao="editar", subunidades=subunidades, postos=postos,
            )

        flash(f"Usuário {nome} atualizado com sucesso!", "success")
        return redirect(url_for("admin.listar_usuarios"))

    return render_template(
        "admin/form_usuario.html", usuario=usuario,
        acao="editar", subunidades=subunidades, postos=postos,
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
    db.session.delete(usuario)
    ok, erro = commit_seguro(
        db,
        mensagem_erro="Não foi possível excluir o usuário. Ele pode possuir registros vinculados.",
    )
    if not ok:
        flash(erro, "danger")
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
        db.session.add(sub)
        ok, erro = commit_seguro(
            db,
            mensagem_erro="Não foi possível criar a subunidade. Tente novamente.",
            mensagem_duplicado="Já existe uma subunidade com este nome.",
        )
        if not ok:
            flash(erro, "danger")
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
        ok, erro = commit_seguro(
            db,
            mensagem_erro="Não foi possível salvar as alterações. Tente novamente.",
            mensagem_duplicado="Já existe uma subunidade com este nome.",
        )
        if not ok:
            flash(erro, "danger")
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
    except Exception:
        db.session.rollback()
        flash("Não foi possível remover a subunidade. Tente novamente.", "danger")
        return redirect(url_for("admin.listar_subunidades"))

    ok, erro = commit_seguro(
        db,
        mensagem_erro="Não foi possível remover a subunidade. Tente novamente.",
    )
    if not ok:
        flash(erro, "danger")
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
# Postos/Graduações (níveis de hierarquia)
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/postos")
@login_required
@admin_required
def listar_postos():
    postos = PostoGraduacao.query.order_by(
        PostoGraduacao.nivel.desc(), PostoGraduacao.nome
    ).all()
    return render_template("admin/postos.html", postos=postos)


@admin_bp.route("/postos/novo", methods=["GET", "POST"])
@login_required
@admin_required
def novo_posto():
    if request.method == "POST":
        nome, erros_nome = validar_texto_livre(
            request.form.get("nome", ""), campo="nome do posto/graduação",
            max_len=60, min_len=2, obrigatorio=True,
        )
        sigla, erros_sigla = validar_texto_livre(
            request.form.get("sigla", ""), campo="sigla",
            max_len=20, obrigatorio=False,
        )
        nivel = parse_int_seguro(request.form.get("nivel", "0"), minimo=0, maximo=999)

        errors = [*erros_nome, *erros_sigla]
        if nivel is None:
            errors.append("Nível hierárquico inválido. Use um número entre 0 e 999.")
        if not errors and PostoGraduacao.query.filter_by(nome=nome).first():
            errors.append("Já existe um posto/graduação com este nome.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("admin/form_posto.html", acao="novo")

        posto = PostoGraduacao(nome=nome, sigla=sigla or None, nivel=nivel or 0)
        db.session.add(posto)
        ok, erro = commit_seguro(
            db,
            mensagem_erro="Não foi possível criar o posto/graduação. Tente novamente.",
            mensagem_duplicado="Já existe um posto/graduação com este nome.",
        )
        if not ok:
            flash(erro, "danger")
            return render_template("admin/form_posto.html", acao="novo")

        flash(f"Posto/Graduação '{nome}' criado(a) com sucesso!", "success")
        return redirect(url_for("admin.listar_postos"))
    return render_template("admin/form_posto.html", acao="novo")


@admin_bp.route("/postos/editar/<int:id>", methods=["GET", "POST"])
@login_required
@admin_required
def editar_posto(id):
    posto = db.session.get(PostoGraduacao, id)
    if not posto:
        flash("Posto/Graduação não encontrado(a).", "danger")
        return redirect(url_for("admin.listar_postos"))

    if request.method == "POST":
        nome, erros_nome = validar_texto_livre(
            request.form.get("nome", ""), campo="nome do posto/graduação",
            max_len=60, min_len=2, obrigatorio=True,
        )
        sigla, erros_sigla = validar_texto_livre(
            request.form.get("sigla", ""), campo="sigla",
            max_len=20, obrigatorio=False,
        )
        nivel = parse_int_seguro(request.form.get("nivel", "0"), minimo=0, maximo=999)
        ativo = request.form.get("ativo") == "on"

        errors = [*erros_nome, *erros_sigla]
        if nivel is None:
            errors.append("Nível hierárquico inválido. Use um número entre 0 e 999.")
        if not errors:
            duplicado = PostoGraduacao.query.filter(
                PostoGraduacao.nome == nome, PostoGraduacao.id != id
            ).first()
            if duplicado:
                errors.append("Já existe um posto/graduação com este nome.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("admin/form_posto.html", posto=posto, acao="editar")

        posto.nome  = nome
        posto.sigla = sigla or None
        posto.nivel = nivel or 0
        posto.ativo = ativo
        ok, erro = commit_seguro(
            db,
            mensagem_erro="Não foi possível salvar as alterações. Tente novamente.",
            mensagem_duplicado="Já existe um posto/graduação com este nome.",
        )
        if not ok:
            flash(erro, "danger")
            return render_template("admin/form_posto.html", posto=posto, acao="editar")

        flash(f"Posto/Graduação '{nome}' atualizado(a).", "success")
        return redirect(url_for("admin.listar_postos"))

    return render_template("admin/form_posto.html", posto=posto, acao="editar")


@admin_bp.route("/postos/excluir/<int:id>", methods=["POST"])
@login_required
@admin_required
def excluir_posto(id):
    """
    Exclui um posto/graduação. Segue a mesma estratégia de desassociação
    usada em `excluir_subunidade`: usuários vinculados são desvinculados
    (posto_graduacao_id -> NULL) antes da exclusão, para não violar a FK
    e não quebrar cadastros já existentes.
    """
    posto = db.session.get(PostoGraduacao, id)
    if not posto:
        flash("Posto/Graduação não encontrado(a).", "danger")
        return redirect(url_for("admin.listar_postos"))

    nome = posto.nome
    usuarios_vinculados = Usuario.query.filter_by(posto_graduacao_id=id).all()
    qtd_desvinculados = len(usuarios_vinculados)

    try:
        for u in usuarios_vinculados:
            u.posto_graduacao_id = None
        db.session.delete(posto)
    except Exception:
        db.session.rollback()
        flash("Não foi possível remover o posto/graduação. Tente novamente.", "danger")
        return redirect(url_for("admin.listar_postos"))

    ok, erro = commit_seguro(
        db,
        mensagem_erro="Não foi possível remover o posto/graduação. Tente novamente.",
    )
    if not ok:
        flash(erro, "danger")
        return redirect(url_for("admin.listar_postos"))

    if qtd_desvinculados:
        flash(
            f"Posto/Graduação '{nome}' removido(a). "
            f"{qtd_desvinculados} usuário(s) foram desvinculados.",
            "warning",
        )
    else:
        flash(f"Posto/Graduação '{nome}' removido(a) com sucesso.", "success")

    return redirect(url_for("admin.listar_postos"))


# ─────────────────────────────────────────────────────────────────────────────
# Solicitações de alteração de Posto/Graduação
# ─────────────────────────────────────────────────────────────────────────────

@admin_bp.route("/solicitacoes")
@login_required
@admin_required
def listar_solicitacoes():
    status_filtro = request.args.get("status", SolicitacaoPostoGraduacao.STATUS_PENDENTE)
    query = SolicitacaoPostoGraduacao.query
    if status_filtro in SolicitacaoPostoGraduacao.STATUS_TODOS:
        query = query.filter_by(status=status_filtro)
    solicitacoes = query.order_by(SolicitacaoPostoGraduacao.data_solicitacao.desc()).all()
    return render_template(
        "admin/solicitacoes.html",
        solicitacoes=solicitacoes,
        status_filtro=status_filtro,
        SolicitacaoPostoGraduacao=SolicitacaoPostoGraduacao,
    )


@admin_bp.route("/solicitacoes/<int:id>/responder", methods=["POST"])
@login_required
@admin_required
def responder_solicitacao(id):
    """
    Aprova ou rejeita uma solicitação de alteração de posto/graduação feita
    por um militar. A alteração no cadastro do usuário só acontece de fato
    aqui, quando aprovada — antes disso o usuário continua com o
    posto/graduação anterior.
    """
    solicitacao = db.session.get(SolicitacaoPostoGraduacao, id)
    if not solicitacao:
        flash("Solicitação não encontrada.", "danger")
        return redirect(url_for("admin.listar_solicitacoes"))

    if solicitacao.status != SolicitacaoPostoGraduacao.STATUS_PENDENTE:
        flash("Esta solicitação já foi respondida anteriormente.", "warning")
        return redirect(url_for("admin.listar_solicitacoes"))

    decisao = request.form.get("decisao", "")
    if decisao not in ("aprovar", "rejeitar"):
        flash("Ação inválida.", "danger")
        return redirect(url_for("admin.listar_solicitacoes"))

    obs, erros_obs = validar_texto_livre(
        request.form.get("observacao", ""), campo="observação",
        max_len=255, obrigatorio=False,
    )
    if erros_obs:
        for e in erros_obs:
            flash(e, "danger")
        return redirect(url_for("admin.listar_solicitacoes"))

    solicitacao.status = (
        SolicitacaoPostoGraduacao.STATUS_APROVADA if decisao == "aprovar"
        else SolicitacaoPostoGraduacao.STATUS_REJEITADA
    )
    solicitacao.resposta_obs      = obs or None
    solicitacao.data_resposta     = datetime.utcnow()
    solicitacao.respondido_por_id = current_user.id

    if decisao == "aprovar":
        usuario_alvo = db.session.get(Usuario, solicitacao.usuario_id)
        if usuario_alvo:
            usuario_alvo.posto_graduacao_id = solicitacao.posto_solicitado_id

    ok, erro = commit_seguro(
        db,
        mensagem_erro="Não foi possível registrar a resposta. Tente novamente.",
    )
    if not ok:
        flash(erro, "danger")
        return redirect(url_for("admin.listar_solicitacoes"))

    nome_usuario = solicitacao.usuario.nome if solicitacao.usuario else "usuário"
    if decisao == "aprovar":
        flash(f"Solicitação de {nome_usuario} aprovada. Cadastro atualizado.", "success")
    else:
        flash(f"Solicitação de {nome_usuario} rejeitada.", "info")
    return redirect(url_for("admin.listar_solicitacoes"))


# ─────────────────────────────────────────────────────────────────────────────
# Saídas
# ─────────────────────────────────────────────────────────────────────────────

SAIDAS_ADMIN_POR_PAGINA = 5


def _query_saidas_admin_filtrada():
    """Monta a query filtrada de saídas (admin) a partir dos parâmetros GET
    atuais. Reaproveitada por `listar_saidas` (1ª página, renderizada no
    servidor) e por `api_saidas` (páginas seguintes, carregadas via "Ver
    mais" sem recarregar a tela)."""
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

    query = query.order_by(Registro.data_registro.desc())
    contexto_filtros = {
        "busca": busca, "status_filtro": status_filtro,
        "data_inicio": data_inicio, "data_fim": data_fim,
        "subunidade_id": subunidade_id,
    }
    return query, contexto_filtros


@admin_bp.route("/saidas")
@login_required
@admin_required
def listar_saidas():
    query, filtros = _query_saidas_admin_filtrada()

    page = max(1, parse_int_seguro(request.args.get("page", "1"), minimo=1) or 1)
    per_page = SAIDAS_ADMIN_POR_PAGINA

    total = query.count()
    saidas = query.offset((page - 1) * per_page).limit(per_page).all()
    tem_mais = (page * per_page) < total

    subunidades = Subunidade.query.filter_by(ativa=True).order_by(Subunidade.nome).all()
    return render_template(
        "admin/saidas.html",
        saidas=saidas,
        total=total,
        page=page,
        per_page=per_page,
        tem_mais=tem_mais,
        subunidades=subunidades,
        StatusSaida=StatusSaida,
        **filtros,
    )


def _saida_admin_para_dict(saida: Registro) -> dict:
    return {
        "id": saida.id,
        "militar_nome": saida.usuario.nome if saida.usuario else "—",
        "militar_cpf": saida.cpf_usuario,
        "local": saida.local,
        "motivo": saida.motivo,
        "data_saida": saida.data_saida.strftime("%d/%m/%Y") if saida.data_saida else None,
        "data_retorno": saida.data_retorno.strftime("%d/%m/%Y") if saida.data_retorno else None,
        "status": saida.status,
        "status_label": saida.status_label,
        "status_badge": saida.status_badge,
        "status_atualizado_em": (
            saida.status_atualizado_em.strftime("%d/%m") if saida.status_atualizado_em else None
        ),
    }


@admin_bp.route("/saidas/api")
@login_required
@admin_required
def api_saidas():
    """Endpoint AJAX usado pelo botão "Ver mais" — carrega a próxima
    página de saídas sem recarregar a tela inteira, evitando despejar
    todos os registros de uma vez na tabela."""
    query, _ = _query_saidas_admin_filtrada()

    page = max(1, parse_int_seguro(request.args.get("page", "1"), minimo=1) or 1)
    per_page = SAIDAS_ADMIN_POR_PAGINA

    total = query.count()
    saidas = query.offset((page - 1) * per_page).limit(per_page).all()
    tem_mais = (page * per_page) < total

    return jsonify({
        "saidas": [_saida_admin_para_dict(s) for s in saidas],
        "total": total,
        "page": page,
        "tem_mais": tem_mais,
    })


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
            "dica_login":   150,
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

        # Hierarquia (Posto/Graduação) — recurso opcional, liga/desliga sem
        # afetar nenhum cadastro já existente (o campo no usuário continua
        # como está; apenas deixa de aparecer/ser exigido nos formulários).
        ConfigSistema.set(
            "postos_habilitados",
            "1" if request.form.get("postos_habilitados") == "on" else "0",
        )

        # Controla se algum upload falhou nesta submissão — usado para NÃO
        # mostrar "Configurações salvas com sucesso!" isoladamente quando na
        # verdade um ou mais arquivos foram recusados. Sem isso, o usuário via
        # o erro específico (ex.: "excede o tamanho máximo") E, logo em
        # seguida, um aviso verde de sucesso — dando a impressão de que o
        # arquivo recusado tinha sido salvo mesmo assim, quando na verdade só
        # os OUTROS campos (texto, cores, etc.) foram salvos.
        houve_erro_upload = False

        for campo_img in ["logo", "logo_relatorio", "brasao", "favicon"]:
            if request.form.get(f"remover_{campo_img}") == "1":
                valor_atual = ConfigSistema.get(campo_img)
                remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], valor_atual)
                ConfigSistema.set(campo_img, "")
                continue

            nome_arquivo, erro_upload = _save_upload(campo_img, campo_img)
            if erro_upload:
                flash(f"{campo_img}: {erro_upload}", "danger")
                houve_erro_upload = True
                continue
            if nome_arquivo:
                valor_antigo = ConfigSistema.get(campo_img)
                ConfigSistema.set(campo_img, nome_arquivo)
                remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], valor_antigo)

        # ── Tema padrão da interface (claro / escuro / verde-oliva) ────────
        # É apenas o valor inicial: cada usuário pode trocar seu próprio
        # tema a qualquer momento (fica salvo no navegador dele), sem
        # afetar esta preferência padrão da organização.
        tema_padrao = request.form.get("tema_padrao", "light")
        if tema_padrao not in ("light", "dark", "olive"):
            tema_padrao = "light"
        ConfigSistema.set("tema_padrao", tema_padrao)

        # ── Aparência da tela de login (fundo em imagem ou vídeo curto) ────
        login_bg_tipo = request.form.get("login_bg_tipo", "")
        if login_bg_tipo not in ("", "imagem", "video"):
            login_bg_tipo = ""
        ConfigSistema.set("login_bg_tipo", login_bg_tipo)

        login_bg_posicao = request.form.get("login_bg_posicao", "centro")
        if login_bg_posicao not in ("topo", "centro", "base"):
            login_bg_posicao = "centro"
        ConfigSistema.set("login_bg_posicao", login_bg_posicao)

        overlay = parse_int_seguro(request.form.get("login_bg_overlay", "55"), minimo=0)
        if overlay is None:
            overlay = 55
        overlay = max(0, min(overlay, 90))
        ConfigSistema.set("login_bg_overlay", str(overlay))

        if request.form.get("remover_login_bg_imagem") == "1":
            remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], ConfigSistema.get("login_bg_imagem"))
            ConfigSistema.set("login_bg_imagem", "")
        else:
            nome_imagem, erro_imagem = _save_upload("login_bg_imagem", "login_bg")
            if erro_imagem:
                flash(f"Imagem de fundo do login: {erro_imagem}", "danger")
                houve_erro_upload = True
            elif nome_imagem:
                valor_antigo = ConfigSistema.get("login_bg_imagem")
                ConfigSistema.set("login_bg_imagem", nome_imagem)
                remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], valor_antigo)

        if request.form.get("remover_login_bg_video") == "1":
            remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], ConfigSistema.get("login_bg_video"))
            ConfigSistema.set("login_bg_video", "")
        else:
            nome_video, erro_video = _save_video_upload("login_bg_video", "login_bg")
            if erro_video:
                flash(f"Vídeo de fundo do login: {erro_video}", "danger")
                houve_erro_upload = True
            elif nome_video:
                valor_antigo = ConfigSistema.get("login_bg_video")
                ConfigSistema.set("login_bg_video", nome_video)
                remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], valor_antigo)

        if houve_erro_upload:
            flash(
                "Configurações salvas. Os demais campos foram atualizados, mas "
                "um ou mais arquivos foram recusados — veja os avisos acima e "
                "tente novamente apenas com esses arquivos.",
                "warning",
            )
        else:
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


def _validar_posto(posto_id: str, errors: list) -> int | None:
    """
    Valida o ID de posto/graduação vindo do formulário. Segue o mesmo
    padrão de `_validar_subunidade` — o campo é sempre opcional, então o
    recurso nunca impede o cadastro/edição de um usuário, mesmo se o
    super-usuário resolver desativá-lo depois de já haver vínculos.
    """
    if not posto_id:
        return None
    posto_id_valido = parse_int_seguro(posto_id, minimo=1)
    if posto_id_valido is None:
        errors.append("Posto/Graduação inválido(a).")
        return None
    if not db.session.get(PostoGraduacao, posto_id_valido):
        errors.append("Posto/Graduação não encontrado(a).")
        return None
    return posto_id_valido


# ─────────────────────────────────────────────────────────────────────────────
# Motivos de Cancelamento
# ─────────────────────────────────────────────────────────────────────────────

from app.models import MotivoCancelamento  # noqa: E402 (append)


@admin_bp.route("/motivos-cancelamento")
@login_required
@admin_required
def listar_motivos():
    motivos = MotivoCancelamento.query.order_by(
        MotivoCancelamento.ordem, MotivoCancelamento.id
    ).all()
    return render_template("admin/motivos_cancelamento.html", motivos=motivos)


@admin_bp.route("/motivos-cancelamento/salvar", methods=["POST"])
@login_required
@admin_required
def salvar_motivos():
    """Salva criação, edição e exclusão de motivos via POST único."""
    # Motivos existentes para editar
    ids_existentes = request.form.getlist("motivo_id")
    textos = request.form.getlist("motivo_texto")
    ativos = request.form.getlist("motivo_ativo")
    ordens = request.form.getlist("motivo_ordem")
    excluir = request.form.getlist("motivo_excluir")

    for i, mid in enumerate(ids_existentes):
        # parse_int_seguro nunca lança exceção: um "motivo_id" malformado
        # vindo de um POST manual/malicioso antes derrubava a rota inteira
        # com um ValueError não tratado (500 genérico). Um id inválido
        # agora é simplesmente ignorado, sem afetar os demais motivos do
        # mesmo formulário.
        mid_valido = parse_int_seguro(mid, minimo=1)
        if mid_valido is None:
            continue
        if mid in excluir:
            obj = db.session.get(MotivoCancelamento, mid_valido)
            if obj:
                db.session.delete(obj)
            continue
        texto = (textos[i] if i < len(textos) else "").strip()[:150]
        if not texto:
            continue
        obj = db.session.get(MotivoCancelamento, mid_valido)
        if obj:
            obj.texto = texto
            obj.ativo = str(mid) in ativos
            try:
                obj.ordem = int(ordens[i]) if i < len(ordens) else 0
            except (ValueError, TypeError):
                obj.ordem = 0

    # Novos motivos
    novos_textos = request.form.getlist("novo_texto")
    novos_ordens = request.form.getlist("nova_ordem")
    for j, texto in enumerate(novos_textos):
        texto = texto.strip()[:150]
        if not texto:
            continue
        try:
            ordem = int(novos_ordens[j]) if j < len(novos_ordens) else 0
        except (ValueError, TypeError):
            ordem = 0
        db.session.add(MotivoCancelamento(texto=texto, ativo=True, ordem=ordem))

    ok, erro = commit_seguro(
        db,
        mensagem_erro="Não foi possível salvar os motivos.",
    )
    if ok:
        flash("Motivos de cancelamento salvos com sucesso!", "success")
    else:
        flash(erro, "danger")

    return redirect(url_for("admin.listar_motivos"))
