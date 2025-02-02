# Sistema de Controle de Registros - Relatório de Saídas

Este projeto é um sistema robusto de controle de registros de saídas, desenvolvido em **PHP, HTML e CSS**, que oferece diversas funcionalidades para facilitar a gestão e análise de informações. Com foco na praticidade e eficiência, o sistema é destinado a administradores responsáveis pelo controle e geração de relatórios de saídas.

## Funcionalidades

### 📌 Cadastro de Usuários

- **Adição de Usuários:** Registra usuários no sistema, incluindo informações cruciais como CPF, nome, senha e tipo de usuário (Super Admin ou Usuário Convencional).
- **Exclusão de Usuários:** Facilita a remoção de usuários do sistema, mantendo o controle sobre as contas ativas.

### 📊 Geração de Relatórios de Saídas

- **Filtragem por Data:** Permite a geração de relatórios de saídas filtrados por data de início e fim, proporcionando maior flexibilidade na análise de registros.
- **Visualização no Navegador:** Relatórios podem ser visualizados diretamente no navegador, simplificando o processo de verificação.
- **Exportação em PDF:** Opção de exportação dos relatórios em formato PDF, facilitando o compartilhamento e armazenamento.
- **Exportação em Planilha Excel:** Gera versões dos relatórios em planilhas Excel para análises mais detalhadas.

## 🔧 Requisitos

- **PHP 7.0 ou superior**
- **MySQL ou outro banco de dados compatível**
- **Navegador Web moderno**
- **Servidor Web (Apache, Nginx, etc.)**

## 🚀 Instalação

1. Clone este repositório para o diretório do seu servidor web:
   ```bash
   git clone https://github.com/Gerson-if/projeto_saida.git
   ```

2. Configure o banco de dados no arquivo **conexao.php** e insira as credenciais corretas para conexão.

3. Importe o arquivo **banco_original.sql** para criar a estrutura do banco de dados:
   ```bash
   mysql -u seu-usuario -p sua-senha seu-banco-de-dados < banco_original.sql
   ```

4. Certifique-se de que o **PHP** e a biblioteca **TCPDF** estão instalados:
   ```bash
   composer install
   ```

5. Abra o sistema em um navegador:
   ```bash
   http://localhost/saida
   ```

## 🐧 Guia de Instalação no Linux

### ⚠️ Avisos Importantes

- **Não use este script em ambientes de produção!**
- **Compatibilidade:** Testado no **Ubuntu 20.04**. Outras versões podem necessitar ajustes.

---

## 🚀 Passo a Passo da Instalação

### 1️⃣ Baixar e Descompactar o Arquivo

Baixe o arquivo **linux_saida.zip** e extraia-o:
```bash
unzip linux_saida.zip
```

---

### 2️⃣ Configurar Permissões
Ajuste as permissões da pasta extraída:
```bash
chmod 777 -R pasta_descompactada
```

---

### 3️⃣ Executar o Script de Instalação
Este script instalará e configurará:
- **Apache** (servidor web)
- **MariaDB** (banco de dados)
- Configurações do banco de dados automaticamente aplicadas

Execute:
```bash
./linux_saida_update.sh
```

**⚠️ Importante:** Este script não deve ser executado em servidores de produção devido às permissões aplicadas.

---

### 4️⃣ Estrutura de Diretórios e Acesso ao Sistema

Durante a instalação, o diretório padrão do Apache **/var/www/html/** é alterado para **/var/www/saida/**. Dentro dele, há uma **subpasta 'saida'**, que contém o sistema propriamente dito. Essa organização permite a configuração de outros sistemas em níveis superiores.

Para acessar o sistema:
```bash
http://localhost/saida
```
Ou pelo IP do servidor:
```bash
http://seu_ip/saida
```

Credenciais padrão:
- **Usuário:** admin
- **Senha:** admin_123

---

### 5️⃣ Resolver Problemas de Permissão
Caso enfrente problemas com gravação de arquivos, ajuste as permissões:
```bash
chmod 777 -R /var/www/saida/saida
```

---

### 6️⃣ Instalar Interface Web para Gerenciamento de Banco de Dados
Para facilitar a administração do banco de dados, instale o **Adminer**:

1. Baixe o arquivo para o diretório **/var/www/saida/saida**:
   ```bash
   cp adminer.php /var/www/saida/saida
   ```
2. (Opcional) Renomeie o arquivo:
   ```bash
   mv /var/www/saida/saida/adminer.php /var/www/saida/saida/admin.php
   ```
3. Ajuste as permissões:
   ```bash
   chmod 777 -R /var/www/saida/saida/admin.php
   ```

Para acessar o gerenciador:
```bash
http://localhost/admin.php
```

Credenciais padrão:
- **Usuário:** root
- **Senha:** root

---

## 🛠️ Logs e Depuração

Se encontrar problemas, verifique os logs do Apache:
```bash
/var/log/apache2/error.log
```

---

## 📜 Licença

Este projeto é distribuído sob a licença **MIT**. Sinta-se à vontade para modificá-lo e distribuí-lo conforme necessário.

---

## ✅ Considerações Finais

- **Segurança:** Este script é para uso **somente em ambientes de teste**.
- **Compatibilidade:** Testado no **Ubuntu 20.04**. Para outras distribuições, ajustes podem ser necessários.
- **Contribuições:** Caso encontre algo que possa ser melhorado, envie um **Pull Request** ou abra uma **Issue**.

---

## 📂 Estrutura do Projeto

- **index.php**: Página de login.
- **dashboard_admin.php**: Painel de controle do administrador.
- **gerar_pdf.php**: Página para geração de relatórios em PDF.
- **tcpdf/**: Diretório contendo a biblioteca TCPDF.
- **css/**: Estilos CSS para o projeto.
- **images/**: Imagens utilizadas no projeto.

---
