from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.models import Backup, Usuario, LogCategoria, LogSeveridade, Sessao, Log
from app.extensions import db
from app.backup_manager import BackupManager
from uuid import uuid4
from datetime import datetime
import json
from flask import request
from enum import Enum
import json


backup_parser = reqparse.RequestParser()
backup_parser.add_argument('description', 
                         type=str, 
                         location='json', 
                         required=False,
                         help='Descrição opcional para o backup')

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



class BackupResource(Resource):
    @jwt_required()
    def post(self):
        
        try:
            current_user_id = get_jwt_identity()
            user = Usuario.query.get(current_user_id)
            
            if not user:
                return {'message': 'Usuário não encontrado'}, 404
            
           
            jti = get_jwt()["jti"]
            sessao = Sessao.query.filter_by(
                id_usuario=current_user_id,
                jwt_token=jti,
                dois_fatores_validado=True  
            ).first()
            
            if not sessao:
                return {"error": "Sessão não encontrada ou não verificada"}, 401

            args = backup_parser.parse_args()
            description = args.get('description')

            backup_manager = BackupManager()
            success = backup_manager.create_full_backup(current_user_id)

            if success:
              
                registrar_log(
                    usuario_id=current_user_id,
                    categoria=LogCategoria.SISTEMA,
                    severidade=LogSeveridade.INFO,
                    acao='Backup criado',
                    detalhe='Backup completo do sistema realizado com sucesso',
                    ip_origem=request.remote_addr
                )
                
                return {
                    'message': 'Backup criado com sucesso',
                    'status': 'completed',
                    'timestamp': datetime.utcnow().isoformat()
                }, 201
            else:
                
                registrar_log(
                    usuario_id=current_user_id,
                    categoria=LogCategoria.SISTEMA,
                    severidade=LogSeveridade.ERRO,
                    acao='Falha no backup',
                    detalhe='Falha ao tentar criar backup completo',
                    ip_origem=request.remote_addr
                )
                
                return {
                    'message': 'Falha ao criar backup',
                    'status': 'failed',
                    'timestamp': datetime.utcnow().isoformat()
                }, 500

        except Exception as e:
            
            registrar_log(
                usuario_id=current_user_id,
                categoria=LogCategoria.SISTEMA,
                severidade=LogSeveridade.CRITICO,
                acao='Erro no backup',
                detalhe=f'Exceção durante criação de backup: {str(e)}',
                ip_origem=request.remote_addr
            )
            
            return {
                'message': 'Erro durante a criação do backup',
                'error': str(e),
                'status': 'error'
            }, 500

    @jwt_required()
    def get(self):
        """Lista todos os backups do usuário"""
        try:
            current_user_id = get_jwt_identity()
            user = Usuario.query.get(current_user_id)
            
            if not user:
                return {'message': 'Usuário não encontrado'}, 404
            
            # Verificar sessão e 2FA
            jti = get_jwt()["jti"]
            sessao = Sessao.query.filter_by(
                id_usuario=current_user_id,
                jwt_token=jti,
                dois_fatores_validado=True  
            ).first()
            
            if not sessao:
                return {"error": "Sessão não encontrada ou não verificada"}, 401

           
            backups = Backup.query.filter_by(id_usuario=current_user_id)\
                                .order_by(Backup.data_criacao.desc())\
                                .all()

            backup_list = []
            for backup in backups:
                backup_list.append({
                    'id': str(backup.id),
                    'type': backup.tipo,
                    'path': backup.caminho,
                    'size': backup.tamanho,
                    'date': backup.data_criacao.isoformat(),
                    'status': backup.status,
                    'metadata': backup.metadados if backup.metadados else {}
                })

            
            registrar_log(
                usuario_id=current_user_id,
                categoria=LogCategoria.SISTEMA,
                severidade=LogSeveridade.INFO,
                acao='Listagem de backups',
                detalhe=f'Listados {len(backup_list)} backups',
                ip_origem=request.remote_addr
            )

            return {
                'backups': backup_list,
                'count': len(backup_list),
                'timestamp': datetime.utcnow().isoformat()
            }, 200

        except Exception as e:
           
            registrar_log(
                usuario_id=current_user_id,
                categoria=LogCategoria.SISTEMA,
                severidade=LogSeveridade.ERRO,
                acao='Erro ao listar backups',
                detalhe=f'Exceção durante listagem de backups: {str(e)}',
                ip_origem=request.remote_addr
            )
            
            return {
                'message': 'Erro ao listar backups',
                'error': str(e),
                'status': 'error'
            }, 500


