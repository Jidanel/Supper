# inventaire/management/commands/generer_snapshots.py
"""
Commande Django pour générer des snapshots d'état des inventaires
Usage: python manage.py generer_snapshots --date-debut 2025-01-01 --date-fin 2025-11-13
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import datetime, date, timedelta
from accounts.models import Poste
from inventaire.services.snapshot_service import SnapshotService
import logging

logger = logging.getLogger('supper')


class Command(BaseCommand):
    help = 'Génère des snapshots d\'état des inventaires pour une période donnée'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--date-debut',
            type=str,
            help='Date de début (format YYYY-MM-DD)',
            required=False
        )
        
        parser.add_argument(
            '--date-fin',
            type=str,
            help='Date de fin (format YYYY-MM-DD)',
            required=False
        )
        
        parser.add_argument(
            '--poste',
            type=str,
            help='Code du poste (optionnel, tous par défaut)',
            required=False
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forcer la regénération des snapshots existants',
        )
        
        parser.add_argument(
            '--aujourd-hui',
            action='store_true',
            help='Générer uniquement le snapshot d\'aujourd\'hui',
        )
    
    def handle(self, *args, **options):
        # Déterminer les dates
        if options['aujourd_hui']:
            date_debut = date.today()
            date_fin = date.today()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Génération du snapshot pour aujourd'hui : {date_debut}"
                )
            )
        else:
            # Parser les dates
            if options['date_debut']:
                try:
                    date_debut = datetime.strptime(options['date_debut'], '%Y-%m-%d').date()
                except ValueError:
                    raise CommandError('Format de date_debut invalide. Utilisez YYYY-MM-DD')
            else:
                # Par défaut: début du mois courant
                today = date.today()
                date_debut = date(today.year, today.month, 1)
            
            if options['date_fin']:
                try:
                    date_fin = datetime.strptime(options['date_fin'], '%Y-%m-%d').date()
                except ValueError:
                    raise CommandError('Format de date_fin invalide. Utilisez YYYY-MM-DD')
            else:
                # Par défaut: aujourd'hui
                date_fin = date.today()
            
            # Vérifier la cohérence
            if date_debut > date_fin:
                raise CommandError('La date de début doit être antérieure à la date de fin')
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"Génération des snapshots du {date_debut} au {date_fin}"
                )
            )
        
        # Déterminer les postes
        if options['poste']:
            try:
                postes = Poste.objects.filter(code=options['poste'], is_active=True)
                if not postes.exists():
                    raise CommandError(f"Poste {options['poste']} introuvable")
                self.stdout.write(f"Poste sélectionné: {postes.first().nom}")
            except Poste.DoesNotExist:
                raise CommandError(f"Poste {options['poste']} introuvable")
        else:
            postes = Poste.objects.filter(is_active=True)
            self.stdout.write(f"Tous les postes actifs: {postes.count()} postes")
        
        # Calculer le nombre de jours
        nb_jours = (date_fin - date_debut).days + 1
        total_snapshots = nb_jours * postes.count()
        
        self.stdout.write(
            self.style.WARNING(
                f"⚠️  {total_snapshots} snapshots à générer "
                f"({nb_jours} jours × {postes.count()} postes)"
            )
        )
        
        # Confirmation si gros volume
        if total_snapshots > 1000 and not options['force']:
            confirm = input(
                'Cela peut prendre du temps. Continuer ? (o/N) '
            )
            if confirm.lower() != 'o':
                self.stdout.write(self.style.ERROR('Opération annulée'))
                return
        
        # Générer les snapshots
        self.stdout.write(self.style.SUCCESS('Génération en cours...'))
        
        stats = SnapshotService.creer_snapshots_periode(
            date_debut=date_debut,
            date_fin=date_fin,
            postes=postes
        )
        
        # Afficher les statistiques
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('✅ Génération terminée !'))
        self.stdout.write('')
        self.stdout.write(f"📊 Statistiques:")
        self.stdout.write(f"  • Total snapshots: {stats['total_snapshots']}")
        self.stdout.write(
            self.style.SUCCESS(f"  • Snapshots créés: {stats['snapshots_crees']}")
        )
        self.stdout.write(
            self.style.WARNING(f"  • Snapshots mis à jour: {stats['snapshots_mis_a_jour']}")
        )
        
        if stats['erreurs'] > 0:
            self.stdout.write(
                self.style.ERROR(f"  • Erreurs: {stats['erreurs']}")
            )
        
        self.stdout.write('')
        self.stdout.write(
            self.style.SUCCESS(
                'Les snapshots sont maintenant disponibles pour les rapports !'
            )
        )