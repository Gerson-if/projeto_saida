"""
routes/reports.py — Geração de relatórios (PDF e CSV).
"""

import csv
import io
import os
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint, current_app, flash, redirect,
    render_template, request, send_file, url_for,
)
from flask_login import current_user, login_required
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from app import db
from app.models import ConfigSistema, Registro, Subunidade, Usuario
from app.validators import parse_int_seguro, validar_data

reports_bp = Blueprint("reports", __name__)

# Categorias de status disponíveis para o relatório
STATUS_OPCOES = [
    ("agendada",    "Agendada"),
    ("em_transito", "Em Trânsito"),
    ("retornado",   "Retornado"),
    ("cancelado",   "Cancelado"),
    ("finalizado",  "Finalizado"),
]
STATUS_VALIDOS = {k for k, _ in STATUS_OPCOES}


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Acesso restrito ao administrador.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────────────────────────────────────
# Filtro de saídas
# ─────────────────────────────────────────────────────────────────────────────

def get_saidas_filtradas(
    data_inicio=None, data_fim=None, usuario_id=None,
    status_list=None, busca_exata=None, subunidade_id=None,
):
    """Retorna registros de saída com base nos filtros fornecidos.
    
    status_list: lista de status para filtrar. None ou lista vazia = todos.
    """
    query = Registro.query.join(Usuario, Registro.cpf_usuario == Usuario.cpf)

    di_dt, _ = validar_data(data_inicio or "", campo="data de início") if data_inicio else (None, [])
    df_dt, _ = validar_data(data_fim or "", campo="data de fim") if data_fim else (None, [])

    if di_dt and df_dt:
        query = query.filter(
            ((Registro.data_saida >= di_dt) & (Registro.data_saida <= df_dt))
            | ((Registro.data_retorno >= di_dt) & (Registro.data_retorno <= df_dt))
            | ((Registro.data_saida <= di_dt) & (Registro.data_retorno >= df_dt))
        )
    elif busca_exata:
        data_exata_dt, _ = validar_data(busca_exata, campo="data exata")
        if data_exata_dt:
            query = query.filter(
                db.func.date(Registro.data_saida) == data_exata_dt.date()
            )

    sub_id_valida = parse_int_seguro(subunidade_id, minimo=1) if subunidade_id else None
    if sub_id_valida is not None:
        query = query.filter(Usuario.subunidade_id == sub_id_valida)

    usuario_id_valido = parse_int_seguro(usuario_id, minimo=1) if usuario_id else None
    if usuario_id_valido is not None:
        usuario = db.session.get(Usuario, usuario_id_valido)
        if usuario:
            query = query.filter(Registro.cpf_usuario == usuario.cpf)

    # Filtro de múltiplos status
    status_filtrados = [s for s in (status_list or []) if s in STATUS_VALIDOS]
    if status_filtrados:
        query = query.filter(Registro.status.in_(status_filtrados))

    return query.order_by(Registro.data_saida.desc()).all()


# ─────────────────────────────────────────────────────────────────────────────
# Geração de PDF
# ─────────────────────────────────────────────────────────────────────────────

def _load_image_safe(filepath: str, max_w_cm: float, max_h_cm: float):
    """Carrega imagem e ajusta proporcionalmente para caber em max_w x max_h."""
    try:
        from PIL import Image as PILImage
        with PILImage.open(filepath) as pil_img:
            orig_w, orig_h = pil_img.size
    except Exception:
        orig_w, orig_h = 1, 1

    max_w = max_w_cm * cm
    max_h = max_h_cm * cm
    ratio = min(max_w / max(orig_w, 1), max_h / max(orig_h, 1), 1.0)
    return Image(filepath, width=orig_w * ratio, height=orig_h * ratio)


