# Nuvem – Sistema de Armazenamento de Arquivos

**Nuvem** é um projeto **acadêmico e experimental** voltado para o armazenamento seguro de arquivos. Nele, usuários podem fazer upload de arquivos para o servidor, escolhendo se desejam mantê-los **públicos** (acessíveis por link) ou **privados** (acesso restrito ao dono). A aplicação foca em práticas de **segurança da informação**, utilizando autenticação em duas etapas, criptografia e controle de sessões.

O sistema utiliza **Python (Flask)** no backend e **React.js** no frontend, com comunicação via **API RESTful**.

---

## 🔐 Medidas de Segurança

1. **Autenticação via JWT (JSON Web Token)**
   O servidor gera tokens JWT com tempo de expiração, evitando sessões persistentes inseguras.

2. **Verificação em Duas Etapas (2SV por e-mail)**
   Após inserir a senha, um código de verificação é enviado por e-mail.

3. **Criptografia de Senhas com Bcrypt**
   Todas as senhas são armazenadas como hashes seguros.

4. **Criptografia dos Nomes de Arquivos com Fernet (cryptography)**
   Os nomes dos arquivos são criptografados para dificultar a identificação.

5. **HTTPS**
   Suporte a HTTPS para proteger a comunicação em produção.

6. **Registro de Logs com IP e Horário**
   Logs de atividades são mantidos para rastreabilidade e auditoria.

7. **Exclusão de Conta e Dados**
   O usuário pode excluir sua conta e arquivos, seguindo política de retenção.

8. **Política de Senha Forte**
   Validação de complexidade mínima de senhas.

9. **Política de Consentimento**
   O sistema exige aceite dos termos de privacidade antes do uso.

10. **Backup dos Dados**
    Estrutura prevista para backups regulares de arquivos e banco de dados.

---

## ⚙️ Estrutura Técnica

| Camada    | Tecnologias                                        |
| --------- | -------------------------------------------------- |
| Backend   | Flask, SQLAlchemy, Flask-Mail, JWT, Flask-SocketIO |
| Segurança | JWT, bcrypt, cryptography.fernet, logs             |
| Banco     | PostgreSQL, Flask-Migrate                          |
| Frontend  | React.js, Axios, React Router                      |
| Infra     | Dotenv, CORS, eventlet, WebSocket                  |

---

## 📁 Funcionalidades

* Upload de arquivos públicos ou privados
* Compartilhamento de arquivos por link
* Login com autenticação em duas etapas (2SV)
* Exclusão de arquivos e da conta
* Registro de logs
* Upload de foto de perfil
* WebSocket (em desenvolvimento)

---

## 👨‍💻 Autor

**Everton Hian dos Santos Pinheiro**
Desenvolvimento completo do backend, frontend e arquitetura de segurança.

---

## 📦 Requisitos

### Backend

* Python 3.10+
* PostgreSQL
* Ambiente virtual (venv)

### Frontend

* Node.js 18+
* npm

---

## ⚙️ Configuração do `.env`

Crie um arquivo `.env` dentro da pasta `backend/` com o seguinte conteúdo, substituindo os valores de exemplo pelos seus:

```env
# Banco de Dados
SQLALCHEMY_DATABASE_URI=postgresql+psycopg2://usuario:senha@localhost:5432/nomedobanco

# Chaves de Segurança
SECRET_KEY=sua_chave_secreta_flask
JWT_SECRET_KEY=sua_chave_secreta_jwt

# Uploads
UPLOAD_FOLDER=uploads/fotos_perfil

# WebSocket (opcional)
SOCKETIO_ASYNC_MODE=eventlet
SOCKETIO_CORS_ALLOWED_ORIGINS=http://localhost:3000
SOCKETIO_LOGGER=false
SOCKETIO_ENGINEIO_LOGGER=false
SOCKETIO_PING_TIMEOUT=60
SOCKETIO_PING_INTERVAL=25

# E-mail (para 2SV)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=seu_email@gmail.com
MAIL_PASSWORD=sua_senha_de_app
MAIL_DEFAULT_SENDER=seu_email@gmail.com

# Ambiente
ENV=development
DEBUG=true
USE_RELOADER=True
```

> ⚠️ **Atenção:** Para usar o Gmail com esse sistema, você deve gerar uma [senha de app](https://support.google.com/accounts/answer/185833?hl=pt-BR), pois sua senha normal do Gmail **não funciona**.

---

## 🚀 Como Executar o Projeto

### 1. Clonando o Repositório

```bash
git clone git@github.com:EvertonHSP/Nuvem.git
cd Nuvem
```

---

### 2. Executando o Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate       # No Windows
pip install -r requirements.txt
python manage.py
```

---

### 3. Executando o Frontend

```bash
cd frontend
npm install
npm start           # Modo desenvolvimento
```

Para produção:

```bash
npm run build
npx serve -s build
```

---

## 📚 Bibliotecas Utilizadas

### Backend

```
Flask
SQLAlchemy
psycopg2-binary
marshmallow
python-dotenv
flask-cors
flask-migrate
flask-bcrypt
flask-restful
flask_jwt_extended
flask_mail
requests
Flask-SocketIO
python-engineio
python-socketio
eventlet
cryptography
```

### Frontend

```
| Biblioteca                    | Finalidade                                                    |
| ----------------------------- | ------------------------------------------------------------- |
| `react`                       | Biblioteca principal para criação de interfaces               |
| `react-dom`                   | Responsável por renderizar o React na árvore DOM              |
| `react-router-dom`            | Gerenciamento de rotas no frontend                            |
| `axios`                       | Realiza requisições HTTP para o backend                       |
| `crypto-js`                   | Criptografia de dados no frontend                             |
| `dexie`                       | Abstração simples para uso do IndexedDB (armazenamento local) |
| `react-icons`                 | Ícones SVG prontos para uso em React                          |
| `react-scripts`               | Scripts para build, start, test e eject do Create React App   |
| `web-vitals`                  | Coleta métricas de performance (opcional)                     |
| `@testing-library/react`      | Ferramentas para testes de componentes React                  |
| `@testing-library/jest-dom`   | Extensões de matchers do Jest para testes mais legíveis       |
| `@testing-library/user-event` | Simula interações reais do usuário nos testes                 |


```

---
