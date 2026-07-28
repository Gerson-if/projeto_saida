from flask import Blueprint, render_template, redirect, url_for, flash, request
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

        if usuario and usuario.check_senha(senha):
            if not usuario.ativo:
                flash('Sua conta está desativada. Entre em contato com o administrador.', 'danger')
                return render_template('auth/login.html')

            login_user(usuario, remember=lembrar)
            next_page = request.args.get('next')

            flash(f'Bem-vindo(a), {usuario.nome}!', 'success')

            # Nunca redireciona para uma URL absoluta/externa vinda de "next"
            # (evita open redirect): só aceitamos caminhos internos relativos.
            if next_page and next_page.startswith('/') and not next_page.startswith('//'):
                return redirect(next_page)
            if usuario.is_admin:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('user.dashboard'))
        else:
            flash('CPF ou senha incorretos. Verifique seus dados e tente novamente.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema com sucesso.', 'info')
    return redirect(url_for('auth.login'))
