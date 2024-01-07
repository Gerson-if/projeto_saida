<?php
require_once('tcpdf/tcpdf.php');
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

$saidasFiltradas = obterSaidasFiltradas($conexao, $dataInicio, $dataFim);

// Criação do arquivo PDF
$pdf = new TCPDF('L', 'mm', 'A4');
$pdf->SetMargins(10, 10, 10);
$pdf->AddPage();

$pdf->SetFont('helvetica', 'B', 18);
$pdf->Cell(0, 10, 'Relatório de Saídas', 0, 1, 'C');

$pdf->SetFont('helvetica', '', 14);
$pdf->Cell(0, 10, 'De Guarnição: ' . $nomeUsuario, 0, 1, 'C');

// Monta a tabela HTML
$html = '<table border="1" cellpadding="5">
    <tr>
        <th>ID</th>
        <th>Nome do Usuário</th>
        <th>Telefone de Contato</th>
        <th>Motivo da Saída</th>
        <th>Local de Destino</th>
        <th>Endereço</th>
        <th>Data de Saída</th>
        <th>Data de Retorno</th>
        <th>Data do Registro</th>
    </tr>';

foreach ($saidasFiltradas as $saida) {
    $html .= '<tr>
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
}

$html .= '</table>';

$pdf->writeHTML($html, true, false, true, false, '');

$pdf->Ln(10);

// Caminho local para salvar o PDF
$pdfFileName = 'relatorio_saidas.pdf';
$pdf->Output($_SERVER['DOCUMENT_ROOT'] . '/saida/' . $pdfFileName, 'F');

// Caminho local para salvar a planilha (Excel)
$excelFileName = 'relatorio_saidas.xls';
$htmlToExcel = str_replace('</td>', "</td>\n", $html);
file_put_contents($_SERVER['DOCUMENT_ROOT'] . '/saida/' . $excelFileName, $htmlToExcel);
?>

<!DOCTYPE html>
<html lang="pt-br">
<head>
    <title>Relatório de Saídas</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f0f0f0;
            margin: 0;
            padding: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            text-align: center;
        }

        .container {
            background-color: #fff;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 0 20px rgba(0, 0, 0, 0.2);
            max-width: 800px;
            width: 100%;
        }

        h2 {
            color: #333;
        }

        p {
            color: #4caf50;
            font-weight: bold;
        }

        a {
            color: #007bff;
            text-decoration: none;
            font-weight: bold;
            margin-top: 10px;
            display: inline-block;
        }

        .download-buttons {
            display: flex;
            justify-content: space-around;
            margin-top: 20px;
        }

        .download-buttons a {
            padding: 10px 20px;
            border-radius: 5px;
            background-color: #007bff;
            color: #fff;
            transition: background-color 0.3s ease;
        }

        .download-buttons a:hover {
            background-color: #0056b3;
        }
    </style>
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
