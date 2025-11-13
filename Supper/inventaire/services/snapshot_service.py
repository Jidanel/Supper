# inventaire/services/snapshot_service.py
"""
Service pour gérer les snapshots d'état des inventaires
Permet de capturer et reconstruire l'état d'un poste à n'importe quelle date
"""

from django.db.models import Sum, Avg, Count
from datetime import date, timedelta
from decimal import Decimal
from inventaire.models import *
import logging

logger = logging.getLogger('supper')


class SnapshotService:
    """Service centralisé pour la gestion des snapshots d'inventaire"""
    
    @staticmethod
    def creer_snapshot_pour_date(poste, date_snapshot):
        """
        Crée un snapshot complet de l'état d'un poste à une date donnée
        
        Args:
            poste: Instance du Poste
            date_snapshot: Date pour laquelle créer le snapshot
            
        Returns:
            EtatInventaireSnapshot: Le snapshot créé ou mis à jour
        """
        
        
        # 1. CALCULER LE TAUX DE DÉPERDITION à cette date
        derniere_recette = RecetteJournaliere.objects.filter(
            poste=poste,
            date__lte=date_snapshot,
            taux_deperdition__isnull=False
        ).order_by('-date').first()
        
        taux_deperdition = derniere_recette.taux_deperdition if derniere_recette else None
        
        # 2. CALCULER LE RISQUE DE BAISSE ANNUEL à cette date
        annee = date_snapshot.year
        debut_annee = date(annee, 1, 1)
        
        # Recettes cumulées de l'année jusqu'à date_snapshot
        recettes_actuelles = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[debut_annee, date_snapshot]
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        # Même période année précédente
        debut_annee_prec = date(annee - 1, 1, 1)
        
        # IMPORTANT: Calculer jusqu'au même jour/mois l'année précédente
        try:
            date_fin_prec = date(annee - 1, date_snapshot.month, date_snapshot.day)
        except ValueError:
            # Si le jour n'existe pas (ex: 29 février), prendre le dernier jour du mois
            import calendar
            dernier_jour = calendar.monthrange(annee - 1, date_snapshot.month)[1]
            date_fin_prec = date(annee - 1, date_snapshot.month, dernier_jour)
        
        recettes_n1 = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[debut_annee_prec, date_fin_prec]
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        # Calculer l'évolution
        risque_baisse = False
        pourcentage_evolution = None
        
        if recettes_n1 > 0:
            pourcentage_evolution = ((recettes_actuelles - recettes_n1) / recettes_n1) * 100
            risque_baisse = pourcentage_evolution < -5  # Seuil de -5%
        
        # 3. CALCULER LE STOCK à cette date via Event Sourcing
        stock_valeur, stock_tickets = StockEvent.get_stock_at_date(poste, date_snapshot)
        
        # 4. CALCULER LA DATE D'ÉPUISEMENT DU STOCK
        date_epuisement = None
        risque_grand_stock = False
        ventes = {'total': None, 'count': 0}  # CORRECTION: Initialisation de la variable ventes
        
        if stock_valeur > 0:
            # Moyenne des ventes sur les 30 jours précédents
            date_debut_moyenne = date_snapshot - timedelta(days=30)
            
            ventes = RecetteJournaliere.objects.filter(
                poste=poste,
                date__range=[date_debut_moyenne, date_snapshot],
                date__lte=date_snapshot  # IMPORTANT: seulement les jours <= date_snapshot
            ).aggregate(
                total=Sum('montant_declare'),
                count=Count('id')
            )
            
            if ventes['total'] and ventes['count'] > 0:
                vente_moy_jour = ventes['total'] / ventes['count']
                
                if vente_moy_jour > 0:
                    jours_restants = int(stock_valeur / vente_moy_jour)
                    date_epuisement = date_snapshot + timedelta(days=jours_restants)
                    
                    # Vérifier si dépasse le 31 décembre de l'année du snapshot
                    fin_annee = date(date_snapshot.year, 12, 31)
                    risque_grand_stock = date_epuisement > fin_annee
        
        # 5. CRÉER OU METTRE À JOUR LE SNAPSHOT
        snapshot, created = EtatInventaireSnapshot.objects.update_or_create(
            poste=poste,
            date_snapshot=date_snapshot,
            defaults={
                'taux_deperdition': taux_deperdition,
                'risque_baisse_annuel': risque_baisse,
                'recettes_periode_actuelle': recettes_actuelles,
                'recettes_periode_n1': recettes_n1,
                'pourcentage_evolution': pourcentage_evolution,
                'stock_valeur': stock_valeur,
                'stock_tickets': stock_tickets,
                'date_epuisement_prevu': date_epuisement,
                'risque_grand_stock': risque_grand_stock,
                'metadata': {
                    'annee_reference': annee,
                    'derniere_recette_date': derniere_recette.date.isoformat() if derniere_recette else None,
                    'jours_donnees_stock': ventes['count'] if ventes['count'] else 0,
                }
            }
        )
        
        logger.info(
            f"Snapshot créé pour {poste.nom} au {date_snapshot}: "
            f"Taux={taux_deperdition}, Risque baisse={risque_baisse}, Stock={stock_valeur}"
        )
        
        return snapshot
    
    @staticmethod
    def creer_snapshots_periode(date_debut, date_fin, postes=None):
        """
        Crée des snapshots pour tous les postes sur une période
        Utile pour l'initialisation ou la reconstruction
        
        Args:
            date_debut: Date de début
            date_fin: Date de fin
            postes: Liste de postes (optionnel, tous par défaut)
            
        Returns:
            dict: Statistiques de création
        """
        from accounts.models import Poste
        
        if postes is None:
            postes = Poste.objects.filter(is_active=True)
        
        stats = {
            'total_snapshots': 0,
            'snapshots_crees': 0,
            'snapshots_mis_a_jour': 0,
            'erreurs': 0
        }
        
        current_date = date_debut
        
        while current_date <= date_fin:
            for poste in postes:
                try:
                    snapshot, created = SnapshotService.creer_snapshot_pour_date(
                        poste, current_date
                    )
                    
                    stats['total_snapshots'] += 1
                    if created:
                        stats['snapshots_crees'] += 1
                    else:
                        stats['snapshots_mis_a_jour'] += 1
                        
                except Exception as e:
                    logger.error(
                        f"Erreur création snapshot {poste.nom} - {current_date}: {str(e)}"
                    )
                    stats['erreurs'] += 1
            
            current_date += timedelta(days=1)
        
        logger.info(f"Création snapshots terminée: {stats}")
        return stats
    
    @staticmethod
    def obtenir_snapshot(poste, date_snapshot, creer_si_absent=True):
        """
        Récupère un snapshot pour un poste à une date donnée
        Le crée automatiquement s'il n'existe pas
        
        Args:
            poste: Instance du Poste
            date_snapshot: Date du snapshot
            creer_si_absent: Créer le snapshot s'il n'existe pas
            
        Returns:
            EtatInventaireSnapshot ou None
        """
        from inventaire.models import EtatInventaireSnapshot
        
        try:
            return EtatInventaireSnapshot.objects.get(
                poste=poste,
                date_snapshot=date_snapshot
            )
        except EtatInventaireSnapshot.DoesNotExist:
            if creer_si_absent:
                return SnapshotService.creer_snapshot_pour_date(poste, date_snapshot)
            return None
    
    @staticmethod
    def calculer_impact_taux_deperdition(snapshot_actuel, snapshot_initial):
        """
        Calcule l'impact sur le taux de déperdition entre deux périodes
        
        Règles métier:
        - Régression du taux (ex: -35% → -32%) = POSITIF
        - Passage en zone critique (>= -30% → < -30%) = NÉGATIF
        - Sortie de zone critique (< -30% → >= -30%) = POSITIF
        - Dégradation du taux = NÉGATIF
        - Pas de changement = NUL
        
        Returns:
            str: 'positif', 'negatif', ou 'nul'
        """
        if not snapshot_actuel or not snapshot_actuel.taux_deperdition:
            return 'nul'
        
        if not snapshot_initial or not snapshot_initial.taux_deperdition:
            # Pas de référence initiale
            if snapshot_actuel.taux_deperdition < -30:
                return 'negatif'
            return 'nul'
        
        taux_initial = snapshot_initial.taux_deperdition
        taux_actuel = snapshot_actuel.taux_deperdition
        
        # Cas 1: Régression du taux (amélioration)
        if taux_actuel > taux_initial:
            return 'positif'
        
        # Cas 2: Passage en zone critique
        if taux_initial >= -30 and taux_actuel < -30:
            return 'negatif'
        
        # Cas 3: Sortie de zone critique
        if taux_initial < -30 and taux_actuel >= -30:
            return 'positif'
        
        # Cas 4: Dégradation
        if taux_actuel < taux_initial:
            return 'negatif'
        
        # Cas 5: Pas de changement
        return 'nul'
    
    @staticmethod
    def calculer_impact_risque_baisse(snapshot_actuel, snapshot_initial):
        """
        Calcule l'impact sur le risque de baisse annuel
        
        Règles:
        - Était en risque et ne l'est plus = POSITIF
        - N'était pas en risque et l'est maintenant = NÉGATIF
        - Pas de changement = NUL
        
        Returns:
            str: 'positif', 'negatif', ou 'nul'
        """
        if not snapshot_actuel or not snapshot_initial:
            return 'nul'
        
        initial_risque = snapshot_initial.risque_baisse_annuel
        actuel_risque = snapshot_actuel.risque_baisse_annuel
        
        # Sortie du risque
        if initial_risque and not actuel_risque:
            return 'positif'
        
        # Entrée en risque
        if not initial_risque and actuel_risque:
            return 'negatif'
        
        # Pas de changement
        return 'nul'
    
    @staticmethod
    def calculer_impact_grand_stock(snapshot_actuel, snapshot_initial):
        """
        Calcule l'impact sur le risque de grand stock
        
        Règles:
        - Date d'épuisement s'est rapprochée du 31 déc = POSITIF
        - Date d'épuisement s'est éloignée du 31 déc = NÉGATIF
        - Même date = NUL
        
        Returns:
            str: 'positif', 'negatif', ou 'nul'
        """
        if not snapshot_actuel or not snapshot_initial:
            return 'nul'
        
        if not snapshot_actuel.date_epuisement_prevu or not snapshot_initial.date_epuisement_prevu:
            return 'nul'
        
        # Rapprochement = positif
        if snapshot_actuel.date_epuisement_prevu < snapshot_initial.date_epuisement_prevu:
            return 'positif'
        
        # Éloignement = négatif
        if snapshot_actuel.date_epuisement_prevu > snapshot_initial.date_epuisement_prevu:
            return 'negatif'
        
        return 'nul'
    
    @staticmethod
    def compter_journees_impertinentes(poste, date_debut, date_fin):
        """
        Compte les journées impertinentes pour un poste sur une période
        
        Args:
            poste: Instance du Poste
            date_debut: Date de début
            date_fin: Date de fin
            
        Returns:
            int: Nombre de journées impertinentes
        """
        from inventaire.models import JourneeImpertinente
        
        return JourneeImpertinente.objects.filter(
            poste=poste,
            date__range=[date_debut, date_fin]
        ).count()