"""
routes/user.py — Rotas do painel do usuário (militar).

Permite registrar, editar e cancelar saídas.
O status é gerenciado automaticamente pelo sistema.
"""

from datetime import datetime

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app import db
from app.models import Registro, StatusSaida

user_bp = Blueprint("user", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard do usuário
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/dashboard")
@login_required
def dashboard():
    status_filtro = request.args.get("status", "")
    query = Registro.query.filter_by(cpf_usuario=current_user.cpf)
    if status_filtro and status_filtro in StatusSaida.TODOS:
        query = query.filter_by(status=status_filtro)
    saidas = query.order_by(Registro.data_registro.desc()).all()
    return render_template(
        "user/dashboard.html",
        saidas=saidas,
        status_filtro=status_filtro,
        StatusSaida=StatusSaida,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Registrar saída
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/registrar", methods=["GET", "POST"])
@login_required
def registrar_saida():
    motivos_sugeridos = current_app.config.get("MOTIVOS_SUGERIDOS", [])
    motivo_max = current_app.config.get("MOTIVO_MAX_LENGTH", 300)

    if request.method == "POST":
        local           = request.form.get("local", "").strip()
        motivo          = request.form.get("motivo", "").strip()
        data_saida_str  = request.form.get("data_saida", "")
        data_retorno_str = request.form.get("data_retorno", "")
        telefone        = request.form.get("telefone_contato", "").strip()
        endereco        = request.form.get("endereco_destino", "").strip()

        errors = []
        if not local:
            errors.append("O local de destino é obrigatório.")
        if not motivo:
            errors.append("O motivo é obrigatório.")
        elif len(motivo) > motivo_max:
            errors.append(f"O motivo deve ter no máximo {motivo_max} caracteres.")
        if not data_saida_str:
            errors.append("A data de saída é obrigatória.")

        data_saida = data_retorno = None

        if data_saida_str:
            try:
                data_saida = datetime.strptime(data_saida_str, "%Y-%m-%d")
                if data_saida.date() < datetime.today().date():
                    errors.append("A data de saída não pode ser anterior ao dia atual.")
            except ValueError:
                errors.append("Data de saída inválida.")

        if data_retorno_str:
            try:
                data_retorno = datetime.strptime(data_retorno_str, "%Y-%m-%d")
                if data_saida and data_retorno < data_saida:
                    errors.append("A data de retorno não pode ser anterior à data de saída.")
            except ValueError:
                errors.append("Data de retorno inválida.")

        # Verifica duplicidade (mesmo usuário, mesmo local, mesma data)
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

        # Determina status inicial com base na data
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
        db.session.add(registro)
        db.session.commit()
        flash("Saída registrada com sucesso!", "success")
        return redirect(url_for("user.dashboard"))

    return render_template(
        "user/registrar.html",
        form_data={},
        motivos_sugeridos=motivos_sugeridos,
        motivo_max=motivo_max,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Editar saída (apenas enquanto agendada)
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/editar/<int:id>", methods=["GET", "POST"])
@login_required
def editar_saida(id):
    saida = Registro.query.filter_by(
        id=id, cpf_usuario=current_user.cpf
    ).first_or_404()

    # Impede edição de saídas já em trânsito ou finalizadas
    if saida.status not in (StatusSaida.AGENDADA,):
        flash(
            "Não é possível editar uma saída que já está em trânsito ou finalizada.",
            "warning",
        )
        return redirect(url_for("user.dashboard"))

    motivos_sugeridos = current_app.config.get("MOTIVOS_SUGERIDOS", [])
    motivo_max = current_app.config.get("MOTIVO_MAX_LENGTH", 300)

    if request.method == "POST":
        local           = request.form.get("local", "").strip()
        motivo          = request.form.get("motivo", "").strip()
        data_saida_str  = request.form.get("data_saida", "")
        data_retorno_str = request.form.get("data_retorno", "")
        telefone        = request.form.get("telefone_contato", "").strip()
        endereco        = request.form.get("endereco_destino", "").strip()

        errors = []
        data_saida = data_retorno = None

        if data_saida_str:
            try:
                data_saida = datetime.strptime(data_saida_str, "%Y-%m-%d")
            except ValueError:
                errors.append("Data de saída inválida.")

        if data_retorno_str:
            try:
                data_retorno = datetime.strptime(data_retorno_str, "%Y-%m-%d")
                if data_saida and data_retorno < data_saida:
                    errors.append("A data de retorno não pode ser anterior à data de saída.")
            except ValueError:
                errors.append("Data de retorno inválida.")

        if motivo and len(motivo) > motivo_max:
            errors.append(f"O motivo deve ter no máximo {motivo_max} caracteres.")

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
        db.session.commit()
        flash("Saída atualizada com sucesso!", "success")
        return redirect(url_for("user.dashboard"))

    return render_template(
        "user/editar.html",
        saida=saida,
        motivos_sugeridos=motivos_sugeridos,
        motivo_max=motivo_max,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cancelar saída (apenas enquanto agendada)
# ─────────────────────────────────────────────────────────────────────────────

@user_bp.route("/cancelar/<int:id>", methods=["POST"])
@login_required
def cancelar_saida(id):
    saida = Registro.query.filter_by(
        id=id, cpf_usuario=current_user.cpf
    ).first_or_404()

    if saida.status != StatusSaida.AGENDADA:
        flash("Apenas saídas agendadas podem ser canceladas.", "warning")
        return redirect(url_for("user.dashboard"))

    saida.status = StatusSaida.CANCELADO
    saida.status_atualizado_em = datetime.utcnow()
    db.session.commit()
    flash("Saída cancelada com sucesso.", "info")
    return redirect(url_for("user.dashboard"))
