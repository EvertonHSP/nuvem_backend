from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from enum import Enum 
from app.models import Usuario, Arquivo, Pasta, Log, LogCategoria, LogSeveridade, Sessao, Compartilhamento
from app.extensions import db
from uuid import uuid4
from datetime import datetime, timezone
from flask import request, send_file, abort, send_file, make_response
from werkzeug.datastructures import FileStorage 
import os
import hashlib
from cryptography.fernet import Fernet
from werkzeug.utils import secure_filename 
import json
import mimetypes
from werkzeug.exceptions import abort


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

ALLOWED_EXTENSIONS = {
    # Imagens
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'tiff', 'svg',
    # Documentos
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf', 'odt', 'ods', 'odp', 'epub',
    # Arquivos compactados
    'zip', 'rar', '7z', 'tar', 'gz', 'fzip',
    # Áudio
    'mp3', 'wav', 'ogg', 'flac', 'aac',
    # Vídeo
    'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv',
    # Outros
    'csv', 'json', 'xml', 'html', 'htm', 'js', 'css', 'py', 'php', 'exe', 'c', 'py', 'cdr', 
}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

upload_parser = reqparse.RequestParser()
upload_parser.add_argument('file', 
                         type=FileStorage, 
                         location='files', 
                         required=True, 
                         help='Arquivo é obrigatório')
upload_parser.add_argument('is_public', 
                         type=bool, 
                         location='form', 
                         default=False)
upload_parser.add_argument('folder_id', 
                         type=str, 
                         location='form')
upload_parser.add_argument('description', 
                         type=str, 
                         location='form')
upload_parser.add_argument('tags', 
                         type=str, 
                         location='form')

rename_parser = reqparse.RequestParser()
rename_parser.add_argument('novo_nome', 
                            type=str, 
                            required=True, 
                            help='Novo nome do arquivo é obrigatório')
rename_parser.add_argument('manter_extensao', 
                            type=bool, 
                            default=True,
                            help='Se deve manter a extensão original do arquivo')

share_parser = reqparse.RequestParser()
share_parser.add_argument('expira_em', 
                        type=str, 
                        location='json', 
                        required=False,
                        help='Data de expiração no formato YYYY-MM-DD')
share_parser.add_argument('max_acessos', 
                        type=int, 
                        location='json', 
                        required=False,
                        help='Número máximo de acessos')

