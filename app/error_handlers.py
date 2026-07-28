"""
app/error_handlers.py — Páginas de erro amigáveis para toda a aplicação.

Sem isso, qualquer exceção não tratada (ex: upload maior que
MAX_CONTENT_LENGTH, URL inexistente, erro inesperado de banco de dados)
mostraria a página padrão do Werkzeug/Flask — feia, em inglês, e que em modo
DEBUG pode até expor detalhes internos do servidor. Aqui interceptamos os
códigos de erro mais comuns e devolvemos uma página consistente com a
identidade visual do sistema, com uma mensagem compreensível para o usuário.
"""

from __future__ import annotations

from flask import Flask, render_template, request, flash, redirect, url_for
from werkzeug.exceptions import HTTPException


def register_error_handlers(app: Flask) -> None:

    def _render_erro(codigo: int, icone: str, titulo: str, mensagem: str):
        try:
            return render_template(
                "errors/erro.html",
                codigo=codigo, icone=icone, titulo=titulo, mensagem=mensagem,
            ), codigo
        except Exception:
            # Fallback minimalista se até o template de erro falhar (ex.:
            # banco de dados fora do ar e o context_processor não conseguiu
            # carregar config_sistema) — nunca deixamos o usuário sem resposta.
            return f"<h1>{codigo}</h1><p>{titulo}: {mensagem}</p>", codigo

    @app.errorhandler(400)
    def erro_400(e):
        return _render_erro(
            400, "bi-exclamation-triangle",
            "Requisição inválida",
            "Os dados enviados não puderam ser processados. Verifique o formulário e tente novamente.",
        )

    @app.errorhandler(401)
    def erro_401(e):
        flash("É necessário fazer login para acessar esta página.", "warning")
        return redirect(url_for("auth.login"))

    @app.errorhandler(403)
    def erro_403(e):
        return _render_erro(
            403, "bi-shield-lock",
            "Acesso negado",
            "Você não tem permissão para acessar esta página.",
        )

    @app.errorhandler(404)
    def erro_404(e):
        return _render_erro(
            404, "bi-signpost-split",
            "Página não encontrada",
            "O endereço acessado não existe ou foi movido.",
        )

    @app.errorhandler(413)
    def erro_413(e):
        limite_mb = app.config.get("MAX_CONTENT_LENGTH", 5 * 1024 * 1024) / (1024 * 1024)
        return _render_erro(
            413, "bi-file-earmark-x",
            "Arquivo muito grande",
            f"O arquivo enviado excede o limite máximo permitido ({limite_mb:.0f} MB). "
            "Reduza o tamanho do arquivo e tente novamente.",
        )

    @app.errorhandler(429)
    def erro_429(e):
        return _render_erro(
            429, "bi-hourglass-split",
            "Muitas requisições",
            "Você fez muitas requisições em pouco tempo. Aguarde um instante e tente novamente.",
        )

    @app.errorhandler(500)
    def erro_500(e):
        app.logger.exception("Erro interno não tratado.")
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass
        return _render_erro(
            500, "bi-tools",
            "Erro interno do servidor",
            "Ocorreu um erro inesperado ao processar sua solicitação. "
            "Tente novamente em alguns instantes.",
        )

    @app.errorhandler(HTTPException)
    def erro_http_generico(e):
        # Captura qualquer outro código HTTP não tratado explicitamente acima,
        # para nunca expor a página padrão do Werkzeug.
        return _render_erro(
            e.code or 500, "bi-exclamation-circle",
            e.name or "Erro",
            e.description or "Ocorreu um erro ao processar sua solicitação.",
        )

    @app.errorhandler(Exception)
    def erro_nao_tratado(e):
        # Última linha de defesa: qualquer exceção Python não capturada em
        # nenhuma rota (bug, falha de conexão com o banco, etc.) cai aqui em
        # vez de derrubar a resposta com um traceback bruto para o usuário.
        if isinstance(e, HTTPException):
            return erro_http_generico(e)
        app.logger.exception("Exceção não tratada.")
        try:
            from app import db
            db.session.rollback()
        except Exception:
            pass
        return _render_erro(
            500, "bi-tools",
            "Erro interno do servidor",
            "Ocorreu um erro inesperado ao processar sua solicitação. "
            "Tente novamente em alguns instantes.",
        )
