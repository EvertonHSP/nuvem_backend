from flask_restful import Resource, reqparse
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, get_jwt, decode_token
from app import bcrypt, mail
from app.models import Codigo2FA, Usuario, Arquivo, Pasta, Log, LogCategoria, LogSeveridade, Sessao, Compartilhamento
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

def enviar_email_recuperacao(email, codigo):
    try:
        plain_content = f"Seu código de recuperação de senha é: {codigo}\nEste código é válido por 30 minutos."
        html_content = f"""<!DOCTYPE html>
        <html><head><meta charset="utf-8"></head>
        <body>
            <p>Você solicitou a recuperação de senha.</p>
            <p>Seu código: <strong>{codigo}</strong></p>
            <p>Este código é válido por 30 minutos.</p>
            <p>Se não foi você quem solicitou, ignore este email.</p>
        </body></html>"""
        
        msg = Message(
            subject="Recuperação de Senha",  
            recipients=[email],
            charset='utf-8',
            body=plain_content,
            html=html_content
        )
        
        msg.extra_headers = {'Content-Transfer-Encoding': '8bit'}
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Erro ao enviar email de recuperação: {str(e)}")
        return False



class RecuperarSenhaResource(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('email', type=str, required=True)
        args = parser.parse_args()

        usuario = Usuario.query.filter_by(email=args['email']).first()
        
        if not usuario or usuario.conta_exclusao_solicitada:
            return {"message": "Se o email existir em nosso sistema, um código de recuperação será enviado"}, 200

        limite_tempo = datetime.now(timezone.utc) - timedelta(minutes=15)
        codigo_existente = Codigo2FA.query.filter(
            Codigo2FA.id_usuario == usuario.id,
            Codigo2FA.timestamp >= limite_tempo,
            Codigo2FA.utilizado == False
        ).first()

        if codigo_existente:
            return {"message": "Um código de recuperação já foi enviado recentemente. Verifique seu email ou aguarde para solicitar um novo."}, 200

        codigo = str(random.randint(100000, 999999))
        hash_codigo = sha256(codigo.encode()).hexdigest()

        registro_recuperacao = Codigo2FA(
            id=uuid4(),
            id_usuario=usuario.id,
            codigo=hash_codigo,
            timestamp=datetime.now(timezone.utc),
            expiracao=datetime.now(timezone.utc) + timedelta(minutes=30),  # Código válido por 30 minutos
            utilizado=False,
            ip_address=request.remote_addr
        )

        db.session.add(registro_recuperacao)
        db.session.commit()

        if not enviar_email_recuperacao(usuario.email, codigo):
            db.session.rollback()
            registrar_log(
                usuario_id=usuario.id,
                categoria=LogCategoria.SEGURANCA,
                severidade=LogSeveridade.ERRO,
                acao="RECUPERACAO_SENHA_FALHA_ENVIO_EMAIL",
                detalhe="Falha ao enviar email de recuperação de senha"
            )
            return {"error": "Falha ao enviar email de recuperação"}, 500

        registrar_log(
            usuario_id=usuario.id,
            categoria=LogCategoria.SEGURANCA,
            severidade=LogSeveridade.INFO,
            acao="RECUPERACAO_SENHA_SOLICITADA",
            detalhe="Solicitação de recuperação de senha enviada",
            ip_origem=request.remote_addr
        )

        return {"message": "Um código de recuperação foi enviado para seu email"}, 200


class ValidarCodigoRecuperacaoResource(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('email', type=str, required=True)
        parser.add_argument('codigo', type=str, required=True)
        args = parser.parse_args()

        usuario = Usuario.query.filter_by(email=args['email']).first()
        if not usuario:
            return {"error": "Código inválido ou expirado"}, 400

        # Buscar código válido
        limite_tempo = datetime.now(timezone.utc) - timedelta(minutes=30)
        registro = Codigo2FA.query.filter(
            Codigo2FA.id_usuario == usuario.id,
            Codigo2FA.timestamp >= limite_tempo,
            Codigo2FA.utilizado == False
        ).order_by(Codigo2FA.timestamp.desc()).first()

        if not registro:
            return {"error": "Código inválido ou expirado"}, 400

        if sha256(args['codigo'].encode()).hexdigest() != registro.codigo:
            registrar_log(
                usuario_id=usuario.id,
                categoria=LogCategoria.SEGURANCA,
                severidade=LogSeveridade.ALERTA,
                acao="RECUPERACAO_SENHA_CODIGO_INVALIDO",
                detalhe="Código de recuperação inválido fornecido",
                ip_origem=request.remote_addr
            )
            return {"error": "Código inválido ou expirado"}, 400

        # Marcar código como utilizado
        registro.utilizado = True
        db.session.commit()

        # Gerar token temporário para permitir alteração de senha
        token_temp = create_access_token(
            identity=usuario.id,
            expires_delta=timedelta(minutes=15),
            additional_claims={"recuperacao_senha": True}
        )

        registrar_log(
            usuario_id=usuario.id,
            categoria=LogCategoria.SEGURANCA,
            severidade=LogSeveridade.INFO,
            acao="RECUPERACAO_SENHA_CODIGO_VALIDADO",
            detalhe="Código de recuperação validado com sucesso",
            ip_origem=request.remote_addr
        )

        return {"message": "Código validado com sucesso", "token": token_temp}, 200


class AtualizarSenhaRecuperacaoResource(Resource):
    @jwt_required()
    def post(self):
       
        claims = get_jwt()
        if not claims.get("recuperacao_senha"):
            return {"error": "Token inválido para esta operação"}, 403

        parser = reqparse.RequestParser()
        parser.add_argument('nova_senha', type=str, required=True)
        args = parser.parse_args()

        usuario_id = get_jwt_identity()
        usuario = Usuario.query.get(usuario_id)
        
        if not usuario or usuario.conta_exclusao_solicitada:
            return {"error": "Usuário não encontrado"}, 404

        
        usuario.senha_hash = bcrypt.generate_password_hash(args['nova_senha']).decode('utf-8')
        
       
        Sessao.query.filter_by(id_usuario=usuario.id).delete()
        
        db.session.commit()

        registrar_log(
            usuario_id=usuario.id,
            categoria=LogCategoria.SEGURANCA,
            severidade=LogSeveridade.INFO,
            acao="SENHA_ATUALIZADA_RECUPERACAO",
            detalhe="Senha atualizada via processo de recuperação",
            ip_origem=request.remote_addr
        )

        return {"message": "Senha atualizada com sucesso. Faça login novamente."}, 200



class ExcluirContaResource(Resource):
    @jwt_required()
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('password', type=str, required=True)
        args = parser.parse_args()

        usuario_id = get_jwt_identity()
        usuario = Usuario.query.get(usuario_id)
        
        
        registrar_log(
            usuario_id=usuario_id,
            categoria=LogCategoria.CONTA,
            severidade=LogSeveridade.INFO,
            acao="EXCLUSAO_CONTA_SOLICITADA",
            detalhe="Solicitação de exclusão de conta iniciada"
        )
        

        if not usuario or usuario.conta_exclusao_solicitada:
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.CONTA,
                severidade=LogSeveridade.ERRO,
                acao="EXCLUSAO_CONTA_FALHA",
                detalhe="Usuário não encontrado"
            )
            return {"error": "Usuário não encontrado"}, 404
            
        if not bcrypt.check_password_hash(usuario.senha_hash, args['password']):
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.CONTA,
                severidade=LogSeveridade.ALERTA,
                acao="EXCLUSAO_CONTA_FALHA",
                detalhe="Senha incorreta fornecida"
            )
            return {"error": "Senha incorreta"}, 401

      
        jti = get_jwt()["jti"]
        sessao = Sessao.query.filter_by(
            id_usuario=usuario_id,
            jwt_token=jti
        ).first()
        
        if not sessao or not sessao.dois_fatores_validado:
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.CONTA,
                severidade=LogSeveridade.ALERTA,
                acao="EXCLUSAO_CONTA_FALHA",
                detalhe="Autenticação em duas etapas necessária"
            )
            return {"error": "Autenticação em duas etapas necessária"}, 403
        
        
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
                usuario_id=usuario_id,
                categoria=LogCategoria.CONTA,
                severidade=LogSeveridade.ERRO,
                acao="EXCLUSAO_CONTA_FALHA",
                detalhe="Falha ao enviar código de verificação por email"
            )
            return {"error": "Falha ao enviar código de verificação"}, 500

        registrar_log(
            usuario_id=usuario_id,
            categoria=LogCategoria.CONTA,
            severidade=LogSeveridade.INFO,
            acao="EXCLUSAO_CONTA_CODIGO_ENVIADO",
            detalhe="Código de confirmação enviado para email do usuário"
        )

        return {"message": "Código de confirmação enviado para seu email"}, 200
 

