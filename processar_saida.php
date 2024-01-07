<?php
session_start();

if ($_SERVER["REQUEST_METHOD"] == "POST") {
    require 'conexao.php';

    if (!isset($_SESSION['cpf'])) {
        header("Location: index.php");
        exit();
    }

    $cpf_usuario = $_SESSION['cpf'];
    $local = isset($_POST['local']) ? trim($_POST['local']) : '';
    $motivo = isset($_POST['motivo']) ? trim($_POST['motivo']) : '';
    $data_saida = isset($_POST['data_saida']) ? trim($_POST['data_saida']) : '';
    $data_retorno = isset($_POST['data_retorno']) ? trim($_POST['data_retorno']) : '';
    $telefone_contato = isset($_POST['telefone_contato']) ? trim($_POST['telefone_contato']) : '';
    $endereco_destino = isset($_POST['endereco_destino']) ? trim($_POST['endereco_destino']) : '';

    // Validar e sanitizar os dados antes de inserir no banco de dados
    $local = mysqli_real_escape_string($conexao, $local);
    $motivo = mysqli_real_escape_string($conexao, $motivo);
    $data_saida = mysqli_real_escape_string($conexao, $data_saida);
    $data_retorno = mysqli_real_escape_string($conexao, $data_retorno);
    $telefone_contato = mysqli_real_escape_string($conexao, $telefone_contato);
    $endereco_destino = mysqli_real_escape_string($conexao, $endereco_destino);

    // Validar se os campos obrigatórios foram preenchidos
    if (empty($local) || empty($motivo) || empty($data_saida)) {
        echo "Por favor, preencha todos os campos obrigatórios.";
        exit();
    }

    // Validar a data de saída
    if (!strtotime($data_saida)) {
        echo "A data de saída é inválida.";
        exit();
    }

    // Validar a data de retorno, se fornecida
    if ($data_retorno && !strtotime($data_retorno)) {
        echo "A data de retorno é inválida.";
        exit();
    }

    // Inserir os dados no banco de dados usando Prepared Statement
    $query = "INSERT INTO registros (cpf_usuario, local, motivo, data_saida, data_retorno, telefone_contato, endereco_destino) VALUES (?, ?, ?, ?, ?, ?, ?)";
    
    $stmt = $conexao->prepare($query);
    $stmt->bind_param("sssssss", $cpf_usuario, $local, $motivo, $data_saida, $data_retorno, $telefone_contato, $endereco_destino);
    $result = $stmt->execute();

    if ($result) {
        echo "Saída registrada com sucesso!";
    } else {
        echo "Erro ao registrar saída: " . $stmt->error;
    }

    $stmt->close();
    $conexao->close();
} else {
    header("Location: formulario_saida.php");
    exit();
}
?>
