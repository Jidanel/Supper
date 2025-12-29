# ===================================================================
# inventaire/services/notation_agent_service.py
# SERVICE DE NOTATION AVANCÉE DES AGENTS D'INVENTAIRE
# Application SUPPER - Système de notation avec cohérence 3 critères
# ===================================================================
"""
Ce service implémente un algorithme avancé de notation des agents d'inventaire
basé sur la cohérence entre 3 critères:
1. Évolution des recettes (J vs J-1)
2. Évolution du taux de déperdition (J vs J-1)
3. Évolution de la date d'épuisement du stock (J vs J-1)

RÈGLES DE NOTATION:
- 3/3 critères cohérents: Note de base 15-18/20
- 2/3 critères cohérents: Note de base 10-14/20
- 0-1/3 critères cohérents: Note de base 6-9/20
- Journée impertinente: -3 ou -4 points
- Bonus régularité: +2 points par jour de saisie régulière (max +10)

AUTEUR: Service SUPPER
DATE: 2025
"""

import logging
import datetime
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import math

from django.db.models import Sum, Avg, Count, Q, F
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger('supper.notation')


# ===================================================================
# DATACLASSES POUR STRUCTURER LES DONNÉES
# ===================================================================

@dataclass
class DonneesJournalieres:
    """Données d'une journée pour un agent/poste"""
    date: date
    agent_id: int
    agent_nom: str
    poste_id: int
    poste_nom: str
    recette_declaree: Decimal = Decimal('0')
    recette_potentielle: Decimal = Decimal('0')
    taux_deperdition: Optional[float] = None
    date_epuisement_stock: Optional[datetime.date] = None
    est_impertinent: bool = False
    a_saisi_inventaire: bool = False
    
    
@dataclass
class AnalyseCoherence:
    """Résultat de l'analyse de cohérence entre J et J-1"""
    # Critère 1: Évolution recettes
    recettes_coherent: bool = False
    recettes_evolution_pct: float = 0.0
    recettes_direction_attendue: str = ""  # 'baisse' ou 'hausse'
    
    # Critère 2: Évolution taux de déperdition
    taux_coherent: bool = False
    taux_evolution_points: float = 0.0
    taux_direction_attendue: str = ""  # 'baisse' ou 'hausse'
    
    # Critère 3: Évolution date épuisement
    epuisement_coherent: bool = False
    epuisement_evolution_jours: int = 0
    epuisement_direction_attendue: str = ""  # 'eloignement' ou 'rapprochement'
    
    # Résumé
    nombre_criteres_coherents: int = 0
    score_coherence: float = 0.0
    explication: str = ""


@dataclass
class NoteJournaliere:
    """Note calculée pour une journée"""
    date: date
    agent_id: int
    poste_id: int
    
    # Notes composantes
    note_base: float = 0.0
    note_coherence: float = 0.0
    malus_impertinence: float = 0.0
    bonus_regularite: float = 0.0
    
    # Note finale
    note_finale: float = 0.0
    
    # Détails
    analyse_coherence: Optional[AnalyseCoherence] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceAgentPeriode:
    """Performance globale d'un agent sur une période"""
    agent_id: int
    agent_nom: str
    agent_username: str
    
    date_debut: date
    date_fin: date
    
    # Statistiques de saisie
    jours_travailles: int = 0
    jours_possibles: int = 0
    taux_presence: float = 0.0
    
    # Notes
    moyenne_notes_journalieres: float = 0.0
    bonus_regularite_total: float = 0.0
    malus_impertinence_total: float = 0.0
    note_finale: float = 0.0
    
    # Statistiques cohérence
    jours_3_criteres: int = 0
    jours_2_criteres: int = 0
    jours_1_critere: int = 0
    jours_0_critere: int = 0
    
    # Jours impertinents
    jours_impertinents: int = 0
    
    # Postes associés
    postes_travailles: List[str] = field(default_factory=list)
    
    # Détails par jour
    notes_journalieres: List[NoteJournaliere] = field(default_factory=list)


# ===================================================================
# SERVICE PRINCIPAL DE NOTATION
# ===================================================================

