# ===================================================================
# common/management/commands/cleanup_logs.py
# Commande pour nettoyer les anciens logs
# ===================================================================

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger('supper')


class Command(BaseCommand):
    help = 'Nettoie les anciens logs d\'audit selon la politique de rétention'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=180,
            help='Nombre de jours à conserver (défaut: 180 jours / 6 mois)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulation sans suppression effective'
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Affichage détaillé'
        )
    
    def handle(self, *args, **options):
        try:
            from accounts.models import JournalAudit
        except ImportError:
            self.stdout.write(
                self.style.ERROR('Impossible d\'importer JournalAudit')
            )
            return
        
        days = options['days']
        dry_run = options['dry_run']
        verbose = options['verbose']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Compter les logs à supprimer
        logs_to_delete = JournalAudit.objects.filter(timestamp__lt=cutoff_date)
        count = logs_to_delete.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Aucun log à supprimer (antérieur à {cutoff_date.date()})'
                )
            )
            return
        
        if verbose:
            self.stdout.write(f'Logs trouvés pour suppression: {count}')
            self.stdout.write(f'Date limite: {cutoff_date}')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'SIMULATION: {count} logs seraient supprimés '
                    f'(antérieurs à {cutoff_date.date()})'
                )
            )
        else:
            # Suppression effective
            deleted_count = logs_to_delete.delete()[0]
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Supprimé {deleted_count} entrées de log '
                    f'antérieures à {cutoff_date.date()}'
                )
            )
            
            # Journaliser cette action de maintenance
            logger.info(f'Nettoyage automatique: {deleted_count} logs supprimés')
