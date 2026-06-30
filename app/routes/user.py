"""
routes/user.py — Rotas do painel do usuário (militar).
"""

from datetime import datetime, timedelta

from flask import (
    Blueprint, current_app, flash, jsonify, redirect,
    render_template, request, url_for,
)
from flask_login import current_user, login_required

from app import db
from app.models import Registro, StatusSaida, ConfigSistema, MotivoCancelamento
from app.uploads import validar_e_salvar_imagem, remover_upload_seguro
from app.validators import validar_texto_livre, validar_telefone, validar_data

user_bp = Blueprint("user", __name__)


def _get_user_stats(cpf):
    todos = Registro.query.filter_by(cpf_usuario=cpf).all()
    total = len(todos)

    agendadas   = sum(1 for s in todos if s.status == StatusSaida.AGENDADA)
    em_transito = sum(1 for s in todos if s.status == StatusSaida.EM_TRANSITO)
    retornadas  = sum(1 for s in todos if s.status in (StatusSaida.RETORNADO, StatusSaida.FINALIZADO))
    canceladas  = sum(1 for s in todos if s.status == StatusSaida.CANCELADO)

    hoje = datetime.today()
    meses_labels = []
    meses_qtd = []
    NOMES_MES = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
    for i in range(5, -1, -1):
        mes_dt = hoje - timedelta(days=i * 30)
        mes_label = f"{NOMES_MES[mes_dt.month - 1]}/{mes_dt.year % 100:02d}"
        qtd = sum(
            1 for s in todos
            if s.data_registro.year == mes_dt.year and s.data_registro.month == mes_dt.month
        )
        meses_labels.append(mes_label)
        meses_qtd.append(qtd)

    return {
        'total': total,
        'agendadas': agendadas,
        'em_transito': em_transito,
        'retornadas': retornadas,
        'canceladas': canceladas,
        'meses_labels': meses_labels,
        'meses_qtd': meses_qtd,
    }


def _saida_to_dict(saida):
    """Serializa um Registro para JSON (usado na API AJAX do dashboard)."""
    return {
        'id': saida.id,
        'local': saida.local,
        'motivo': saida.motivo,
        'status': saida.status,
        'status_label': saida.status_label,
        'status_badge': saida.status_badge,
        'data_registro': saida.data_registro.strftime('%d/%m/%Y'),
        'data_saida': saida.data_saida.strftime('%d/%m/%Y') if saida.data_saida else None,
        'data_retorno': saida.data_retorno.strftime('%d/%m/%Y') if saida.data_retorno else None,
        'telefone_contato': saida.telefone_contato or '',
        'editavel': saida.editavel,
        'motivo_cancelamento': saida.motivo_cancelamento or '',
        'obs_cancelamento': saida.obs_cancelamento or '',
        'url_editar': url_for('user.editar_saida', id=saida.id),
    }


@user_bp.route("/dashboard")
@login_required
def dashboard():
    stats = _get_user_stats(current_user.cpf)
    config_sistema = {c.chave: c.valor for c in ConfigSistema.query.all()}

    return render_template(
        "user/dashboard.html",
        stats=stats,
        config_sistema=config_sistema,
    )


@user_bp.route("/api/saidas")
@login_required
def api_saidas():
    """Endpoint AJAX: retorna saídas filtradas em JSON sem recarregar a página."""
    status_filtro = request.args.get("status", "")
    historico = request.args.get("historico", "0") == "1"
    page = max(1, int(request.args.get("page", 1)))
    per_page = 9

    query = Registro.query.filter_by(cpf_usuario=current_user.cpf)
    if status_filtro and status_filtro in StatusSaida.TODOS:
        query = query.filter_by(status=status_filtro)

    query = query.order_by(Registro.data_registro.desc())

    total = query.count()

    if historico or status_filtro:
        saidas = query.offset((page - 1) * per_page).limit(per_page).all()
        tem_mais = (page * per_page) < total
    else:
        saidas = query.limit(6).all()
        tem_mais = total > 6

    return jsonify({
        'saidas': [_saida_to_dict(s) for s in saidas],
        'total': total,
        'tem_mais': tem_mais,
        'page': page,
    })


