<?php
session_start();

if ($_SERVER["REQUEST_METHOD"] == "POST") {
    require 'conexao.php';

    $cpf = $_POST['cpf'];
    $senha = $_POST['senha'];
    $tipo = $_POST['tipo'];

    // Validação dos dados (exemplo: verificar se os campos não estão vazios)

    // Verificar se o CPF já existe
    $verifica_cpf = "SELECT * FROM usuarios WHERE cpf = '$cpf'";
    $result_verifica_cpf = $conexao->query($verifica_cpf);

    if ($result_verifica_cpf->num_rows > 0) {
        echo "Erro ao cadastrar usuário: CPF já cadastrado.";
        exit();
    }

    // Inserir novo usuário
    $query = "INSERT INTO usuarios (cpf, senha, tipo) VALUES ('$cpf', '$senha', '$tipo')";
    $result = $conexao->query($query);

    if ($result) {
        echo "Usuário cadastrado com sucesso!";
    } else {
        echo "Erro ao cadastrar usuário: " . $conexao->error;
    }
} else {
    header("Location: dashboard_admin.php");
    exit();
}
?>