class FileUploadResource(Resource):
    @jwt_required()
    def post(self):
        try:
            
            if not request.content_type.startswith('multipart/form-data'):
                return {'message': 'Content-Type deve ser multipart/form-data'}, 415

            usuario_id = get_jwt_identity()
            usuario = Usuario.query.get(usuario_id)
            if not usuario or usuario.conta_exclusao_solicitada:
                return {'message': 'Usuário não encontrado'}, 404
            if not usuario.termos_aceitos:
                return {"error": "Termos não aceitos."}, 403
            
            jti = get_jwt()["jti"]
            print(jti)
            sessao = Sessao.query.filter_by(
                id_usuario=usuario_id,
                jwt_token=jti,
                dois_fatores_validado=True  
            ).first()
            if not sessao:
                return {"error": "Sessão não encontrada ou não verificada"}, 401

            

            args = upload_parser.parse_args()
            uploaded_file = args['file']
            
            if not uploaded_file:
                return {'message': 'Nenhum arquivo recebido'}, 400

           
            if not allowed_file(uploaded_file.filename):
                return {'message': 'Tipo de arquivo não permitido'}, 400

            
            uploaded_file.seek(0, os.SEEK_END)
            file_size = uploaded_file.tell()
            uploaded_file.seek(0)

            if usuario.armazenamento_utilizado + file_size > usuario.quota_armazenamento:
                return {'message': 'Quota de armazenamento excedida'}, 400

            
            upload_dir = os.path.join('uploads', str(usuario.id))
            os.makedirs(upload_dir, exist_ok=True)

            
            file_ext = os.path.splitext(uploaded_file.filename)[1].lower()
            unique_filename = f"{uuid4().hex}{file_ext}"
            file_path = os.path.join(upload_dir, unique_filename)


            
            folder_id = args.get('folder_id')
            existing_file = Arquivo.query.filter_by(
                id_usuario=usuario_id,
                nome_original=uploaded_file.filename,
                id_pasta=folder_id,
                excluido=False
            ).first()

            if existing_file:
                return {
                    'message': 'Já existe um arquivo com este nome na pasta de destino',
                    'file_id': str(existing_file.id),
                    'existing_file': True
                }, 409
            
            
            uploaded_file.save(file_path)

            
            file_hash = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    file_hash.update(chunk)

            
            mime_type, _ = mimetypes.guess_type(uploaded_file.filename)
            if not mime_type:
                mime_type = 'application/octet-stream'

            
            new_file = Arquivo(
                id=uuid4(),
                id_usuario=usuario.id,
                nome_criptografado=unique_filename,
                nome_original=uploaded_file.filename,
                caminho_armazenamento=file_path,
                tamanho=file_size,
                tipo_mime=mime_type,
                publico=args['is_public'],
                descricao=args.get('description'),
                tags=args.get('tags'),
                hash_arquivo=file_hash.hexdigest(),
                id_pasta=args.get('folder_id')
            )

            db.session.add(new_file)
            usuario.armazenamento_utilizado += file_size
            db.session.commit()

            return {
                'message': 'Upload realizado com sucesso',
                'file_id': str(new_file.id),
                'file_name': uploaded_file.filename,
                'file_size': file_size,
                'mime_type': mime_type
            }, 201

        except Exception as e:
            db.session.rollback()
            
            if 'file_path' in locals() and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except:
                    pass
            
            print(f"ERRO NO UPLOAD: {str(e)}")
            return {
                'message': 'Erro no processamento do arquivo',
                'error': str(e)
            }, 500
        
class FileDownloadResource(Resource):
    @jwt_required()
    def get(self, file_id):
        try:
            usuario_id = get_jwt_identity()
            usuario = Usuario.query.get(usuario_id)
            jti = get_jwt()["jti"]

            if not usuario or usuario.conta_exclusao_solicitada:
                return {'message': 'Usuário não encontrado'}, 404
            if not usuario.termos_aceitos:
                return {"error": "Termos não aceitos."}, 403
            
            
            sessao = Sessao.query.filter_by(
                id_usuario=usuario_id,
                jwt_token=jti,
                dois_fatores_validado=True  
            ).first()
        
            if not sessao:
                return {"error": "Sessão não encontrada ou não verificada"}, 401
            
            arquivo = Arquivo.query.filter_by(id=file_id, id_usuario=usuario_id).first()
            
            if not arquivo:
                
                arquivo = Arquivo.query.filter_by(id=file_id, publico=True).first()
                if not arquivo:
                    return {'message': 'Arquivo não encontrado ou acesso negado'}, 404

            
            if not os.path.exists(arquivo.caminho_armazenamento):
                return {'message': 'Arquivo não encontrado no servidor'}, 404

            
            file_hash = hashlib.sha256()
            with open(arquivo.caminho_armazenamento, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    file_hash.update(chunk)
            
            if file_hash.hexdigest() != arquivo.hash_arquivo:
                return {'message': 'Arquivo corrompido'}, 500

           
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.ARQUIVO,
                severidade=LogSeveridade.INFO,
                acao='Download de arquivo',
                detalhe=f"Arquivo: {arquivo.nome_original}",
                metadados={
                    'file_id': str(arquivo.id),
                    'file_size': arquivo.tamanho
                },
                ip_origem=request.remote_addr
            )

           
            return send_file(
                arquivo.caminho_armazenamento,
                as_attachment=True,
                download_name=secure_filename(arquivo.nome_original),
                mimetype=arquivo.tipo_mime
            )

        except Exception as e:
            print(f"ERRO NO DOWNLOAD: {str(e)}")
            return {
                'message': 'Erro ao processar download',
                'error': str(e)
            }, 500

