from flask_restful import Resource, reqparse
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, get_jwt, decode_token
from app import bcrypt, mail
from app.models import Usuario, Sessao, Codigo2FA, Log, LogCategoria, LogSeveridade
from app.extensions import db, mail
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from flask_mail import Message
import random
from flask import request
from enum import Enum
import json



def registrar_log(usuario_id, categoria, severidade, acao, detalhe=None, metadados=None, ip_origem=None):
   
    if ip_origem is None:
        ip_origem = request.remote_addr
    
    try:
        novo_log = Log(
            id=uuid4(),
            id_usuario=usuario_id,
            categoria=categoria.value if isinstance(categoria, Enum) else categoria,
            severidade=severidade.value if isinstance(severidade, Enum) else severidade,
            acao=acao,
            detalhe=detalhe,
            ip_origem=ip_origem,
            metadados=json.dumps(metadados) if metadados else None
        )
        
        db.session.add(novo_log)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao registrar log: {str(e)}")
        return False

def enviar_email_2fa(email, codigo):
    try:
        
        plain_content = f"Your verification code is: {codigo}\nUse this code to complete your registration/login."
        html_content = f"""<!DOCTYPE html>
        <html><head><meta charset="utf-8"></head>
        <body><p>Your code: <strong>{codigo}</strong></p></body></html>"""
        
        
        
        msg = Message(
            subject="Code",  
            recipients=[email],
            charset='utf-8',
            body=plain_content,
            html=html_content
        )
        
        
        msg.extra_headers = {'Content-Transfer-Encoding': '8bit'}
        
        mail.send(msg)
        return True
    except Exception as e:
        print(f"ERRO DETALHADO: {str(e)}")
        print(f"Tipo do erro: {type(e)}")
        if hasattr(e, 'args'):
            print(f"Args do erro: {e.args}")
        return False


