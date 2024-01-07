-- Crie o banco de dados
CREATE DATABASE IF NOT EXISTS sistema_saida;

-- Use o banco de dados
USE sistema_saida;

-- Crie a tabela de usuários
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cpf VARCHAR(11) UNIQUE NOT NULL,
    senha VARCHAR(255) NOT NULL,
    tipo ENUM('admin', 'usuario') NOT NULL
);

-- Crie a tabela de registros
CREATE TABLE IF NOT EXISTS registros (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cpf_usuario VARCHAR(11) NOT NULL,
    local VARCHAR(255) NOT NULL,
    motivo TEXT NOT NULL,
    data_saida DATETIME NOT NULL,
    data_retorno DATETIME,
    FOREIGN KEY (cpf_usuario) REFERENCES usuarios(cpf)
);

-- Insira o super admin
INSERT IGNORE INTO usuarios (cpf, senha, tipo) VALUES ('admin', 'admin', 'admin');
-- Criação da tabela 'usuarios'
CREATE TABLE usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    cpf VARCHAR(11) NOT NULL UNIQUE,
    senha VARCHAR(255) NOT NULL,
    tipo ENUM('admin', 'usuario') NOT NULL
);

-- Criação da tabela 'registros' (caso não exista)
CREATE TABLE IF NOT EXISTS registros (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cpf_usuario VARCHAR(11) NOT NULL,
    local VARCHAR(255) NOT NULL,
    motivo TEXT NOT NULL,
    data_saida DATE NOT NULL,
    data_retorno DATE NOT NULL
);