def gerar_pdf_relatorio(saidas: list, titulo: str = "Relatório de Saídas", subtitulo: str = ""):
    """Gera e retorna um buffer BytesIO com o PDF do relatório."""
    from xml.sax.saxutils import escape as _xml_escape

    def _p(texto: str, estilo) -> Paragraph:
        return Paragraph(_xml_escape(str(texto or "")), estilo)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        rightMargin=1.5 * cm, leftMargin=1.5 * cm,
        topMargin=1.8 * cm, bottomMargin=1.5 * cm,
    )

    # ── Configurações do sistema ───────────────────────────────────────────
    nome_sistema = ConfigSistema.get("nome_sistema", "Sistema de Controle de Saídas") or "Sistema de Controle de Saídas"
    organizacao  = ConfigSistema.get("organizacao", "Organização Militar") or "Organização Militar"
    logo_rel     = ConfigSistema.get("logo_relatorio")
    brasao       = ConfigSistema.get("brasao")
    rodape_texto = (
        ConfigSistema.get("rodape")
        or f'Documento gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")}'
    )

    cor_hex = (ConfigSistema.get("cor_primaria", "#2c3e50") or "#2c3e50").lstrip("#")
    try:
        cor_primaria = colors.Color(
            int(cor_hex[0:2], 16) / 255,
            int(cor_hex[2:4], 16) / 255,
            int(cor_hex[4:6], 16) / 255,
        )
    except Exception:
        cor_primaria = colors.HexColor("#2c3e50")

    upload_folder = os.path.join(current_app.static_folder, "uploads")

    # ── Imagens do cabeçalho ───────────────────────────────────────────────
    def _img_cell(nome_arquivo: str | None) -> str | Image:
        if not nome_arquivo:
            return ""
        fp = os.path.join(upload_folder, nome_arquivo)
        if not os.path.exists(fp):
            return ""
        try:
            return _load_image_safe(fp, 2.5, 2.0)
        except Exception:
            return ""

    brasao_cell = _img_cell(brasao)
    logo_cell   = _img_cell(logo_rel)

    # ── Estilos de texto ───────────────────────────────────────────────────
    titulo_style = ParagraphStyle(
        "TitRel", fontName="Helvetica-Bold", fontSize=14,
        alignment=TA_CENTER, textColor=cor_primaria, spaceAfter=2,
    )
    sub_style = ParagraphStyle(
        "SubRel", fontName="Helvetica", fontSize=10,
        alignment=TA_CENTER, textColor=colors.grey,
    )
    org_style = ParagraphStyle(
        "Org", fontName="Helvetica-Bold", fontSize=10,
        alignment=TA_CENTER, textColor=colors.grey,
    )

    centro = [
        _p(organizacao.upper(), org_style),
        _p(nome_sistema, titulo_style),
        _p(titulo, ParagraphStyle(
            "TitSub", fontName="Helvetica-Bold", fontSize=11,
            alignment=TA_CENTER, textColor=cor_primaria,
        )),
    ]
    if subtitulo:
        centro.append(_p(subtitulo, sub_style))

    story = []

    header_table = Table(
        [[brasao_cell or "", centro, logo_cell or ""]],
        colWidths=[2.8 * cm, None, 2.8 * cm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",        (0, 0), (0, 0),   "LEFT"),
        ("ALIGN",        (2, 0), (2, 0),   "RIGHT"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.25 * cm))
    story.append(HRFlowable(width="100%", thickness=2, color=cor_primaria))
    story.append(Spacer(1, 0.3 * cm))

    # ── Info de geração ────────────────────────────────────────────────────
    info_style = ParagraphStyle(
        "Info", fontName="Helvetica", fontSize=9,
        textColor=colors.grey, alignment=TA_LEFT,
    )
    story.append(Paragraph(
        f'Total de registros: <b>{len(saidas)}</b> &nbsp;|&nbsp; '
        f'Gerado em: <b>{datetime.now().strftime("%d/%m/%Y às %H:%M")}</b>',
        info_style,
    ))
    story.append(Spacer(1, 0.3 * cm))

    # ── Tabela de dados ────────────────────────────────────────────────────
    col_style  = ParagraphStyle("ColStyle",  fontName="Helvetica-Bold", fontSize=7.5,
                                textColor=colors.white, alignment=TA_CENTER)
    cell_style = ParagraphStyle("CellStyle", fontName="Helvetica", fontSize=7.5,
                                alignment=TA_LEFT, wordWrap="LTR", leading=9)
    ctr_style  = ParagraphStyle("CtrStyle",  fontName="Helvetica", fontSize=7.5,
                                alignment=TA_CENTER, leading=9)

    headers    = ["#", "Nome", "CPF", "Subunidade", "Telefone", "Motivo", "Local", "Saída", "Retorno", "Status"]
    data_rows  = [[_p(h, col_style) for h in headers]]

    STATUS_COLORS = {
        "agendada":    "#b7791f",
        "em_transito": "#1d4ed8",
        "retornado":   "#166534",
        "cancelado":   "#6b7280",
        "finalizado":  "#374151",
    }

    for i, saida in enumerate(saidas, 1):
        st_color = STATUS_COLORS.get(saida.status, "#333333")
        st_style = ParagraphStyle(
            f"St{i}", fontName="Helvetica-Bold", fontSize=7,
            textColor=colors.HexColor(st_color), alignment=TA_CENTER,
        )
        sub_nome = ""
        if saida.usuario and saida.usuario.subunidade:
            sub_nome = saida.usuario.subunidade.sigla or saida.usuario.subunidade.nome

        motivo_txt = saida.motivo or ""
        local_txt  = saida.local or ""
        data_rows.append([
            _p(str(i), ctr_style),
            _p(saida.usuario.nome if saida.usuario else "-", cell_style),
            _p(saida.cpf_usuario or "-", ctr_style),
            _p(sub_nome or "-", ctr_style),
            _p(saida.telefone_contato or "-", ctr_style),
            _p((motivo_txt[:55] + "…") if len(motivo_txt) > 55 else motivo_txt, cell_style),
            _p((local_txt[:40] + "…") if len(local_txt) > 40 else local_txt, cell_style),
            _p(saida.data_saida.strftime("%d/%m/%Y") if saida.data_saida else "-", ctr_style),
            _p(saida.data_retorno.strftime("%d/%m/%Y") if saida.data_retorno else "-", ctr_style),
            _p(saida.status_label, st_style),
        ])

    col_widths = [0.7*cm, 3.3*cm, 2.3*cm, 1.8*cm, 2.3*cm, 4.5*cm, 3.0*cm, 2.0*cm, 2.0*cm, 1.9*cm]
    table = Table(data_rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  cor_primaria),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  8),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#dee2e6")),
        ("ROWHEIGHT",     (0, 0), (-1, -1), 0.65 * cm),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    # ── Rodapé ────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 0.15 * cm))
    rodape_style = ParagraphStyle(
        "Rodape", fontName="Helvetica", fontSize=8,
        textColor=colors.grey, alignment=TA_CENTER,
    )
    story.append(_p(rodape_texto, rodape_style))

    doc.build(story)
    buffer.seek(0)
    return buffer


