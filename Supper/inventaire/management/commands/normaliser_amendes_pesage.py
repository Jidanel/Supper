# ===================================================================
# inventaire/management/commands/normaliser_amendes_pesage.py
# Commande pour normaliser les champs des amendes existantes
# ===================================================================

from django.core.management.base import BaseCommand
from django.db import transaction
import logging

logger = logging.getLogger('supper')


class Command(BaseCommand):
    help = 'Normalise les champs immatriculation, transporteur et operateur des amendes existantes'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=500,
            help='Nombre d\'amendes à traiter par lot (défaut: 500)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulation sans modification effective'
        )
    
    def handle(self, *args, **options):
        from inventaire.models_pesage import AmendeEmise
        from inventaire.utils_pesage import normalize_search_text, normalize_immatriculation
        
        batch_size = options['batch_size']
        dry_run = options['dry_run']
        
        # Compter les amendes à traiter
        total = AmendeEmise.objects.count()
        
        if total == 0:
            self.stdout.write(self.style.WARNING('Aucune amende à normaliser.'))
            return
        
        self.stdout.write(f'Normalisation de {total} amendes...')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('Mode simulation (--dry-run) activé.'))
        
        processed = 0
        updated = 0
        errors = 0
        
        # Traiter par lots
        amendes = AmendeEmise.objects.all().order_by('id')
        
        for i in range(0, total, batch_size):
            batch = amendes[i:i+batch_size]
            
            with transaction.atomic():
                for amende in batch:
                    try:
                        # Calculer les valeurs normalisées
                        immat_norm = normalize_immatriculation(amende.immatriculation)
                        transp_norm = normalize_search_text(amende.transporteur)
                        op_norm = normalize_search_text(amende.operateur)
                        
                        # Vérifier si mise à jour nécessaire
                        needs_update = (
                            amende.immatriculation_normalise != immat_norm or
                            amende.transporteur_normalise != transp_norm or
                            amende.operateur_normalise != op_norm
                        )
                        
                        if needs_update:
                            if not dry_run:
                                amende.immatriculation_normalise = immat_norm
                                amende.transporteur_normalise = transp_norm
                                amende.operateur_normalise = op_norm
                                amende.save(update_fields=[
                                    'immatriculation_normalise',
                                    'transporteur_normalise',
                                    'operateur_normalise'
                                ])
                            updated += 1
                        
                        processed += 1
                        
                    except Exception as e:
                        errors += 1
                        self.stdout.write(
                            self.style.ERROR(f'Erreur amende {amende.pk}: {str(e)}')
                        )
            
            # Afficher la progression
            progress = (processed / total) * 100
            self.stdout.write(f'Progression: {processed}/{total} ({progress:.1f}%) - {updated} mises à jour')
        
        # Résumé
        self.stdout.write('')
        self.stdout.write('=' * 50)
        self.stdout.write(self.style.SUCCESS(f'Normalisation terminée!'))
        self.stdout.write(f'- Amendes traitées: {processed}')
        self.stdout.write(f'- Mises à jour: {updated}')
        self.stdout.write(f'- Erreurs: {errors}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\nMode simulation - Aucune modification effectuée.'
                '\nRelancez sans --dry-run pour appliquer les modifications.'
            ))
        
        logger.info(f'Normalisation amendes pesage: {updated}/{processed} mises à jour')