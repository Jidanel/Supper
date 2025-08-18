# ===================================================================
# common/management/commands/test_calculs_deperdition.py
# Commande pour tester et déboguer les calculs de déperdition
# ===================================================================

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date
import logging

logger = logging.getLogger('supper')


class Command(BaseCommand):
    help = 'Teste et débogue les calculs de taux de déperdition'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--poste-id',
            type=int,
            help='ID du poste à tester (optionnel)'
        )
        
        parser.add_argument(
            '--date',
            type=str,
            help='Date au format YYYY-MM-DD (optionnel, défaut: aujourd\'hui)'
        )
        
        parser.add_argument(
            '--recalculer',
            action='store_true',
            help='Forcer le recalcul de tous les indicateurs'
        )
    
    def handle(self, *args, **options):
        try:
            from accounts.models import Poste
            from inventaire.models import InventaireJournalier, RecetteJournaliere
        except ImportError as e:
            self.stdout.write(
                self.style.ERROR(f'Impossible d\'importer les modèles: {str(e)}')
            )
            return
        
        poste_id = options.get('poste_id')
        date_str = options.get('date')
        recalculer = options['recalculer']
        
        # Déterminer la date
        if date_str:
            try:
                test_date = date.fromisoformat(date_str)
            except ValueError:
                self.stdout.write(
                    self.style.ERROR('Format de date invalide. Utilisez YYYY-MM-DD')
                )
                return
        else:
            test_date = date.today()
        
        self.stdout.write(f'=== TEST CALCULS DÉPERDITION - {test_date} ===\n')
        
        # Sélectionner les postes
        if poste_id:
            try:
                postes = [Poste.objects.get(id=poste_id)]
            except Poste.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Poste avec ID {poste_id} non trouvé')
                )
                return
        else:
            postes = Poste.objects.filter(is_active=True)[:5]  # Limiter à 5 pour le test
        
        for poste in postes:
            self.tester_poste(poste, test_date, recalculer)
    
    def tester_poste(self, poste, test_date, recalculer):
        """Teste les calculs pour un poste donné"""
        from inventaire.models import InventaireJournalier, RecetteJournaliere
        
        self.stdout.write(f'\n🏭 POSTE: {poste.nom} ({poste.code})')
        self.stdout.write('-' * 60)
        
        # Chercher l'inventaire
        try:
            inventaire = InventaireJournalier.objects.get(
                poste=poste,
                date=test_date
            )
            self.analyser_inventaire(inventaire)
        except InventaireJournalier.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(f'❌ Aucun inventaire trouvé pour le {test_date}')
            )
            return
        
        # Chercher les recettes
        recettes = RecetteJournaliere.objects.filter(
            poste=poste,
            date=test_date
        )
        
        if not recettes.exists():
            self.stdout.write(
                self.style.WARNING(f'❌ Aucune recette trouvée pour le {test_date}')
            )
            return
        
        for recette in recettes:
            self.analyser_recette(recette, recalculer)
    
    def analyser_inventaire(self, inventaire):
        """Analyse détaillée d'un inventaire"""
        self.stdout.write(f'📊 INVENTAIRE:')
        
        # Statistiques détaillées
        stats = inventaire.get_statistiques_detaillees()
        
        if 'erreur' in stats:
            self.stdout.write(
                self.style.ERROR(f'   ❌ {stats["erreur"]}')
            )
            return
        
        self.stdout.write(f'   • Total véhicules: {inventaire.total_vehicules}')
        self.stdout.write(f'   • Périodes saisies: {inventaire.nombre_periodes_saisies}')
        self.stdout.write(f'   • Somme véhicules: {stats["somme_vehicules"]}')
        self.stdout.write(f'   • Moyenne horaire: {stats["moyenne_horaire"]}')
        self.stdout.write(f'   • Estimation 24h: {stats["estimation_24h"]}')
        self.stdout.write(f'   • Véhicules effectifs (75%): {stats["vehicules_effectifs_75%"]}')
        self.stdout.write(f'   • Recette potentielle: {stats["recette_potentielle"]} FCFA')
        
        # Détails par période
        details = inventaire.details_periodes.all().order_by('periode')
        if details.exists():
            self.stdout.write(f'   📅 Détails par période:')
            for detail in details:
                self.stdout.write(f'      - {detail.periode}: {detail.nombre_vehicules} véhicules')
    
    def analyser_recette(self, recette, recalculer):
        """Analyse détaillée d'une recette"""
        self.stdout.write(f'\n💰 RECETTE:')
        
        if recalculer:
            self.stdout.write('   🔄 Recalcul forcé des indicateurs...')
            recette.calculer_indicateurs()
            recette.save()
        
        self.stdout.write(f'   • Montant déclaré: {recette.montant_declare} FCFA')
        
        if recette.inventaire_associe:
            self.stdout.write(f'   ✅ Inventaire associé: OUI')
        else:
            self.stdout.write(
                self.style.WARNING('   ❌ Inventaire associé: NON')
            )
            return
        
        if recette.recette_potentielle is not None:
            self.stdout.write(f'   • Recette potentielle: {recette.recette_potentielle} FCFA')
        else:
            self.stdout.write(
                self.style.WARNING('   ❌ Recette potentielle: Non calculée')
            )
            return
        
        if recette.ecart is not None:
            ecart_str = f'{recette.ecart} FCFA'
            if recette.ecart > 0:
                self.stdout.write(
                    self.style.SUCCESS(f'   • Écart: +{ecart_str} (excédent)')
                )
            elif recette.ecart < 0:
                self.stdout.write(
                    self.style.ERROR(f'   • Écart: {ecart_str} (déficit)')
                )
            else:
                self.stdout.write(f'   • Écart: {ecart_str} (équilibré)')
        
        if recette.taux_deperdition is not None:
            td = float(recette.taux_deperdition)
            couleur = recette.get_couleur_alerte()
            statut = recette.get_statut_deperdition()
            
            # Couleurs pour la console
            if couleur == 'success':
                style_method = self.style.SUCCESS
            elif couleur == 'warning':
                style_method = self.style.WARNING
            elif couleur == 'danger':
                style_method = self.style.ERROR
            else:
                style_method = lambda x: x
            
            self.stdout.write(
                style_method(f'   • Taux déperdition: {td:.2f}% - {statut}')
            )
            
            # Détails du calcul
            self.stdout.write(f'   📈 FORMULE APPLIQUÉE:')
            self.stdout.write(f'      TD = (Écart / Montant déclaré) × 100')
            self.stdout.write(f'      TD = ({recette.ecart} / {recette.montant_declare}) × 100')
            self.stdout.write(f'      TD = {td:.2f}%')
            
            # Interprétation selon les seuils
            self.stdout.write(f'   🎯 INTERPRÉTATION:')
            if td > -5:
                self.stdout.write(
                    self.style.ERROR('      > -5% → IMPERTINENT (journée marquée)')
                )
            elif -5 >= td >= -9.99:
                self.stdout.write(
                    self.style.SUCCESS('      -5% à -9.99% → BON')
                )
            elif -10 >= td >= -29.99:
                self.stdout.write(
                    self.style.WARNING('      -10% à -29.99% → ACCEPTABLE')
                )
            else:
                self.stdout.write(
                    self.style.ERROR('      < -30% → MAUVAIS')
                )
        else:
            self.stdout.write(
                self.style.WARNING('   ❌ Taux déperdition: Non calculé')
            )
    
    def handle_test_manuel(self):
        """Test manuel avec données factices"""
        self.stdout.write('\n🧪 TEST MANUEL AVEC DONNÉES EXEMPLE:')
        self.stdout.write('=' * 60)
        
        # Exemple de calcul manuel
        periodes_exemple = [10, 15, 20, 18, 25, 22, 16, 12, 8, 14]  # 10 périodes
        montant_declare = 50000  # FCFA
        
        # Calculs étape par étape
        somme_vehicules = sum(periodes_exemple)
        nombre_periodes = len(periodes_exemple)
        moyenne_horaire = somme_vehicules / nombre_periodes
        estimation_24h = moyenne_horaire * 24
        vehicules_effectifs = estimation_24h * 0.75
        recette_potentielle = vehicules_effectifs * 500
        ecart = recette_potentielle - montant_declare
        taux_deperdition = (ecart / montant_declare) * 100
        
        self.stdout.write(f'Données exemple: {periodes_exemple}')
        self.stdout.write(f'Montant déclaré: {montant_declare} FCFA')
        self.stdout.write(f'')
        self.stdout.write(f'CALCULS:')
        self.stdout.write(f'• Somme véhicules: {somme_vehicules}')
        self.stdout.write(f'• Nombre périodes: {nombre_periodes}')
        self.stdout.write(f'• Moyenne horaire: {moyenne_horaire:.2f}')
        self.stdout.write(f'• Estimation 24h: {estimation_24h:.2f}')
        self.stdout.write(f'• Véhicules effectifs (75%): {vehicules_effectifs:.2f}')
        self.stdout.write(f'• Recette potentielle: {recette_potentielle:.2f} FCFA')
        self.stdout.write(f'• Écart: {ecart:.2f} FCFA')
        self.stdout.write(f'• Taux déperdition: {taux_deperdition:.2f}%')
        
        # Interprétation
        if taux_deperdition > -5:
            status = "IMPERTINENT"
            color = self.style.ERROR
        elif -5 >= taux_deperdition >= -9.99:
            status = "BON"
            color = self.style.SUCCESS
        elif -10 >= taux_deperdition >= -29.99:
            status = "ACCEPTABLE"
            color = self.style.WARNING
        else:
            status = "MAUVAIS"
            color = self.style.ERROR
        
        self.stdout.write(f'')
        self.stdout.write(color(f'RÉSULTAT: {status}'))