class FileDeleteResource(Resource):
    @jwt_required()
    def delete(self, file_id):
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

            
            arquivo = Arquivo.query.filter_by(
                id=file_id, 
                id_usuario=usuario_id,
                excluido=False  
            ).first()
            
            if not arquivo:
                return {'message': 'Arquivo não encontrado ou já excluído'}, 404

            
            arquivo.excluido = True
            arquivo.data_exclusao = datetime.now(timezone.utc)
            
            
            db.session.commit()

            
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.ARQUIVO,
                severidade=LogSeveridade.INFO,
                acao='Exclusão lógica de arquivo',
                detalhe=f"Arquivo: {arquivo.nome_original} - Exclusão marcada (remoção física em 90 dias)",
                metadados={
                    'file_id': str(arquivo.id),
                    'file_size': arquivo.tamanho,
                    'data_exclusao': arquivo.data_exclusao.isoformat()
                },
                ip_origem=request.remote_addr
            )

            return {
                'message': 'Arquivo marcado como excluído com sucesso',
                'file_id': str(arquivo.id),
                'nome_arquivo': arquivo.nome_original,
                'data_exclusao': arquivo.data_exclusao.isoformat(),
                'observacao': 'O arquivo será removido fisicamente após 90 dias'
            }, 200

        except Exception as e:
            db.session.rollback()
            print(f"ERRO AO EXCLUIR ARQUIVO: {str(e)}")
            return {
                'message': 'Erro ao marcar arquivo como excluído',
                'error': str(e)
            }, 500

class FileRenameResource(Resource):
    @jwt_required()
    def put(self, file_id):
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

            
            args = self.rename_parser.parse_args()
            novo_nome = args['novo_nome']
            manter_extensao = args['manter_extensao']

            
            arquivo = Arquivo.query.filter_by(
                id=file_id,
                id_usuario=usuario_id,
                excluido=False
            ).first()
            
            if not arquivo:
                return {'message': 'Arquivo não encontrado ou acesso negado'}, 404

            
            extensao_original = os.path.splitext(arquivo.nome_original)
            
            
            if manter_extensao:
                
                novo_nome_base, extensao_nova = os.path.splitext(novo_nome)
                if not extensao_nova:
                    novo_nome = f"{novo_nome}{extensao_original}"
                elif extensao_nova.lower() != extensao_original.lower():
                    return {'message': 'Não é permitido alterar a extensão do arquivo'}, 400
            else:
                
                if not allowed_file(novo_nome):
                    return {'message': 'Tipo de arquivo não permitido'}, 400

           
            novo_nome = secure_filename(novo_nome)
            
           
            existing_file = Arquivo.query.filter_by(
                id_usuario=usuario_id,
                nome_original=novo_nome,
                id_pasta=arquivo.id_pasta,
                excluido=False
            ).first()
            
            if existing_file and existing_file.id != file_id:
                return {'message': 'Já existe um arquivo com este nome na pasta de destino'}, 409

           
            nome_antigo = arquivo.nome_original

            
            arquivo.nome_original = novo_nome
            arquivo.data_modificacao = datetime.now(timezone.utc)
            
            db.session.commit()

            
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.ARQUIVO,
                severidade=LogSeveridade.INFO,
                acao='Renomeação de arquivo',
                detalhe=f"De '{nome_antigo}' para '{novo_nome}'",
                metadados={
                    'arquivo_id': str(arquivo.id),
                    'nome_antigo': nome_antigo,
                    'novo_nome': novo_nome,
                    'pasta_id': str(arquivo.id_pasta) if arquivo.id_pasta else None
                },
                ip_origem=request.remote_addr
            )

            return {
                'message': 'Arquivo renomeado com sucesso',
                'arquivo': {
                    'id': str(arquivo.id),
                    'nome_antigo': nome_antigo,
                    'novo_nome': arquivo.nome_original,
                    'pasta_id': str(arquivo.id_pasta) if arquivo.id_pasta else None,
                    'data_modificacao': arquivo.data_modificacao.isoformat()
                }
            }, 200

        except Exception as e:
            db.session.rollback()
            print(f"ERRO AO RENOMEAR ARQUIVO: {str(e)}")
            return {
                'message': 'Erro ao renomear arquivo',
                'error': str(e)
            }, 500