class BackupDetailResource(Resource):
    @jwt_required()
    def get(self, backup_id):
        """Obtém detalhes de um backup específico"""
        try:
            current_user_id = get_jwt_identity()
            user = Usuario.query.get(current_user_id)
            
            if not user:
                return {'message': 'Usuário não encontrado'}, 404
            
           
            jti = get_jwt()["jti"]
            sessao = Sessao.query.filter_by(
                id_usuario=current_user_id,
                jwt_token=jti,
                dois_fatores_validado=True  
            ).first()
            
            if not sessao:
                return {"error": "Sessão não encontrada ou não verificada"}, 401

            backup = Backup.query.filter_by(id=backup_id, id_usuario=current_user_id).first()
            
            if not backup:
                return {'message': 'Backup não encontrado ou acesso negado'}, 404

            
            registrar_log(
                usuario_id=current_user_id,
                categoria=LogCategoria.SISTEMA,
                severidade=LogSeveridade.INFO,
                acao='Consulta de backup',
                detalhe=f'Consultado backup ID: {backup_id}',
                ip_origem=request.remote_addr
            )

            return {
                'id': str(backup.id),
                'type': backup.tipo,
                'path': backup.caminho,
                'size': backup.tamanho,
                'date': backup.data_criacao.isoformat(),
                'status': backup.status,
                'metadata': backup.metadados if backup.metadados else {},
                'timestamp': datetime.utcnow().isoformat()
            }, 200

        except Exception as e:
            
            registrar_log(
                usuario_id=current_user_id,
                categoria=LogCategoria.SISTEMA,
                severidade=LogSeveridade.ERRO,
                acao='Erro ao consultar backup',
                detalhe=f'Exceção durante consulta de backup: {str(e)}',
                ip_origem=request.remote_addr
            )
            
            return {
                'message': 'Erro ao consultar backup',
                'error': str(e),
                'status': 'error'
            }, 500

    @jwt_required()
    def delete(self, backup_id):
        """Remove um backup específico"""
        try:
            current_user_id = get_jwt_identity()
            user = Usuario.query.get(current_user_id)
            
            if not user:
                return {'message': 'Usuário não encontrado'}, 404
            
           
            jti = get_jwt()["jti"]
            sessao = Sessao.query.filter_by(
                id_usuario=current_user_id,
                jwt_token=jti,
                dois_fatores_validado=True  
            ).first()
            
            if not sessao:
                return {"error": "Sessão não encontrada ou não verificada"}, 401

            backup = Backup.query.filter_by(id=backup_id, id_usuario=current_user_id).first()
            
            if not backup:
                return {'message': 'Backup não encontrado ou acesso negado'}, 404

          
            backup_manager = BackupManager()
            

            db.session.delete(backup)
            db.session.commit()

         
            registrar_log(
                usuario_id=current_user_id,
                categoria=LogCategoria.SISTEMA,
                severidade=LogSeveridade.INFO,
                acao='Backup removido',
                detalhe=f'Backup ID: {backup_id} removido',
                ip_origem=request.remote_addr
            )

            return {
                'message': 'Backup removido com sucesso',
                'id': str(backup_id),
                'timestamp': datetime.utcnow().isoformat()
            }, 200

        except Exception as e:
            db.session.rollback()
            registrar_log(
                usuario_id=current_user_id,
                categoria=LogCategoria.SISTEMA,
                severidade=LogSeveridade.ERRO,
                acao='Erro ao remover backup',
                detalhe=f'Exceção durante remoção de backup: {str(e)}',
                ip_origem=request.remote_addr
            )
            
            return {
                'message': 'Erro ao remover backup',
                'error': str(e),
                'status': 'error'
            }, 500