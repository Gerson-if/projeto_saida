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
    # IMPORTANTE: este atalho de "já está logado, redireciona direto" só
    # pode valer para GET. Antes, ele rodava também no POST, ANTES de olhar
    # para o CPF/senha enviados no formulário — ou seja, se por qualquer
    # motivo o navegador ainda carregasse um resquício de autenticação
    # (cookie de "lembrar-me", sessão que ainda não expirou, aba antiga
    # ainda aberta, cache, etc.), a tentativa de login com OUTRO usuário
    # nunca era sequer avaliada: o sistema simplesmente devolvia o
    # dashboard de quem já estava logado. Era esse o "erro grave" — não
    # importava o que a pessoa digitasse no formulário, se ainda havia
    # qualquer sinal de sessão anterior válida, era ele quem prevalecia.
    #
    # Agora, todo POST em /login SEMPRE valida CPF/senha de verdade contra
    # o banco, mesmo que exista uma sessão anterior ativa — e, se as
    # credenciais forem de um usuário diferente do que estava logado, a
    # sessão antiga é encerrada por completo antes de abrir a nova (ver
    # abaixo), para nunca misturar estado de dois usuários.
    if request.method == 'GET' and current_user.is_authenticated:
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

            # Se já havia alguém logado nesta sessão (ex: usuário tentando
            # trocar de conta sem clicar em "Sair" antes), encerra essa
            # sessão anterior de verdade — inclusive o cookie de
            # "lembrar-me" dela — antes de autenticar o novo usuário.
            # Sem isso, dava para acabar com uma mistura de estado de dois
            # usuários diferentes na mesma sessão/cookie.
            if current_user.is_authenticated:
                logout_user()

            # Regenera a sessão antes de autenticar (limpa qualquer dado de
            # sessão anterior e força um novo cookie de sessão). Isso evita
            # "fixação de sessão": se, por qualquer motivo, um identificador
            # de sessão antigo estivesse em uso, ele não é reaproveitado
            # depois do login — a sessão pós-login é sempre nova.
            session.clear()

            login_user(usuario, remember=lembrar)
            # A sessão só deve ser "permanente" (sobreviver ao fechar o
            # navegador, com validade de PERMANENT_SESSION_LIFETIME) quando
            # o usuário realmente marcou "lembrar-me". Antes, isso era
            # sempre True — todo login virava uma sessão de longa duração
            # (8h) mesmo sem o usuário pedir, o que também contribuía para
            # sessões "grudarem" além do esperado.
            session.permanent = bool(lembrar)
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
    # ATENÇÃO À ORDEM — esta era a causa do bug de "loga sozinho com o
    # usuário anterior": logout_user() marca session['_remember'] = 'clear'
    # para avisar o Flask-Login que o cookie de "lembrar-me" precisa ser
    # apagado na resposta. Se session.clear() for chamado DEPOIS de
    # logout_user(), essa marcação é apagada junto com o resto da sessão —
    # e aí o cookie "lembrar-me" nunca é removido do navegador.
    #
    # Na requisição seguinte (ex: a própria página de login, ou uma nova
    # tentativa de POST /login), o Flask-Login lê esse cookie que sobrou e
    # autentica de novo o usuário anterior automaticamente, ANTES de
    # qualquer verificação de CPF/senha — e como login() redireciona
    # imediatamente se current_user.is_authenticated, a tentativa de login
    # com outro usuário nem chega a ser processada: o sistema simplesmente
    # volta a logar com a última sessão. Por isso o problema só aparecia ao
    # tentar trocar de usuário logo após sair, e piorava com "lembrar-me"
    # marcado.
    #
    # Corrigido limpando a sessão ANTES de logout_user(), para que a
    # marcação '_remember' = 'clear' feita por ele sobreviva até a resposta
    # e o cookie seja de fato apagado.
    session.clear()
    logout_user()
    flash('Você saiu do sistema com sucesso.', 'info')
    return redirect(url_for('auth.login'))
