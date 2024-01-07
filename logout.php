<?php
session_start();

// Função para realizar o logout do usuário
function realizarLogout() {
    // Limpa todas as variáveis de sessão
    $_SESSION = array();

    // Expira o cookie de sessão, se existir
    if (isset($_COOKIE[session_name()])) {
        setcookie(session_name(), '', time() - 3600, '/');
    }

    // Destroi a sessão
    session_destroy();
}

// Função para redirecionar para a página de login
function redirecionarParaLogin() {
    header("Location: index.php");
    exit();
}

// Realiza o logout
realizarLogout();

// Redireciona para a página de login
redirecionarParaLogin();
?>
