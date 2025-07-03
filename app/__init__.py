from flask import Flask
from flask_cors import CORS
from app.config import Config
from app.extensions import db, bcrypt, migrate, mail, socketio
from app.api import init_app as init_api
from flask_jwt_extended import JWTManager
import os
import psycopg2
from urllib.parse import urlparse
from app.models import PoliticaSistema
from uuid import uuid4

def create_database_if_not_exists():
    db_url = os.getenv('SQLALCHEMY_DATABASE_URI')
    parsed = urlparse(db_url)

    db_name = parsed.path[1:]  
    user = parsed.username
    password = parsed.password
    host = parsed.hostname
    port = parsed.port or 5432

    
    conn = psycopg2.connect(
        dbname='postgres',
        user=user,
        password=password,
        host=host,
        port=port
    )
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}';")
    exists = cur.fetchone()

    if not exists:
        cur.execute(f'CREATE DATABASE "{db_name}";')
        print(f'[✓] Banco de dados "{db_name}" criado com sucesso.')
    else:
        print(f'[i] Banco de dados "{db_name}" já existe.')

    cur.close()
    conn.close()

def load_terms_of_service():
    
    try:
        terms_file_path = os.path.join(os.path.dirname(__file__), 'terms', 'termos_uso.html')
        
        with open(terms_file_path, 'r', encoding='utf-8') as file:
            terms_content = file.read()
        
        current_terms = PoliticaSistema.query.filter_by(
            tipo_politica='uso',
            ativa=True
        ).first()
        
        if not current_terms:
            new_terms = PoliticaSistema(
                versao_termos=str(uuid4())[:8],  
                conteudo_termos=terms_content,
                tipo_politica='uso',
                dias_retencao=90  
            )
            db.session.add(new_terms)
            db.session.commit()
            print('[✓] Termos de uso carregados no banco de dados')
        else:
            print('[i] Termos de uso já existem no banco de dados')
            
    except Exception as e:
        print(f'[!] Erro ao carregar termos de uso: {str(e)}')

def create_app():
    create_database_if_not_exists()  
    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app, resources={
        r"/api/*": {
            "origins": "http://localhost:3000",
            "supports_credentials": True
        }
    })

    
    jwt = JWTManager(app)
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    socketio.init_app(
        app,
        async_mode=app.config['SOCKETIO_ASYNC_MODE'],
        cors_allowed_origins=app.config['SOCKETIO_CORS_ALLOWED_ORIGINS'],
        logger=app.config['SOCKETIO_LOGGER'],
        engineio_logger=app.config['SOCKETIO_ENGINEIO_LOGGER'],
        ping_timeout=app.config['SOCKETIO_PING_TIMEOUT'],
        ping_interval=app.config['SOCKETIO_PING_INTERVAL']
    )


    init_api(app)
    with app.app_context():
        db.create_all()
        load_terms_of_service()

    return app

