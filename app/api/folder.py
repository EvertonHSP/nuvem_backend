from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from enum import Enum 
from app.models import Usuario, Arquivo, Pasta, Log, LogCategoria, LogSeveridade, Sessao, CompartilhamentoPasta
from app.extensions import db
from uuid import uuid4
from datetime import datetime, timezone
from flask import request
from werkzeug.datastructures import FileStorage 
import os
import hashlib
from cryptography.fernet import Fernet
from werkzeug.utils import secure_filename 
import json
import mimetypes
from werkzeug.exceptions import abort
import traceback 

folder_parser = reqparse.RequestParser()
folder_parser.add_argument('nome', 
                         type=str, 
                         location='json', 
                         required=True, 
                         help='Nome da pasta é obrigatório')
folder_parser.add_argument('pasta_pai_id', 
                         type=str, 
                         location='json', 
                         required=False)

folder_share_parser = reqparse.RequestParser()
folder_share_parser = reqparse.RequestParser()
folder_share_parser.add_argument('email_usuario', 
                               type=str,
                               required=True,
                               help='E-mail do usuário a compartilhar é obrigatório')
folder_share_parser.add_argument('permissao_editar', 
                               type=bool, 
                               default=False)
folder_share_parser.add_argument('permissao_excluir', 
                               type=bool, 
                               default=False)
folder_share_parser.add_argument('permissao_compartilhar', 
                               type=bool, 
                               default=False)

unshare_parser = reqparse.RequestParser()
unshare_parser.add_argument(
    'email_usuario',
    type=str,
    required=True,
    help='E-mail do usuário é obrigatório'
)

