# ===================================================================
# common/management/commands/generate_test_data.py
# Commande pour générer des données de test
# ===================================================================

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import random
import logging

logger = logging.getLogger('supper')


class Command(BaseCommand):
    help = 'Génère des données de test pour SUPPER'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Nombre de jours de données à générer (défaut: 30)'
        )
        
        parser.add_argument(
            '--postes',
            type=str,
            default='all',
            help='Codes des postes (séparés par des virgules) ou "all"'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Forcer la génération même si des données existent'
        )
    
    def handle(self, *args, **options):
        try:
            from accounts.models import Poste, UtilisateurSUPPER
            from inventaire.models import (
                InventaireJournalier, DetailInventairePeriode, 
                RecetteJournaliere, ConfigurationJour
            )
        except ImportError as e:
            self.stdout.write(
                self.style.ERROR(f'Impossible d\'importer les modèles: {str(e)}')
            )
            return
        
        days = options['days']
        postes_param = options['postes']
        force = options['force']
        
        # Sélectionner les postes
        if postes_param == 'all':
            postes = Poste.objects.filter(is_active=True)
        else:
            codes_postes = [code.strip() for code in postes_param.split(',')]
            postes = Poste.objects.filter(code__in=codes_postes, is_active=True)
        
        if not postes.exists():
            self.stdout.write(
                self.style.ERROR('Aucun poste trouvé')
            )
            return
        
        # Récupérer un agent inventaire pour les tests
        try:
            agent = UtilisateurSUPPER.objects.filter(
                habilitation='agent_inventaire'
            ).first()
            
            if not agent:
                # Créer un agent de test si aucun n'existe
                self.stdout.write(
                    self.style.WARNING(
                        'Aucun agent inventaire trouvé. '
                        'Création d\'un agent de test...'
                    )
                )
                
                agent = UtilisateurSUPPER.objects.create_user(
                    username='TEST001',
                    nom_complet='Agent Test Inventaire',
                    telephone='+237600000000',
                    habilitation='agent_inventaire',
                    password='testpass123'
                )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Agent de test créé: {agent.username}'
                    )
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Erreur création agent: {str(e)}')
            )
            return
        
        # Générer les données
        start_date = date.today() - timedelta(days=days)
        created_count = 0
        updated_count = 0
        
        self.stdout.write(f'Génération de données pour {postes.count()} poste(s)...')
        
        for single_date in (start_date + timedelta(n) for n in range(days)):
            # Ouvrir le jour pour la saisie
            config, created = ConfigurationJour.objects.get_or_create(
                date=single_date,
                defaults={
                    'statut': 'ouvert',
                    'cree_par': agent,
                    'commentaire': 'Généré automatiquement pour les tests'
                }
            )
            
            for poste in postes:
                # Vérifier si l'inventaire existe déjà
                inventaire_exists = InventaireJournalier.objects.filter(
                    poste=poste,
                    date=single_date
                ).exists()
                
                if inventaire_exists and not force:
                    continue
                
                # Créer ou récupérer un inventaire
                inventaire, created = InventaireJournalier.objects.get_or_create(
                    poste=poste,
                    date=single_date,
                    defaults={
                        'agent_saisie': agent,
                        'observations': 'Données de test générées automatiquement'
                    }
                )
                
                if created:
                    created_count += 1
                else:
                    updated_count += 1
                    # Supprimer les anciens détails si on force la mise à jour
                    if force:
                        inventaire.details_periodes.all().delete()
                
                # Ajouter des détails par période
                periodes = [
                    '08h-09h', '09h-10h', '10h-11h', '11h-12h',
                    '12h-13h', '13h-14h', '14h-15h', '15h-16h',
                    '16h-17h', '17h-18h'
                ]
                
                for i, periode in enumerate(periodes):
                    # Simuler une activité variable selon l'heure
                    if i < 2 or i > 7:  # Heures creuses (8-10h et 16-18h)
                        nb_vehicules = random.randint(5, 15)
                    else:  # Heures de pointe (10-16h)
                        nb_vehicules = random.randint(15, 35)
                    
                    # Ajouter une variation aléatoire
                    variation = random.uniform(0.7, 1.3)
                    nb_vehicules = int(nb_vehicules * variation)
                    nb_vehicules = max(0, min(nb_vehicules, 50))  # Limiter entre 0 et 50
                    
                    detail, detail_created = DetailInventairePeriode.objects.get_or_create(
                        inventaire=inventaire,
                        periode=periode,
                        defaults={
                            'nombre_vehicules': nb_vehicules,
                            'observations_periode': 'Donnée de test' if random.random() > 0.8 else ''
                        }
                    )
                    
                    if not detail_created and force:
                        detail.nombre_vehicules = nb_vehicules
                        detail.save()
                
                # Recalculer les totaux
                inventaire.recalculer_totaux()
                
                
                # Créer ou mettre à jour une recette correspondante
                recette_potentielle = inventaire.calculer_recette_potentielle()
                
                # Simuler une variation de ±30% sur la recette déclarée
                variation = random.uniform(0.7, 1.3)
                montant_declare = recette_potentielle * Decimal(str(variation))
                
                # Arrondir à l'entier le plus proche
                montant_declare = montant_declare.quantize(Decimal('1'))
                
                recette, recette_created = RecetteJournaliere.objects.get_or_create(
                    poste=poste,
                    date=single_date,
                    defaults={
                        'montant_declare': montant_declare,
                        'chef_poste': agent,
                        'inventaire_associe': inventaire,
                        'observations': 'Recette de test générée automatiquement'
                    }
                )
                
                if not recette_created and force:
                    recette.montant_declare = montant_declare
                    recette.inventaire_associe = inventaire
                    recette.save()
        
        # Résumé
        self.stdout.write(
            self.style.SUCCESS(
                f'Génération terminée:'
                f'\n- {created_count} nouveaux inventaires créés'
                f'\n- {updated_count} inventaires mis à jour' if force else ''
                f'\n- Période: {start_date} à {date.today() - timedelta(days=1)}'
                f'\n- Postes concernés: {postes.count()}'
            )
        )
        
        logger.info(f'Données de test générées: {created_count} inventaires pour {postes.count()} postes')