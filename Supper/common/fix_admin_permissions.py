# Créez le fichier : accounts/management/commands/fix_admin_permissions.py

from django.core.management.base import BaseCommand
from accounts.models import UtilisateurSUPPER

class Command(BaseCommand):
    help = 'Corrige les permissions pour tous les administrateurs'

    def handle(self, *args, **options):
        # Trouver tous les administrateurs
        admins = UtilisateurSUPPER.objects.filter(
            habilitation__in=['admin_principal', 'coord_psrr', 'serv_info']
        )
        
        for admin in admins:
            # Forcer les permissions d'admin
            admin.is_staff = True
            if admin.habilitation == 'admin_principal':
                admin.is_superuser = True
            
            # Sauvegarder (cela déclenche attribuer_permissions_automatiques)
            admin.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Permissions mises à jour pour {admin.username} ({admin.nom_complet})'
                )
            )
        
        self.stdout.write(
            self.style.SUCCESS(f'Total: {admins.count()} administrateurs corrigés')
        )