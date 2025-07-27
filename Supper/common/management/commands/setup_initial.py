# ===================================================================
# common/management/commands/setup_initial.py
# Commande pour configurer le système SUPPER initial
# ===================================================================

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date
import logging

logger = logging.getLogger('supper')
User = get_user_model()


class Command(BaseCommand):
    help = 'Configure le système SUPPER avec les données initiales'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force la recréation des données existantes'
        )
        
        parser.add_argument(
            '--demo',
            action='store_true',
            help='Créer des données de démonstration'
        )
    
    def handle(self, *args, **options):
        force = options['force']
        demo = options['demo']
        
        self.stdout.write(
            self.style.SUCCESS('🚀 Configuration initiale de SUPPER')
        )
        
        # 1. Créer l'administrateur principal
        self.create_admin_user(force)
        
        # 2. Créer les postes de base
        self.create_basic_postes(force)
        
        # 3. Configurer les jours
        self.configure_days()
        
        # 4. Créer des utilisateurs de test
        if demo:
            self.create_demo_users(force)
            self.create_demo_data()
        
        self.stdout.write(
            self.style.SUCCESS('✅ Configuration terminée avec succès!')
        )
    
    def create_admin_user(self, force):
        """Créer l'utilisateur administrateur principal"""
        try:
            admin = User.objects.get(username='ADMIN001')
            if force:
                admin.delete()
                self.stdout.write('🗑️ Administrateur existant supprimé')
            else:
                self.stdout.write('ℹ️ Administrateur principal existe déjà')
                return
        except User.DoesNotExist:
            pass
        
        admin = User.objects.create_user(
            username='ADMIN001',
            nom_complet='Administrateur Principal SUPPER',
            telephone='+237600000001',
            email='admin@supper.cm',
            habilitation='admin_principal',
            password='admin123'
        )
        
        # Activer tous les privilèges
        admin.is_staff = True
        admin.is_superuser = True
        admin.acces_tous_postes = True
        admin.save()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'👤 Administrateur créé: {admin.username} / admin123'
            )
        )
    
    def create_basic_postes(self, force):
        """Créer les postes de base"""
        from accounts.models import Poste
        
        postes_base = [
            {
                'nom': 'Péage de Yaoundé-Nord',
                'code': 'YDE-N-01',
                'type_poste': 'peage',
                'region': 'centre',
                'departement': 'Mfoundi',
                'localisation': 'Autoroute Yaoundé-Douala, sortie Nord'
            },
            {
                'nom': 'Péage de Douala-Littoral',
                'code': 'DLA-L-01',
                'type_poste': 'peage',
                'region': 'littoral',
                'departement': 'Wouri',
                'localisation': 'Entrée de Douala, zone portuaire'
            },
            {
                'nom': 'Pesage de Garoua-Centre',
                'code': 'GRA-C-01',
                'type_poste': 'pesage',
                'region': 'nord',
                'departement': 'Bénoué',
                'localisation': 'Centre-ville de Garoua, axe principal'
            },
            {
                'nom': 'Péage de Bafoussam-Ouest',
                'code': 'BAF-O-01',
                'type_poste': 'peage',
                'region': 'ouest',
                'departement': 'Mifi',
                'localisation': 'Sortie ouest de Bafoussam'
            },
            {
                'nom': 'Pesage de Maroua-Extrême',
                'code': 'MAR-E-01',
                'type_poste': 'pesage',
                'region': 'extreme_nord',
                'departement': 'Diamaré',
                'localisation': 'Entrée de Maroua, route du Tchad'
            }
        ]
        
        created_count = 0
        
        for poste_data in postes_base:
            try:
                poste = Poste.objects.get(code=poste_data['code'])
                if force:
                    poste.delete()
                    self.stdout.write(f'🗑️ Poste {poste_data["code"]} supprimé')
                else:
                    continue
            except Poste.DoesNotExist:
                pass
            
            poste = Poste.objects.create(**poste_data)
            created_count += 1
            self.stdout.write(f'📍 Poste créé: {poste.nom} ({poste.code})')
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ {created_count} poste(s) créé(s)')
        )
    
    def configure_days(self):
        """Configurer les jours pour la saisie"""
        from inventaire.models import ConfigurationJour
        
        # Ouvrir les 7 derniers jours pour la saisie
        admin = User.objects.get(username='ADMIN001')
        
        for i in range(7):
            day = date.today() - timezone.timedelta(days=i)
            
            config, created = ConfigurationJour.objects.get_or_create(
                date=day,
                defaults={
                    'statut': 'ouvert',
                    'cree_par': admin,
                    'commentaire': 'Configuration initiale automatique'
                }
            )
            
            if created:
                self.stdout.write(f'📅 Jour ouvert: {day.strftime("%d/%m/%Y")}')
        
        self.stdout.write(
            self.style.SUCCESS('✅ Jours configurés pour la saisie')
        )
    
    def create_demo_users(self, force):
        """Créer des utilisateurs de démonstration"""
        from accounts.models import Poste
        
        users_demo = [
            {
                'username': 'AGENT001',
                'nom_complet': 'Jean-Pierre NGONO',
                'telephone': '+237650000001',
                'habilitation': 'agent_inventaire',
                'password': '1234',
                'poste_code': 'YDE-N-01'
            },
            {
                'username': 'CHEF001',
                'nom_complet': 'Marie BELLO',
                'telephone': '+237650000002',
                'habilitation': 'chef_peage',
                'password': '1234',
                'poste_code': 'YDE-N-01'
            },
            {
                'username': 'COORD001',
                'nom_complet': 'Paul MBIDA',
                'telephone': '+237650000003',
                'habilitation': 'coord_psrr',
                'password': '1234',
                'poste_code': None
            },
            {
                'username': 'AGENT002',
                'nom_complet': 'Fatima HASSAN',
                'telephone': '+237650000004',
                'habilitation': 'agent_inventaire',
                'password': '1234',
                'poste_code': 'GRA-C-01'
            },
            {
                'username': 'CHEF002',
                'nom_complet': 'Robert TCHAMI',
                'telephone': '+237650000005',
                'habilitation': 'chef_pesage',
                'password': '1234',
                'poste_code': 'GRA-C-01'
            }
        ]
        
        created_count = 0
        
        for user_data in users_demo:
            try:
                user = User.objects.get(username=user_data['username'])
                if force:
                    user.delete()
                else:
                    continue
            except User.DoesNotExist:
                pass
            
            # Récupérer le poste si spécifié
            poste = None
            if user_data['poste_code']:
                try:
                    poste = Poste.objects.get(code=user_data['poste_code'])
                except Poste.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f'⚠️ Poste {user_data["poste_code"]} non trouvé')
                    )
            
            user = User.objects.create_user(
                username=user_data['username'],
                nom_complet=user_data['nom_complet'],
                telephone=user_data['telephone'],
                habilitation=user_data['habilitation'],
                poste_affectation=poste,
                password=user_data['password'],
                cree_par=User.objects.get(username='ADMIN001')
            )
            
            created_count += 1
            self.stdout.write(
                f'👤 Utilisateur demo: {user.username} / {user_data["password"]}'
            )
        
        self.stdout.write(
            self.style.SUCCESS(f'✅ {created_count} utilisateur(s) de demo créé(s)')
        )
    
    def create_demo_data(self):
        """Créer des données de démonstration"""
        from inventaire.models import InventaireJournalier, DetailInventairePeriode, RecetteJournaliere
        from accounts.models import Poste
        import random
        
        # Créer des inventaires et recettes pour les 3 derniers jours
        agent = User.objects.get(username='AGENT001')
        chef = User.objects.get(username='CHEF001')
        poste = Poste.objects.get(code='YDE-N-01')
        
        for i in range(3):
            day = date.today() - timezone.timedelta(days=i)
            
            # Créer un inventaire
            inventaire = InventaireJournalier.objects.create(
                poste=poste,
                date=day,
                agent_saisie=agent,
                observations='Données de démonstration'
            )
            
            # Ajouter des détails par période
            periodes = ['08h-09h', '09h-10h', '10h-11h', '11h-12h', 
                       '12h-13h', '13h-14h', '14h-15h', '15h-16h', '17h-18h']
            
            for periode in periodes:
                nb_vehicules = random.randint(10, 30)
                DetailInventairePeriode.objects.create(
                    inventaire=inventaire,
                    periode=periode,
                    nombre_vehicules=nb_vehicules
                )
            
            # Recalculer les totaux
            inventaire.recalculer_totaux()
            inventaire.verrouiller(agent)
            
            # Créer une recette correspondante
            recette_potentielle = inventaire.calculer_recette_potentielle()
            variation = random.uniform(0.8, 1.2)  # Variation de ±20%
            montant_declare = recette_potentielle * variation
            
            RecetteJournaliere.objects.create(
                poste=poste,
                date=day,
                montant_declare=montant_declare.quantize(timezone.Decimal('1')),
                chef_poste=chef,
                inventaire_associe=inventaire,
                observations='Recette de démonstration'
            )
            
            self.stdout.write(f'📊 Données demo créées pour {day.strftime("%d/%m/%Y")}')
        
        self.stdout.write(
            self.style.SUCCESS('✅ Données de démonstration créées')
        )