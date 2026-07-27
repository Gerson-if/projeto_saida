import os
import csv
import io
from datetime import datetime
from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from functools import wraps
from app.models import Registro, Usuario, ConfigSistema
from app import db
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT

reports_bp = Blueprint('reports', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Acesso restrito ao administrador.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def get_saidas_filtradas(data_inicio=None, data_fim=None, usuario_id=None, status=None, busca_exata=None):
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

    if usuario_id:
        usuario = Usuario.query.get(usuario_id)
        if usuario:
            query = query.filter(Registro.cpf_usuario == usuario.cpf)

    if status:
        query = query.filter(Registro.status == status)

    return query.order_by(Registro.data_saida.desc()).all()


def gerar_pdf_relatorio(saidas, titulo="Relatório de Saídas", subtitulo=""):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            rightMargin=1.5*cm, leftMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=1.5*cm)

    styles = getSampleStyleSheet()
    story = []

    # Config do sistema
    nome_sistema = ConfigSistema.get('nome_sistema', 'Sistema de Controle de Saídas')
    organizacao = ConfigSistema.get('organizacao', 'Organização Militar')
    logo_rel = ConfigSistema.get('logo_relatorio')
    brasao = ConfigSistema.get('brasao')
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

    # Cabeçalho com logo
    header_data = []
    logo_cell = []
    brasao_cell = []

    upload_folder = current_app.config['UPLOAD_FOLDER']

    if brasao:
        brasao_path = os.path.join(upload_folder, brasao)
        if os.path.exists(brasao_path):
            try:
                brasao_cell = [Image(brasao_path, width=2.5*cm, height=2.5*cm)]
            except Exception:
                brasao_cell = ['']

    if logo_rel:
        logo_path = os.path.join(upload_folder, logo_rel)
        if os.path.exists(logo_path):
            try:
                logo_cell = [Image(logo_path, width=2.5*cm, height=2.5*cm)]
            except Exception:
                logo_cell = ['']

    titulo_style = ParagraphStyle('TituloRel', fontName='Helvetica-Bold',
                                   fontSize=14, alignment=TA_CENTER, textColor=cor_primaria,
                                   spaceAfter=4)
    sub_style = ParagraphStyle('SubRel', fontName='Helvetica',
                                fontSize=10, alignment=TA_CENTER, textColor=colors.grey)

    centro = [
        Paragraph(organizacao.upper(), ParagraphStyle('Org', fontName='Helvetica-Bold',
                  fontSize=11, alignment=TA_CENTER, textColor=colors.grey)),
        Paragraph(nome_sistema, titulo_style),
        Paragraph(titulo, ParagraphStyle('TitSub', fontName='Helvetica-Bold',
                  fontSize=12, alignment=TA_CENTER, textColor=cor_primaria)),
    ]
    if subtitulo:
        centro.append(Paragraph(subtitulo, sub_style))

    header_table_data = [[brasao_cell or '', centro, logo_cell or '']]
    header_table = Table(header_table_data, colWidths=[3*cm, None, 3*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="100%", thickness=2, color=cor_primaria))
    story.append(Spacer(1, 0.4*cm))

    # Info do relatório
    data_geracao = datetime.now().strftime('%d/%m/%Y às %H:%M')
    info_style = ParagraphStyle('Info', fontName='Helvetica', fontSize=9,
                                 textColor=colors.grey, alignment=TA_LEFT)
    story.append(Paragraph(f'Total de registros: <b>{len(saidas)}</b> | Gerado em: <b>{data_geracao}</b>', info_style))
    story.append(Spacer(1, 0.4*cm))

    # Tabela de dados
    col_style = ParagraphStyle('ColStyle', fontName='Helvetica-Bold', fontSize=8,
                                textColor=colors.white, alignment=TA_CENTER)
    cell_style = ParagraphStyle('CellStyle', fontName='Helvetica', fontSize=8,
                                 alignment=TA_LEFT, wordWrap='LTR')

    headers = ['#', 'Nome', 'CPF', 'Telefone', 'Motivo', 'Local', 'Endereço', 'Saída', 'Retorno', 'Status']
    header_row = [Paragraph(h, col_style) for h in headers]
    data_rows = [header_row]

    for i, saida in enumerate(saidas, 1):
        status_colors = {'pendente': '#f39c12', 'ativo': '#27ae60', 'retornado': '#7f8c8d'}
        st_color = status_colors.get(saida.status, '#333')
        st_style = ParagraphStyle(f'St{i}', fontName='Helvetica-Bold', fontSize=7,
                                   textColor=colors.HexColor(st_color), alignment=TA_CENTER)

        row = [
            Paragraph(str(i), cell_style),
            Paragraph(saida.usuario.nome if saida.usuario else '-', cell_style),
            Paragraph(saida.cpf_usuario or '-', cell_style),
            Paragraph(saida.telefone_contato or '-', cell_style),
            Paragraph((saida.motivo[:50] + '...') if len(saida.motivo) > 50 else saida.motivo, cell_style),
            Paragraph(saida.local or '-', cell_style),
            Paragraph((saida.endereco_destino[:40] + '...') if saida.endereco_destino and len(saida.endereco_destino) > 40 else (saida.endereco_destino or '-'), cell_style),
            Paragraph(saida.data_saida.strftime('%d/%m/%Y') if saida.data_saida else '-', cell_style),
            Paragraph(saida.data_retorno.strftime('%d/%m/%Y') if saida.data_retorno else '-', cell_style),
            Paragraph(saida.status_label, st_style),
        ]
        data_rows.append(row)

    col_widths = [0.8*cm, 3.5*cm, 2.5*cm, 2.5*cm, 4.5*cm, 3*cm, 3.5*cm, 2.2*cm, 2.2*cm, 2*cm]

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
        ('ROWHEIGHT', (0, 0), (-1, -1), 0.7*cm),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    # Rodapé
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 0.2*cm))
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
    usuarios = Usuario.query.order_by(Usuario.nome).all()
    saidas = []
    filtros = {}

    if request.method == 'POST':
        data_inicio = request.form.get('data_inicio', '')
        data_fim = request.form.get('data_fim', '')
        usuario_id = request.form.get('usuario_id') or None
        status = request.form.get('status') or None
        formato = request.form.get('formato', 'visualizar')

        filtros = {'data_inicio': data_inicio, 'data_fim': data_fim,
                   'usuario_id': usuario_id, 'status': status}

        saidas = get_saidas_filtradas(data_inicio=data_inicio, data_fim=data_fim,
                                       usuario_id=usuario_id, status=status)

        subtitulo = f'Período: {datetime.strptime(data_inicio, "%Y-%m-%d").strftime("%d/%m/%Y")} a {datetime.strptime(data_fim, "%Y-%m-%d").strftime("%d/%m/%Y")}' if data_inicio and data_fim else ''

        if formato == 'pdf':
            buffer = gerar_pdf_relatorio(saidas, titulo='Relatório de Saídas por Período', subtitulo=subtitulo)
            return send_file(buffer, as_attachment=True,
                             download_name=f'relatorio_periodo_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf',
                             mimetype='application/pdf')

        elif formato == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['#', 'Nome', 'CPF', 'Telefone', 'Motivo', 'Local', 'Endereço', 'Saída', 'Retorno', 'Status', 'Registro'])
            for i, s in enumerate(saidas, 1):
                writer.writerow([
                    i, s.usuario.nome if s.usuario else '-', s.cpf_usuario,
                    s.telefone_contato or '-', s.motivo, s.local,
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

    return render_template('reports/periodo.html', usuarios=usuarios, saidas=saidas, filtros=filtros)


@reports_bp.route('/data-exata', methods=['GET', 'POST'])
@login_required
@admin_required
def data_exata():
    usuarios = Usuario.query.order_by(Usuario.nome).all()
    saidas = []
    filtros = {}

    if request.method == 'POST':
        data = request.form.get('data_exata', '')
        usuario_id = request.form.get('usuario_id') or None
        status = request.form.get('status') or None
        formato = request.form.get('formato', 'visualizar')

        filtros = {'data_exata': data, 'usuario_id': usuario_id, 'status': status}
        saidas = get_saidas_filtradas(busca_exata=data, usuario_id=usuario_id, status=status)

        subtitulo = f'Data: {datetime.strptime(data, "%Y-%m-%d").strftime("%d/%m/%Y")}' if data else ''

        if formato == 'pdf':
            buffer = gerar_pdf_relatorio(saidas, titulo='Relatório de Saídas por Data', subtitulo=subtitulo)
            return send_file(buffer, as_attachment=True,
                             download_name=f'relatorio_data_{data}.pdf',
                             mimetype='application/pdf')

        elif formato == 'csv':
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['#', 'Nome', 'CPF', 'Telefone', 'Motivo', 'Local', 'Endereço', 'Saída', 'Retorno', 'Status'])
            for i, s in enumerate(saidas, 1):
                writer.writerow([
                    i, s.usuario.nome if s.usuario else '-', s.cpf_usuario,
                    s.telefone_contato or '-', s.motivo, s.local,
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

    return render_template('reports/data_exata.html', usuarios=usuarios, saidas=saidas, filtros=filtros)
