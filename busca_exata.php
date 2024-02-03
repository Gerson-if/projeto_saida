<?php
require 'vendor/autoload.php';
use Dompdf\Dompdf;
use Dompdf\Options;
require 'conexao.php';

function obterSaidasPorPeriodo($conexao, $dataInicio, $dataFim) {
    $query = "SELECT registros.*, usuarios.nome as nome_usuario 
              FROM registros 
              JOIN usuarios ON registros.cpf_usuario = usuarios.cpf
              WHERE ((DATE(registros.data_saida) >= ? AND DATE(registros.data_saida) <= ?)
                 OR (DATE(registros.data_retorno) >= ? AND DATE(registros.data_retorno) <= ?)
                 OR (DATE(registros.data_saida) <= ? AND DATE(registros.data_retorno) >= ?))
                AND DATE(registros.data_registro) BETWEEN ? AND ?";
                    
    $stmt = $conexao->prepare($query);
    $stmt->bind_param("ssssssss", $dataInicio, $dataFim, $dataInicio, $dataFim, $dataInicio, $dataFim, $dataInicio, $dataFim);
    $stmt->execute();
    $result = $stmt->get_result();

    $saidas = [];
    while ($row = $result->fetch_assoc()) {
        $saidas[] = $row;
    }

    return $saidas;
}

if ($_SERVER["REQUEST_METHOD"] == "POST") {
    $dataInicio = isset($_POST['data_inicio']) ? $_POST['data_inicio'] : '';
    $dataFim = isset($_POST['data_fim']) ? $_POST['data_fim'] : '';

    $saidasPesquisadas = obterSaidasPorPeriodo($conexao, $dataInicio, $dataFim);

    $options = new Options();
    $options->set('isHtml5ParserEnabled', true);
    $options->set('isPhpEnabled', true);

    $dompdf = new Dompdf($options);
    $dompdf->setPaper('A4', 'landscape');
    $dompdf->loadHtml('<html><body>' .
        '<h1>Relatório de Saídas Por Data Exata ' . '</h1>' .
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
        }, $saidasPesquisadas)) .
        '</tbody></table></body></html>');

    $dompdf->render();

    $pdfFileName = 'relatorio_saidas_periodo.pdf';
    file_put_contents($_SERVER['DOCUMENT_ROOT'] . '/saida/' . $pdfFileName, $dompdf->output());

    $csvFileName = 'relatorio_saidas_periodo.csv';
    $csvFile = fopen($_SERVER['DOCUMENT_ROOT'] . '/saida/' . $csvFileName, 'w');

    $headers = ['ID', 'Nome do Usuário', 'Telefone de Contato', 'Motivo da Saída', 'Local de Destino', 'Endereço', 'Data de Saída', 'Data de Retorno', 'Data do Registro'];
    fputcsv($csvFile, $headers);

    foreach ($saidasPesquisadas as $saida) {
        $rowData = [
            $saida['id'],
            $saida['nome_usuario'],
            $saida['telefone_contato'],
            $saida['motivo'],
            $saida['local'],
            $saida['endereco_destino'],
            date('d/m/Y', strtotime($saida['data_saida'])),
            date('d/m/Y', strtotime($saida['data_retorno'])),
            date('d/m/Y H:i:s', strtotime($saida['data_registro'])),
        ];
        fputcsv($csvFile, $rowData);
    }

    fclose($csvFile);
}
?>

<!DOCTYPE html>
<html lang="pt-br">
<head>
    <title>Relatório de Saídas por Data Exata</title>
    <link rel="stylesheet" href="css/gerar_pdf.css">
    <style>
        form {
            margin-top: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        label {
            font-size: 18px;
            margin-bottom: 8px;
            color: #333;
        }

        input {
            padding: 12px;
            margin-bottom: 20px;
            border: 1px solid #ddd;
            border-radius: 5px;
            width: 100%;
            box-sizing: border-box;
            font-size: 16px;
        }

        button {
            padding: 15px 30px;
            border: none;
            border-radius: 5px;
            background-color: #007bff;
            color: #fff;
            cursor: pointer;
            transition: background-color 0.3s ease;
            font-size: 18px;
            width: 100%;
            box-sizing: border-box;
        }

        button:hover {
            background-color: #0056b3;
        }

        input:focus {
            outline: none;
            border-color: #007bff;
            box-shadow: 0 0 5px rgba(0, 123, 255, 0.5);
        }
    </style>
</head>
<body>
    <div class="container">
        <h2>Relatório de Saídas por Data Exata</h2>
        
        <form method="post" action="">
            <label for="data_inicio">Data de Início:</label>
            <input type="date" name="data_inicio" required>

            <label for="data_fim">Data de Fim:</label>
            <input type="date" name="data_fim" required>

            <button type="submit">Gerar Relatório</button>
        </form>
        
        <?php if ($_SERVER["REQUEST_METHOD"] == "POST"): ?>
            <p class="success-message">Relatório gerado com sucesso. <?php echo count($saidasPesquisadas); ?> registros encontrados.</p>
            <div class="download-buttons">
                <a href='relatorio_saidas_periodo.pdf' target='_blank'>Baixar PDF</a>
                <a href='relatorio_saidas_periodo.csv' target='_blank'>Baixar em CSV</a>
            </div>
        <?php endif; ?>
        <a class="back-to-dashboard" href='dashboard_admin.php'>Voltar para o Dashboard</a>
    </div>
</body>
</html>