class FolderContentResource(Resource):
    @jwt_required()
    def get(self, folder_id=None):
        try:
            def verificar_acesso(pasta_id, usuario_id):
                    
                    pasta_atual = Pasta.query.get(pasta_id)
                    if str(pasta_atual.id_usuario) == str(usuario_id):
                        return True
                    
                   
                    if CompartilhamentoPasta.query.filter_by(
                        id_pasta=pasta_id,
                        id_usuario_compartilhado=usuario_id,
                        ativo=True
                    ).first():
                        return True
                    
                    
                    if pasta_atual.id_pasta_pai:
                        return verificar_acesso(pasta_atual.id_pasta_pai, usuario_id)
                    
                    return False
            def pasta_tem_pai_compartilhado(pasta, usuario_id):
                if not pasta.id_pasta_pai:
                    
                    return False

                pai = Pasta.query.get(pasta.id_pasta_pai)
                if not pai:
                    
                    return False

                

                compartilhamento_pai = CompartilhamentoPasta.query.filter_by(
                    id_pasta=pai.id,
                    id_usuario_compartilhado=usuario_id,
                    ativo=True
                ).first()

                if compartilhamento_pai:
                    
                    return True

                return pasta_tem_pai_compartilhado(pai, usuario_id)


            usuario_id = get_jwt_identity()
            usuario = Usuario.query.get(usuario_id)
            
            
            if not usuario or usuario.conta_exclusao_solicitada:
                return {'message': 'Usuário não encontrado'}, 404
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

            if folder_id is None:
                
                subpastas = Pasta.query.filter_by(
                    id_usuario=usuario_id,
                    id_pasta_pai=None,
                    excluida=False
                ).all()

                
                todos_compartilhamentos = CompartilhamentoPasta.query.filter_by(
                    id_usuario_compartilhado=usuario_id,
                    ativo=True
                ).join(Pasta).filter(Pasta.excluida == False).all()

               
                compartilhamentos_validos = []
                for compartilhamento in todos_compartilhamentos:
                    pasta = compartilhamento.pasta
                    if not pasta_tem_pai_compartilhado(pasta, usuario_id):
                        
                        compartilhamentos_validos.append(pasta)

                
                for pasta in compartilhamentos_validos:
                    if pasta not in subpastas:
                        subpastas.append(pasta)

                
                arquivos = Arquivo.query.filter_by(
                    id_usuario=usuario_id,
                    id_pasta=None,
                    excluido=False
                ).all()

            else:
                
                pasta = Pasta.query.filter_by(
                    id=folder_id,
                    excluida=False
                ).first()
                
                if not pasta:
                    return {'message': 'Pasta não encontrada'}, 404
                
                

                if not verificar_acesso(folder_id, usuario_id):
                    return {'message': 'Acesso negado a esta pasta'}, 403
                
               
                subpastas = Pasta.query.filter_by(
                    id_pasta_pai=folder_id,
                    excluida=False
                ).all()
                
                
                arquivos = Arquivo.query.filter_by(
                    id_pasta=folder_id,
                    excluido=False
                ).all()
            
            
            
            response = {
                'pasta_atual': {
                    'id': str(folder_id) if folder_id else None,
                    'nome': pasta.nome if folder_id else 'Raiz',
                    'dono': {
                        'id': str(pasta.id_usuario) if folder_id else None,
                        'nome': pasta.usuario.nome if folder_id else None
                    } if folder_id else None
                },
                'pastas': [{
                    'id': str(pasta.id),
                    'nome': pasta.nome,
                    'data_criacao': pasta.data_criacao.isoformat(),
                    'quantidade_arquivos': len(pasta.arquivos),
                    'caminho': pasta.caminho,
                    'compartilhada': pasta.id_usuario != usuario_id,  
                    'dono': {
                        'id': str(pasta.id_usuario),
                        'nome': pasta.usuario.nome
                    } if pasta.id_usuario != usuario_id else None
                } for pasta in subpastas],
                'arquivos': [{
                    'id': str(arquivo.id),
                    'nome': arquivo.nome_original,
                    'tamanho': arquivo.tamanho,
                    'tipo': arquivo.tipo_mime,
                    'publico': arquivo.publico,
                    'data_upload': arquivo.data_upload.isoformat(),
                    'descricao': arquivo.descricao,
                    'tags': arquivo.tags,
                    'pasta_id': str(arquivo.id_pasta) if arquivo.id_pasta else None
                } for arquivo in arquivos]
            }

            return response, 200

        except Exception as e:
            print(f"ERRO AO LISTAR CONTEÚDO: {str(e)}", exc_info=True)
            return {
                'message': 'Erro ao listar conteúdo da pasta',
                'error': str(e),
                'stack_trace': traceback.format_exc()
            }, 500


class FolderCreateResource(Resource):
    @jwt_required()
    def post(self):
        try:
            usuario_id = get_jwt_identity()
            usuario = Usuario.query.get(usuario_id)
            
            if not usuario or usuario.conta_exclusao_solicitada:
                return {'message': 'Usuário não encontrado'}, 404
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


            args = folder_parser.parse_args()
            nome_pasta = args['nome']
            pasta_pai_id = args.get('pasta_pai_id')

       
            if not nome_pasta or len(nome_pasta.strip()) == 0:
                return {'message': 'Nome da pasta não pode ser vazio'}, 400

            
            existing_folder = Pasta.query.filter_by(
                id_usuario=usuario_id,
                id_pasta_pai=pasta_pai_id,
                nome=nome_pasta,
                excluida=False
            ).first()
            
            if existing_folder:
                return {'message': 'Já existe uma pasta com este nome no local especificado'}, 409

          
            pasta_pai = None
            caminho = nome_pasta
            if pasta_pai_id:
                pasta_pai = Pasta.query.filter_by(
                    id=pasta_pai_id,
                    id_usuario=usuario_id,
                    excluida=False
                ).first()
                
                if not pasta_pai:
                    return {'message': 'Pasta pai não encontrada ou acesso negado'}, 404
                
                caminho = f"{pasta_pai.caminho}/{nome_pasta}"

           
            nova_pasta = Pasta(
                id=uuid4(),
                id_usuario=usuario_id,
                nome=nome_pasta,
                id_pasta_pai=pasta_pai_id,
                caminho=caminho,
                excluida=False
            )

            db.session.add(nova_pasta)
            db.session.commit()

            
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.PASTA,
                severidade=LogSeveridade.INFO,
                acao='Criação de pasta',
                detalhe=f"Nome: {nome_pasta}",
                metadados={
                    'pasta_id': str(nova_pasta.id),
                    'pasta_pai_id': pasta_pai_id
                },
                ip_origem=request.remote_addr
            )

            return {
                'message': 'Pasta criada com sucesso',
                'pasta': {
                    'id': str(nova_pasta.id),
                    'nome': nova_pasta.nome,
                    'caminho': nova_pasta.caminho,
                    'pasta_pai_id': pasta_pai_id,
                    'data_criacao': nova_pasta.data_criacao.isoformat()
                }
            }, 201

        except Exception as e:
            db.session.rollback()
            print(f"ERRO AO CRIAR PASTA: {str(e)}")
            return {
                'message': 'Erro ao criar pasta',
                'error': str(e)
            }, 500
        

