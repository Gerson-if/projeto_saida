# Sistema de Controle de Registros - Relatório de Saídas

Este projeto é um sistema robusto de controle de registros de saídas, desenvolvido em PHP, HTML e CSS, que oferece diversas funcionalidades para facilitar a gestão e análise de informações. Com foco na praticidade e eficiência, o sistema é destinado a administradores responsáveis pelo controle e geração de relatórios de saídas.

## Funcionalidades

### Cadastro de Usuários

- **Adição de Usuários:** Registra usuários no sistema, incluindo informações cruciais como CPF, nome, senha e tipo de usuário (Super Admin ou Usuário Convencional).

- **Exclusão de Usuários:** Facilita a remoção de usuários do sistema, mantendo o controle sobre as contas ativas.

### Geração de Relatórios de Saídas

- **Filtragem por Data:** Possibilita a geração de relatórios de saídas filtrados por data de início e fim, proporcionando maior flexibilidade na análise de registros.

- **Visualização no Navegador:** Permite a visualização imediata dos relatórios no navegador, simplificando o processo de verificação.

- **Exportação em PDF:** Oferece a opção de exportar os relatórios de saídas em formato PDF, facilitando o compartilhamento e armazenamento.

- **Exportação em Planilha Excel:** Gera versões dos relatórios em planilhas Excel, proporcionando uma visão tabular dos dados para análises mais avançadas.

## Requisitos

- **PHP 7.0 ou superior**
- **MySQL ou outro banco de dados compatível**
- **Navegador Web moderno**
- **Servidor Web (por exemplo, Apache, Nginx)**

## Instalação

1. Clone este repositório para o diretório do seu servidor web.

   ```bash
   git clone https://github.com/Gerson-if/projeto_saida.git
   ```

2. Configure o banco de dados no arquivo `conexao.php`. Insira as informações corretas para se conectar ao seu banco de dados.

3. Importe o arquivo `banco_original.sql` para criar a estrutura do banco de dados.

   ```bash
   mysql -u seu-usuario -p sua-senha seu-banco-de-dados < banco_orignal.sql
   ```

4. Certifique-se de que o PHP e o TCPDF estão instalados no seu servidor.

   ```bash
   composer install
   ```

5. Abra o sistema em um navegador e inicie a administração dos usuários e registros de saídas.

   ```bash
   http://localhost/saida
   ```
```markdown
# Guia de Instalação no Linux

**⚠️ Aviso Importante:**  
- Este script **não deve ser utilizado em ambientes de produção**. 
Ele foi desenvolvido para fins de testes ou ambientes de desenvolvimento. 
O uso em servidores de produção pode representar riscos de segurança, 
especialmente devido às permissões e configurações padrão aplicadas pelo script.  

- O script foi **testado exclusivamente no Ubuntu 20.04**. 
Seu funcionamento em outras versões ou distribuições Linux não está garantido.

---

## Passo a Passo da Instalação

### 1. Baixar o Script
Faça o download do arquivo `linux_saida.zip`.

---

### 2. Descompactar o Arquivo
Use o comando abaixo para descompactar o arquivo:  
```bash
unzip linux_saida.zip
```

---

### 3. Configurar Permissões
Após descompactar, aplique as permissões adequadas para a pasta extraída de forma recursiva:  
```bash
chmod 777 -R pasta_descompactada
```

---

### 4. Executar o Script de Instalação
Execute o script de instalação para configurar automaticamente os seguintes componentes:  
- **Apache**  
- **MariaDB**  
- Configuração completa do banco de dados  

Comando para rodar o script:  
```bash
./linux_saida_update.sh
```

> **⚠️ Atenção:** Certifique-se de que o script não seja executado em servidores de produção. Ele pode alterar configurações críticas e aplicar permissões amplas que não são seguras em ambientes públicos.

---

### 5. Acessar o Sistema
Após a instalação, acesse o sistema pelo navegador:  
```
http://localhost
```
Utilize as seguintes credenciais padrão para login:  
- **Usuário:** `admin`  
- **Senha:** `admin_123`

---

### 6. Resolver Problemas de Permissão
Caso encontre problemas relacionados à escrita de relatórios, ajuste as permissões da pasta de saída com o seguinte comando:  
```bash
chmod 777 -R /var/www/saida/saida
```

---

### 7. Configuração do Diretório Web
O script altera o diretório padrão do Apache (`/var/www/html`) para o novo diretório `/var/www/saida/saida`.  
Certifique-se de que este diretório tenha as permissões corretas para funcionamento.

---

### 8. Instalar Interface Web para Gerenciamento do Banco de Dados
Caso deseje uma interface web para gerenciar o banco de dados, siga os passos abaixo:  
1. Baixe o **Adminer** (ou outra ferramenta similar).  
2. Copie o arquivo para a pasta `/var/www/saida/saida`:  
   ```bash
   cp adminer.php /var/www/saida/saida
   ```
3. Renomeie o arquivo, se preferir, para algo mais amigável:  
   ```bash
   mv /var/www/saida/saida/adminer.php /var/www/saida/saida/admin.php
   ```
4. Ajuste as permissões do arquivo:  
   ```bash
   chmod 777 -R /var/www/saida/saida/admin.php
   ```

---

### 9. Acessar o Gerenciador de Banco de Dados
Após a configuração, acesse o gerenciador no navegador:  
```
http://localhost/admin.php
```
Utilize as credenciais padrão do banco de dados configurado pelo script:  
- **Usuário:** `root`  
- **Senha:** `root`

---

## Considerações Finais
- **Segurança:** Não use o script em servidores expostos publicamente ou ambientes de produção. Revise as permissões e credenciais antes de qualquer uso.  
- **Compatibilidade:** Este script foi testado apenas no Ubuntu 20.04. Para outras versões ou distribuições, ajustes podem ser necessários.  
- **Logs e Debugging:** Em caso de problemas, verifique os logs do Apache em:  
  ```
  /var/log/apache2/error.log
  ```

---

Pronto! Seu ambiente Linux está configurado para rodar o sistema com Apache, MariaDB e a interface web para administração. Se tiver dúvidas ou encontrar problemas, revise as permissões ou as configurações aplicadas pelo script.
```

## Estrutura do Projeto

- `index.php`: Página de login.
- `dashboard_admin.php`: Painel de controle do administrador.
- `gerar_pdf.php`: Página para geração de relatórios em PDF.
- `tcpdf/`: Diretório contendo a biblioteca TCPDF.
- `css/`: Estilos CSS para o projeto.
- `images/`: Imagens utilizadas no projeto.
- `schema.sql`: Script SQL para criação da estrutura do banco de dados.

## Contribuição

Contribuições são bem-vindas! Sinta-se à vontade para abrir problemas (issues) e pull requests para melhorar o projeto.

## Licença

Este projeto está licenciado sob a Licença MIT - consulte o arquivo [LICENSE](LICENSE) para obter detalhes. 
