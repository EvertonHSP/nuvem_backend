from app import create_app
from app.extensions import db, socketio
from app.api.termo import check_terms_version 
from app.backup_manager import BackupManager
import threading
import time
import datetime
import os
from app.limpeza import DeletionManager

SCHEDULED_BACKUP_TIME = "15:54"
SCHEDULED_DELETION_TIME = "16:50"
RETENTION_MINUTES = 1 

app = create_app()

def run_scheduled_deletions(app, retention_minutes):
    with app.app_context():
        deletion_manager = DeletionManager(retention_minutes=retention_minutes)

        hour_str, minute_str = SCHEDULED_DELETION_TIME.split(":")
        scheduled_hour = int(hour_str)
        scheduled_minute = int(minute_str)

        while True:
            now = datetime.datetime.now()
            next_run = now.replace(hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0)
            if now >= next_run:
                next_run += datetime.timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()
            print(f"🗓️ Próxima limpeza agendada para: {next_run.strftime('%Y-%m-%d %H:%M:%S')} (em {wait_seconds:.0f} segundos)")
            time.sleep(wait_seconds)

            print(f"\n🧹 Executando limpeza agendada em: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            if deletion_manager.delete_old_records():
                print("✅ Limpeza agendada concluída com sucesso")
            else:
                print("ℹ️ Nenhum registro para apagar")


def run_scheduled_backups(app):
    
    with app.app_context():
        backup_manager = BackupManager()
        
        hour_str, minute_str = SCHEDULED_BACKUP_TIME.split(":")
        scheduled_hour = int(hour_str)
        scheduled_minute = int(minute_str)

        while True:
            now = datetime.datetime.now()
            next_run = now.replace(hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0)
            
            if now >= next_run:
                next_run += datetime.timedelta(days=1)
            
            wait_seconds = (next_run - now).total_seconds()
            print(f"Próximo backup agendado para: {next_run.strftime('%Y-%m-%d %H:%M:%S')} (em {wait_seconds:.0f} segundos)")
            time.sleep(wait_seconds)
            
            print(f"\nExecutando backup agendado em: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            if backup_manager.create_full_backup():
                print("✅ Backup agendado concluído com sucesso")
            else:
                print("❌ Falha no backup agendado")


def run_initial_backup(app):
    with app.app_context():
        print("\n📦 Iniciando backup inicial...")
        backup_manager = BackupManager()
        if backup_manager.create_full_backup():
            print("✅ Backup inicial concluído com sucesso")
        else:
            print("❌ Falha no backup inicial")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        new_version = check_terms_version()
        if new_version:
            print(f'Termos de uso atualizados para versão {new_version}')
        

        threading.Thread(
            target=run_scheduled_deletions,
            args=(app, RETENTION_MINUTES),
            daemon=True
        ).start()

        
        threading.Thread(
            target=run_initial_backup,
            args=(app,),
            daemon=True
        ).start()
        
       
        threading.Thread(
            target=run_scheduled_backups,
            args=(app,),
            daemon=True
        ).start()
        
        time.sleep(3) 

    app.run(
        ssl_context=('localhost+2.pem', 'localhost+2-key.pem'),
        debug=True,
        host='0.0.0.0',
        port=5000
    )