class FolderDeleteResource(Resource):
    @jwt_required()
    def delete(self, folder_id):
        try:
            usuario_id = get_jwt_identity()
            usuario = Usuario.query.get(usuario_id)
            
            if not usuario or usuario.conta_exclusao_solicitada:
                return {'message': 'Usuário não encontrado'}, 404
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

           
            pasta = Pasta.query.filter_by(
                id=folder_id, 
                id_usuario=usuario_id,
                excluida=False  
            ).first()
            
            if not pasta:
                return {'message': 'Pasta não encontrada ou já excluída'}, 404

           
            self._marcar_conteudo_como_excluido(pasta, usuario_id)

            
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.PASTA,
                severidade=LogSeveridade.INFO,
                acao='Exclusão lógica de pasta',
                detalhe=f"Pasta: {pasta.nome} - Exclusão marcada (remoção física em 90 dias)",
                metadados={
                    'pasta_id': str(pasta.id),
                    'caminho': pasta.caminho,
                    'data_exclusao': pasta.data_exclusao.isoformat()
                },
                ip_origem=request.remote_addr
            )

            return {
                'message': 'Pasta e todo seu conteúdo marcados como excluídos com sucesso',
                'pasta_id': str(pasta.id),
                'nome_pasta': pasta.nome,
                'data_exclusao': pasta.data_exclusao.isoformat(),
                'observacao': 'A pasta e seu conteúdo serão removidos fisicamente após 90 dias'
            }, 200

        except Exception as e:
            db.session.rollback()
            print(f"ERRO AO EXCLUIR PASTA: {str(e)}")
            return {
                'message': 'Erro ao marcar pasta como excluída',
                'error': str(e)
            }, 500

    def _marcar_conteudo_como_excluido(self, pasta, usuario_id):
        """Função recursiva para marcar pasta, subpastas e arquivos como excluídos"""
       
        pasta.excluida = True
        pasta.data_exclusao = datetime.now(timezone.utc)
        
        
        for arquivo in pasta.arquivos:
            if not arquivo.excluido:
                arquivo.excluido = True
                arquivo.data_exclusao = datetime.now(timezone.utc)
        
        
        subpastas = Pasta.query.filter_by(
            id_pasta_pai=pasta.id,
            excluida=False
        ).all()
        
       
        for subpasta in subpastas:
            self._marcar_conteudo_como_excluido(subpasta, usuario_id)
        
        db.session.commit()