class FileVisibilityResource(Resource):
    @jwt_required()
    def patch(self, file_id):
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

            
            arquivo = Arquivo.query.filter_by(id=file_id, id_usuario=usuario_id).first()
            if not arquivo:
                return {'message': 'Arquivo não encontrado ou acesso negado'}, 404

            
            parser = reqparse.RequestParser()
            parser.add_argument('is_public', type=bool, required=True, help='Status de visibilidade é obrigatório (true/false)')
            args = parser.parse_args()

           
            novo_status = args['is_public']
            arquivo.publico = novo_status
            arquivo.data_modificacao = datetime.now(timezone.utc)
            
            db.session.commit()

            
            registrar_log(
                usuario_id=usuario_id,
                categoria=LogCategoria.ARQUIVO,
                severidade=LogSeveridade.INFO,
                acao='Alteração de visibilidade do arquivo',
                detalhe=f"Arquivo: {arquivo.nome_original} - Novo status: {'Público' if novo_status else 'Privado'}",
                metadados={
                    'file_id': str(arquivo.id),
                    'novo_status': novo_status
                },
                ip_origem=request.remote_addr
            )

            return {
                'message': 'Visibilidade do arquivo atualizada com sucesso',
                'file_id': str(arquivo.id),
                'nome_arquivo': arquivo.nome_original,
                'is_public': arquivo.publico
            }, 200

        except Exception as e:
            db.session.rollback()
            print(f"ERRO AO ALTERAR VISIBILIDADE: {str(e)}")
            return {
                'message': 'Erro ao alterar visibilidade do arquivo',
                'error': str(e)
            }, 500

class FilePreviewResource(Resource):
    @jwt_required()
    def get(self, file_id):
        """Endpoint privado para visualização de arquivos (requer autenticação)"""
        try:
            usuario_id = get_jwt_identity()
            usuario = Usuario.query.get(usuario_id)
            
            if not usuario or usuario.conta_exclusao_solicitada:
                return abort(404, description="Usuário não encontrado")
            if not usuario.termos_aceitos:
                return {"error": "Termos não aceitos."}, 403
                
            jti = get_jwt()["jti"]
            sessao = Sessao.query.filter_by(
                id_usuario=usuario_id,
                jwt_token=jti,
                dois_fatores_validado=True  
            ).first()
            
            if not sessao:
                return abort(401, description="Sessão não encontrada ou não verificada")

           
            arquivo = Arquivo.query.filter_by(
                id=file_id,
                id_usuario=usuario_id,
                excluido=False
            ).first()
            
            if not arquivo:
                return abort(404, description="Arquivo não encontrado ou acesso negado")

            
            viewable_types = [
                'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml',
                'application/pdf', 
                'text/plain', 'text/html', 'text/css', 'text/javascript',
                'application/json'
            ]

            
            if arquivo.tipo_mime in viewable_types:
                
                registrar_log(
                    usuario_id=usuario_id,
                    categoria=LogCategoria.ARQUIVO,
                    severidade=LogSeveridade.INFO,
                    acao='Visualização de arquivo',
                    detalhe=f"Arquivo: {arquivo.nome_original}",
                    metadados={
                        'file_id': str(arquivo.id),
                        'file_type': arquivo.tipo_mime,
                        'preview': True
                    },
                    ip_origem=request.remote_addr
                )

                
                return {
                    'preview_available': True,
                    'file_id': str(arquivo.id),
                    'file_name': arquivo.nome_original,
                    'file_size': arquivo.tamanho,
                    'file_type': arquivo.tipo_mime,
                    'is_image': arquivo.tipo_mime.startswith('image/'),
                    'is_pdf': arquivo.tipo_mime == 'application/pdf',
                    'is_text': arquivo.tipo_mime.startswith('text/') or 
                              arquivo.tipo_mime == 'application/json',
                    'download_url': f'/api/files/{arquivo.id}/download',
                    'preview_url': f'/api/files/{arquivo.id}/preview-content'
                }, 200
            else:
                
                return {
                    'preview_available': False,
                    'file_id': str(arquivo.id),
                    'file_name': arquivo.nome_original,
                    'file_size': arquivo.tamanho,
                    'file_type': arquivo.tipo_mime,
                    'download_url': f'/api/files/{arquivo.id}/download'
                }, 200

        except Exception as e:
            print(f"ERRO NA PRÉ-VISUALIZAÇÃO: {str(e)}")
            return abort(500, description=f"Erro ao processar a pré-visualização: {str(e)}")

