# common/management/commands/fix_user_permissions.py

from django.core.management.base import BaseCommand
from accounts.models import UtilisateurSUPPER


class Command(BaseCommand):
    help = 'Reconfigure les permissions de tous les utilisateurs selon leur habilitation actuelle'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche les changements sans les appliquer'
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Corriger uniquement un utilisateur spécifique (matricule)'
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        specific_user = options.get('user')
        
        if specific_user:
            users = UtilisateurSUPPER.objects.filter(username=specific_user)
        else:
            users = UtilisateurSUPPER.objects.all()
        
        self.stdout.write(f"Vérification de {users.count()} utilisateur(s)...")
        
        corrected = 0
        
        for user in users:
            old_values = {
                'is_superuser': user.is_superuser,
                'is_staff': user.is_staff,
                'acces_tous_postes': user.acces_tous_postes,
            }
            
            # Forcer la reconfiguration
            user.attribuer_permissions_automatiques()
            
            new_values = {
                'is_superuser': user.is_superuser,
                'is_staff': user.is_staff,
                'acces_tous_postes': user.acces_tous_postes,
            }
            
            # Vérifier si quelque chose a changé
            if old_values != new_values:
                corrected += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"\n{user.username} ({user.habilitation}):"
                    )
                )
                
                for key in old_values:
                    if old_values[key] != new_values[key]:
                        self.stdout.write(
                            f"  {key}: {old_values[key]} → {new_values[key]}"
                        )
                
                if not dry_run:
                    user.save()
                    self.stdout.write(self.style.SUCCESS("  ✓ Corrigé"))
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\n[DRY RUN] {corrected} utilisateur(s) à corriger. "
                    "Relancez sans --dry-run pour appliquer."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n{corrected} utilisateur(s) corrigé(s)."
                )
            )