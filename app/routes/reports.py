import os
import csv
import io
from datetime import datetime
from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from functools import wraps
from app.models import Registro, Usuario, ConfigSistema, Subunidade
from app import db
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

reports_bp = Blueprint('reports', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Acesso restrito ao administrador.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def get_saidas_filtradas(data_inicio=None, data_fim=None, usuario_id=None,
                          status=None, busca_exata=None, subunidade_id=None):
    query = Registro.query.join(Usuario, Registro.cpf_usuario == Usuario.cpf)

    if data_inicio and data_fim:
        di = datetime.strptime(data_inicio, '%Y-%m-%d')
        df = datetime.strptime(data_fim, '%Y-%m-%d')
        query = query.filter(
            ((Registro.data_saida >= di) & (Registro.data_saida <= df)) |
            ((Registro.data_retorno >= di) & (Registro.data_retorno <= df)) |
            ((Registro.data_saida <= di) & (Registro.data_retorno >= df))
        )
    elif busca_exata:
        data_exata = datetime.strptime(busca_exata, '%Y-%m-%d')
        query = query.filter(
            db.func.date(Registro.data_saida) == data_exata.date()
        )

    if subunidade_id:
        query = query.filter(Usuario.subunidade_id == int(subunidade_id))

    if usuario_id:
        usuario = Usuario.query.get(usuario_id)
        if usuario:
            query = query.filter(Registro.cpf_usuario == usuario.cpf)

    if status:
        query = query.filter(Registro.status == status)

    return query.order_by(Registro.data_saida.desc()).all()


def _load_image_safe(filepath, max_w_cm, max_h_cm):
    """Carrega imagem e ajusta para caber em max_w x max_h sem distorcer."""
    try:
        from PIL import Image as PILImage
        with PILImage.open(filepath) as pil_img:
            orig_w, orig_h = pil_img.size
    except Exception:
        orig_w, orig_h = 1, 1

    max_w = max_w_cm * cm
    max_h = max_h_cm * cm

    # Escala mantendo proporção
    ratio_w = max_w / orig_w if orig_w else 1
    ratio_h = max_h / orig_h if orig_h else 1
    ratio = min(ratio_w, ratio_h, 1.0)   # nunca ampliar

    w = orig_w * ratio
    h = orig_h * ratio
    return Image(filepath, width=w, height=h)


def gerar_pdf_relatorio(saidas, titulo="Relatório de Saídas", subtitulo=""):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=1.8*cm, bottomMargin=1.5*cm)

    story = []

    # Config
    nome_sistema = ConfigSistema.get('nome_sistema', 'Sistema de Controle de Saídas')
    organizacao  = ConfigSistema.get('organizacao', 'Organização Militar')
    logo_rel     = ConfigSistema.get('logo_relatorio')
    brasao       = ConfigSistema.get('brasao')
    rodape_texto = ConfigSistema.get('rodape', f'Documento gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")}')

    # Cor primária
    cor_hex = ConfigSistema.get('cor_primaria', '#2c3e50').lstrip('#')
    try:
        cor_r = int(cor_hex[0:2], 16) / 255
        cor_g = int(cor_hex[2:4], 16) / 255
        cor_b = int(cor_hex[4:6], 16) / 255
        cor_primaria = colors.Color(cor_r, cor_g, cor_b)
    except Exception:
        cor_primaria = colors.HexColor('#2c3e50')

    upload_folder = os.path.join(current_app.static_folder, 'uploads')

    # Imagens do cabeçalho (safe, respeitando proporção)
    brasao_cell = ''
    logo_cell   = ''

    if brasao:
        fp = os.path.join(upload_folder, brasao)
        if os.path.exists(fp):
            try:
                brasao_cell = _load_image_safe(fp, 2.5, 2.0)
            except Exception:
                brasao_cell = ''

    if logo_rel:
        fp = os.path.join(upload_folder, logo_rel)
        if os.path.exists(fp):
            try:
                logo_cell = _load_image_safe(fp, 2.5, 2.0)
            except Exception:
                logo_cell = ''

    titulo_style = ParagraphStyle('TitRel', fontName='Helvetica-Bold',
                                   fontSize=14, alignment=TA_CENTER,
                                   textColor=cor_primaria, spaceAfter=2)
    sub_style    = ParagraphStyle('SubRel', fontName='Helvetica',
                                   fontSize=10, alignment=TA_CENTER, textColor=colors.grey)

    centro = [
        Paragraph(organizacao.upper(), ParagraphStyle('Org', fontName='Helvetica-Bold',
                  fontSize=10, alignment=TA_CENTER, textColor=colors.grey)),
        Paragraph(nome_sistema, titulo_style),
        Paragraph(titulo, ParagraphStyle('TitSub', fontName='Helvetica-Bold',
                  fontSize=11, alignment=TA_CENTER, textColor=cor_primaria)),
    ]
    if subtitulo:
        centro.append(Paragraph(subtitulo, sub_style))

    # Altura fixa da linha de cabeçalho para não distorcer layout
    header_table_data = [[brasao_cell or '', centro, logo_cell or '']]
    header_table = Table(header_table_data, colWidths=[2.8*cm, None, 2.8*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.25*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=cor_primaria))
    story.append(Spacer(1, 0.3*cm))

    # Info
    data_geracao = datetime.now().strftime('%d/%m/%Y às %H:%M')
    info_style = ParagraphStyle('Info', fontName='Helvetica', fontSize=9,
                                 textColor=colors.grey, alignment=TA_LEFT)
    story.append(Paragraph(
        f'Total de registros: <b>{len(saidas)}</b> &nbsp;|&nbsp; Gerado em: <b>{data_geracao}</b>',
        info_style))
    story.append(Spacer(1, 0.3*cm))

    # Tabela
    col_style  = ParagraphStyle('ColStyle',  fontName='Helvetica-Bold', fontSize=7.5,
                                 textColor=colors.white, alignment=TA_CENTER)
    cell_style = ParagraphStyle('CellStyle', fontName='Helvetica', fontSize=7.5,
                                 alignment=TA_LEFT, wordWrap='LTR', leading=9)
    ctr_style  = ParagraphStyle('CtrStyle',  fontName='Helvetica', fontSize=7.5,
                                 alignment=TA_CENTER, leading=9)

    headers    = ['#', 'Nome', 'CPF', 'Subunidade', 'Telefone', 'Motivo', 'Local', 'Saída', 'Retorno', 'Status']
    header_row = [Paragraph(h, col_style) for h in headers]
    data_rows  = [header_row]

    status_colors_map = {
        'agendada': '#b7791f', 'em_transito': '#1d4ed8',
        'retornado': '#166534', 'cancelado': '#6b7280', 'finalizado': '#374151',
    }

    for i, saida in enumerate(saidas, 1):
        st_color = status_colors_map.get(saida.status, '#333333')
        st_style = ParagraphStyle(f'St{i}', fontName='Helvetica-Bold', fontSize=7,
                                   textColor=colors.HexColor(st_color), alignment=TA_CENTER)
        sub_nome = ''
        if saida.usuario and saida.usuario.subunidade:
            sub_nome = saida.usuario.subunidade.sigla or saida.usuario.subunidade.nome

        row = [
            Paragraph(str(i), ctr_style),
            Paragraph(saida.usuario.nome if saida.usuario else '-', cell_style),
            Paragraph(saida.cpf_usuario or '-', ctr_style),
            Paragraph(sub_nome or '-', ctr_style),
            Paragraph(saida.telefone_contato or '-', ctr_style),
            Paragraph((saida.motivo[:55] + '…') if len(saida.motivo) > 55 else saida.motivo, cell_style),
            Paragraph((saida.local[:40] + '…') if len(saida.local) > 40 else saida.local, cell_style),
            Paragraph(saida.data_saida.strftime('%d/%m/%Y') if saida.data_saida else '-', ctr_style),
            Paragraph(saida.data_retorno.strftime('%d/%m/%Y') if saida.data_retorno else '-', ctr_style),
            Paragraph(saida.status_label, st_style),
        ]
        data_rows.append(row)

    # Larguras ajustadas para landscape A4 (~25.5cm utilizável)
    col_widths = [0.7*cm, 3.3*cm, 2.3*cm, 1.8*cm, 2.3*cm, 4.5*cm, 3.0*cm, 2.0*cm, 2.0*cm, 1.9*cm]

    table = Table(data_rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), cor_primaria),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#dee2e6')),
        ('ROWHEIGHT', (0, 0), (-1, -1), 0.65*cm),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    # Rodapé
    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 0.15*cm))
    rodape_style = ParagraphStyle('Rodape', fontName='Helvetica', fontSize=8,
                                   textColor=colors.grey, alignment=TA_CENTER)
    story.append(Paragraph(rodape_texto, rodape_style))

    doc.build(story)
    buffer.seek(0)
    return buffer