class FilePreviewContentResource(Resource):
    @jwt_required()
    def get(self, file_id):
        """Endpoint que serve o conteúdo do arquivo para pré-visualização (requer autenticação)"""
        
        try:
            usuario_id = get_jwt_identity()
            usuario = Usuario.query.get(usuario_id)
            
            if not usuario or usuario.conta_exclusao_solicitada:
                return abort(404, description="Usuário não encontrado")
            if not usuario.termos_aceitos:
                return {"error": "Termos não aceitos."}, 403
                
            jti = get_jwt()["jti"]
            sessao = Sessao.query.filter_by(
                id_usuario=usuario_id,
                jwt_token=jti,
                dois_fatores_validado=True  
            ).first()
            
            if not sessao:
                return abort(401, description="Sessão não encontrada ou não verificada")

            
            arquivo = Arquivo.query.filter_by(
                id=file_id,
                id_usuario=usuario_id,
                excluido=False
            ).first()
            print("\n\n\nCaminho do arquivo no DB:", arquivo.caminho_armazenamento)
            print("Caminho absoluto:", os.path.abspath(arquivo.caminho_armazenamento))
            print("Arquivo existe?", os.path.exists(arquivo.caminho_armazenamento))
            if not arquivo:
                return abort(404, description="Arquivo não encontrado ou acesso negado")
            
            
            caminho_absoluto = os.path.abspath(arquivo.caminho_armazenamento)
            
            
            print(f"""
            [DEBUG] Caminho no banco: {arquivo.caminho_armazenamento}
            Caminho absoluto: {caminho_absoluto}
            Existe? {os.path.exists(caminho_absoluto)}
            """)
            
            if not os.path.exists(caminho_absoluto):
                return abort(404, description="Arquivo físico não encontrado no servidor")
            
            
            viewable_types = [
                'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/svg+xml',
                'application/pdf', 
                'text/plain', 'text/html', 'text/css', 'text/javascript',
                'application/json'
            ]

            if arquivo.tipo_mime not in viewable_types:
                return abort(400, description="Este tipo de arquivo não pode ser pré-visualizado")

            
            if arquivo.tipo_mime.startswith('image/'):
                return send_file(
                    caminho_absoluto,  
                    mimetype=arquivo.tipo_mime
                )
            elif arquivo.tipo_mime == 'application/pdf':
                response = make_response(send_file(
                    caminho_absoluto,  
                    mimetype=arquivo.tipo_mime
                ))
                response.headers['Content-Disposition'] = f'inline; filename="{secure_filename(arquivo.nome_original)}"'
                return response
            else:
                
                with open(caminho_absoluto, 'rb') as f: 
                    content = f.read()
                
                response = make_response(content)
                response.headers['Content-Type'] = arquivo.tipo_mime
                response.headers['Content-Disposition'] = f'inline; filename="{secure_filename(arquivo.nome_original)}"'
                return response

        except Exception as e:
            print(f"ERRO NO SERVIÇO DE CONTEÚDO: {str(e)}")
            return abort(500, description=f"Erro ao servir conteúdo para pré-visualização: {str(e)}")