class FolderRenameResource(Resource):
    @jwt_required()
    def put(self, folder_id):
        try:
            usuario_id = get_jwt_identity()
            usuario = Usuario.query.get(usuario_id)
            
            if not usuario or usuario.conta_exclusao_solicitada:
                return {'message': 'Usuário não encontrado'}, 404
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

            
            args = folder_parser.parse_args()
            novo_nome = args['nome']
            
            if not novo_nome or len(novo_nome.strip()) == 0:
                return {'message': 'Novo nome da pasta não pode ser vazio'}, 400

            
            pasta = Pasta.query.filter_by(
                id=folder_id,
                id_usuario=usuario_id,
                excluida=False
            ).first()
            
            if not pasta:
                return {'message': 'Pasta não encontrada ou acesso negado'}, 404

            
            existing_folder = Pasta.query.filter_by(
                id_usuario=usuario_id,
                id_pasta_pai=pasta.id_pasta_pai,
                nome=novo_nome,
                excluida=False
            ).first()
            
            if existing_folder and existing_folder.id != folder_id:
                return {'message': 'Já existe uma pasta com este nome no local especificado'}, 409

            
            nome_antigo = pasta.nome
            caminho_antigo = pasta.caminho

            
            pasta.nome = novo_nome
            
           
            if pasta.id_pasta_pai:
                pasta_pai = Pasta.query.get(pasta.id_pasta_pai)
                novo_caminho_base = f"{pasta_pai.caminho}/{novo_nome}"
            else:
                novo_caminho_base = novo_nome
                
            self._atualizar_caminho_pasta(pasta, novo_caminho_base)

            db.session.commit()

            
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.PASTA,
                severidade=LogSeveridade.INFO,
                acao='Renomeação de pasta',
                detalhe=f"De '{nome_antigo}' para '{novo_nome}'",
                metadados={
                    'pasta_id': str(pasta.id),
                    'nome_antigo': nome_antigo,
                    'novo_nome': novo_nome,
                    'caminho_antigo': caminho_antigo,
                    'novo_caminho': pasta.caminho
                },
                ip_origem=request.remote_addr
            )

            return {
                'message': 'Pasta renomeada com sucesso',
                'pasta': {
                    'id': str(pasta.id),
                    'nome_antigo': nome_antigo,
                    'novo_nome': pasta.nome,
                    'caminho': pasta.caminho,
                    'pasta_pai_id': str(pasta.id_pasta_pai) if pasta.id_pasta_pai else None
                }
            }, 200

        except Exception as e:
            db.session.rollback()
            print(f"ERRO AO RENOMEAR PASTA: {str(e)}")
            return {
                'message': 'Erro ao renomear pasta',
                'error': str(e)
            }, 500

    def _atualizar_caminho_pasta(self, pasta, novo_caminho_base):
        """Função recursiva para atualizar o caminho da pasta e de todas as subpastas"""
        caminho_antigo = pasta.caminho
        pasta.caminho = novo_caminho_base
        
        
        subpastas = Pasta.query.filter_by(
            id_pasta_pai=pasta.id,
            excluida=False
        ).all()
        
        for subpasta in subpastas:
            novo_subcaminho = f"{novo_caminho_base}/{subpasta.nome}"
            self._atualizar_caminho_pasta(subpasta, novo_subcaminho)



