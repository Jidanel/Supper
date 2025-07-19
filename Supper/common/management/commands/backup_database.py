# ===================================================================
# common/management/commands/backup_database.py
# Commande pour sauvegarder la base de données
# ===================================================================

from django.core.management.base import BaseCommand
from django.conf import settings
from datetime import datetime
import subprocess
import os
import logging

logger = logging.getLogger('supper')


class Command(BaseCommand):
    help = 'Crée une sauvegarde de la base de données PostgreSQL'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default='backups',
            help='Répertoire de sortie pour les sauvegardes'
        )
        
        parser.add_argument(
            '--compress',
            action='store_true',
            help='Compresser la sauvegarde'
        )
    
    def handle(self, *args, **options):
        output_dir = options['output_dir']
        compress = options['compress']
        
        # Créer le répertoire de sauvegarde s'il n'existe pas
        os.makedirs(output_dir, exist_ok=True)
        
        # Récupérer les paramètres de la base de données
        db_settings = settings.DATABASES['default']
        
        if db_settings['ENGINE'] != 'django.db.backends.postgresql':
            self.stdout.write(
                self.style.ERROR(
                    'Cette commande ne fonctionne qu\'avec PostgreSQL'
                )
            )
            return
        
        # Nom du fichier de sauvegarde
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"supper_backup_{timestamp}.sql"
        
        if compress:
            filename += '.gz'
        
        filepath = os.path.join(output_dir, filename)
        
        # Commande pg_dump
        cmd = [
            'pg_dump',
            '--host', db_settings['HOST'],
            '--port', str(db_settings['PORT']),
            '--username', db_settings['USER'],
            '--dbname', db_settings['NAME'],
            '--verbose',
            '--no-password',
        ]
        
        if compress:
            cmd.extend(['--compress', '9'])
        
        cmd.extend(['--file', filepath])
        
        # Variables d'environnement pour le mot de passe
        env = os.environ.copy()
        env['PGPASSWORD'] = db_settings['PASSWORD']
        
        try:
            self.stdout.write(f'Création de la sauvegarde: {filename}')
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600  # Timeout de 1 heure
            )
            
            if result.returncode == 0:
                file_size = os.path.getsize(filepath)
                size_mb = file_size / (1024 * 1024)
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Sauvegarde créée avec succès: {filepath} '
                        f'({size_mb:.2f} MB)'
                    )
                )
                
                logger.info(f'Sauvegarde base de données créée: {filename} ({size_mb:.2f} MB)')
                
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f'Erreur lors de la sauvegarde: {result.stderr}'
                    )
                )
                logger.error(f'Erreur sauvegarde: {result.stderr}')
                
        except subprocess.TimeoutExpired:
            self.stdout.write(
                self.style.ERROR('Timeout: la sauvegarde a pris trop de temps')
            )
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(
                    'pg_dump non trouvé. Assurez-vous que PostgreSQL '
                    'est installé et dans le PATH'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Erreur inattendue: {str(e)}')
            )