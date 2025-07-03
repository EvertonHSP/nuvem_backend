from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timedelta
from app.models import Usuario, PoliticaSistema, Log, LogCategoria, LogSeveridade, Sessao
from app.extensions import db
import os  
from uuid import uuid4
from flask import request
import json
from enum import Enum

class TermosUsoResource(Resource):
    @jwt_required()
    def get(self):
        """Retorna os termos de uso atuais"""
        termos = PoliticaSistema.query.filter_by(
            tipo_politica='uso',
            ativa=True
        ).order_by(PoliticaSistema.data_atualizacao.desc()).first()

        if not termos:
            return {"error": "Termos de uso não encontrados"}, 404

        return {
            "versao": termos.versao_termos,
            "conteudo": termos.conteudo_termos,
            "data_atualizacao": termos.data_atualizacao.isoformat()
        }, 200

    @jwt_required()
    def post(self):
        """Aceita ou recusa os termos de uso"""
        parser = reqparse.RequestParser()
        parser.add_argument('aceito', type=bool, required=True, help="Deve ser true ou false")
        args = parser.parse_args()

        usuario_id = get_jwt_identity()
        jti = get_jwt()["jti"]
        usuario = Usuario.query.get(usuario_id)

        if not usuario:
            return {"error": "Usuário não encontrado"}, 404

        termos = PoliticaSistema.query.filter_by(
            tipo_politica='uso',
            ativa=True
        ).order_by(PoliticaSistema.data_atualizacao.desc()).first()

        if not termos:
            return {"error": "Termos de uso não encontrados"}, 404

        if args['aceito']:
            
            data_aceite = datetime.utcnow()
            usuario.termos_aceitos = True
            usuario.termos_versao = termos.versao_termos
            usuario.termos_data_aceite = data_aceite
            usuario.conta_exclusao_solicitada = False
            usuario.conta_exclusao_data = None
            usuario.conta_exclusao_codigo = None

            try:
                registrar_log(
                    usuario_id=usuario_id,
                    categoria=LogCategoria.CONTA,
                    severidade=LogSeveridade.INFO,
                    acao="TERMOS_ACEITOS",
                    detalhe=f"Versão dos termos: {termos.versao_termos}"
                )
            except Exception as e:
                print(f"Erro ao registrar log (não crítico): {str(e)}")

            db.session.commit()

            return {
                "message": "Termos de uso aceitos com sucesso",
                "termos_aceitos": True,
                "versao_termos": termos.versao_termos,
                "data_aceite": data_aceite.isoformat()  
            }, 200
        else:
            
            print(f'/n sessao apagada/n')
            Sessao.query.filter_by(
                id_usuario=usuario_id,
                jwt_token=jti
            ).delete()
            data_exclusao = datetime.utcnow() + timedelta(days=90)
            usuario.termos_aceitos = False
            usuario.conta_exclusao_solicitada = True
            usuario.conta_exclusao_data = data_exclusao
            usuario.conta_exclusao_codigo = str(uuid4())

            try:
                registrar_log(
                    usuario_id=usuario_id,
                    categoria=LogCategoria.CONTA,
                    severidade=LogSeveridade.ALERTA,
                    acao="TERMOS_RECUSADOS",
                    detalhe=f"Conta marcada para exclusão em 90 dias. Código: {usuario.conta_exclusao_codigo}"
                )
            except Exception as e:
                print(f"Erro ao registrar log (não crítico): {str(e)}")

            db.session.commit()

            return {
                "message": "Termos de uso recusados. Sua conta será excluída em 90 dias.",
                "termos_aceitos": False,
                "data_exclusao": data_exclusao.isoformat(),  
                "conta_inativada": True
            }, 200

class VerificarTermosResource(Resource):
    @jwt_required()
    def get(self):
        """Verifica se o usuário aceitou os termos atuais"""
        usuario_id = get_jwt_identity()
        usuario = Usuario.query.get(usuario_id)

        if not usuario:
            return {"error": "Usuário não encontrado"}, 404

        termos = PoliticaSistema.query.filter_by(
            tipo_politica='uso',
            ativa=True
        ).order_by(PoliticaSistema.data_atualizacao.desc()).first()

        if not termos:
            return {"error": "Termos de uso não encontrados"}, 404

        
        termos_aceitos = usuario.termos_aceitos and usuario.termos_versao == termos.versao_termos

        return {
            "termos_aceitos": termos_aceitos,
            "versao_atual": termos.versao_termos,
            "versao_aceita": usuario.termos_versao if usuario.termos_aceitos else None,
            "data_aceite": usuario.termos_data_aceite.isoformat() if usuario.termos_data_aceite else None,
            "conta_exclusao_solicitada": usuario.conta_exclusao_solicitada,
            "data_exclusao": usuario.conta_exclusao_data.isoformat() if usuario.conta_exclusao_data else None
        }, 200

def registrar_log(usuario_id, categoria, severidade, acao, detalhe=None, metadados=None, ip_origem=None):
    """
    Registra uma ação no sistema de logs
    """
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
    

def check_terms_version():
    """Verifica se a versão no arquivo corresponde à versão no banco"""
    try:
        
        terms_file_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),  
            'terms',
            'termos_uso.html'
        )
        
        with open(terms_file_path, 'r', encoding='utf-8') as file:
            file_content = file.read()
        
        
        current_terms = PoliticaSistema.query.filter_by(
            tipo_politica='uso',
            ativa=True
        ).first()
        
        
        if current_terms and current_terms.conteudo_termos != file_content:
            
            new_version = str(uuid4())[:8]
            
            
            current_terms.ativa = False
            
            
            new_terms = PoliticaSistema(
                versao_termos=new_version,
                conteudo_termos=file_content,
                tipo_politica='uso',
                dias_retencao=90
            )
            
            db.session.add(new_terms)
            db.session.commit()
            return new_version
        
        return None
    except Exception as e:
        print(f"Erro ao verificar versão dos termos: {str(e)}")
        return None