class FolderShareResource(Resource):
    @jwt_required()
    def post(self, folder_id):
        """Compartilha uma pasta com outro usuário via e-mail"""
        try:
           
            usuario_id = get_jwt_identity()
            usuario = Usuario.query.get(usuario_id)
            
            if not usuario or usuario.conta_exclusao_solicitada:
                return {'message': 'Usuário não encontrado'}, 404
                
            if not usuario.termos_aceitos:
                return {"error": "Termos não aceitos."}, 403
        
           
            jti = get_jwt().get("jti")
            sessao = Sessao.query.filter_by(
                id_usuario=usuario_id,
                jwt_token=jti,
                dois_fatores_validado=True  
            ).first()
            
            if not sessao:
                return {"error": "Sessão inválida ou 2FA não verificado"}, 401

            
            pasta = Pasta.query.filter_by(
                id=folder_id,
                id_usuario=usuario_id,
                excluida=False
            ).first()
            
            if not pasta:
                return {'message': 'Pasta não encontrada ou sem permissão'}, 404
            
            
            args = folder_share_parser.parse_args()
            email_usuario_compartilhado = args['email_usuario'].strip().lower()  

            
            if '@' not in email_usuario_compartilhado:
                return {'message': 'Formato de e-mail inválido'}, 400

           
            usuario_compartilhado = Usuario.query.filter(
                db.func.lower(Usuario.email) == email_usuario_compartilhado,
                Usuario.conta_exclusao_solicitada == False
            ).first()

            if not usuario_compartilhado:
                return {
                    'message': 'Usuário não encontrado',
                    'sugestao': 'Verifique se o e-mail está correto'
                }, 404
            
           
            if usuario_compartilhado.id == usuario_id:
                return {'message': 'Não é possível compartilhar uma pasta com você mesmo'}, 400
            
            
            existing_share = CompartilhamentoPasta.query.filter_by(
                id_pasta=folder_id,
                id_usuario_compartilhado=usuario_compartilhado.id,
                ativo=True
            ).first()
            
            if existing_share:
                return {
                    'message': 'Pasta já compartilhada com este usuário',
                    'compartilhamento_id': str(existing_share.id)
                }, 409
            
            
            novo_compartilhamento = CompartilhamentoPasta(
                id=uuid4(),
                id_pasta=folder_id,
                id_usuario_dono=usuario_id,
                id_usuario_compartilhado=usuario_compartilhado.id,
                permissao_editar=args.get('permissao_editar', False),
                permissao_excluir=args.get('permissao_excluir', False),
                permissao_compartilhar=args.get('permissao_compartilhar', False)
            )
            
            db.session.add(novo_compartilhamento)
            db.session.commit()
            
           
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.PASTA,
                severidade=LogSeveridade.INFO,
                acao='Compartilhamento de pasta',
                detalhe=f"Pasta '{pasta.nome}' compartilhada com {email_usuario_compartilhado}",
                metadados={
                    'pasta_id': str(pasta.id),
                    'usuario_compartilhado': str(usuario_compartilhado.id),
                    'permissoes': {
                        'editar': novo_compartilhamento.permissao_editar,
                        'excluir': novo_compartilhamento.permissao_excluir,
                        'compartilhar': novo_compartilhamento.permissao_compartilhar
                    }
                }
            )
            
            
            return {
                'message': f'Pasta compartilhada com {usuario_compartilhado.email}',
                'dados': {
                    'compartilhamento_id': str(novo_compartilhamento.id),
                    'pasta': {
                        'id': str(pasta.id),
                        'nome': pasta.nome
                    },
                    'permissões': {
                        'visualizar': True, 
                        'editar': novo_compartilhamento.permissao_editar,
                        'excluir': novo_compartilhamento.permissao_excluir,
                        'compartilhar': novo_compartilhamento.permissao_compartilhar
                    },
                    'data': novo_compartilhamento.data_compartilhamento.isoformat()
                }
            }, 201
            
        except Exception as e:
            db.session.rollback()
            print(f"ERRO: {str(e)}")
            return {
                'message': 'Erro no compartilhamento',
                'error': str(e),
                'dica': 'Tente novamente ou contate o suporte'
            }, 500