class ConfirmarExclusaoContaResource(Resource):
    @jwt_required()
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('codigo', type=str, required=True)
        args = parser.parse_args()

        usuario_id = get_jwt_identity()
        
        
        limite_tempo = datetime.now(timezone.utc) - timedelta(minutes=15)
        registro = Codigo2FA.query.filter(
            Codigo2FA.id_usuario == usuario_id,
            Codigo2FA.timestamp >= limite_tempo
        ).order_by(Codigo2FA.timestamp.desc()).first()

        if not registro:
            return {"error": "Código 2FA expirado ou não encontrado"}, 404

        registrar_log(
            usuario_id=usuario_id,
            categoria=LogCategoria.CONTA,
            severidade=LogSeveridade.INFO,
            acao="EXCLUSAO_CONTA_VALIDAR",
            detalhe="Validação de código 2FA para exclusão de conta"
        )

        if sha256(args['codigo'].encode()).hexdigest() != registro.codigo:
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.CONTA,
                severidade=LogSeveridade.ALERTA,
                acao="EXCLUSAO_CONTA_VALIDAR_FALHA",
                detalhe="Código 2FA inválido fornecido para exclusão de conta"
            )
            return {"error": "Código 2FA inválido"}, 400

        
        db.session.delete(registro)
        
        # Obtém o usuário
        usuario = Usuario.query.get(usuario_id)
        if not usuario or usuario.conta_exclusao_solicitada:
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.CONTA,
                severidade=LogSeveridade.ERRO,
                acao="EXCLUSAO_CONTA_FALHA",
                detalhe="Usuário não encontrado durante processo de exclusão"
            )
            return {"error": "Usuário não encontrado"}, 404

        registrar_log(
            usuario_id=usuario_id,
            categoria=LogCategoria.CONTA,
            severidade=LogSeveridade.INFO,
            acao="EXCLUSAO_CONTA_INICIADA",
            detalhe="Processo de exclusão de conta iniciado",
            ip_origem=request.remote_addr
        )

        
        usuario.dois_fatores_ativo = False
        usuario.conta_exclusao_solicitada = True
        usuario.conta_exclusao_data = datetime.now(timezone.utc)

        
        Arquivo.query.filter_by(id_usuario=usuario_id).update({
            'excluido': True,
            'data_exclusao': datetime.now(timezone.utc)
        })

   
        Pasta.query.filter_by(id_usuario=usuario_id).update({
            'excluida': True,
            'data_exclusao': datetime.now(timezone.utc)
        })

       
        compartilhamentos = db.session.query(Compartilhamento).join(Arquivo).filter(
            Arquivo.id_usuario == usuario_id
        ).all()
        
        for compartilhamento in compartilhamentos:
            compartilhamento.ativo = False

       
        Sessao.query.filter_by(id_usuario=usuario_id).delete()

       
        Codigo2FA.query.filter_by(id_usuario=usuario_id).delete()

        db.session.commit()

        registrar_log(
            usuario_id=usuario_id,
            categoria=LogCategoria.CONTA,
            severidade=LogSeveridade.INFO,
            acao="EXCLUSAO_CONTA_CONCLUIDA",
            detalhe="Conta marcada para exclusão e dados anonimizados com sucesso"
        )

        return {
            "message": "Conta marcada para exclusão. Seus dados serão completamente removidos após 90 dias.",
            "logout": True  
        }, 200