@user_bp.route("/registrar", methods=["GET", "POST"])
@login_required
def registrar_saida():
    motivos_sugeridos = current_app.config.get("MOTIVOS_SUGERIDOS", [])
    motivo_max = current_app.config.get("MOTIVO_MAX_LENGTH", 300)

    if request.method == "POST":
        local, erros_local = validar_texto_livre(
            request.form.get("local", ""), campo="local de destino",
            max_len=255, obrigatorio=True,
        )
        motivo, erros_motivo = validar_texto_livre(
            request.form.get("motivo", ""), campo="motivo",
            max_len=motivo_max, obrigatorio=True, permitir_emoji=False,
        )
        telefone, erros_telefone = validar_telefone(request.form.get("telefone_contato", ""))
        endereco, erros_endereco = validar_texto_livre(
            request.form.get("endereco_destino", ""), campo="endereço no destino",
            max_len=500, obrigatorio=False,
        )

        data_saida_str   = request.form.get("data_saida", "")
        data_retorno_str = request.form.get("data_retorno", "")

        data_saida, erros_data_saida = validar_data(
            data_saida_str, campo="data de saída", obrigatoria=True
        )
        data_retorno, erros_data_retorno = validar_data(
            data_retorno_str, campo="data de retorno", obrigatoria=False
        )

        errors = [
            *erros_local, *erros_motivo, *erros_telefone, *erros_endereco,
            *erros_data_saida, *erros_data_retorno,
        ]

        if data_saida and data_saida.date() < datetime.today().date():
            errors.append("A data de saída não pode ser anterior ao dia atual.")

        if data_retorno and data_saida and data_retorno < data_saida:
            errors.append("A data de retorno não pode ser anterior à data de saída.")

        if not errors and data_saida:
            duplicado = Registro.query.filter_by(
                cpf_usuario=current_user.cpf,
                local=local,
            ).filter(
                db.func.date(Registro.data_saida) == data_saida.date()
            ).first()
            if duplicado:
                errors.append("Já existe um registro para este local e data de saída.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "user/registrar.html",
                form_data=request.form,
                motivos_sugeridos=motivos_sugeridos,
                motivo_max=motivo_max,
            )

        hoje = datetime.today().date()
        status_inicial = (
            StatusSaida.EM_TRANSITO
            if data_saida and data_saida.date() <= hoje
            else StatusSaida.AGENDADA
        )

        registro = Registro(
            cpf_usuario=current_user.cpf,
            local=local,
            motivo=motivo,
            data_saida=data_saida,
            data_retorno=data_retorno,
            telefone_contato=telefone,
            endereco_destino=endereco,
            status=status_inicial,
            status_atualizado_em=datetime.utcnow(),
        )
        try:
            db.session.add(registro)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Não foi possível registrar a saída. Verifique os dados e tente novamente.", "danger")
            return render_template(
                "user/registrar.html",
                form_data=request.form,
                motivos_sugeridos=motivos_sugeridos,
                motivo_max=motivo_max,
            )

        return redirect(url_for("user.dashboard", registrado="1"))

    return render_template(
        "user/registrar.html",
        form_data={},
        motivos_sugeridos=motivos_sugeridos,
        motivo_max=motivo_max,
    )


