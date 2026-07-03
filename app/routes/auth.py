from datetime import datetime

from flask import Blueprint, current_app, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models import Usuario
from app.validators import sanitizar_texto
from app import db

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/', methods=['GET', 'POST'])
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('user.dashboard'))

    if request.method == 'POST':
        # Sanitiza e limita o tamanho de qualquer entrada antes de consultar o
        # banco — evita strings gigantes/com caracteres de controle chegarem
        # à consulta, e garante que nunca comparamos algo maior que a coluna.
        cpf = sanitizar_texto(request.form.get('cpf', ''), max_len=14)
        senha = (request.form.get('senha', '') or '').strip()[:255]
        lembrar = request.form.get('lembrar') == 'on'

        if not cpf or not senha:
            flash('Por favor, preencha todos os campos.', 'danger')
            return render_template('auth/login.html')

        usuario = Usuario.query.filter_by(cpf=cpf).first()

        # Bloqueio por excesso de tentativas erradas (proteção contra força
        # bruta). O contador é incrementado de forma atômica no banco — veja
        # Usuario.registrar_tentativa_falha — então continua correto mesmo
        # com várias tentativas simultâneas para o mesmo CPF.
        if usuario and usuario.esta_bloqueado:
            minutos_restantes = max(
                1, int((usuario.bloqueado_ate - datetime.utcnow()).total_seconds() // 60) + 1
            )
            current_app.logger.warning(
                "Tentativa de login bloqueada para CPF %s (%s min restantes).",
                cpf, minutos_restantes,
            )
            flash(
                f'Muitas tentativas incorretas. Tente novamente em {minutos_restantes} minuto(s).',
                'danger',
            )
            return render_template('auth/login.html')

        if usuario and usuario.check_senha(senha):
            if not usuario.ativo:
                flash('Sua conta está desativada. Entre em contato com o administrador.', 'danger')
                return render_template('auth/login.html')

            Usuario.limpar_tentativas(usuario.id)

            # Regenera a sessão antes de autenticar (limpa qualquer dado de
            # sessão anterior e força um novo cookie de sessão). Isso evita
            # "fixação de sessão": se, por qualquer motivo, um identificador
            # de sessão antigo estivesse em uso, ele não é reaproveitado
            # depois do login — a sessão pós-login é sempre nova.
            session.clear()

            login_user(usuario, remember=lembrar)
            session.permanent = True
            next_page = request.args.get('next')

            current_app.logger.info("Login bem-sucedido: usuário %s (CPF %s).", usuario.id, cpf)
            flash(f'Bem-vindo(a), {usuario.nome}!', 'success')

            # Nunca redireciona para uma URL absoluta/externa vinda de "next"
            # (evita open redirect): só aceitamos caminhos internos relativos.
            if next_page and next_page.startswith('/') and not next_page.startswith('//'):
                return redirect(next_page)
            if usuario.is_admin:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('user.dashboard'))
        else:
            if usuario:
                Usuario.registrar_tentativa_falha(
                    usuario.id,
                    max_tentativas=current_app.config.get('LOGIN_MAX_TENTATIVAS', 5),
                    bloqueio_minutos=current_app.config.get('LOGIN_BLOQUEIO_MINUTOS', 15),
                )
            current_app.logger.info("Tentativa de login falhou para CPF %s.", cpf)
            flash('CPF ou senha incorretos. Verifique seus dados e tente novamente.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    # Limpa qualquer dado remanescente na sessão (flashes já emitidos à
    # parte) para garantir que nada da sessão anterior sobrevive no mesmo
    # cookie após o logout.
    session.clear()
    flash('Você saiu do sistema com sucesso.', 'info')
    return redirect(url_for('auth.login'))
