-- Criação da tabela 'usuarios'
ALTER TABLE usuarios
ADD COLUMN nome VARCHAR(100) NOT NULL;

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


--aletração relacionamento
ALTER TABLE registros
ADD CONSTRAINT fk_cpf_usuario
FOREIGN KEY (cpf_usuario)
REFERENCES usuarios(cpf)
ON DELETE CASCADE;