class RegisterResource(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('email', type=str, required=True)
        parser.add_argument('password', type=str, required=True)
        parser.add_argument('nome', type=str, required=True)
        args = parser.parse_args()
        
        
        usuario_existente = Usuario.query.filter_by(email=args['email']).first()
        
        if usuario_existente:
            if usuario_existente.dois_fatores_ativo:
                return {"error": "E-mail já registrado e verificado"}, 400
            
           
            um_minuto_atras = datetime.now(timezone.utc) - timedelta(seconds=60)
            codigo_recente = Codigo2FA.query.filter(
                Codigo2FA.id_usuario == usuario_existente.id,
                Codigo2FA.timestamp >= um_minuto_atras
            ).first()

            if codigo_recente:
                return {
                    "error": "Aguarde 60 segundos antes de solicitar outro código."
                }, 429  

            usuario_existente.nome = args['nome']
            usuario_existente.senha_hash = bcrypt.generate_password_hash(args['password']).decode('utf-8')
            
           
            Codigo2FA.query.filter_by(id_usuario=usuario_existente.id).delete()
            
            usuario = usuario_existente
        else:
            
            usuario = Usuario(
                nome=args['nome'],
                email=args['email'],
                senha_hash=bcrypt.generate_password_hash(args['password']).decode('utf-8'),
                dois_fatores_ativo=False,
                termos_aceitos=False  
            )
            db.session.add(usuario)
        
        db.session.commit()

        
        codigo = str(random.randint(100000, 999999))
        hash_codigo = sha256(codigo.encode()).hexdigest()

        registro_2fa = Codigo2FA(
            id=uuid4(),
            id_usuario=usuario.id,
            codigo=hash_codigo,
            timestamp=datetime.now(timezone.utc),
            expiracao=datetime.now(timezone.utc) + timedelta(minutes=15),  
            utilizado=False,
            ip_address=request.remote_addr 
        )
        db.session.add(registro_2fa)
        db.session.commit()
        
        
        registrar_log(
            usuario_id=usuario.id,
            categoria=LogCategoria.AUTENTICACAO,
            severidade=LogSeveridade.INFO,
            acao="REGISTRO_TENTATIVA",
            detalhe=f"Novo registro para {args['email']}"
        )
        
        if not enviar_email_2fa(usuario.email, codigo):
            
            registrar_log(
                usuario_id=usuario.id,
                categoria=LogCategoria.AUTENTICACAO,
                severidade=LogSeveridade.ERRO,
                acao="REGISTRO_ERRO_ENVIO_EMAIL",  
                detalhe="Falha ao enviar código 2FA"
            )
            return {"error": "Falha ao enviar código de verificação"}, 500

        additional_claims = {
            "dois_fatores": False,
            "termo": False
        }
        token_parcial = create_access_token(identity=str(usuario.id), additional_claims=additional_claims)

        return {
            "message": "Código de verificação enviado por e-mail",
            "access_token": token_parcial,
            "conta_verificada": False
        }, 201

class VerificarCodigo2FAResource(Resource):
    @jwt_required()
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('codigo', type=str, required=True)
        args = parser.parse_args()

        user_id = get_jwt_identity()
        usuario = Usuario.query.filter_by(id=user_id).first()

        if not usuario:
            return {"error": "Usuário não encontrado"}, 404
        if usuario.dois_fatores_ativo:
            return {"error": "Conta já verificada. Faça login normalmente."}, 400

        limite_tempo = datetime.now(timezone.utc) - timedelta(minutes=15)
        registro = Codigo2FA.query.filter(
            Codigo2FA.id_usuario == usuario.id,
            Codigo2FA.timestamp >= limite_tempo
        ).order_by(Codigo2FA.timestamp.desc()).first()

        registrar_log(
            usuario_id=usuario.id,
            categoria=LogCategoria.AUTENTICACAO,
            severidade=LogSeveridade.INFO,
            acao="REGISTRO_VALIDAR",
            detalhe="Validar código 2FA"
        )

        if not registro:
            registrar_log(
                usuario_id=usuario.id,
                categoria=LogCategoria.AUTENTICACAO,
                severidade=LogSeveridade.ALERTA,
                acao="REGISTRO_VALIDAR_FALHA",
                detalhe="Código 2FA expirado ou não encontrado"
            )
            return {"error": "Código 2FA expirado ou não encontrado"}, 404

        if sha256(args['codigo'].encode()).hexdigest() != registro.codigo:
            registrar_log(
                usuario_id=usuario.id,
                categoria=LogCategoria.AUTENTICACAO,
                severidade=LogSeveridade.ALERTA,
                acao="REGISTRO_VALIDAR_FALHA",
                detalhe="Código 2FA inválido"
            )
            return {"error": "Código 2FA inválido"}, 400

        usuario.dois_fatores_ativo = True
        usuario.ultimo_login = datetime.utcnow()

       
        additional_claims = {
            "dois_fatores": True,
            "termo": False
        }
        new_token = create_access_token(identity=str(usuario.id), additional_claims=additional_claims)

        new_jti = decode_token(new_token)["jti"]  

        sessao = Sessao(
            id=uuid4(),
            id_usuario=usuario.id,
            jwt_token=new_jti,  
            dois_fatores_validado=True,
            data_expiracao=datetime.now(timezone.utc) + timedelta(days=1)
        )

        db.session.delete(registro)
        db.session.add(sessao)
        db.session.commit()

        registrar_log(
            usuario_id=usuario.id,
            categoria=LogCategoria.AUTENTICACAO,
            severidade=LogSeveridade.INFO,
            acao="REGISTRO_VALIDAR_SUCESSO",
            detalhe="Registro validado com sucesso!"
        )

        return {
            "success": True,
            "message": "Conta verificada com sucesso!",
            "access_token": new_token,
            "user_id": str(usuario.id),
            "nome": usuario.nome,
            "email": usuario.email,
            "foto_perfil": usuario.foto_perfil if usuario.foto_perfil else "",
            "conta_verificada": True
        }, 200

class LoginResource(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('email', type=str, required=True)
        parser.add_argument('password', type=str, required=True)
        args = parser.parse_args()

        usuario = Usuario.query.filter_by(email=args['email']).first()
        
        registrar_log(
            usuario_id=usuario.id if usuario else None,
            categoria=LogCategoria.AUTENTICACAO,
            severidade=LogSeveridade.INFO,
            acao="LOGIN_TENTATIVA",
            detalhe=f"Tentativa de login de {request.remote_addr}"  # Adicionar IP
        )

        if not usuario or not bcrypt.check_password_hash(usuario.senha_hash, args["password"]) or (usuario.conta_exclusao_solicitada and usuario.termos_aceitos):
            registrar_log(
                usuario_id=usuario.id if usuario else None,
                categoria=LogCategoria.AUTENTICACAO,
                severidade=LogSeveridade.ALERTA,
                acao="LOGIN_TENTATIVA_FALHA",
                detalhe="Credenciais inválidas"
            )
            return {"error": "Credenciais inválidas"}, 401

        if not usuario.dois_fatores_ativo:
            registrar_log(
                usuario_id=usuario.id,
                categoria=LogCategoria.AUTENTICACAO,
                severidade=LogSeveridade.ALERTA,
                acao="LOGIN_TENTATIVA_FALHA",
                detalhe="Conta não ativada"
            )
            return {"error": "Conta não verificada. Verifique seu email."}, 403
        

        codigo = str(random.randint(100000, 999999))
        hash_codigo = sha256(codigo.encode()).hexdigest()

        registro_2fa = Codigo2FA(
            id=uuid4(),
            id_usuario=usuario.id,
            codigo=hash_codigo,
            timestamp=datetime.now(timezone.utc),
            expiracao=datetime.now(timezone.utc) + timedelta(minutes=15),  
            utilizado=False,
            ip_address=request.remote_addr 
        )
        db.session.add(registro_2fa)
        db.session.commit()

        if not enviar_email_2fa(usuario.email, codigo):
            registrar_log(
                usuario_id=usuario.id,
                categoria=LogCategoria.AUTENTICACAO,
                severidade=LogSeveridade.ERRO,
                acao="LOGIN_ERRO_ENVIO_EMAIL",
                detalhe="Falha ao enviar código 2FA"
            )
            return {"error": "Falha ao enviar código de verificação"}, 500

        return {
            "message": "Código 2FA enviado para seu email",
            "email": usuario.email,
            "conta_verificada": usuario.dois_fatores_ativo  
        }, 200

class VerificarLogin2FAResource(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('email', type=str, required=True)
        parser.add_argument('codigo', type=str, required=True)
        args = parser.parse_args()

        usuario = Usuario.query.filter_by(email=args['email']).first()
        if not usuario or (usuario.conta_exclusao_solicitada and usuario.termos_aceitos):
            return {"error": "Usuário não encontrado"}, 404

       
        registro = Codigo2FA.query.filter(
            Codigo2FA.id_usuario == usuario.id,
            Codigo2FA.expiracao > datetime.now(timezone.utc),  # Usar campo de expiração
            Codigo2FA.utilizado == False
        ).order_by(Codigo2FA.timestamp.desc()).first()

        if not registro or sha256(args['codigo'].encode()).hexdigest() != registro.codigo:
            registrar_log(
                usuario_id=usuario.id,
                categoria=LogCategoria.AUTENTICACAO,
                severidade=LogSeveridade.ALERTA,
                acao="LOGIN_VALIDAR_FALHA",
                detalhe="Código 2FA inválido ou expirado"
            )
            return {"error": "Código 2FA inválido ou expirado"}, 400

       
        registro.utilizado = True
        usuario.ultimo_login = datetime.now(timezone.utc)

        
        additional_claims = {"jti": str(uuid4())}
        token = create_access_token(
            identity=str(usuario.id),
            additional_claims=additional_claims
        )

        sessao = Sessao(
            id=uuid4(),
            id_usuario=usuario.id,
            jwt_token=additional_claims["jti"],
            dois_fatores_validado=True,  
            data_expiracao=datetime.now(timezone.utc) + timedelta(days=1),  
            ip_address=request.remote_addr  
        )
        
        db.session.add(sessao)
        db.session.commit()

        registrar_log(
            usuario_id=usuario.id,
            categoria=LogCategoria.AUTENTICACAO,
            severidade=LogSeveridade.INFO,
            acao="LOGIN_VALIDAR_SUCESSO",
            detalhe=f"Login realizado de {request.remote_addr}"
        )

        return {
            "success": True,
            "message": "Login verificado com sucesso!",
            "access_token": token,
            "user_id": str(usuario.id),
            "nome": usuario.nome,
            "email": usuario.email,
            "foto_perfil": usuario.foto_perfil or "",
            "conta_verificada": True  
        }, 200

class LogoutResource(Resource):
    @jwt_required()
    def post(self):
        """Encerra apenas a sessão atual"""
        usuario_id = get_jwt_identity()
        jti = get_jwt()["jti"]
        
        
        registrar_log(
            usuario_id=usuario_id,
            categoria=LogCategoria.AUTENTICACAO,
            severidade=LogSeveridade.INFO,
            acao="LOGOUT",
            detalhe=f"Encerramento de sessão (JTI: {jti})",
            ip_origem=request.remote_addr
        )
        
        
        Sessao.query.filter_by(
            id_usuario=usuario_id,
            jwt_token=jti
        ).delete()
        db.session.commit()
        
        return {"message": "Sessão atual encerrada com sucesso"}, 200

class UserProfileResource(Resource):
    @jwt_required()
    def get(self):
        
        usuario_id = get_jwt_identity()
        usuario = Usuario.query.get(usuario_id)
        if not usuario or usuario.conta_exclusao_solicitada:
            return {"error": "Usuário não encontrado"}, 404
        if not usuario.termos_aceitos:
            return {"error": "Termos não aceitos."}, 403
        
        
        jti = get_jwt()["jti"]
        
        
        sessao = Sessao.query.filter_by(
            id_usuario=usuario_id,
            jwt_token=jti,
            dois_fatores_validado=True  
        ).first()
        
        if not sessao:
            return {"error": "Sessão não encontrada ou não verificada"}, 401
        
        
        
        
        
        return {
            "id": str(usuario.id),
            "nome": usuario.nome,
            "email": usuario.email,
            "dois_fatores_ativo": usuario.dois_fatores_ativo,
            "data_criacao": usuario.data_criacao.isoformat() if usuario.data_criacao else None,
            "ultimo_login": usuario.ultimo_login.isoformat() if usuario.ultimo_login else None,
            "foto_perfil": usuario.foto_perfil,
            "termos_aceitos": usuario.termos_aceitos,
            "quota_armazenamento": usuario.quota_armazenamento,
            "armazenamento_utilizado": usuario.armazenamento_utilizado,
        }, 200