class FileShareResource(Resource):
    @jwt_required()
    def post(self, file_id):
        """Gera um link de compartilhamento para um arquivo"""
        try:
            args = share_parser.parse_args()  
            usuario_id = get_jwt_identity()
            usuario = Usuario.query.get(usuario_id)

            if not usuario or usuario.conta_exclusao_solicitada:
                return {'message': 'Usuário não encontrado'}, 404
            if not usuario.termos_aceitos:
                return {"error": "Termos não aceitos."}, 403

          
            arquivo = Arquivo.query.filter_by(
                id=file_id,
                id_usuario=usuario_id,
                excluido=False
            ).first()
            
            if not arquivo:
                return {'message': 'Arquivo não encontrado ou acesso negado'}, 404

          
            token = hashlib.sha256(f"{file_id}{datetime.now().isoformat()}{usuario_id}".encode()).hexdigest()

            
            novo_compartilhamento = Compartilhamento(
                id_arquivo=file_id,
                token=token,
                data_expiracao=args.get('expira_em'),
                max_acessos=args.get('max_acessos'),
                ip_origem=request.remote_addr
            )

            db.session.add(novo_compartilhamento)
            db.session.commit()

            
            share_url = f"{request.host_url}api/share/{token}"
            
            return {
                'message': 'Link de compartilhamento gerado com sucesso',
                'share_url': share_url,
                'expires_at': args.get('expira_em'),
                'max_access': args.get('max_acessos')
            }, 201

        except Exception as e:
            db.session.rollback()
            return {
                'message': 'Erro ao gerar link de compartilhamento',
                'error': str(e)
            }, 500

