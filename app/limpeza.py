from datetime import datetime, timedelta
from app.extensions import db
from app.models import Usuario, Arquivo, Pasta

class DeletionManager:
    def __init__(self, retention_minutes=None):
        # Usa o valor passado ou um valor padrão de 90 dias (em minutos)
        self.retention_minutes = retention_minutes if retention_minutes is not None else (90 * 24 * 60)

    def delete_old_records(self):
        cutoff_date = datetime.utcnow() - timedelta(minutes=self.retention_minutes)
        total_deletados = 0

        usuarios = Usuario.query.filter(
            Usuario.conta_exclusao_solicitada == True,
            Usuario.conta_exclusao_data <= cutoff_date
        ).all()
        for u in usuarios:
            db.session.delete(u)
            total_deletados += 1

        pastas = Pasta.query.filter(
            Pasta.excluida == True,
            Pasta.data_exclusao <= cutoff_date
        ).all()
        for p in pastas:
            db.session.delete(p)
            total_deletados += 1

        arquivos = Arquivo.query.filter(
            Arquivo.excluido == True,
            Arquivo.data_exclusao <= cutoff_date
        ).all()
        for a in arquivos:
            db.session.delete(a)
            total_deletados += 1

        db.session.commit()
        print(f"🧹 Exclusão concluída. Registros apagados: {total_deletados}")
        return total_deletados > 0
