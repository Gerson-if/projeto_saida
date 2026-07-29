"""
app/uploads.py — Validação, otimização e gravação segura de uploads de mídia.

Por que não basta checar a extensão do arquivo
-----------------------------------------------
`secure_filename()` + checar `arquivo.png` no nome NÃO garante que o
conteúdo do arquivo seja realmente uma imagem. Qualquer pessoa pode
renomear um arquivo qualquer (executável, script, HTML com JS, etc.)
para terminar em `.png` e o servidor aceitaria sem perceber.

Este módulo abre o arquivo recebido com a biblioteca Pillow e verifica:
  1. Se o conteúdo é de fato uma imagem decodificável (Pillow.verify()).
  2. Se o formato real do arquivo está na lista de formatos permitidos
     (comparando o formato detectado pela biblioteca, não a extensão).
  3. Se as dimensões (largura x altura) estão dentro de um limite máximo
     razoável, para evitar "bombas de descompressão" (imagens com poucos
     KB mas dimensões gigantescas que consomem memória ao serem abertas).
     Esse limite é checado ANTES de qualquer operação que decodifique os
     pixels (rotação/redimensionamento), porque só ler o cabeçalho da
     imagem (via `img.size`) é uma operação barata — decodificar pixels de
     uma imagem gigante não é.
  4. Se o tamanho do arquivo em bytes está dentro do limite configurado.

Se tudo estiver certo, a imagem é regravada em disco a partir dos dados
decodificados pelo Pillow (re-encode), o que automaticamente descarta
qualquer metadado/payload malicioso que não seja parte da imagem em si.

Otimização automática de imagens
---------------------------------
Fotos tiradas com celular hoje em dia chegam facilmente a 4000-6000px de
largura e vários MB — perfeitamente válidas, mas desnecessariamente
pesadas para serem exibidas num avatar de 40px ou num logotipo de
relatório. Por isso, além de validar, este módulo:
  - Corrige a rotação da imagem conforme o metadado EXIF de orientação
    (comum em fotos de celular) ANTES de descartar os metadados — sem
    isso, fotos tiradas "de lado" apareceriam giradas incorretamente no
    sistema, já que o re-encode joga fora o EXIF original.
  - Redimensiona (nunca amplia) a imagem para caber numa caixa máxima
    razoável, preservando a proporção, antes de salvar.
  - Salva com compressão otimizada (JPEG/PNG `optimize=True`).
Isso reduz drasticamente o espaço em disco e o tempo de carregamento das
páginas, sem exigir nenhuma ação do usuário.

Upload de vídeo (fundo animado da tela de login)
--------------------------------------------------
Vídeo não pode ser validado com Pillow. A checagem de conteúdo aqui é:
tamanho do arquivo + assinatura binária ("magic bytes") do formato real,
para reduzir o risco de alguém enviar um arquivo qualquer apenas
renomeado para .mp4/.webm.

Se o binário `ffmpeg` estiver disponível no servidor, o vídeo validado é
automaticamente recomprimido (resolução reduzida, H.264/AAC, bitrate
controlado) antes de ser salvo — isso é o que realmente evita que um
vídeo "cru" de várias dezenas de MB pese no servidor e no carregamento da
tela de login. Se `ffmpeg` não estiver instalado (ou a otimização falhar
por qualquer motivo: timeout, arquivo problemático, etc.), o vídeo
validado é salvo do jeito que foi enviado — a aplicação NUNCA falha o
upload por causa da etapa de otimização, ela é sempre "best effort".
`deploy/install.sh` já instala `ffmpeg` automaticamente em produção.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from typing import Optional

from werkzeug.datastructures import FileStorage

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:  # Pillow é dependência obrigatória (ver requirements.txt)
    Image = None
    ImageOps = None
    UnidentifiedImageError = Exception


# Formatos aceitos: nome interno do Pillow -> extensão de arquivo a salvar.
FORMATOS_ACEITOS = {
    "PNG": "png",
    "JPEG": "jpg",
    "GIF": "gif",
    "WEBP": "webp",
    "ICO": "ico",
}

# Tamanho máximo de arquivo (bytes) — também reforçado por MAX_CONTENT_LENGTH
# no Flask, mas validado aqui de novo para gerar uma mensagem amigável em vez
# de um erro genérico 413. 10 MB comporta fotos de celular modernas em alta
# resolução (uma foto de 12-48MP em JPEG normalmente fica entre 3-9MB) — o
# limite antigo de 5MB rejeitava desnecessariamente fotos legítimas.
TAMANHO_MAXIMO_BYTES = 10 * 1024 * 1024  # 10 MB

# Dimensões máximas ACEITAS na entrada (pixels) — checadas antes de qualquer
# decodificação de pixels, para servir de defesa contra "bombas de
# descompressão". 8000x8000 (64 milhões de pixels) cobre confortavelmente
# até as câmeras de celular mais alta resolução do mercado, e ainda fica bem
# abaixo do limite padrão de segurança do Pillow (Image.MAX_IMAGE_PIXELS,
# ~178 milhões de pixels).
LARGURA_MAXIMA_PX = 8000
ALTURA_MAXIMA_PX = 8000

# Dimensões mínimas (evita arquivos de 1x1 px usados para "passar" a validação).
LARGURA_MINIMA_PX = 8
ALTURA_MINIMA_PX = 8

# Caixa máxima de ARMAZENAMENTO (pixels) — depois de validada, a imagem é
# redimensionada (nunca ampliada) para caber nesta caixa, preservando a
# proporção. É isso que mantém o servidor leve: uma foto de 6000x4000px
# enviada pelo usuário é validada contra o limite acima, mas armazenada a
# no máximo 1920x1920px.
LARGURA_ALVO_OTIMIZACAO_PX = 1920
ALTURA_ALVO_OTIMIZACAO_PX = 1920


@dataclass
class ResultadoUpload:
    ok: bool
    nome_arquivo: Optional[str] = None
    erro: Optional[str] = None


def _tamanho_arquivo(file_storage: FileStorage) -> int:
    stream = file_storage.stream
    pos_atual = stream.tell()
    stream.seek(0, os.SEEK_END)
    tamanho = stream.tell()
    stream.seek(pos_atual)
    return tamanho


def _remover_arquivo_silencioso(caminho: Optional[str]) -> None:
    """Remove um arquivo temporário/intermediário, ignorando erros (ex.:
    arquivo já removido, sem permissão) — usado em limpeza best-effort."""
    if not caminho:
        return
    try:
        if os.path.isfile(caminho):
            os.remove(caminho)
    except OSError:
        pass


def validar_e_salvar_imagem(
    file_storage: Optional[FileStorage],
    *,
    destino_dir: str,
    prefixo: str,
    tamanho_maximo_bytes: int = TAMANHO_MAXIMO_BYTES,
    largura_maxima: int = LARGURA_MAXIMA_PX,
    altura_maxima: int = ALTURA_MAXIMA_PX,
    largura_alvo: int = LARGURA_ALVO_OTIMIZACAO_PX,
    altura_alvo: int = ALTURA_ALVO_OTIMIZACAO_PX,
) -> ResultadoUpload:
    """
    Valida o conteúdo real de `file_storage` como imagem e, se válido,
    otimiza (rotação EXIF + redimensionamento + compressão) e salva em
    `destino_dir` com um nome de arquivo seguro e único.

    Retorna ResultadoUpload(ok=True, nome_arquivo=...) em caso de sucesso,
    ou ResultadoUpload(ok=False, erro="mensagem amigável") caso contrário.

    Se nenhum arquivo foi enviado (campo vazio), retorna ok=True com
    nome_arquivo=None — isso permite que a rota trate "sem upload" como
    "manter o que já existia", sem confundir com um erro de validação.
    """
    if file_storage is None or not file_storage.filename:
        return ResultadoUpload(ok=True, nome_arquivo=None)

    if Image is None:
        return ResultadoUpload(
            ok=False,
            erro="Não foi possível processar imagens neste servidor (Pillow não instalado).",
        )

    # 1) Tamanho em bytes.
    tamanho = _tamanho_arquivo(file_storage)
    if tamanho <= 0:
        return ResultadoUpload(ok=False, erro="O arquivo enviado está vazio.")
    if tamanho > tamanho_maximo_bytes:
        limite_mb = tamanho_maximo_bytes / (1024 * 1024)
        return ResultadoUpload(
            ok=False,
            erro=f"A imagem excede o tamanho máximo permitido ({limite_mb:.0f} MB).",
        )

    # 2) Conteúdo é realmente uma imagem decodificável?
    try:
        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as img:
            img.verify()  # valida integridade sem decodificar pixels
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return ResultadoUpload(
            ok=False,
            erro="O arquivo enviado não é uma imagem válida (PNG, JPG, GIF ou WEBP).",
        )

    # img.verify() invalida o objeto para uso posterior — reabrimos para
    # checar formato e dimensões antes de decodificar/regravar em disco.
    try:
        file_storage.stream.seek(0)
        with Image.open(file_storage.stream) as img:
            formato = (img.format or "").upper()
            largura, altura = img.size

            if formato not in FORMATOS_ACEITOS:
                return ResultadoUpload(
                    ok=False,
                    erro="Formato de imagem não suportado. Use PNG, JPG, GIF ou WEBP.",
                )

            if largura < LARGURA_MINIMA_PX or altura < ALTURA_MINIMA_PX:
                return ResultadoUpload(
                    ok=False,
                    erro="A imagem é muito pequena. Envie um arquivo com dimensões maiores.",
                )

            # Checagem de dimensões ANTES de qualquer decodificação de
            # pixels (exif_transpose/thumbnail/save decodificam) — é essa
            # ordem que realmente protege contra "bombas de descompressão"
            # (arquivo pequeno em bytes, mas com dimensões enormes no
            # cabeçalho, que consumiriam memória excessiva ao decodificar).
            if largura > largura_maxima or altura > altura_maxima:
                return ResultadoUpload(
                    ok=False,
                    erro=(
                        f"A imagem excede as dimensões máximas permitidas "
                        f"({largura_maxima}x{altura_maxima}px). Redimensione e tente novamente."
                    ),
                )

            # Corrige a rotação conforme o metadado EXIF (comum em fotos de
            # celular) ANTES de descartar os metadados no re-encode —
            # sem isso, a foto reapareceria "deitada" para quem a visse
            # depois, já que o re-encode joga fora o EXIF original.
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                # Falha ao ler EXIF não deve impedir o upload — segue com
                # a imagem como veio.
                pass

            # Redimensiona (nunca amplia) para a caixa alvo de armazenamento
            # — é isso que garante que uploads pesados (fotos de celular em
            # alta resolução) não fiquem pesando o disco/carregamento do
            # servidor. thumbnail() preserva a proporção automaticamente e
            # não faz nada se a imagem já for menor que o alvo.
            img.thumbnail((largura_alvo, altura_alvo), Image.LANCZOS)
            largura, altura = img.size

            extensao = FORMATOS_ACEITOS[formato]

            # Normaliza modo de cor problemático antes de salvar (ex.:
            # paletas com transparência em JPEG, que não suporta canal alpha).
            if extensao == "jpg" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            os.makedirs(destino_dir, exist_ok=True)
            nome_final = f"{prefixo}_{uuid.uuid4().hex[:12]}.{extensao}"
            caminho_final = os.path.join(destino_dir, nome_final)

            # Regrava a imagem a partir dos pixels decodificados pelo Pillow:
            # isso descarta qualquer payload extra que não faça parte da
            # imagem (ex.: scripts embutidos em metadados) e garante que o
            # arquivo no disco corresponda exatamente ao formato detectado,
            # já otimizado (redimensionado + comprimido).
            if extensao == "jpg":
                img.save(caminho_final, format="JPEG", quality=85, optimize=True, progressive=True)
            elif extensao == "png":
                img.save(caminho_final, format="PNG", optimize=True)
            elif extensao == "ico":
                img.save(caminho_final, format="ICO", sizes=[(min(largura, 256), min(altura, 256))])
            else:
                img.save(caminho_final, format=formato)

    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, MemoryError):
        return ResultadoUpload(
            ok=False,
            erro="Não foi possível processar a imagem enviada. Tente outro arquivo.",
        )

    return ResultadoUpload(ok=True, nome_arquivo=nome_final)


# ─────────────────────────────────────────────────────────────────────────────
# Upload de vídeo (fundo animado da tela de login)
# ─────────────────────────────────────────────────────────────────────────────

TAMANHO_MAXIMO_VIDEO_BYTES = 20 * 1024 * 1024  # 20 MB — suficiente para um clipe curto

# (assinatura, extensão) — a extensão salva vem da assinatura detectada,
# nunca do nome enviado pelo usuário.
_ASSINATURAS_VIDEO = [
    (b"\x1a\x45\xdf\xa3", "webm"),   # WebM/Matroska (EBML header)
    (b"OggS", "ogg"),                 # Ogg
]

# ── Otimização automática via ffmpeg (opcional, best-effort) ────────────────
# Tempo máximo para a recompressão. Fica abaixo do timeout do Gunicorn
# (60s, ver deploy/gunicorn_conf.py) com margem confortável — se a
# otimização demorar mais que isso (VM lenta, arquivo grande), é
# interrompida e o vídeo original validado é salvo sem recompressão, em vez
# de arriscar o worker ser derrubado pelo timeout do servidor de aplicação.
_FFMPEG_TIMEOUT_SEGUNDOS = 45
_VIDEO_LARGURA_MAXIMA_OTIMIZADA = 1280
_VIDEO_CRF = 28
_VIDEO_AUDIO_BITRATE = "96k"


def _detectar_formato_video(cabecalho: bytes) -> Optional[str]:
    for assinatura, extensao in _ASSINATURAS_VIDEO:
        if cabecalho.startswith(assinatura):
            return extensao
    # MP4/MOV: caixa "ftyp" aparece a partir do byte 4, não no início do arquivo.
    if len(cabecalho) >= 12 and cabecalho[4:8] == b"ftyp":
        return "mp4"
    return None


def _ffmpeg_disponivel() -> bool:
    return shutil.which("ffmpeg") is not None


def _otimizar_video_com_ffmpeg(caminho_origem: str, caminho_destino: str) -> bool:
    """
    Tenta recomprimir o vídeo (resolução reduzida, H.264 + AAC, bitrate
    controlado) usando `ffmpeg`, se disponível no servidor.

    Retorna True se a otimização foi bem-sucedida e gerou um arquivo válido
    e não-vazio. NUNCA lança exceção: qualquer problema (ffmpeg ausente,
    timeout, arquivo corrompido/incomum) apenas retorna False — a
    aplicação nunca quebra por causa desta etapa, que é sempre opcional.
    """
    if not _ffmpeg_disponivel():
        return False
    try:
        resultado = subprocess.run(
            [
                "ffmpeg", "-y", "-i", caminho_origem,
                "-vf", f"scale='min({_VIDEO_LARGURA_MAXIMA_OTIMIZADA},iw)':-2",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", str(_VIDEO_CRF),
                "-c:a", "aac", "-b:a", _VIDEO_AUDIO_BITRATE,
                "-movflags", "+faststart",
                caminho_destino,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=_FFMPEG_TIMEOUT_SEGUNDOS,
            check=False,
        )
        return (
            resultado.returncode == 0
            and os.path.isfile(caminho_destino)
            and os.path.getsize(caminho_destino) > 0
        )
    except (subprocess.TimeoutExpired, OSError):
        return False


def validar_e_salvar_video(
    file_storage: Optional[FileStorage],
    *,
    destino_dir: str,
    prefixo: str,
    tamanho_maximo_bytes: int = TAMANHO_MAXIMO_VIDEO_BYTES,
) -> ResultadoUpload:
    """
    Valida (por tamanho e assinatura binária) um upload de vídeo curto
    usado como plano de fundo da tela de login e, se possível, recomprime
    automaticamente com `ffmpeg` antes de salvar (ver `_otimizar_video_com_ffmpeg`).

    Segue o mesmo contrato de `validar_e_salvar_imagem`: se nenhum arquivo
    foi enviado, retorna ok=True com nome_arquivo=None (mantém o valor
    anterior); em caso de conteúdo inválido, retorna ok=False com uma
    mensagem amigável.
    """
    if file_storage is None or not file_storage.filename:
        return ResultadoUpload(ok=True, nome_arquivo=None)

    tamanho = _tamanho_arquivo(file_storage)
    if tamanho <= 0:
        return ResultadoUpload(ok=False, erro="O arquivo enviado está vazio.")
    if tamanho > tamanho_maximo_bytes:
        limite_mb = tamanho_maximo_bytes / (1024 * 1024)
        return ResultadoUpload(
            ok=False,
            erro=f"O vídeo excede o tamanho máximo permitido ({limite_mb:.0f} MB). Use um clipe mais curto.",
        )

    try:
        file_storage.stream.seek(0)
        cabecalho = file_storage.stream.read(64)
        file_storage.stream.seek(0)
    except OSError:
        return ResultadoUpload(ok=False, erro="Não foi possível ler o arquivo enviado.")

    extensao_original = _detectar_formato_video(cabecalho)
    if not extensao_original:
        return ResultadoUpload(
            ok=False,
            erro="Formato de vídeo não suportado ou arquivo corrompido. Use MP4, WEBM ou OGG.",
        )

    os.makedirs(destino_dir, exist_ok=True)

    # Salva primeiro em um arquivo TEMPORÁRIO dentro do próprio destino
    # (mesmo filesystem, para que a troca final com os.replace seja atômica)
    # — nunca escreve diretamente no nome final antes de otimizar, para não
    # deixar um arquivo parcialmente processado utilizável em caso de falha.
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix="tmp_upload_video_", suffix=f".{extensao_original}", dir=destino_dir
        )
        os.close(tmp_fd)
    except OSError:
        return ResultadoUpload(ok=False, erro="Não foi possível preparar o upload do vídeo. Tente novamente.")

    try:
        file_storage.save(tmp_path)
    except OSError:
        _remover_arquivo_silencioso(tmp_path)
        return ResultadoUpload(ok=False, erro="Não foi possível salvar o vídeo enviado. Tente novamente.")

    # ── Otimização automática (best-effort) ────────────────────────────
    caminho_atual = tmp_path
    extensao_final = extensao_original
    caminho_otimizado = tmp_path + ".opt.mp4"
    if _otimizar_video_com_ffmpeg(tmp_path, caminho_otimizado):
        try:
            tamanho_otimizado = os.path.getsize(caminho_otimizado)
        except OSError:
            tamanho_otimizado = 0
        # Só troca pelo resultado otimizado se ele realmente ficou menor
        # (ou igual) que o original — em casos raros de vídeos já bem
        # comprimidos, recodificar poderia aumentar o tamanho, e nesse caso
        # não faz sentido usar o resultado "otimizado".
        if 0 < tamanho_otimizado <= max(tamanho, 1):
            _remover_arquivo_silencioso(tmp_path)
            caminho_atual = caminho_otimizado
            extensao_final = "mp4"
        else:
            _remover_arquivo_silencioso(caminho_otimizado)
    else:
        _remover_arquivo_silencioso(caminho_otimizado)

    nome_final = f"{prefixo}_{uuid.uuid4().hex[:12]}.{extensao_final}"
    caminho_final = os.path.join(destino_dir, nome_final)
    try:
        os.replace(caminho_atual, caminho_final)
    except OSError:
        _remover_arquivo_silencioso(caminho_atual)
        return ResultadoUpload(ok=False, erro="Não foi possível salvar o vídeo enviado. Tente novamente.")

    return ResultadoUpload(ok=True, nome_arquivo=nome_final)


def remover_upload_seguro(upload_folder: str, nome_arquivo: Optional[str]) -> None:
    """Remove um arquivo de upload do disco, ignorando erros e tentativas
    de path traversal (nomes contendo '/', '\\' ou '..')."""
    if not nome_arquivo:
        return
    nome_base = os.path.basename(nome_arquivo)
    if nome_base != nome_arquivo or ".." in nome_arquivo:
        return
    try:
        caminho = os.path.join(upload_folder, nome_base)
        if os.path.isfile(caminho):
            os.remove(caminho)
    except OSError:
        pass