class FileShareViewResource(Resource):
    def get(self, token):
        """Endpoint público para visualização de arquivos compartilhados"""
        try:
            
            compartilhamento = Compartilhamento.query.filter_by(
                token=token,
                ativo=True
            ).first()
            
            if not compartilhamento:
                return abort(404, description="Link não encontrado ou expirado")

            
            if compartilhamento.data_expiracao:
                now = datetime.now(timezone.utc)
                if compartilhamento.data_expiracao < now:
                    return abort(403, description="Este link expirou")

            
            if compartilhamento.max_acessos and compartilhamento.acessos >= compartilhamento.max_acessos:
                return abort(403, description="Limite de acessos atingido")

            arquivo = compartilhamento.arquivo
            compartilhamento.acessos += 1
            db.session.commit()

            
            if arquivo.publico:
                
                viewable_types = [
                    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
                    'application/pdf', 
                    'text/plain', 'text/html', 'text/css',
                    'application/json'
                ]

                if arquivo.tipo_mime in viewable_types:
                    
                    if arquivo.tipo_mime.startswith('image/'):
                        content = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <title>{arquivo.nome_original}</title>
                            <style>
                                body {{ font-family: Arial, sans-serif; text-align: center; }}
                                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                                img {{ max-width: 100%; max-height: 80vh; }}
                                .btn {{ 
                                    display: inline-block; 
                                    padding: 10px 20px; 
                                    background: #4CAF50; 
                                    color: white; 
                                    text-decoration: none; 
                                    border-radius: 5px; 
                                    margin-top: 20px;
                                }}
                            </style>
                        </head>
                        <body>
                            <div class="container">
                                <h2>{arquivo.nome_original}</h2>
                                <img src="/api/files/download-shared/{arquivo.id}?token={token}&preview=true" alt="{arquivo.nome_original}">
                                <div>
                                    <p>Tamanho: {round(arquivo.tamanho/(1024*1024), 2)} MB</p>
                                    <a href="/api/files/download-shared/{arquivo.id}?token={token}" class="btn">Baixar Arquivo</a>
                                </div>
                            </div>
                        </body>
                        </html>
                        """
                    elif arquivo.tipo_mime == 'application/pdf':
                        content = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <title>{arquivo.nome_original}</title>
                            <style>
                                body {{ font-family: Arial, sans-serif; }}
                                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                                .btn {{ 
                                    display: inline-block; 
                                    padding: 10px 20px; 
                                    background: #4CAF50; 
                                    color: white; 
                                    text-decoration: none; 
                                    border-radius: 5px; 
                                    margin-top: 20px;
                                }}
                                iframe {{
                                    width: 100%;
                                    height: 80vh;
                                    border: none;
                                }}
                            </style>
                        </head>
                        <body>
                            <div class="container">
                                <h2>{arquivo.nome_original}</h2>
                                <iframe src="/api/files/download-shared/{arquivo.id}?token={token}&preview=true"></iframe>
                                <div>
                                    <p>Tamanho: {round(arquivo.tamanho/(1024*1024), 2)} MB</p>
                                    <a href="/api/files/download-shared/{arquivo.id}?token={token}" class="btn">Baixar Arquivo</a>
                                </div>
                            </div>
                        </body>
                        </html>
                        """
                    else: 
                        content = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <title>{arquivo.nome_original}</title>
                            <style>
                                body {{ font-family: Arial, sans-serif; }}
                                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                                .btn {{ 
                                    display: inline-block; 
                                    padding: 10px 20px; 
                                    background: #4CAF50; 
                                    color: white; 
                                    text-decoration: none; 
                                    border-radius: 5px; 
                                    margin-top: 20px;
                                }}
                                iframe {{
                                    width: 100%;
                                    height: 80vh;
                                    border: 1px solid #ddd;
                                }}
                            </style>
                        </head>
                        <body>
                            <div class="container">
                                <h2>{arquivo.nome_original}</h2>
                                <iframe src="/api/files/download-shared/{arquivo.id}?token={token}&preview=true"></iframe>
                                <div>
                                    <p>Tamanho: {round(arquivo.tamanho/(1024*1024), 2)} MB</p>
                                    <a href="/api/files/download-shared/{arquivo.id}?token={token}" class="btn">Baixar Arquivo</a>
                                </div>
                            </div>
                        </body>
                        </html>
                        """
                else:
                    
                    content = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>{arquivo.nome_original}</title>
                        <style>
                            body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                            .container {{ max-width: 600px; margin: 0 auto; }}
                            .btn {{ 
                                display: inline-block; 
                                padding: 10px 20px; 
                                background: #4CAF50; 
                                color: white; 
                                text-decoration: none; 
                                border-radius: 5px; 
                                margin-top: 20px;
                            }}
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>{arquivo.nome_original}</h1>
                            <p>Tamanho: {round(arquivo.tamanho/(1024*1024), 2)} MB</p>
                            <p>Tipo: {arquivo.tipo_mime}</p>
                            <a href="/api/files/download-shared/{arquivo.id}?token={token}" class="btn">Baixar Arquivo</a>
                        </div>
                    </body>
                    </html>
                    """

                response = make_response(content)
                response.headers['Content-Type'] = 'text/html'
                return response
            
            return abort(403, description="Este arquivo é privado e não pode ser acessado através deste link")

        except Exception as e:
            return abort(500, description=f"Erro ao processar o link: {str(e)}")

class FileDownloadSharedResource(Resource):
    def get(self, file_id):
        """Endpoint para download de arquivos compartilhados"""
        try:
            token = request.args.get('token')
            preview = request.args.get('preview', 'false').lower() == 'true'
            
            if not token:
                return abort(401, description="Token de acesso necessário")

            compartilhamento = Compartilhamento.query.filter_by(
                token=token,
                id_arquivo=file_id,
                ativo=True
            ).first()
            
            if not compartilhamento:
                return abort(403, description="Acesso negado - token inválido")

            arquivo = compartilhamento.arquivo
            caminho_absoluto = os.path.abspath(arquivo.caminho_armazenamento)
            
            if not os.path.exists(caminho_absoluto):
                return abort(404, description="Arquivo não encontrado no servidor")

            compartilhamento.acessos += 1
            db.session.commit()

          
            return send_file(
                caminho_absoluto,
                as_attachment=not preview,
                download_name=arquivo.nome_original if not preview else None,
                mimetype=arquivo.tipo_mime
            )

        except Exception as e:
            return abort(500, description=f"Erro ao baixar arquivo: {str(e)}")
