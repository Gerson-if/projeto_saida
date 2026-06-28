from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models import Usuario
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
        cpf = request.form.get('cpf', '').strip()
        senha = request.form.get('senha', '').strip()
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

            if next_page:
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