@user_bp.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_saida(id):
    saida = Registro.query.filter_by(
        id=id, cpf_usuario=current_user.cpf
    ).first_or_404()

    if not saida.editavel:
        flash("Esta saída não pode mais ser editada.", "warning")
        return redirect(url_for("user.dashboard"))

    motivos_sugeridos = current_app.config.get("MOTIVOS_SUGERIDOS", [])
    motivo_max = current_app.config.get("MOTIVO_MAX_LENGTH", 300)

    if request.method == "POST":
        local, erros_local = validar_texto_livre(
            request.form.get("local", ""), campo="local de destino",
            max_len=255, obrigatorio=True,
        )
        motivo, erros_motivo = validar_texto_livre(
            request.form.get("motivo", ""), campo="motivo",
            max_len=motivo_max, obrigatorio=True,
        )
        telefone, erros_telefone = validar_telefone(request.form.get("telefone_contato", ""))
        endereco, erros_endereco = validar_texto_livre(
            request.form.get("endereco_destino", ""), campo="endereço no destino",
            max_len=500, obrigatorio=False,
        )

        data_saida_str   = request.form.get("data_saida", "")
        data_retorno_str = request.form.get("data_retorno", "")

        data_saida, erros_data_saida = validar_data(data_saida_str, campo="data de saída", obrigatoria=True)
        data_retorno, erros_data_retorno = validar_data(data_retorno_str, campo="data de retorno")

        errors = [
            *erros_local, *erros_motivo, *erros_telefone, *erros_endereco,
            *erros_data_saida, *erros_data_retorno,
        ]

        if data_retorno and data_saida and data_retorno < data_saida:
            errors.append("A data de retorno não pode ser anterior à data de saída.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "user/editar.html",
                saida=saida,
                motivos_sugeridos=motivos_sugeridos,
                motivo_max=motivo_max,
            )

        saida.local            = local
        saida.motivo           = motivo
        saida.data_saida       = data_saida
        saida.data_retorno     = data_retorno
        saida.telefone_contato = telefone
        saida.endereco_destino = endereco
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Não foi possível salvar as alterações. Tente novamente.", "danger")
            return render_template(
                "user/editar.html",
                saida=saida,
                motivos_sugeridos=motivos_sugeridos,
                motivo_max=motivo_max,
            )

        flash("Saída atualizada com sucesso!", "success")
        return redirect(url_for("user.dashboard"))

    return render_template(
        "user/editar.html",
        saida=saida,
        motivos_sugeridos=motivos_sugeridos,
        motivo_max=motivo_max,
    )


@user_bp.route("/cancelar/<int:id>", methods=["POST"])
@login_required
def cancelar_saida(id):
    saida = Registro.query.filter_by(
        id=id, cpf_usuario=current_user.cpf
    ).first_or_404()

    origem = request.form.get("origem", "registros")  # 'registros' ou 'dashboard'

    if not saida.editavel:
        flash("Esta saída não pode mais ser cancelada.", "warning")
        return redirect(url_for("user.meus_registros"))

    # Valida o motivo selecionado (deve existir na lista de motivos ativos)
    motivo_id = request.form.get("motivo_cancelamento_id", "").strip()
    obs_raw   = request.form.get("obs_cancelamento", "").strip()

    if not motivo_id:
        flash("Selecione um motivo para o cancelamento.", "danger")
        return redirect(url_for("user.meus_registros"))

    motivo_obj = MotivoCancelamento.query.filter_by(id=motivo_id, ativo=True).first()
    if not motivo_obj:
        flash("Motivo de cancelamento inválido.", "danger")
        return redirect(url_for("user.meus_registros"))

    # Observação opcional — limitada a 200 caracteres
    obs, erros_obs = validar_texto_livre(
        obs_raw, campo="observação",
        max_len=200, obrigatorio=False,
    )
    if erros_obs:
        for e in erros_obs:
            flash(e, "danger")
        return redirect(url_for("user.meus_registros"))

    saida.status               = StatusSaida.CANCELADO
    saida.status_atualizado_em = datetime.utcnow()
    saida.motivo_cancelamento  = motivo_obj.texto
    saida.obs_cancelamento     = obs or None
    saida.data_cancelamento    = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash("Não foi possível cancelar a saída. Tente novamente.", "danger")
        return redirect(url_for("user.meus_registros"))

    flash("Saída cancelada com sucesso.", "info")
    return redirect(url_for("user.meus_registros"))


