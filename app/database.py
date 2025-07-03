from flask import current_app as app
from app.models import Usuario
from werkzeug.security import generate_password_hash
from app.extensions import db


def criar_superusuario():
    with app.app_context():
        if not Usuario.query.filter_by(email="admin@snapgram.com").first():
            senha_hash = generate_password_hash("admin123")
            admin = Usuario(username="admin",
                            email="admin@snapgram.com", senha=senha_hash)
            db.session.add(admin)
            db.session.commit()
            print("Superusuário criado com sucesso!")
