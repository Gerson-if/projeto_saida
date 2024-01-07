<?php
session_start();

if (!isset($_SESSION['cpf']) || $_SESSION['tipo'] !== 'admin') {
    header("Location: index.php");
    exit();
}

require 'conexao.php';

if (isset($_GET['id'])) {
    $id_usuario = $_GET['id'];

    // Excluir registros associados ao usuário na tabela 'registros'
    $query_delete_registros = "DELETE FROM registros WHERE cpf_usuario = (SELECT cpf FROM usuarios WHERE id = ?)";
    $stmt_delete_registros = $conexao->prepare($query_delete_registros);
    $stmt_delete_registros->bind_param("i", $id_usuario);
    $stmt_delete_registros->execute();

    if ($stmt_delete_registros->affected_rows > 0) {
        // Agora podemos excluir o usuário na tabela 'usuarios'
        $query_delete_usuario = "DELETE FROM usuarios WHERE id = ?";
        $stmt_delete_usuario = $conexao->prepare($query_delete_usuario);
        $stmt_delete_usuario->bind_param("i", $id_usuario);
        $stmt_delete_usuario->execute();

        if ($stmt_delete_usuario->affected_rows > 0) {
            // Usuário excluído com sucesso
            redirecionarComMensagem("dashboard_admin.php", "Usuário excluído com sucesso!");
        } else {
            // Erro ao excluir usuário
            redirecionarComMensagem("dashboard_admin.php", "Erro ao excluir usuário!");
        }
    } else {
        // Erro ao excluir registros associados
        redirecionarComMensagem("dashboard_admin.php", "Erro ao excluir registros associados!");
    }
} else {
    // ID de usuário não fornecido
    redirecionarComMensagem("dashboard_admin.php", "ID de usuário não fornecido!");
}

// Função para redirecionar com uma mensagem
function redirecionarComMensagem($destino, $mensagem) {
    echo "<script>alert('$mensagem'); window.location.href = '$destino';</script>";
    exit();
}
?>