@user_bp.route("/api/registro/<int:id>")
@login_required
def api_registro_detalhe(id):
    """Retorna JSON com detalhes de um registro para preview."""
    saida = Registro.query.filter_by(
        id=id, cpf_usuario=current_user.cpf
    ).first_or_404()
    return jsonify({
        'id': saida.id,
        'local': saida.local,
        'motivo': saida.motivo,
        'status': saida.status,
        'status_label': saida.status_label,
        'status_badge': saida.status_badge,
        'data_registro': saida.data_registro.strftime('%d/%m/%Y %H:%M'),
        'data_saida': saida.data_saida.strftime('%d/%m/%Y') if saida.data_saida else None,
        'data_retorno': saida.data_retorno.strftime('%d/%m/%Y') if saida.data_retorno else None,
        'telefone_contato': saida.telefone_contato or '',
        'endereco_destino': saida.endereco_destino or '',
        'editavel': saida.editavel,
        'motivo_cancelamento': saida.motivo_cancelamento or '',
        'obs_cancelamento': saida.obs_cancelamento or '',
        'data_cancelamento': saida.data_cancelamento.strftime('%d/%m/%Y %H:%M') if saida.data_cancelamento else None,
        'url_editar': url_for('user.editar_saida', id=saida.id),
        'url_cancelar': url_for('user.cancelar_saida', id=saida.id),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Perfil do usuário
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/meus-registros")
@login_required
def meus_registros():
    """Página de consulta/pesquisa dos registros do próprio usuário."""
    busca_local = request.args.get("local", "").strip()
    data_inicio = request.args.get("data_inicio", "").strip()
    data_fim    = request.args.get("data_fim", "").strip()
    status_filtro = request.args.get("status", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = 10

    query = Registro.query.filter_by(cpf_usuario=current_user.cpf)

    if busca_local:
        query = query.filter(Registro.local.ilike(f"%{busca_local}%"))

    if data_inicio:
        try:
            dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
            query = query.filter(Registro.data_registro >= dt_ini)
        except ValueError:
            pass

    if data_fim:
        try:
            from datetime import timedelta
            dt_fim = datetime.strptime(data_fim, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Registro.data_registro < dt_fim)
        except ValueError:
            pass

    if status_filtro and status_filtro in StatusSaida.TODOS:
        query = query.filter_by(status=status_filtro)

    query = query.order_by(Registro.data_registro.desc())
    total = query.count()
    saidas = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = max(1, -(-total // per_page))  # ceil division

    tem_filtro = any([busca_local, data_inicio, data_fim, status_filtro])
    motivos_cancelamento = MotivoCancelamento.listar_ativos()

    return render_template(
        "user/meus_registros.html",
        saidas=saidas,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        tem_filtro=tem_filtro,
        busca_local=busca_local,
        data_inicio=data_inicio,
        data_fim=data_fim,
        status_filtro=status_filtro,
        StatusSaida=StatusSaida,
        motivos_cancelamento=motivos_cancelamento,
    )


@user_bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    """Permite que o usuário atualize sua foto, telefone e e-mail."""
    if request.method == "POST":
        acao = request.form.get("acao", "dados")

        if acao == "senha":
            # Troca de senha
            senha_atual = request.form.get("senha_atual", "").strip()
            nova_senha  = request.form.get("nova_senha", "").strip()
            confirmar   = request.form.get("confirmar_senha", "").strip()

            if not current_user.check_senha(senha_atual):
                flash("Senha atual incorreta.", "danger")
            elif len(nova_senha) < 4:
                flash("A nova senha deve ter pelo menos 4 caracteres.", "danger")
            elif nova_senha != confirmar:
                flash("As senhas não coincidem.", "danger")
            else:
                current_user.set_senha(nova_senha)
                try:
                    db.session.commit()
                    flash("Senha alterada com sucesso!", "success")
                except Exception:
                    db.session.rollback()
                    flash("Não foi possível alterar a senha.", "danger")
            return redirect(url_for("user.perfil"))

        # Dados + foto
        telefone, erros_tel = validar_telefone(request.form.get("telefone", ""))
        email_raw = request.form.get("email", "").strip()[:120]

        errors = list(erros_tel)

        # Validação simples de e-mail
        if email_raw and ("@" not in email_raw or "." not in email_raw.split("@")[-1]):
            errors.append("E-mail inválido.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return redirect(url_for("user.perfil"))

        current_user.telefone = telefone or None
        current_user.email    = email_raw or None

        # Foto
        if request.form.get("remover_foto") == "1":
            if current_user.foto:
                remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], current_user.foto)
            current_user.foto = None
        else:
            file = request.files.get("foto")
            resultado = validar_e_salvar_imagem(
                file,
                destino_dir=current_app.config["UPLOAD_FOLDER"],
                prefixo=f"user_{current_user.id}",
            )
            if not resultado.ok:
                flash(resultado.erro, "danger")
                return redirect(url_for("user.perfil"))
            if resultado.nome_arquivo:
                foto_antiga = current_user.foto
                current_user.foto = resultado.nome_arquivo
                remover_upload_seguro(current_app.config["UPLOAD_FOLDER"], foto_antiga)

        try:
            db.session.commit()
            flash("Perfil atualizado com sucesso!", "success")
        except Exception:
            db.session.rollback()
            flash("Não foi possível salvar as alterações.", "danger")

        return redirect(url_for("user.perfil"))

    return render_template("user/perfil.html")
