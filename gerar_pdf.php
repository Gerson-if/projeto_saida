<?php
require 'vendor/autoload.php'; // Supondo que dompdf está instalado via Composer
use Dompdf\Dompdf;
use Dompdf\Options;
require 'conexao.php';

// Função para obter saídas com filtro de datas
function obterSaidasFiltradas($conexao, $dataInicio, $dataFim) {
    $query = "SELECT registros.*, usuarios.nome as nome_usuario 
              FROM registros 
              JOIN usuarios ON registros.cpf_usuario = usuarios.cpf
              WHERE registros.data_saida BETWEEN ? AND ?";
    $stmt = $conexao->prepare($query);
    $stmt->bind_param("ss", $dataInicio, $dataFim);
    $stmt->execute();
    $result = $stmt->get_result();

    $saidas = [];
    if ($result->num_rows > 0) {
        while ($row = $result->fetch_assoc()) {
            $saidas[] = $row;
        }
    }

    return $saidas;
}

$dataInicio = isset($_POST['data_inicio']) ? $_POST['data_inicio'] : '';
$dataFim = isset($_POST['data_fim']) ? $_POST['data_fim'] : '';
$nomeUsuario = isset($_POST['nome_usuario']) ? $_POST['nome_usuario'] : '';

// Obter saídas filtradas com base nas datas
$saidasFiltradas = obterSaidasFiltradas($conexao, $dataInicio, $dataFim);

// Configurar dompdf
$options = new Options();
$options->set('isHtml5ParserEnabled', true);
$options->set('isPhpEnabled', true);

$dompdf = new Dompdf($options);
$dompdf->setPaper('A4', 'landscape');
$dompdf->loadHtml('<html><body>' .
    '<h1>Relatório de Saídas</h1>' .
    '<p>De Guarnição: ' . $nomeUsuario . '</p>' .
    '<table border="1" cellpadding="5" style="width: 100%; border-collapse: collapse;">
        <thead>
            <tr style="background-color: #f2f2f2;">
                <th>ID</th>
                <th>Nome do Usuário</th>
                <th>Telefone de Contato</th>
                <th>Motivo da Saída</th>
                <th>Local de Destino</th>
                <th>Endereço</th>
                <th>Data de Saída</th>
                <th>Data de Retorno</th>
                <th>Data do Registro</th>
            </tr>
        </thead>' .
    '<tbody>' .
    implode('', array_map(function ($saida) {
        return '<tr>
            <td>' . $saida['id'] . '</td>
            <td>' . $saida['nome_usuario'] . '</td>
            <td>' . $saida['telefone_contato'] . '</td>
            <td>' . nl2br($saida['motivo']) . '</td>
            <td>' . $saida['local'] . '</td>
            <td>' . nl2br($saida['endereco_destino']) . '</td>
            <td>' . date('d/m/Y', strtotime($saida['data_saida'])) . '</td>
            <td>' . date('d/m/Y', strtotime($saida['data_retorno'])) . '</td>
            <td>' . date('d/m/Y H:i:s', strtotime($saida['data_registro'])) . '</td>
        </tr>';
    }, $saidasFiltradas)) .
    '</tbody></table></body></html>');

$dompdf->render();

// Salvar o PDF em um arquivo
$pdfFileName = 'relatorio_saidas.pdf';
file_put_contents($_SERVER['DOCUMENT_ROOT'] . '/saida/' . $pdfFileName, $dompdf->output());

// Salvar o HTML em um arquivo Excel (opcional, pois o dompdf gera principalmente PDF)
$excelFileName = 'relatorio_saidas.xls';
$htmlToExcel = str_replace('</td>', "</td>\n", $dompdf->outputHtml());
file_put_contents($_SERVER['DOCUMENT_ROOT'] . '/saida/' . $excelFileName, $htmlToExcel);
?>

<!DOCTYPE html>
<html lang="pt-br">
<head>
    <title>Relatório de Saídas</title>
    <link rel="stylesheet" href="css/gerar_pdf.css">
    <script>
        // Verificar se o usuário é um administrador ao pressionar o botão Voltar no navegador
        window.onbeforeunload = function () {
            var isAdmin = <?php echo $isAdmin ? 'true' : 'false'; ?>;
            if (isAdmin) {
                // Redirecionar para o painel de administração
                window.location.href = 'dashboard_admin.php';
            }
        }
    </script>
</head>
<body>
    <div class="container">
        <h2>Relatório de Saídas</h2>
        <p>Relatório gerado com sucesso.</p>
        
        <div class="download-buttons">
            <a href='relatorio_saidas.pdf' target='_blank'>Baixar PDF</a>
            <a href='relatorio_saidas.xls'>Baixar Planilha</a>
        </div>
        
        <a href='dashboard_admin.php'>Voltar para o Dashboard</a>
    </div>
</body>
</html>
