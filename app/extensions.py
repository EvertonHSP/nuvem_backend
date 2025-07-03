from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_mail import Mail
from flask_socketio import SocketIO

db = SQLAlchemy()
bcrypt = Bcrypt()
migrate = Migrate()
mail = Mail()
socketio = SocketIO()