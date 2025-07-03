import os
import datetime
import subprocess
import tarfile
import tempfile
import logging
from cryptography.fernet import Fernet
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from dotenv import load_dotenv
from app.extensions import db
from app.models import Backup
from pathlib import Path
from cryptography.fernet import Fernet
import boto3
from botocore.exceptions import ClientError
import psycopg2
from urllib.parse import urlparse


load_dotenv()

class BackupManager:
    
    print(f"UPLOAD_FOLDER: {os.getenv('UPLOAD_FOLDER')}")  
    def __init__(self):
        self.logger = self._setup_logger()
        self.cipher = Fernet(os.getenv('BACKUP_ENCRYPTION_KEY').encode())
        self.upload_folder = os.getenv('UPLOAD_FOLDER')
        self.backup_folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
        self.db_url = os.getenv('SQLALCHEMY_DATABASE_URI')  
        
    
        self.gauth = GoogleAuth()
        self.drive = None


    def _authenticate_drive(self):
        """Autenticação simplificada e robusta para Google Drive"""
        try:
            self.gauth = GoogleAuth()
            self.gauth.LoadClientConfigFile('client_secrets.json')

            
            if os.path.exists('credentials.json'):
                self.gauth.LoadCredentialsFile('credentials.json')

            
            if self.gauth.credentials is None or self.gauth.access_token_expired:
                self.gauth.LocalWebserverAuth()
                self.gauth.SaveCredentialsFile('credentials.json')

            self.drive = GoogleDrive(self.gauth)

        except Exception as e:
            self.logger.error(f"Falha crítica na autenticação: {str(e)}")
            raise RuntimeError("Não foi possível autenticar no Google Drive")

    
    def _upload_to_drive(self, file_path, backup_type):
        """Faz upload para o Google Drive"""
        if not self.drive:
            self._authenticate_drive()
        
        try:
            gfile = self.drive.CreateFile({
                'title': os.path.basename(file_path),
                'parents': [{'id': self.backup_folder_id}],
                'description': f'Backup {backup_type} - {datetime.datetime.now()}'
            })
            gfile.SetContentFile(file_path)
            gfile.Upload()
            return gfile['id']  
            
        except Exception as e:
            self.logger.error(f"Falha no upload para Google Drive: {str(e)}")
            return None
        
    
    def _setup_logger(self):
        logger = logging.getLogger('backup_manager')
        logger.setLevel(logging.INFO)
        
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger

    def _create_db_dump(self):
        
        parsed = urlparse(self.db_url)
        db_name = parsed.path[1:]
        user = parsed.username
        password = parsed.password
        host = parsed.hostname
        port = parsed.port or 5432
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        dump_filename = f'db_dump_{timestamp}.sql'
        temp_dir = tempfile.mkdtemp()
        dump_path = os.path.join(temp_dir, dump_filename)
        
        try:
            
            env = os.environ.copy()
            env['PGPASSWORD'] = password
            
            cmd = [
                'pg_dump',
                '-h', host,
                '-p', str(port),
                '-U', user,
                '-d', db_name,
                '-f', dump_path,
                '-F', 'c'  
            ]
            
            subprocess.run(cmd, env=env, check=True)
            self.logger.info(f"Dump do banco de dados criado com sucesso: {dump_path}")
            return dump_path
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Falha ao criar dump do banco de dados: {str(e)}")
            return None

    def _create_files_archive(self):
        
        
        if not os.path.exists(self.upload_folder):
            self.logger.warning(f"Pasta de uploads não encontrada: {self.upload_folder}")
            return None
            
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        archive_name = f'uploads_{timestamp}.tar.gz'
        temp_dir = tempfile.mkdtemp()
        archive_path = os.path.join(temp_dir, archive_name)
        
        try:
            with tarfile.open(archive_path, 'w:gz') as tar:
                
                if not os.listdir(self.upload_folder):
                    self.logger.warning("Pasta de uploads vazia - criando backup vazio")
                tar.add(self.upload_folder, arcname=os.path.basename(self.upload_folder))
            self.logger.info(f"Arquivo de uploads compactado: {archive_path}")
            return archive_path
        except Exception as e:
            self.logger.error(f"Falha ao compactar uploads: {str(e)}")
            return None

    def _encrypt_file(self, file_path):
        
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            encrypted_data = self.cipher.encrypt(file_data)
            
            encrypted_path = file_path + '.enc'
            with open(encrypted_path, 'wb') as f:
                f.write(encrypted_data)
            
            os.remove(file_path)  
            return encrypted_path
        except Exception as e:
            self.logger.error(f"Falha ao criptografar arquivo: {str(e)}")
            return None


    def _cleanup_temp_files(self, *files):
        """Remove arquivos temporários"""
        for file_path in files:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    self.logger.debug(f"Arquivo temporário removido: {file_path}")
                except Exception as e:
                    self.logger.warning(f"Falha ao remover arquivo temporário: {str(e)}")

    def _record_backup_in_db(self, user_id, backup_type, s3_key, file_size, status):
        """Registra o backup no banco de dados"""
        try:
            backup = Backup(
                id_usuario=user_id,
                tipo=backup_type,
                caminho=s3_key,
                tamanho=file_size,
                status=status,
                metadados={
                    'storage': 's3',
                    'bucket': self.s3_bucket,
                    'retention_days': self.backup_retention_days
                }
            )
            db.session.add(backup)
            db.session.commit()
            self.logger.info(f"Backup registrado no banco de dados com ID: {backup.id}")
            return backup.id
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"Falha ao registrar backup no banco de dados: {str(e)}")
            return None

    def create_full_backup(self, user_id=None):
        
        self.logger.info("Iniciando backup completo...")
        
        
        db_dump_path = self._create_db_dump()
        if not db_dump_path:
            return False
        
        
        files_archive_path = self._create_files_archive()
        if not files_archive_path:
            self._cleanup_temp_files(db_dump_path)
            return False
        
       
        encrypted_db_path = self._encrypt_file(db_dump_path)
        encrypted_files_path = self._encrypt_file(files_archive_path)
        
        if not encrypted_db_path or not encrypted_files_path:
            self._cleanup_temp_files(db_dump_path, files_archive_path, 
                                    encrypted_db_path, encrypted_files_path)
            return False
        
        
        db_s3_key = self._upload_to_s3(encrypted_db_path, 'database')
        files_s3_key = self._upload_to_s3(encrypted_files_path, 'uploads')
        
        
        success = True
        if db_s3_key:
            file_size = os.path.getsize(encrypted_db_path)
            self._record_backup_in_db(
                user_id, 'database', db_s3_key, file_size, 'completo')
        else:
            success = False
        
        if files_s3_key:
            file_size = os.path.getsize(encrypted_files_path)
            self._record_backup_in_db(
                user_id, 'uploads', files_s3_key, file_size, 'completo')
        else:
            success = False
        
       
        self._cleanup_temp_files(encrypted_db_path, encrypted_files_path)
        
        return success


    def restore_backup(self, backup_id):
        
        pass

    def delete_backup(self, s3_key):
        
        try:
            s3 = boto3.client(
                's3',
                region_name=self.s3_region,
                aws_access_key_id=self.s3_access_key,
                aws_secret_access_key=self.s3_secret_key
            )
            
            s3.delete_object(Bucket=self.s3_bucket, Key=s3_key)
            self.logger.info(f"Backup removido do S3: {s3_key}")
            return True
        except ClientError as e:
            self.logger.error(f"Falha ao remover backup do S3: {str(e)}")
            return False

    def create_full_backup(self, user_id=None):
        
        self.logger.info("Iniciando backup no Google Drive...")
        
        
        db_dump_path = self._create_db_dump()
        if not db_dump_path:
            self.logger.error("Falha ao criar dump do banco de dados")
            return False
        
        
        files_archive_path = self._create_files_archive()
        if not files_archive_path:
            self.logger.warning("Falha ao compactar uploads - continuando apenas com backup do banco")
            
            encrypted_db = self._encrypt_file(db_dump_path)
            db_file_id = self._upload_to_drive(encrypted_db, 'database')
            self._cleanup_temp_files(db_dump_path, encrypted_db)
            if db_file_id:
                return self._record_google_drive_backup(user_id, db_file_id, None)
            return False
        
        
        encrypted_db = self._encrypt_file(db_dump_path)
        encrypted_files = self._encrypt_file(files_archive_path)
        
        
        db_file_id = self._upload_to_drive(encrypted_db, 'database')
        files_file_id = self._upload_to_drive(encrypted_files, 'uploads')
        
        
        self._cleanup_temp_files(db_dump_path, files_archive_path, encrypted_db, encrypted_files)
        
        return self._record_google_drive_backup(user_id, db_file_id, files_file_id)

    def _record_google_drive_backup(self, user_id, db_file_id, files_file_id):
        """Registra o backup no banco de dados com tamanho calculado"""
        try:
            
            tamanho_total = 0
            if db_file_id:
                
                db_file = self.drive.CreateFile({'id': db_file_id})
                db_file.FetchMetadata(fields='fileSize')
                tamanho_total += int(db_file['fileSize'])
            
            if files_file_id:
               
                files_file = self.drive.CreateFile({'id': files_file_id})
                files_file.FetchMetadata(fields='fileSize')
                tamanho_total += int(files_file['fileSize'])
            
            backup_data = {
                'id_usuario': user_id,
                'tipo': 'full' if files_file_id else 'db_only',
                'caminho': f"GoogleDrive:{db_file_id}" + (f",{files_file_id}" if files_file_id else ""),
                'tamanho': tamanho_total, 
                'status': 'completo',
                'metadados': {
                    'storage': 'google_drive',
                    'db_file_id': db_file_id
                }
            }
            
            if files_file_id:
                backup_data['metadados']['files_file_id'] = files_file_id
            
            backup = Backup(**backup_data)
            db.session.add(backup)
            db.session.commit()
            return True
            
        except Exception as e:
            db.session.rollback()
            self.logger.error(f"Falha ao registrar backup: {str(e)}")
            return False
    




