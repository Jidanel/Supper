from django.core.management.base import BaseCommand
from inventaire.models_pesage import AmendeEmise


class Command(BaseCommand):
    help = 'Normalise toutes les immatriculations existantes (sans espaces, majuscules)'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche les changements sans les appliquer',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        amendes = AmendeEmise.objects.all()
        count = 0
        
        for amende in amendes:
            immat_originale = amende.immatriculation
            immat_normalisee = ''.join(immat_originale.split()).upper()
            
            if immat_originale != immat_normalisee:
                if dry_run:
                    self.stdout.write(
                        f"[DRY-RUN] '{immat_originale}' → '{immat_normalisee}'"
                    )
                else:
                    amende.immatriculation = immat_normalisee
                    amende.immatriculation_normalise = immat_normalisee
                    amende.save(update_fields=['immatriculation', 'immatriculation_normalise'])
                    self.stdout.write(
                        self.style.SUCCESS(f"Normalisé: '{immat_originale}' → '{immat_normalisee}'")
                    )
                count += 1
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f"\\n{count} immatriculations à normaliser"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\\n{count} immatriculations normalisées"))


# Usage:
# python manage.py normaliser_immatriculations --dry-run  # Prévisualisation
# python manage.py normaliser_immatriculations            # Exécution