class NotationAgentService:
    """
    Service de notation avancée des agents d'inventaire.
    
    Implémente un algorithme de cohérence basé sur 3 critères:
    - Évolution des recettes
    - Évolution du taux de déperdition
    - Évolution de la date d'épuisement du stock
    """
    
    # Paramètres de notation
    SEUIL_TAUX_FORT = -30  # Taux < -30% = fort taux de déperdition
    SEUIL_TAUX_MOYEN = -10  # Taux entre -30% et -10% = moyen
    
    # Barèmes de notes
    NOTE_MAX_3_CRITERES = 18  # Maximum avec 3 critères cohérents
    NOTE_MIN_3_CRITERES = 15  # Minimum avec 3 critères cohérents
    NOTE_MAX_2_CRITERES = 14  # Maximum avec 2 critères cohérents
    NOTE_MIN_2_CRITERES = 10  # Minimum avec 2 critères cohérents
    NOTE_MAX_1_CRITERE = 9   # Maximum avec 0-1 critère cohérent
    NOTE_MIN_1_CRITERE = 6   # Minimum avec 0-1 critère cohérent
    
    # Malus et bonus
    MALUS_IMPERTINENCE_3_CRITERES = 3  # -3 points si impertinent avec 3 critères
    MALUS_IMPERTINENCE_2_CRITERES = 4  # -4 points si impertinent avec 2 critères
    MALUS_IMPERTINENCE_AUTRE = 2       # -2 points sinon
    
    BONUS_REGULARITE_PAR_JOUR = 0.5  # +0.5 point par jour de saisie régulière
    BONUS_REGULARITE_MAX = 2.0       # Maximum +2 points de bonus régularité
    
    # Seuils de cohérence
    SEUIL_EVOLUTION_RECETTES_SIGNIFICATIF = 5.0  # 5% d'évolution = significatif
    SEUIL_EVOLUTION_TAUX_SIGNIFICATIF = 3.0      # 3 points d'évolution = significatif
    SEUIL_EVOLUTION_EPUISEMENT_SIGNIFICATIF = 2  # 2 jours d'évolution = significatif
    
    def __init__(self):
        """Initialisation du service"""
        self.logger = logging.getLogger('supper.notation')
    
    # ===================================================================
    # MÉTHODE PRINCIPALE: CALCULER PERFORMANCE SUR PÉRIODE
    # ===================================================================
    
    def calculer_performance_agent_periode(
        self,
        agent,
        date_debut: date,
        date_fin: date,
        poste=None
    ) -> PerformanceAgentPeriode:
        """
        Calcule la performance globale d'un agent sur une période.
        
        Args:
            agent: Instance UtilisateurSUPPER de l'agent
            date_debut: Date de début de la période
            date_fin: Date de fin de la période
            poste: Optionnel - limiter à un poste spécifique
            
        Returns:
            PerformanceAgentPeriode avec toutes les statistiques et notes
        """
        from inventaire.models import (
            InventaireJournalier, 
            RecetteJournaliere, 
            ConfigurationJour,
            GestionStock
        )
        from accounts.models import Poste
        
        self.logger.info(
            f"[NOTATION] Calcul performance agent {agent.nom_complet} "
            f"du {date_debut} au {date_fin}"
        )
        
        # Initialiser le résultat
        performance = PerformanceAgentPeriode(
            agent_id=agent.id,
            agent_nom=agent.nom_complet,
            agent_username=agent.username,
            date_debut=date_debut,
            date_fin=date_fin
        )
        
        # Récupérer les inventaires de l'agent sur la période
        inventaires_query = InventaireJournalier.objects.filter(
            agent_saisie=agent,
            date__range=[date_debut, date_fin]
        ).select_related('poste')
        
        if poste:
            inventaires_query = inventaires_query.filter(poste=poste)
        
        inventaires = list(inventaires_query.order_by('date', 'poste'))
        
        if not inventaires:
            self.logger.warning(
                f"[NOTATION] Aucun inventaire trouvé pour {agent.nom_complet} "
                f"sur la période {date_debut} - {date_fin}"
            )
            return performance
        
        # Grouper par poste et collecter les postes travaillés
        postes_uniques = set()
        inventaires_par_poste = defaultdict(list)
        
        for inv in inventaires:
            postes_uniques.add(inv.poste.nom)
            inventaires_par_poste[inv.poste_id].append(inv)
        
        performance.postes_travailles = list(postes_uniques)
        
        # Pour chaque poste, calculer les notes journalières
        toutes_notes = []
        
        for poste_id, invs_poste in inventaires_par_poste.items():
            poste_obj = invs_poste[0].poste
            
            # Trier par date
            invs_poste_tries = sorted(invs_poste, key=lambda x: x.date)
            
            for i, inventaire in enumerate(invs_poste_tries):
                # Récupérer les données du jour J
                donnees_j = self._extraire_donnees_journalieres(
                    inventaire, 
                    agent
                )
                
                # Récupérer les données du jour J-1 (si disponible)
                donnees_j_moins_1 = None
                if i > 0:
                    # J-1 dans les inventaires du poste
                    inv_precedent = invs_poste_tries[i - 1]
                    if inv_precedent.date == inventaire.date - timedelta(days=1):
                        donnees_j_moins_1 = self._extraire_donnees_journalieres(
                            inv_precedent,
                            agent
                        )
                else:
                    # Chercher J-1 dans la base
                    donnees_j_moins_1 = self._chercher_donnees_jour_precedent(
                        agent,
                        poste_obj,
                        inventaire.date
                    )
                
                # Calculer la note du jour
                note_jour = self._calculer_note_journaliere(
                    donnees_j,
                    donnees_j_moins_1,
                    poste_obj
                )
                
                toutes_notes.append(note_jour)
        
        # Statistiques globales
        performance.jours_travailles = len(toutes_notes)
        performance.notes_journalieres = toutes_notes
        
        # Calculer le nombre de jours possibles sur la période
        jours_possibles = (date_fin - date_debut).days + 1
        performance.jours_possibles = jours_possibles
        performance.taux_presence = (
            (performance.jours_travailles / jours_possibles * 100) 
            if jours_possibles > 0 else 0
        )
        
        # Statistiques de cohérence
        for note in toutes_notes:
            if note.analyse_coherence:
                nb = note.analyse_coherence.nombre_criteres_coherents
                if nb >= 3:
                    performance.jours_3_criteres += 1
                elif nb == 2:
                    performance.jours_2_criteres += 1
                elif nb == 1:
                    performance.jours_1_critere += 1
                else:
                    performance.jours_0_critere += 1
            
            if note.malus_impertinence > 0:
                performance.jours_impertinents += 1
        
        # Calculer les totaux de malus/bonus
        performance.malus_impertinence_total = sum(
            n.malus_impertinence for n in toutes_notes
        )
        
        # Bonus régularité: basé sur le taux de présence
        if performance.taux_presence >= 80:
            # Saisie très régulière: bonus maximum
            performance.bonus_regularite_total = self.BONUS_REGULARITE_MAX
        elif performance.taux_presence >= 50:
            # Saisie régulière: bonus proportionnel
            performance.bonus_regularite_total = (
                self.BONUS_REGULARITE_MAX * 
                (performance.taux_presence - 50) / 30
            )
        else:
            performance.bonus_regularite_total = 0
        
        # Calculer la note finale
        if toutes_notes:
            # Moyenne des notes journalières (hors bonus régularité global)
            moyenne_base = sum(n.note_finale for n in toutes_notes) / len(toutes_notes)
            performance.moyenne_notes_journalieres = moyenne_base
            
            # Note finale = moyenne + bonus régularité (plafonné à 20)
            performance.note_finale = min(
                20.0,
                moyenne_base + performance.bonus_regularite_total
            )
        
        self.logger.info(
            f"[NOTATION] Performance calculée pour {agent.nom_complet}: "
            f"Note finale = {performance.note_finale:.2f}/20 | "
            f"Jours travaillés = {performance.jours_travailles} | "
            f"Cohérence 3/3 = {performance.jours_3_criteres} jours"
        )
        
        return performance
    
    # ===================================================================
    # EXTRACTION DES DONNÉES JOURNALIÈRES
    # ===================================================================
    
    def _extraire_donnees_journalieres(
        self,
        inventaire,
        agent
    ) -> DonneesJournalieres:
        """
        Extrait les données d'un inventaire pour l'analyse.
        
        Args:
            inventaire: Instance InventaireJournalier
            agent: Instance UtilisateurSUPPER
            
        Returns:
            DonneesJournalieres avec toutes les informations du jour
        """
        from inventaire.models import RecetteJournaliere, GestionStock, ConfigurationJour
        
        donnees = DonneesJournalieres(
            date=inventaire.date,
            agent_id=agent.id,
            agent_nom=agent.nom_complet,
            poste_id=inventaire.poste_id,
            poste_nom=inventaire.poste.nom,
            a_saisi_inventaire=True
        )
        
        # Récupérer la recette associée
        try:
            recette = RecetteJournaliere.objects.get(
                poste=inventaire.poste,
                date=inventaire.date
            )
            donnees.recette_declaree = recette.montant_declare or Decimal('0')
            donnees.recette_potentielle = recette.recette_potentielle or Decimal('0')
            donnees.taux_deperdition = (
                float(recette.taux_deperdition) 
                if recette.taux_deperdition else None
            )
        except RecetteJournaliere.DoesNotExist:
            self.logger.debug(
                f"[NOTATION] Pas de recette trouvée pour {inventaire.poste.nom} "
                f"le {inventaire.date}"
            )
        
        # Récupérer la date d'épuisement du stock
        try:
            stock = GestionStock.objects.get(poste=inventaire.poste)
            # Utiliser date_epuisement_prevue si disponible
            if hasattr(stock, 'date_epuisement_prevue'):
                donnees.date_epuisement_stock = stock.date_epuisement_prevue
            elif hasattr(stock, 'date_epuisement'):
                donnees.date_epuisement_stock = stock.date_epuisement
            else:
                # Calculer approximativement si non disponible
                donnees.date_epuisement_stock = self._estimer_date_epuisement(
                    stock,
                    inventaire.poste,
                    inventaire.date
                )
        except Exception as e:
            self.logger.debug(
                f"[NOTATION] Erreur récupération stock: {e}"
            )
        
        # Vérifier si journée impertinente
        try:
            config = ConfigurationJour.objects.get(date=inventaire.date)
            donnees.est_impertinent = (config.statut == 'impertinent')
        except ConfigurationJour.DoesNotExist:
            # Vérifier via le taux de déperdition
            if donnees.taux_deperdition and donnees.taux_deperdition > -5:
                # Taux > -5% suggère une journée impertinente
                donnees.est_impertinent = True
        
        return donnees
    
    def _chercher_donnees_jour_precedent(
        self,
        agent,
        poste,
        date_j: date
    ) -> Optional[DonneesJournalieres]:
        """
        Cherche les données du jour J-1 dans la base.
        """
        from inventaire.models import InventaireJournalier
        
        date_j_moins_1 = date_j - timedelta(days=1)
        
        try:
            inv_precedent = InventaireJournalier.objects.get(
                poste=poste,
                date=date_j_moins_1
            )
            return self._extraire_donnees_journalieres(inv_precedent, agent)
        except InventaireJournalier.DoesNotExist:
            return None
    
    def _estimer_date_epuisement(
        self,
        stock,
        poste,
        date_reference: date
    ) -> Optional[date]:
        """
        Estime la date d'épuisement du stock basé sur la consommation moyenne.
        """
        from inventaire.models import RecetteJournaliere
        
        try:
            # Stock actuel en tickets (valeur / 500 FCFA)
            stock_tickets = int(float(stock.valeur_monetaire) / 500) if stock.valeur_monetaire else 0
            
            if stock_tickets <= 0:
                return date_reference
            
            # Consommation moyenne sur les 30 derniers jours
            date_debut = date_reference - timedelta(days=30)
            recettes = RecetteJournaliere.objects.filter(
                poste=poste,
                date__range=[date_debut, date_reference]
            ).aggregate(
                total=Sum('montant_declare'),
                nb_jours=Count('id')
            )
            
            if recettes['nb_jours'] and recettes['nb_jours'] > 0 and recettes['total']:
                consommation_moyenne_fcfa = float(recettes['total']) / recettes['nb_jours']
                consommation_moyenne_tickets = consommation_moyenne_fcfa / 500
                
                if consommation_moyenne_tickets > 0:
                    jours_restants = int(stock_tickets / consommation_moyenne_tickets)
                    return date_reference + timedelta(days=jours_restants)
            
            # Fallback: estimation par défaut
            return date_reference + timedelta(days=90)
            
        except Exception as e:
            self.logger.error(f"[NOTATION] Erreur estimation date épuisement: {e}")
            return None
    
    # ===================================================================
    # ANALYSE DE COHÉRENCE
    # ===================================================================
    
    def _analyser_coherence(
        self,
        donnees_j: DonneesJournalieres,
        donnees_j_moins_1: Optional[DonneesJournalieres],
        poste
    ) -> AnalyseCoherence:
        """
        Analyse la cohérence entre les données de J et J-1.
        
        La cohérence est définie selon 2 scénarios:
        
        SCÉNARIO A - Fort taux de déperdition détecté:
        - Recettes en baisse = COHÉRENT (l'agent signale un problème)
        - Taux de déperdition qui reste fort ou s'aggrave = COHÉRENT
        - Date d'épuisement qui s'éloigne = COHÉRENT (moins de tickets vendus)
        
        SCÉNARIO B - Amélioration détectée:
        - Recettes en hausse = COHÉRENT
        - Taux de déperdition qui s'améliore (moins négatif) = COHÉRENT
        - Date d'épuisement qui se rapproche = COHÉRENT (plus de tickets vendus)
        """
        analyse = AnalyseCoherence()
        
        # Si pas de J-1, on ne peut pas analyser la cohérence
        if not donnees_j_moins_1:
            analyse.explication = "Pas de données J-1 disponibles"
            return analyse
        
        # ===== CRITÈRE 1: ÉVOLUTION DES RECETTES =====
        if donnees_j.recette_declaree and donnees_j_moins_1.recette_declaree:
            recette_j = float(donnees_j.recette_declaree)
            recette_j_moins_1 = float(donnees_j_moins_1.recette_declaree)
            
            if recette_j_moins_1 > 0:
                evolution_pct = ((recette_j - recette_j_moins_1) / recette_j_moins_1) * 100
                analyse.recettes_evolution_pct = evolution_pct
                
                # Déterminer la direction attendue selon le taux de déperdition
                if donnees_j.taux_deperdition and donnees_j.taux_deperdition < self.SEUIL_TAUX_FORT:
                    # Fort taux de déperdition -> on attend une baisse des recettes
                    analyse.recettes_direction_attendue = 'baisse'
                    analyse.recettes_coherent = evolution_pct < -self.SEUIL_EVOLUTION_RECETTES_SIGNIFICATIF
                else:
                    # Taux normal -> on attend une stabilité ou hausse
                    analyse.recettes_direction_attendue = 'hausse_stable'
                    analyse.recettes_coherent = evolution_pct >= -self.SEUIL_EVOLUTION_RECETTES_SIGNIFICATIF
        
        # ===== CRITÈRE 2: ÉVOLUTION DU TAUX DE DÉPERDITION =====
        if donnees_j.taux_deperdition is not None and donnees_j_moins_1.taux_deperdition is not None:
            taux_j = donnees_j.taux_deperdition
            taux_j_moins_1 = donnees_j_moins_1.taux_deperdition
            
            evolution_taux = taux_j - taux_j_moins_1  # Positif = amélioration
            analyse.taux_evolution_points = evolution_taux
            
            # Si fort taux de déperdition
            if taux_j < self.SEUIL_TAUX_FORT:
                # On attend que le taux reste fort ou s'aggrave (cohérent avec baisse recettes)
                analyse.taux_direction_attendue = 'maintien_fort'
                analyse.taux_coherent = taux_j <= taux_j_moins_1
            else:
                # Sinon on attend une amélioration ou stabilité
                analyse.taux_direction_attendue = 'amelioration'
                analyse.taux_coherent = evolution_taux >= -self.SEUIL_EVOLUTION_TAUX_SIGNIFICATIF
        
        # ===== CRITÈRE 3: ÉVOLUTION DATE D'ÉPUISEMENT =====
        if donnees_j.date_epuisement_stock and donnees_j_moins_1.date_epuisement_stock:
            jours_restants_j = (donnees_j.date_epuisement_stock - donnees_j.date).days
            jours_restants_j_moins_1 = (donnees_j_moins_1.date_epuisement_stock - donnees_j_moins_1.date).days
            
            evolution_jours = jours_restants_j - jours_restants_j_moins_1
            analyse.epuisement_evolution_jours = evolution_jours
            
            # Si fort taux de déperdition et recettes en baisse
            if donnees_j.taux_deperdition and donnees_j.taux_deperdition < self.SEUIL_TAUX_FORT:
                # On attend que la date s'éloigne (moins de ventes = stock dure plus)
                analyse.epuisement_direction_attendue = 'eloignement'
                analyse.epuisement_coherent = evolution_jours > 0
            else:
                # Sinon on attend un rapprochement (plus de ventes)
                analyse.epuisement_direction_attendue = 'rapprochement'
                analyse.epuisement_coherent = evolution_jours <= self.SEUIL_EVOLUTION_EPUISEMENT_SIGNIFICATIF
        
        # ===== COMPTAGE DES CRITÈRES COHÉRENTS =====
        criteres_evalues = 0
        criteres_coherents = 0
        
        if analyse.recettes_direction_attendue:
            criteres_evalues += 1
            if analyse.recettes_coherent:
                criteres_coherents += 1
                
        if analyse.taux_direction_attendue:
            criteres_evalues += 1
            if analyse.taux_coherent:
                criteres_coherents += 1
                
        if analyse.epuisement_direction_attendue:
            criteres_evalues += 1
            if analyse.epuisement_coherent:
                criteres_coherents += 1
        
        analyse.nombre_criteres_coherents = criteres_coherents
        
        # Calculer score de cohérence (0-1)
        if criteres_evalues > 0:
            analyse.score_coherence = criteres_coherents / criteres_evalues
        
        # Générer explication
        analyse.explication = self._generer_explication_coherence(analyse, donnees_j)
        
        return analyse
    
    def _generer_explication_coherence(
        self,
        analyse: AnalyseCoherence,
        donnees: DonneesJournalieres
    ) -> str:
        """Génère une explication textuelle de l'analyse de cohérence."""
        parties = []
        
        nb = analyse.nombre_criteres_coherents
        
        if nb >= 3:
            parties.append(f"✅ Excellente cohérence ({nb}/3 critères)")
        elif nb == 2:
            parties.append(f"⚠️ Cohérence partielle ({nb}/3 critères)")
        else:
            parties.append(f"❌ Faible cohérence ({nb}/3 critères)")
        
        if analyse.recettes_direction_attendue:
            signe = "✓" if analyse.recettes_coherent else "✗"
            parties.append(
                f"  {signe} Recettes: {analyse.recettes_evolution_pct:+.1f}% "
                f"(attendu: {analyse.recettes_direction_attendue})"
            )
        
        if analyse.taux_direction_attendue:
            signe = "✓" if analyse.taux_coherent else "✗"
            parties.append(
                f"  {signe} Taux: {analyse.taux_evolution_points:+.1f} pts "
                f"(attendu: {analyse.taux_direction_attendue})"
            )
        
        if analyse.epuisement_direction_attendue:
            signe = "✓" if analyse.epuisement_coherent else "✗"
            parties.append(
                f"  {signe} Épuisement: {analyse.epuisement_evolution_jours:+d} jours "
                f"(attendu: {analyse.epuisement_direction_attendue})"
            )
        
        return "\n".join(parties)
    
    # ===================================================================
    # CALCUL DE LA NOTE JOURNALIÈRE
    # ===================================================================
    
    def _calculer_note_journaliere(
        self,
        donnees_j: DonneesJournalieres,
        donnees_j_moins_1: Optional[DonneesJournalieres],
        poste
    ) -> NoteJournaliere:
        """
        Calcule la note journalière d'un agent.
        
        BARÈME:
        - 3/3 critères cohérents: 15-18/20
        - 2/3 critères cohérents: 10-14/20
        - 0-1/3 critères cohérents: 6-9/20
        - Impertinent avec 3 critères: -3 points
        - Impertinent avec 2 critères: -4 points
        """
        note = NoteJournaliere(
            date=donnees_j.date,
            agent_id=donnees_j.agent_id,
            poste_id=donnees_j.poste_id
        )
        
        # Analyser la cohérence
        analyse = self._analyser_coherence(donnees_j, donnees_j_moins_1, poste)
        note.analyse_coherence = analyse
        
        nb_criteres = analyse.nombre_criteres_coherents
        score_coherence = analyse.score_coherence
        
        # Calculer la note de base selon le nombre de critères cohérents
        if nb_criteres >= 3:
            # 3/3 critères: note entre 15 et 18
            note_min = self.NOTE_MIN_3_CRITERES
            note_max = self.NOTE_MAX_3_CRITERES
            
        elif nb_criteres == 2:
            # 2/3 critères: note entre 10 et 14
            note_min = self.NOTE_MIN_2_CRITERES
            note_max = self.NOTE_MAX_2_CRITERES
            
        else:
            # 0-1/3 critères: note entre 6 et 9
            note_min = self.NOTE_MIN_1_CRITERE
            note_max = self.NOTE_MAX_1_CRITERE
        
        # Moduler la note dans la fourchette selon la qualité des données
        # (évolutions plus marquées = meilleur score dans la fourchette)
        score_modulation = self._calculer_score_modulation(analyse, donnees_j)
        
        note.note_base = note_min + (note_max - note_min) * score_modulation
        note.note_coherence = note.note_base
        
        # Appliquer le malus si journée impertinente
        if donnees_j.est_impertinent:
            if nb_criteres >= 3:
                note.malus_impertinence = self.MALUS_IMPERTINENCE_3_CRITERES
            elif nb_criteres == 2:
                note.malus_impertinence = self.MALUS_IMPERTINENCE_2_CRITERES
            else:
                note.malus_impertinence = self.MALUS_IMPERTINENCE_AUTRE
        
        # Calculer la note finale (plancher à 0)
        note.note_finale = max(0, note.note_base - note.malus_impertinence)
        
        # Stocker les détails
        note.details = {
            'nb_criteres_coherents': nb_criteres,
            'score_coherence': score_coherence,
            'score_modulation': score_modulation,
            'est_impertinent': donnees_j.est_impertinent,
            'recette_declaree': float(donnees_j.recette_declaree),
            'taux_deperdition': donnees_j.taux_deperdition,
            'explication': analyse.explication
        }
        
        self.logger.debug(
            f"[NOTATION] Note {donnees_j.date} pour {donnees_j.poste_nom}: "
            f"{note.note_finale:.2f}/20 (base={note.note_base:.2f}, "
            f"malus={note.malus_impertinence})"
        )
        
        return note
    
    def _calculer_score_modulation(
        self,
        analyse: AnalyseCoherence,
        donnees: DonneesJournalieres
    ) -> float:
        """
        Calcule un score de modulation (0-1) pour affiner la note dans la fourchette.
        
        Prend en compte:
        - L'amplitude des évolutions (plus c'est marqué, mieux c'est)
        - La qualité des données disponibles
        """
        scores = []
        
        # Score basé sur l'amplitude de l'évolution des recettes
        if analyse.recettes_coherent and abs(analyse.recettes_evolution_pct) > 0:
            # Plus l'évolution est marquée, plus le score est élevé
            score_recettes = min(1.0, abs(analyse.recettes_evolution_pct) / 20)
            scores.append(score_recettes)
        
        # Score basé sur l'amplitude de l'évolution du taux
        if analyse.taux_coherent and abs(analyse.taux_evolution_points) > 0:
            score_taux = min(1.0, abs(analyse.taux_evolution_points) / 10)
            scores.append(score_taux)
        
        # Score basé sur l'amplitude de l'évolution de l'épuisement
        if analyse.epuisement_coherent and abs(analyse.epuisement_evolution_jours) > 0:
            score_epuisement = min(1.0, abs(analyse.epuisement_evolution_jours) / 7)
            scores.append(score_epuisement)
        
        # Moyenne des scores disponibles, ou 0.5 par défaut
        if scores:
            return sum(scores) / len(scores)
        else:
            return 0.5
    
    # ===================================================================
    # CLASSEMENT DES AGENTS
    # ===================================================================
    
    def generer_classement_agents(
        self,
        date_debut: date,
        date_fin: date,
        postes_ids: Optional[List[int]] = None
    ) -> List[PerformanceAgentPeriode]:
        """
        Génère le classement des agents d'inventaire sur une période.
        
        Args:
            date_debut: Date de début de la période
            date_fin: Date de fin de la période
            postes_ids: Optionnel - filtrer sur certains postes
            
        Returns:
            Liste des performances triées par note finale décroissante
        """
        from accounts.models import UtilisateurSUPPER
        from inventaire.models import InventaireJournalier
        
        self.logger.info(
            f"[NOTATION] Génération classement agents du {date_debut} au {date_fin}"
        )
        
        # Trouver tous les agents ayant saisi des inventaires sur la période
        query = InventaireJournalier.objects.filter(
            date__range=[date_debut, date_fin],
            agent_saisie__isnull=False
        )
        
        if postes_ids:
            query = query.filter(poste_id__in=postes_ids)
        
        agents_ids = query.values_list('agent_saisie_id', flat=True).distinct()
        
        agents = UtilisateurSUPPER.objects.filter(
            id__in=agents_ids,
            habilitation='agent_inventaire'
        )
        
        # Calculer la performance de chaque agent
        performances = []
        
        for agent in agents:
            try:
                perf = self.calculer_performance_agent_periode(
                    agent,
                    date_debut,
                    date_fin
                )
                performances.append(perf)
            except Exception as e:
                self.logger.error(
                    f"[NOTATION] Erreur calcul performance pour {agent.nom_complet}: {e}"
                )
        
        # Trier par note finale décroissante
        performances.sort(key=lambda x: x.note_finale, reverse=True)
        
        self.logger.info(
            f"[NOTATION] Classement généré avec {len(performances)} agents"
        )
        
        return performances
    
    def obtenir_rang_agent(
        self,
        agent,
        date_debut: date,
        date_fin: date
    ) -> Dict[str, Any]:
        """
        Obtient le rang d'un agent dans le classement.
        
        Returns:
            Dict avec 'rang', 'total_agents', 'note', 'details'
        """
        classement = self.generer_classement_agents(date_debut, date_fin)
        
        for i, perf in enumerate(classement):
            if perf.agent_id == agent.id:
                return {
                    'rang': i + 1,
                    'total_agents': len(classement),
                    'note': perf.note_finale,
                    'jours_travailles': perf.jours_travailles,
                    'taux_presence': perf.taux_presence,
                    'jours_3_criteres': perf.jours_3_criteres,
                    'jours_impertinents': perf.jours_impertinents,
                    'performance': perf
                }
        
        return {
            'rang': None,
            'total_agents': len(classement),
            'note': 0,
            'message': "Agent non trouvé dans le classement"
        }


# ===================================================================
# INSTANCE SINGLETON DU SERVICE
# ===================================================================

_notation_service_instance = None

def get_notation_service() -> NotationAgentService:
    """Retourne l'instance singleton du service de notation."""
    global _notation_service_instance
    if _notation_service_instance is None:
        _notation_service_instance = NotationAgentService()
    return _notation_service_instance