def _escrever_csv(saidas: list) -> bytes:
    """Gera CSV de saídas e retorna como bytes UTF-8-sig."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "#", "Nome", "CPF", "Subunidade", "Telefone",
        "Motivo", "Local", "Endereço", "Saída", "Retorno", "Status", "Registro",
    ])
    for i, s in enumerate(saidas, 1):
        sub_nome = (
            (s.usuario.subunidade.sigla or s.usuario.subunidade.nome)
            if s.usuario and s.usuario.subunidade
            else "-"
        )
        writer.writerow([
            i,
            s.usuario.nome if s.usuario else "-",
            s.cpf_usuario,
            sub_nome,
            s.telefone_contato or "-",
            s.motivo,
            s.local,
            s.endereco_destino or "-",
            s.data_saida.strftime("%d/%m/%Y") if s.data_saida else "-",
            s.data_retorno.strftime("%d/%m/%Y") if s.data_retorno else "-",
            s.status_label,
            s.data_registro.strftime("%d/%m/%Y %H:%M") if s.data_registro else "-",
        ])
    output.seek(0)
    return output.getvalue().encode("utf-8-sig")


def _parse_status_list(form) -> list:
    """Extrai lista de status selecionados do formulário.
    
    Retorna lista vazia se 'todos' estiver selecionado ou nenhum selecionado.
    """
    if form.get("status_todos") == "1":
        return []
    status_list = form.getlist("status[]")
    return [s for s in status_list if s in STATUS_VALIDOS]


def _status_label_resumido(status_list: list) -> str:
    """Retorna texto resumido dos status selecionados para o subtítulo."""
    if not status_list:
        return "Todos os status"
    labels = {k: v for k, v in STATUS_OPCOES}
    nomes = [labels.get(s, s) for s in status_list]
    if len(nomes) == 1:
        return f"Status: {nomes[0]}"
    return f"Status: {', '.join(nomes)}"


# ─────────────────────────────────────────────────────────────────────────────
# Rotas
# ─────────────────────────────────────────────────────────────────────────────

@reports_bp.route("/")
@login_required
@admin_required
def index():
    usuarios = Usuario.query.filter_by(tipo="usuario").order_by(Usuario.nome).all()
    return render_template("reports/index.html", usuarios=usuarios)


@reports_bp.route("/periodo", methods=["GET", "POST"])
@login_required
@admin_required
def por_periodo():
    usuarios    = Usuario.query.order_by(Usuario.nome).all()
    subunidades = Subunidade.query.filter_by(ativa=True).order_by(Subunidade.nome).all()
    saidas      = []
    filtros     = {}

    if request.method == "POST":
        data_inicio   = request.form.get("data_inicio", "")
        data_fim      = request.form.get("data_fim", "")
        usuario_id    = request.form.get("usuario_id") or None
        subunidade_id = request.form.get("subunidade_id") or None
        formato       = request.form.get("formato", "visualizar")
        status_list   = _parse_status_list(request.form)

        filtros = {
            "data_inicio": data_inicio, "data_fim": data_fim,
            "usuario_id": usuario_id,
            "subunidade_id": subunidade_id,
            "status_list": status_list,
            "status_todos": request.form.get("status_todos", "1"),
        }

        data_inicio_dt, erros_di = validar_data(data_inicio, campo="data de início") if data_inicio else (None, [])
        data_fim_dt,   erros_df  = validar_data(data_fim, campo="data de fim") if data_fim else (None, [])

        if erros_di or erros_df:
            for e in (*erros_di, *erros_df):
                flash(e, "danger")
            return render_template(
                "reports/periodo.html",
                usuarios=usuarios, subunidades=subunidades,
                saidas=saidas, filtros=filtros,
                status_opcoes=STATUS_OPCOES,
            )

        saidas = get_saidas_filtradas(
            data_inicio=data_inicio, data_fim=data_fim,
            usuario_id=usuario_id, status_list=status_list,
            subunidade_id=subunidade_id,
        )

        partes = []
        if data_inicio_dt and data_fim_dt:
            partes.append(
                f'Período: {data_inicio_dt.strftime("%d/%m/%Y")} a {data_fim_dt.strftime("%d/%m/%Y")}'
            )
        sub_id_valida = parse_int_seguro(subunidade_id, minimo=1) if subunidade_id else None
        if sub_id_valida:
            sub = db.session.get(Subunidade, sub_id_valida)
            if sub:
                partes.append(f"Subunidade: {sub.sigla or sub.nome}")
        partes.append(_status_label_resumido(status_list))
        subtitulo = " | ".join(partes)

        ts = datetime.now().strftime("%Y%m%d_%H%M")
        if formato == "pdf":
            buffer = gerar_pdf_relatorio(saidas, titulo="Relatório de Saídas por Período", subtitulo=subtitulo)
            return send_file(
                buffer, as_attachment=True,
                download_name=f"relatorio_periodo_{ts}.pdf",
                mimetype="application/pdf",
            )
        elif formato == "csv":
            return send_file(
                io.BytesIO(_escrever_csv(saidas)), as_attachment=True,
                download_name=f"relatorio_periodo_{ts}.csv",
                mimetype="text/csv",
            )

    return render_template(
        "reports/periodo.html",
        usuarios=usuarios, subunidades=subunidades,
        saidas=saidas, filtros=filtros,
        status_opcoes=STATUS_OPCOES,
    )


@reports_bp.route("/data-exata", methods=["GET", "POST"])
@login_required
@admin_required
def data_exata():
    usuarios    = Usuario.query.order_by(Usuario.nome).all()
    subunidades = Subunidade.query.filter_by(ativa=True).order_by(Subunidade.nome).all()
    saidas      = []
    filtros     = {}

    if request.method == "POST":
        data          = request.form.get("data_exata", "")
        usuario_id    = request.form.get("usuario_id") or None
        subunidade_id = request.form.get("subunidade_id") or None
        formato       = request.form.get("formato", "visualizar")
        status_list   = _parse_status_list(request.form)

        filtros = {
            "data_exata": data, "usuario_id": usuario_id,
            "subunidade_id": subunidade_id,
            "status_list": status_list,
            "status_todos": request.form.get("status_todos", "1"),
        }

        data_dt, erros_data = validar_data(data, campo="data") if data else (None, [])
        if erros_data:
            for e in erros_data:
                flash(e, "danger")
            return render_template(
                "reports/data_exata.html",
                usuarios=usuarios, subunidades=subunidades,
                saidas=saidas, filtros=filtros,
                status_opcoes=STATUS_OPCOES,
            )

        saidas = get_saidas_filtradas(
            busca_exata=data, usuario_id=usuario_id,
            status_list=status_list, subunidade_id=subunidade_id,
        )

        data_arquivo = data_dt.strftime("%Y%m%d") if data_dt else datetime.now().strftime("%Y%m%d")

        partes = []
        if data_dt:
            partes.append(f'Data: {data_dt.strftime("%d/%m/%Y")}')
        sub_id_valida = parse_int_seguro(subunidade_id, minimo=1) if subunidade_id else None
        if sub_id_valida:
            sub = db.session.get(Subunidade, sub_id_valida)
            if sub:
                partes.append(f"Subunidade: {sub.sigla or sub.nome}")
        partes.append(_status_label_resumido(status_list))
        subtitulo = " | ".join(partes)

        if formato == "pdf":
            buffer = gerar_pdf_relatorio(saidas, titulo="Relatório de Saídas por Data", subtitulo=subtitulo)
            return send_file(
                buffer, as_attachment=True,
                download_name=f"relatorio_data_{data_arquivo}.pdf",
                mimetype="application/pdf",
            )
        elif formato == "csv":
            return send_file(
                io.BytesIO(_escrever_csv(saidas)), as_attachment=True,
                download_name=f"relatorio_data_{data_arquivo}.csv",
                mimetype="text/csv",
            )

    return render_template(
        "reports/data_exata.html",
        usuarios=usuarios, subunidades=subunidades,
        saidas=saidas, filtros=filtros,
        status_opcoes=STATUS_OPCOES,
    )
