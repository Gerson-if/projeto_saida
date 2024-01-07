-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1
-- Tempo de geração: 04/01/2024 às 16:58
-- Versão do servidor: 10.4.28-MariaDB
-- Versão do PHP: 8.2.4
-- antes de executar crie o banco de daos execute esse script no banco de dados 

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Banco de dados: `sistema_saida`
--

-- --------------------------------------------------------

--
-- Estrutura para tabela `registros`
--

CREATE TABLE `registros` (
  `id` int(11) NOT NULL,
  `cpf_usuario` varchar(11) NOT NULL,
  `local` varchar(255) NOT NULL,
  `motivo` text NOT NULL,
  `data_saida` datetime NOT NULL,
  `data_retorno` datetime DEFAULT NULL,
  `telefone_contato` varchar(20) DEFAULT NULL,
  `endereco_destino` text DEFAULT NULL,
  `data_registro` timestamp NOT NULL DEFAULT current_timestamp()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Despejando dados para a tabela `registros`
--

INSERT INTO `registros` (`id`, `cpf_usuario`, `local`, `motivo`, `data_saida`, `data_retorno`, `telefone_contato`, `endereco_destino`, `data_registro`) VALUES
(34, '123', 'campo grande', 'ferias ', '2024-01-04 00:00:00', '2024-01-18 00:00:00', '67996202782', 'rua sem fim buraco', '2024-01-04 14:50:59'),
(38, '123', 'dsfdsf', 'fdsfds', '2024-01-04 00:00:00', '2024-01-04 00:00:00', '67996202782', 'sem ', '2024-01-04 15:07:04');

-- --------------------------------------------------------

--
-- Estrutura para tabela `usuarios`
--

CREATE TABLE `usuarios` (
  `id` int(11) NOT NULL,
  `cpf` varchar(11) NOT NULL,
  `senha` varchar(255) NOT NULL,
  `tipo` enum('admin','usuario') NOT NULL,
  `nome` varchar(100) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

--
-- Despejando dados para a tabela `usuarios`
--

INSERT INTO `usuarios` (`id`, `cpf`, `senha`, `tipo`, `nome`) VALUES
(1, 'admin', 'admin_123', 'admin', 'Super_User'),
(14, '04579847164', '1234', 'usuario', 'SD DANIEL'),
(15, '123', '123', 'usuario', '3 Sgt filipe ');

--
-- Índices para tabelas despejadas
--

--
-- Índices de tabela `registros`
--
ALTER TABLE `registros`
  ADD PRIMARY KEY (`id`),
  ADD KEY `fk_cpf_usuario` (`cpf_usuario`);

--
-- Índices de tabela `usuarios`
--
ALTER TABLE `usuarios`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `cpf` (`cpf`);

--
-- AUTO_INCREMENT para tabelas despejadas
--

--
-- AUTO_INCREMENT de tabela `registros`
--
ALTER TABLE `registros`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=39;

--
-- AUTO_INCREMENT de tabela `usuarios`
--
ALTER TABLE `usuarios`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=17;

--
-- Restrições para tabelas despejadas
--

--
-- Restrições para tabelas `registros`
--
ALTER TABLE `registros`
  ADD CONSTRAINT `fk_cpf_usuario` FOREIGN KEY (`cpf_usuario`) REFERENCES `usuarios` (`cpf`) ON DELETE CASCADE,
  ADD CONSTRAINT `registros_ibfk_1` FOREIGN KEY (`cpf_usuario`) REFERENCES `usuarios` (`cpf`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