@reports_bp.route('/')
@login_required
@admin_required
def index():
    usuarios = Usuario.query.filter_by(tipo='usuario').order_by(Usuario.nome).all()
    return render_template('reports/index.html', usuarios=usuarios)


@reports_bp.route('/periodo', methods=['GET', 'POST'])
@login_required
@admin_required
def por_periodo():
    usuarios    = Usuario.query.order_by(Usuario.nome).all()
    subunidades = Subunidade.query.filter_by(ativa=True).order_by(Subunidade.nome).all()
    saidas      = []
    filtros     = {}

    if request.method == 'POST':
        data_inicio   = request.form.get('data_inicio', '')
        data_fim      = request.form.get('data_fim', '')
        usuario_id    = request.form.get('usuario_id') or None
        status        = request.form.get('status') or None
        subunidade_id = request.form.get('subunidade_id') or None
        formato       = request.form.get('formato', 'visualizar')

        filtros = {
            'data_inicio': data_inicio, 'data_fim': data_fim,
            'usuario_id': usuario_id, 'status': status,
            'subunidade_id': subunidade_id,
        }

        saidas = get_saidas_filtradas(
            data_inicio=data_inicio, data_fim=data_fim,
            usuario_id=usuario_id, status=status,
            subunidade_id=subunidade_id
        )

        partes = []
        if data_inicio and data_fim:
            partes.append(f'Período: {datetime.strptime(data_inicio, "%Y-%m-%d").strftime("%d/%m/%Y")} a {datetime.strptime(data_fim, "%Y-%m-%d").strftime("%d/%m/%Y")}')
        if subunidade_id:
            sub = Subunidade.query.get(subunidade_id)
            if sub:
                partes.append(f'Subunidade: {sub.sigla or sub.nome}')
        subtitulo = ' | '.join(partes)

        if formato == 'pdf':
            buffer = gerar_pdf_relatorio(saidas, titulo='Relatório de Saídas por Período', subtitulo=subtitulo)
            return send_file(buffer, as_attachment=True,
                             download_name=f'relatorio_periodo_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf',
                             mimetype='application/pdf')

        elif formato == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['#', 'Nome', 'CPF', 'Subunidade', 'Telefone', 'Motivo', 'Local', 'Endereço', 'Saída', 'Retorno', 'Status', 'Registro'])
            for i, s in enumerate(saidas, 1):
                sub_nome = (s.usuario.subunidade.sigla or s.usuario.subunidade.nome) if s.usuario and s.usuario.subunidade else '-'
                writer.writerow([
                    i, s.usuario.nome if s.usuario else '-', s.cpf_usuario,
                    sub_nome, s.telefone_contato or '-', s.motivo, s.local,
                    s.endereco_destino or '-',
                    s.data_saida.strftime('%d/%m/%Y') if s.data_saida else '-',
                    s.data_retorno.strftime('%d/%m/%Y') if s.data_retorno else '-',
                    s.status_label,
                    s.data_registro.strftime('%d/%m/%Y %H:%M') if s.data_registro else '-'
                ])
            output.seek(0)
            return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')),
                             as_attachment=True,
                             download_name=f'relatorio_periodo_{datetime.now().strftime("%Y%m%d_%H%M")}.csv',
                             mimetype='text/csv')

    return render_template('reports/periodo.html',
                           usuarios=usuarios, subunidades=subunidades,
                           saidas=saidas, filtros=filtros)