class FolderUnshareResource(Resource):
    @jwt_required()
    def delete(self, folder_id):
        """Remove o compartilhamento de uma pasta com um usuário usando e-mail"""
        try:
            usuario_id = get_jwt_identity()
            usuario = Usuario.query.get(usuario_id)
            
            if not usuario or usuario.conta_exclusao_solicitada:
                return {'message': 'Usuário não encontrado'}, 404
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

            
            args = unshare_parser.parse_args()
            email_usuario = args['email_usuario'].strip().lower()

            
            pasta = Pasta.query.filter_by(
                id=folder_id,
                id_usuario=usuario_id,
                excluida=False
            ).first()
            
            if not pasta:
                return {'message': 'Pasta não encontrada ou acesso negado'}, 404
            
            
            usuario_compartilhado = Usuario.query.filter(
                db.func.lower(Usuario.email) == email_usuario
            ).first()
            
            if not usuario_compartilhado:
                return {'message': 'Usuário com este e-mail não encontrado'}, 404
            
           
            compartilhamento = CompartilhamentoPasta.query.filter_by(
                id_pasta=folder_id,
                id_usuario_dono=usuario_id,
                id_usuario_compartilhado=usuario_compartilhado.id,
                ativo=True
            ).first()
            
            if not compartilhamento:
                return {
                    'message': 'Compartilhamento não encontrado',
                    'detalhes': f'Nenhum compartilhamento ativo encontrado para {email_usuario}'
                }, 404
            
            
            compartilhamento.ativo = False
            db.session.commit()
            
            
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.PASTA,
                severidade=LogSeveridade.INFO,
                acao='Remoção de compartilhamento de pasta',
                detalhe=f"Pasta '{pasta.nome}' não mais compartilhada com {email_usuario}",
                metadados={
                    'pasta_id': str(pasta.id),
                    'usuario_compartilhado': str(usuario_compartilhado.id),
                    'email_usuario': email_usuario
                },
                ip_origem=request.remote_addr
            )
            
            return {
                'message': 'Compartilhamento removido com sucesso',
                'detalhes': {
                    'pasta_id': str(pasta.id),
                    'pasta_nome': pasta.nome,
                    'usuario': email_usuario,
                    'data_remocao': datetime.now(timezone.utc).isoformat()
                }
            }, 200
            
        except Exception as e:
            db.session.rollback()
            print(f"ERRO AO REMOVER COMPARTILHAMENTO: {str(e)}")
            return {
                'message': 'Erro ao remover compartilhamento',
                'error': str(e),
                'dica': 'Verifique se o e-mail está correto e tente novamente'
            }, 500


class FolderSharedWithMeResource(Resource):
    @jwt_required()
    def get(self):
        """Lista todas as pastas compartilhadas com o usuário"""
        try:
            usuario_id = get_jwt_identity()
            usuario = Usuario.query.get(usuario_id)
            
            if not usuario or usuario.conta_exclusao_solicitada:
                return {'message': 'Usuário não encontrado'}, 404
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

            
            compartilhamentos = CompartilhamentoPasta.query.filter_by(
                id_usuario_compartilhado=usuario_id,
                ativo=True
            ).join(Pasta).filter(
                Pasta.excluida == False
            ).all()
            
            
            pastas_compartilhadas = []
            for compartilhamento in compartilhamentos:
                pasta = compartilhamento.pasta
                dono = compartilhamento.usuario_dono
                
                pastas_compartilhadas.append({
                    'id': str(pasta.id),
                    'nome': pasta.nome,
                    'caminho': pasta.caminho,
                    'data_criacao': pasta.data_criacao.isoformat(),
                    'dono': {
                        'id': str(dono.id),
                        'nome': dono.nome,
                        'email': dono.email
                    },
                    'permissoes': {
                        'editar': compartilhamento.permissao_editar,
                        'excluir': compartilhamento.permissao_excluir,
                        'compartilhar': compartilhamento.permissao_compartilhar
                    },
                    'data_compartilhamento': compartilhamento.data_compartilhamento.isoformat()
                })
            
            return {
                'pastas_compartilhadas': pastas_compartilhadas,
                'total': len(pastas_compartilhadas)
            }, 200
            
        except Exception as e:
            print(f"ERRO AO LISTAR PASTAS COMPARTILHADAS: {str(e)}")
            return {
                'message': 'Erro ao listar pastas compartilhadas',
                'error': str(e)
            }, 500
        



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
