from flask import Blueprint
from flask_restful import Api
from app.api.auth import (
    RegisterResource,
    LoginResource,
    LogoutResource,
    VerificarCodigo2FAResource,
    VerificarLogin2FAResource,
    UserProfileResource,
)
from app.api.account import (
    ConfirmarExclusaoContaResource,
    ExcluirContaResource,
    RecuperarSenhaResource,
    ValidarCodigoRecuperacaoResource,
    AtualizarSenhaRecuperacaoResource,
)
from app.api.file import (
    FileUploadResource,
    FileDownloadResource,
    FileShareResource,
    FileShareViewResource,
    FileDownloadSharedResource,
    FileVisibilityResource,
    FileDeleteResource,
    FilePreviewResource,
    FilePreviewContentResource,
    FileRenameResource,
)

from app.api.folder import (
    FolderContentResource,
    FolderCreateResource,
    FolderDeleteResource,
    FolderRenameResource,
    FolderShareResource,
    FolderUnshareResource,
    FolderSharedWithMeResource,
)

from app.api.termo import (
    TermosUsoResource, 
    VerificarTermosResource,
)
from app.api.backup import BackupResource, BackupDetailResource



api_bp = Blueprint('api', __name__, url_prefix='/api')  
api = Api(api_bp)

# Rotas de autenticação
api.add_resource(RegisterResource, '/auth/register')
api.add_resource(VerificarCodigo2FAResource, '/auth/verify-register')
api.add_resource(LoginResource, '/auth/login')
api.add_resource(VerificarLogin2FAResource, '/auth/verify-login')
api.add_resource(LogoutResource, '/auth/logout')
api.add_resource(UserProfileResource, '/auth/me')

#rotas da conta
api.add_resource(ExcluirContaResource, '/account/excluir')
api.add_resource(ConfirmarExclusaoContaResource, '/account/confirmar-exclusao')
api.add_resource(RecuperarSenhaResource, '/account/recuperar-senha')
api.add_resource(ValidarCodigoRecuperacaoResource, '/account/validar-codigo-recuperacao')
api.add_resource(AtualizarSenhaRecuperacaoResource, '/account/atualizar-senha-recuperacao')

#Rotas de pastas
api.add_resource(FolderCreateResource, '/pastas/create')
api.add_resource(FolderDeleteResource, '/pastas/<string:folder_id>/delete')
api.add_resource(FolderRenameResource, '/pastas/<string:folder_id>/raname')
api.add_resource(FolderContentResource, 
                 '/folders', 
                 '/folders/<uuid:folder_id>')
api.add_resource(FolderShareResource, '/pastas/<string:folder_id>/share')
api.add_resource(FolderUnshareResource, '/pastas/<string:folder_id>/unshare')
api.add_resource(FolderSharedWithMeResource, '/pastas/compartilhadas')

#Rotas de arquivos
api.add_resource(FileUploadResource, '/files/upload')
api.add_resource(FileDownloadResource, '/files/<uuid:file_id>/download')
api.add_resource(FileRenameResource, '/files/<string:file_id>/rename')
api.add_resource(FileDeleteResource, '/files/<string:file_id>/delete')
api.add_resource(FileVisibilityResource, '/files/<string:file_id>/visibility')
api.add_resource(FilePreviewResource, '/files/<string:file_id>/preview')
api.add_resource(FilePreviewContentResource, '/files/<string:file_id>/preview-content')


# Rotas de compartilhamento
api.add_resource(FileShareResource, '/files/share/<uuid:file_id>')
api.add_resource(FileShareViewResource, '/share/<string:token>')
api.add_resource(FileDownloadSharedResource, '/files/download-shared/<uuid:file_id>')

#termo de uso
api.add_resource(TermosUsoResource, '/termos')
api.add_resource(VerificarTermosResource, '/termos/verificar')

#backup
api.add_resource(BackupResource, '/backups')
api.add_resource(BackupDetailResource, '/backups/<string:backup_id>')

def init_app(app):
    app.register_blueprint(api_bp)