@reports_bp.route('/data-exata', methods=['GET', 'POST'])
@login_required
@admin_required
def data_exata():
    usuarios    = Usuario.query.order_by(Usuario.nome).all()
    subunidades = Subunidade.query.filter_by(ativa=True).order_by(Subunidade.nome).all()
    saidas      = []
    filtros     = {}

    if request.method == 'POST':
        data          = request.form.get('data_exata', '')
        usuario_id    = request.form.get('usuario_id') or None
        status        = request.form.get('status') or None
        subunidade_id = request.form.get('subunidade_id') or None
        formato       = request.form.get('formato', 'visualizar')

        filtros = {'data_exata': data, 'usuario_id': usuario_id, 'status': status, 'subunidade_id': subunidade_id}
        saidas  = get_saidas_filtradas(busca_exata=data, usuario_id=usuario_id, status=status, subunidade_id=subunidade_id)

        partes = []
        if data:
            partes.append(f'Data: {datetime.strptime(data, "%Y-%m-%d").strftime("%d/%m/%Y")}')
        if subunidade_id:
            sub = Subunidade.query.get(subunidade_id)
            if sub:
                partes.append(f'Subunidade: {sub.sigla or sub.nome}')
        subtitulo = ' | '.join(partes)

        if formato == 'pdf':
            buffer = gerar_pdf_relatorio(saidas, titulo='Relatório de Saídas por Data', subtitulo=subtitulo)
            return send_file(buffer, as_attachment=True,
                             download_name=f'relatorio_data_{data}.pdf',
                             mimetype='application/pdf')

        elif formato == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['#', 'Nome', 'CPF', 'Subunidade', 'Telefone', 'Motivo', 'Local', 'Endereço', 'Saída', 'Retorno', 'Status'])
            for i, s in enumerate(saidas, 1):
                sub_nome = (s.usuario.subunidade.sigla or s.usuario.subunidade.nome) if s.usuario and s.usuario.subunidade else '-'
                writer.writerow([
                    i, s.usuario.nome if s.usuario else '-', s.cpf_usuario,
                    sub_nome, s.telefone_contato or '-', s.motivo, s.local,
                    s.endereco_destino or '-',
                    s.data_saida.strftime('%d/%m/%Y') if s.data_saida else '-',
                    s.data_retorno.strftime('%d/%m/%Y') if s.data_retorno else '-',
                    s.status_label,
                ])
            output.seek(0)
            return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')),
                             as_attachment=True,
                             download_name=f'relatorio_data_{data}.csv',
                             mimetype='text/csv')

    return render_template('reports/data_exata.html',
                           usuarios=usuarios, subunidades=subunidades,
                           saidas=saidas, filtros=filtros)
