<?php
$host = "localhost";
$usuario_bd = "root";
$senha_bd = "root";
$banco = "sistema_saida";

$conexao = new mysqli($host, $usuario_bd, $senha_bd, $banco);

if ($conexao->connect_error) {
    die("Falha na conexão: " . $conexao->connect_error);
}
?>
