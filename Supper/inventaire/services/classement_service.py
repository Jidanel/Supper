# ===================================================================
# inventaire/services/classement_service.py - Calcul performances
# ===================================================================

from decimal import Decimal
from datetime import date, timedelta
from django.db.models import Avg, Sum, Q, Min, Max
import calendar
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict

from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone

# Import du service de notation
from inventaire.services.notation_agent_service import (
    get_notation_service,
    PerformanceAgentPeriode,
    NoteJournaliere
)

logger = logging.getLogger('supper.classement')

from inventaire.models import (
    RecetteJournaliere, InventaireJournalier, ConfigurationJour,
    GestionStock, HistoriqueStock, HistoriqueAffectation
)
from inventaire.models_performance import PerformancePoste, PerformanceAgent
from accounts.models import Poste, UtilisateurSUPPER


class ClassementService:
    """
    Service pour calculer les performances et classements
    """
    
    @staticmethod
    def calculer_date_epuisement_stock(poste, date_ref):
        """
        Calcule la date d'épuisement du stock à une date donnée
        Exclut les transferts et approvisionnements
        """
        try:
            stock = GestionStock.objects.get(poste=poste)
            valeur_stock = stock.valeur_monetaire
        except GestionStock.DoesNotExist:
            return None
        
        if valeur_stock <= 0:
            return date_ref
        
        # Ventes moyennes sur 30 jours avant date_ref
        date_debut = date_ref - timedelta(days=30)
        
        ventes = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[date_debut, date_ref]
        ).aggregate(
            total=Sum('montant_declare'),
            count=Sum(1)
        )
        
        if not ventes['count'] or ventes['count'] == 0:
            return None
        
        vente_moyenne = ventes['total'] / ventes['count']
        
        if vente_moyenne <= 0:
            return None
        
        jours_restants = int(valeur_stock / vente_moyenne)
        return date_ref + timedelta(days=jours_restants)
    
    @staticmethod
    def calculer_date_epuisement_corrigee(poste, date_debut, date_fin):
        """
        Calcule la date d'épuisement en excluant les mouvements de stock
        (transferts, approvisionnements)
        """
        # Récupérer tous les mouvements de crédit dans la période
        credits = HistoriqueStock.objects.filter(
            poste=poste,
            type_mouvement='CREDIT',
            date_mouvement__range=[date_debut, date_fin]
        ).aggregate(total=Sum('montant'))['total'] or Decimal('0')
        
        # Si des crédits existent, recalculer sans eux
        if credits > 0:
            try:
                stock = GestionStock.objects.get(poste=poste)
                stock_corrige = stock.valeur_monetaire - credits
            except GestionStock.DoesNotExist:
                return None
            
            # Recalculer avec stock corrigé
            ventes = RecetteJournaliere.objects.filter(
                poste=poste,
                date__range=[date_debut, date_fin]
            ).aggregate(
                total=Sum('montant_declare'),
                count=Sum(1)
            )
            
            if not ventes['count'] or ventes['count'] == 0:
                return None
            
            vente_moyenne = ventes['total'] / ventes['count']
            
            if vente_moyenne <= 0 or stock_corrige <= 0:
                return None
            
            jours_restants = int(stock_corrige / vente_moyenne)
            return date_fin + timedelta(days=jours_restants)
        
        # Pas de mouvements, calcul normal
        return ClassementService.calculer_date_epuisement_stock(poste, date_fin)
    
    @staticmethod
    def calculer_performance_poste(poste, date_debut, date_fin):
        """
        Calcule et enregistre la performance d'un poste sur une période
        Exclut les jours impertinents
        """
        # Récupérer jours impertinents
        jours_impertinents = ConfigurationJour.objects.filter(
            statut='impertinent',
            date__range=[date_debut, date_fin]
        ).values_list('date', flat=True)
        
        # Filtrer les recettes
        recettes = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[date_debut, date_fin]
        ).exclude(date__in=jours_impertinents)
        
        if not recettes.exists():
            return None
        
        # Calculer taux moyens
        stats_taux = recettes.aggregate(
            taux_moyen=Avg('taux_deperdition'),
            taux_min=Min('taux_deperdition'),
            taux_max=Max('taux_deperdition')
        )
        
        # Calculer évolution stock
        date_stock_debut = ClassementService.calculer_date_epuisement_corrigee(
            poste, date_debut - timedelta(days=30), date_debut
        )
        date_stock_fin = ClassementService.calculer_date_epuisement_corrigee(
            poste, date_debut, date_fin
        )
        
        evolution_stock = 0
        if date_stock_debut and date_stock_fin:
            evolution_stock = (date_stock_debut - date_stock_fin).days
        
        # Calculer évolution recettes (par rapport période précédente)
        duree_periode = (date_fin - date_debut).days
        date_debut_precedent = date_debut - timedelta(days=duree_periode)
        date_fin_precedent = date_debut - timedelta(days=1)
        
        recettes_periode = recettes.aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        recettes_precedent = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[date_debut_precedent, date_fin_precedent]
        ).exclude(date__in=jours_impertinents).aggregate(
            total=Sum('montant_declare')
        )['total'] or Decimal('0')
        
        taux_evolution = None
        if recettes_precedent > 0:
            taux_evolution = ((recettes_periode - recettes_precedent) / recettes_precedent) * 100
        
        # Identifier motifs
        motifs = []
        if stats_taux['taux_moyen'] and stats_taux['taux_moyen'] < -30:
            motifs.append('taux_deperdition')
        
        if date_stock_fin and date_stock_fin > date(date_fin.year, 12, 31):
            motifs.append('grand_stock')
        
        if taux_evolution and taux_evolution < -5:
            motifs.append('risque_baisse')
        
        # Créer/mettre à jour performance
        perf, created = PerformancePoste.objects.update_or_create(
            poste=poste,
            date_debut=date_debut,
            date_fin=date_fin,
            defaults={
                'motifs': motifs,
                'taux_moyen_deperdition': stats_taux['taux_moyen'],
                'taux_plus_bas': stats_taux['taux_min'],
                'taux_plus_eleve': stats_taux['taux_max'],
                'date_epuisement_debut': date_stock_debut,
                'date_epuisement_fin': date_stock_fin,
                'evolution_stock_jours': evolution_stock,
                'recettes_periode': recettes_periode,
                'recettes_periode_precedente': recettes_precedent,
                'taux_evolution_recettes': taux_evolution,
                'nombre_jours_impertinents': len(jours_impertinents)
            }
        )
        
        return perf
    
    @staticmethod
    def noter_agent_stock(evolution_jours):
        """
        Note l'agent sur l'évolution du stock /20
        Positif = stock rapproché = bon
        Négatif = stock éloigné = mauvais
        """
        if evolution_jours >= 14:  # Réduit de 2+ semaines
            return Decimal('20')
        elif evolution_jours >= 7:  # Réduit de 1+ semaine
            return Decimal('15')
        elif evolution_jours > 0:  # Réduit un peu
            return Decimal('12')
        elif evolution_jours == 0:  # Stable
            return Decimal('10')
        else:  # Éloigné
            return Decimal('0')
    
    @staticmethod
    def noter_agent_recettes(taux_evolution, taux_deperdition):
        """
        Note l'agent sur l'évolution des recettes /20
        Corrélation avec taux de déperdition
        """
        # Taux élevé (<-30%) + recettes baissent = BON (bien fait son travail)
        if taux_deperdition and taux_deperdition < -30:
            if taux_evolution and taux_evolution < 0:
                return Decimal('20')  # Corrélation parfaite
            elif taux_evolution and taux_evolution > 10:
                return Decimal('8')  # Incohérent
            else:
                return Decimal('12')
        
        # Taux bon (>-30%) + recettes augmentent = BON
        elif taux_deperdition and taux_deperdition >= -30:
            if taux_evolution and taux_evolution > 10:
                return Decimal('20')  # Très bon
            elif taux_evolution and taux_evolution > 0:
                return Decimal('15')  # Bon
            else:
                return Decimal('5')  # Mauvais (recettes baissent malgré bon taux)
        
        return Decimal('10')  # Neutre
    
    @staticmethod
    def noter_agent_taux(taux_moyen, taux_evolution_recettes):
        """
        Note l'agent sur le taux de déperdition /20
        """
        # Bon taux (>-30%) + recettes croissent = EXCELLENT
        if taux_moyen and taux_moyen >= -30:
            if taux_evolution_recettes and taux_evolution_recettes > 10:
                return Decimal('20')
            elif taux_evolution_recettes and taux_evolution_recettes > 0:
                return Decimal('18')
            else:
                return Decimal('12')
        
        # Taux moyen (-30% à -50%)
        elif taux_moyen and -50 <= taux_moyen < -30:
            if taux_evolution_recettes and taux_evolution_recettes < 0:
                return Decimal('15')  # Cohérent
            else:
                return Decimal('8')
        
        # Mauvais taux (<-50%)
        else:
            if taux_evolution_recettes and taux_evolution_recettes < -10:
                return Decimal('18')  # Très cohérent
            else:
                return Decimal('5')
        
        return Decimal('10')
    
    @staticmethod
    def calculer_performance_agent(agent, poste, date_debut, date_fin):
        """
        Calcule et enregistre la performance d'un agent à un poste
        """
        # Vérifier que l'agent a travaillé dans ce poste
        inventaires = InventaireJournalier.objects.filter(
            poste=poste,
            agent_saisie=agent,
            date__range=[date_debut, date_fin],
            type_inventaire='normal'
        )
        
        if not inventaires.exists():
            return None
        
        # Jours impertinents de l'agent
        jours_impertinents = ConfigurationJour.objects.filter(
            statut='impertinent',
            date__range=[date_debut, date_fin]
        ).filter(
            date__in=inventaires.values_list('date', flat=True)
        ).count()
        
        # Situation AVANT passage
        date_debut_avant = date_debut - timedelta(days=30)
        
        taux_avant = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[date_debut_avant, date_debut]
        ).aggregate(taux_moyen=Avg('taux_deperdition'))['taux_moyen']
        
        date_stock_avant = ClassementService.calculer_date_epuisement_corrigee(
            poste, date_debut_avant, date_debut
        )
        
        # Calculer recettes mois avant
        mois_avant = date_debut.month - 1 if date_debut.month > 1 else 12
        annee_avant = date_debut.year if date_debut.month > 1 else date_debut.year - 1
        
        recettes_avant = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee_avant,
            date__month=mois_avant
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        # Situation APRÈS passage
        taux_apres = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[date_debut, date_fin]
        ).aggregate(taux_moyen=Avg('taux_deperdition'))['taux_moyen']
        
        date_stock_apres = ClassementService.calculer_date_epuisement_corrigee(
            poste, date_debut, date_fin
        )
        
        # Calculer recettes période
        recettes_apres = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[date_debut, date_fin]
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        # Calculer évolutions
        evolution_stock = 0
        if date_stock_avant and date_stock_apres:
            evolution_stock = (date_stock_avant - date_stock_apres).days
        
        taux_evolution_recettes = None
        if recettes_avant > 0:
            taux_evolution_recettes = ((recettes_apres - recettes_avant) / recettes_avant) * 100
        
        # NOTATION
        note_stock = ClassementService.noter_agent_stock(evolution_stock)
        note_recettes = ClassementService.noter_agent_recettes(
            taux_evolution_recettes, 
            taux_apres
        )
        note_taux = ClassementService.noter_agent_taux(
            taux_apres, 
            taux_evolution_recettes
        )
        
        # Nombre de motifs pour calculer moyenne
        nb_motifs = 3  # stock, recettes, taux (toujours 3)
        note_moyenne = (note_stock + note_recettes + note_taux) / nb_motifs
        
        # Pénalité jours impertinents
        if jours_impertinents > 5:
            note_moyenne = note_moyenne * Decimal('0.8')  # -20%
        elif jours_impertinents > 10:
            note_moyenne = note_moyenne * Decimal('0.5')  # -50%
        
        # Créer/mettre à jour performance
        perf, created = PerformanceAgent.objects.update_or_create(
            agent=agent,
            poste=poste,
            date_debut=date_debut,
            defaults={
                'date_fin': date_fin,
                'taux_moyen_avant': taux_avant,
                'date_stock_avant': date_stock_avant,
                'recettes_mois_avant': recettes_avant,
                'taux_moyen_apres': taux_apres,
                'date_stock_apres': date_stock_apres,
                'recettes_mois_apres': recettes_apres,
                'note_stock': note_stock,
                'note_recettes': note_recettes,
                'note_taux': note_taux,
                'note_moyenne': note_moyenne,
                'nombre_jours_impertinents': jours_impertinents
            }
        )
        
        return perf
    
    @staticmethod
    def generer_classement_periode(date_debut, date_fin):
        """
        Génère le classement complet pour une période
        """
        postes = Poste.objects.filter(is_active=True)
        
        resultats = {
            'postes': [],
            'agents': []
        }
        
        # Calculer performances postes
        for poste in postes:
            perf_poste = ClassementService.calculer_performance_poste(
                poste, date_debut, date_fin
            )
            
            if perf_poste:
                # Calculer performances agents de ce poste
                inventaires = InventaireJournalier.objects.filter(
                    poste=poste,
                    date__range=[date_debut, date_fin],
                    type_inventaire='normal'
                ).values_list('agent_saisie', flat=True).distinct()
                
                agents_data = []
                for agent_id in inventaires:
                    if agent_id:
                        agent = UtilisateurSUPPER.objects.get(id=agent_id)
                        perf_agent = ClassementService.calculer_performance_agent(
                            agent, poste, date_debut, date_fin
                        )
                        
                        if perf_agent:
                            agents_data.append({
                                'agent': agent,
                                'performance': perf_agent
                            })
                
                # Trier agents par note
                agents_data.sort(key=lambda x: x['performance'].note_moyenne, reverse=True)
                
                resultats['postes'].append({
                    'poste': poste,
                    'performance': perf_poste,
                    'agents': agents_data
                })
        
        # Classement global agents (toutes postes confondus)
        performances_agents = PerformanceAgent.objects.filter(
            date_debut__gte=date_debut,
            date_fin__lte=date_fin
        ).select_related('agent', 'poste').order_by('-note_moyenne')
        
        # Regrouper par agent
        agents_global = {}
        for perf in performances_agents:
            if perf.agent.id not in agents_global:
                agents_global[perf.agent.id] = {
                    'agent': perf.agent,
                    'postes': [],
                    'notes': []
                }
            
            agents_global[perf.agent.id]['postes'].append({
                'poste': perf.poste,
                'performance': perf
            })
            agents_global[perf.agent.id]['notes'].append(float(perf.note_moyenne))
        
        # Calculer moyenne globale par agent
        for agent_id, data in agents_global.items():
            if data['notes']:
                data['moyenne_globale'] = sum(data['notes']) / len(data['notes'])
            else:
                data['moyenne_globale'] = 0
        
        # Trier agents par moyenne globale
        resultats['agents'] = sorted(
            agents_global.values(),
            key=lambda x: x['moyenne_globale'],
            reverse=True
        )
        
        return resultats

def get_rang_poste_peage(poste, annee=None):
    """
    Retourne le rang d'un poste de péage dans le classement cumul à date.
    Basé sur le montant_declare des RecetteJournaliere.
    
    Args:
        poste: Instance de Poste (poste de péage)
        annee: Année pour le calcul (par défaut: année en cours)
    
    Returns:
        dict: {'rang': int, 'total_postes': int, 'total_recettes': Decimal}
    """
    from accounts.models import Poste
    from inventaire.models import RecetteJournaliere
    
    if annee is None:
        annee = date.today().year
    
    today = date.today()
    date_debut = date(annee, 1, 1)
    date_fin = today
    
    # Récupérer tous les postes de péage actifs avec leurs totaux
    postes_stats = []
    postes_peage = Poste.objects.filter(type='peage', is_active=True)
    
    for p in postes_peage:
        total = RecetteJournaliere.objects.filter(
            poste=p,
            date__gte=date_debut,
            date__lte=date_fin
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        postes_stats.append({
            'poste_id': p.id,
            'total': float(total)
        })
    
    # Trier par total décroissant
    postes_stats.sort(key=lambda x: x['total'], reverse=True)
    
    # Trouver le rang du poste
    for i, item in enumerate(postes_stats, 1):
        if item['poste_id'] == poste.id:
            return {
                'rang': i,
                'total_postes': len(postes_stats),
                'total_recettes': item['total']
            }
    
    return {
        'rang': None,
        'total_postes': len(postes_stats),
        'total_recettes': 0
    }
# ===================================================================
# inventaire/services/classement_service.py
# SERVICE DE CLASSEMENT DES AGENTS D'INVENTAIRE - VERSION AMÉLIORÉE
# Application SUPPER - Intégration avec le système de notation avancée
# ===================================================================
"""
Ce service gère le classement des agents d'inventaire en utilisant
le nouveau système de notation basé sur la cohérence des 3 critères.

FONCTIONNALITÉS:
- Classement global des agents sur une période
- Classement par poste
- Obtention du rang d'un agent spécifique
- Statistiques détaillées

AUTEUR: Service SUPPER
DATE: 2025
"""




# ===================================================================
# DATACLASSES POUR LES RÉSULTATS
# ===================================================================

@dataclass
class ResultatClassementAgent:
    """Résultat du classement d'un agent"""
    rang: int
    agent: Any  # UtilisateurSUPPER
    performance: PerformanceAgentPeriode
    postes_travailles: List[str]
    
    @property
    def note_finale(self) -> float:
        return self.performance.note_finale
    
    @property
    def moyenne_globale(self) -> float:
        return self.performance.note_finale


@dataclass
class StatistiquesClassement:
    """Statistiques globales du classement"""
    nombre_agents: int = 0
    note_moyenne_globale: float = 0.0
    note_max: float = 0.0
    note_min: float = 0.0
    total_jours_travailles: int = 0
    taux_presence_moyen: float = 0.0
    taux_coherence_3_criteres: float = 0.0


# ===================================================================
# SERVICE DE CLASSEMENT
# ===================================================================

class ClassementService:
    """
    Service de classement des agents d'inventaire.
    Utilise le NotationAgentService pour calculer les performances.
    """
    
    @staticmethod
    def generer_classement_periode(
        date_debut: date,
        date_fin: date,
        postes_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Génère le classement complet des agents sur une période.
        
        Args:
            date_debut: Date de début de la période
            date_fin: Date de fin de la période
            postes_ids: Optionnel - filtrer sur certains postes
            
        Returns:
            Dict avec:
            - 'agents': Liste des ResultatClassementAgent triés par rang
            - 'statistiques': StatistiquesClassement
        """
        notation_service = get_notation_service()
        
        logger.info(
            f"[CLASSEMENT] Génération classement du {date_debut} au {date_fin}"
        )
        
        # Obtenir les performances des agents
        performances = notation_service.generer_classement_agents(
            date_debut,
            date_fin,
            postes_ids
        )
        
        # Construire les résultats du classement
        from accounts.models import UtilisateurSUPPER
        
        resultats = []
        for rang, perf in enumerate(performances, 1):
            try:
                agent = UtilisateurSUPPER.objects.get(id=perf.agent_id)
                
                resultat = ResultatClassementAgent(
                    rang=rang,
                    agent=agent,
                    performance=perf,
                    postes_travailles=perf.postes_travailles
                )
                resultats.append(resultat)
                
            except UtilisateurSUPPER.DoesNotExist:
                logger.warning(f"[CLASSEMENT] Agent ID {perf.agent_id} non trouvé")
        
        # Calculer les statistiques globales
        stats = StatistiquesClassement()
        
        if performances:
            stats.nombre_agents = len(performances)
            stats.note_moyenne_globale = sum(p.note_finale for p in performances) / len(performances)
            stats.note_max = max(p.note_finale for p in performances)
            stats.note_min = min(p.note_finale for p in performances)
            stats.total_jours_travailles = sum(p.jours_travailles for p in performances)
            stats.taux_presence_moyen = sum(p.taux_presence for p in performances) / len(performances)
            
            total_jours_3_criteres = sum(p.jours_3_criteres for p in performances)
            total_jours = stats.total_jours_travailles
            stats.taux_coherence_3_criteres = (
                (total_jours_3_criteres / total_jours * 100) if total_jours > 0 else 0
            )
        
        logger.info(
            f"[CLASSEMENT] Classement généré: {len(resultats)} agents, "
            f"note moyenne = {stats.note_moyenne_globale:.2f}/20"
        )
        
        # Format compatible avec la vue existante
        agents_format_ancien = []
        for resultat in resultats:
            perf = resultat.performance
            
            # Créer les données pour chaque poste
            postes_data = []
            for poste_nom in perf.postes_travailles:
                postes_data.append({
                    'poste': {'nom': poste_nom},
                    'performance': {
                        'note_stock': perf.note_finale * 0.3,  # Approximation
                        'note_recettes': perf.note_finale * 0.3,
                        'note_taux': perf.note_finale * 0.4,
                        'note_moyenne': perf.note_finale,
                        'nombre_jours_impertinents': perf.jours_impertinents,
                        'taux_moyen_avant': None,
                        'taux_moyen_apres': None,
                        'date_debut': perf.date_debut,
                        'date_fin': perf.date_fin
                    }
                })
            
            agents_format_ancien.append({
                'agent': resultat.agent,
                'postes': postes_data,
                'moyenne_globale': perf.note_finale,
                'performance_detaillee': perf
            })
        
        return {
            'agents': agents_format_ancien,
            'resultats': resultats,
            'statistiques': stats
        }
    
    @staticmethod
    def obtenir_rang_agent(
        agent,
        date_debut: date,
        date_fin: date
    ) -> Dict[str, Any]:
        """
        Obtient le rang et les statistiques d'un agent spécifique.
        
        Args:
            agent: Instance UtilisateurSUPPER
            date_debut: Date de début
            date_fin: Date de fin
            
        Returns:
            Dict avec rang, note, statistiques détaillées
        """
        notation_service = get_notation_service()
        
        logger.info(
            f"[CLASSEMENT] Obtention rang de {agent.nom_complet} "
            f"du {date_debut} au {date_fin}"
        )
        
        return notation_service.obtenir_rang_agent(agent, date_debut, date_fin)
    
    @staticmethod
    def obtenir_rang_agent_mois_courant(agent) -> Dict[str, Any]:
        """
        Obtient le rang d'un agent pour le mois en cours.
        
        Args:
            agent: Instance UtilisateurSUPPER
            
        Returns:
            Dict avec rang et statistiques
        """
        today = date.today()
        date_debut = today.replace(day=1)
        date_fin = today
        
        return ClassementService.obtenir_rang_agent(agent, date_debut, date_fin)
    
    @staticmethod
    def obtenir_performance_agent_poste(
        agent,
        poste,
        date_debut: date,
        date_fin: date
    ) -> Optional[PerformanceAgentPeriode]:
        """
        Obtient la performance détaillée d'un agent sur un poste spécifique.
        
        Args:
            agent: Instance UtilisateurSUPPER
            poste: Instance Poste
            date_debut: Date de début
            date_fin: Date de fin
            
        Returns:
            PerformanceAgentPeriode ou None
        """
        notation_service = get_notation_service()
        
        return notation_service.calculer_performance_agent_periode(
            agent,
            date_debut,
            date_fin,
            poste=poste
        )


# ===================================================================
# FONCTIONS UTILITAIRES POUR L'INTÉGRATION
# ===================================================================

def get_rang_agent_inventaire_dashboard(user) -> Optional[Dict[str, Any]]:
    """
    Fonction utilitaire pour obtenir le rang d'un agent d'inventaire
    à afficher dans le dashboard.
    
    Args:
        user: Instance UtilisateurSUPPER
        
    Returns:
        Dict avec les informations de rang, ou None si non applicable
    """
    # Vérifier que c'est bien un agent d'inventaire
    if getattr(user, 'habilitation', None) != 'agent_inventaire':
        return None
    
    try:
        rang_info = ClassementService.obtenir_rang_agent_mois_courant(user)
        
        if rang_info.get('rang'):
            return {
                'rang': rang_info['rang'],
                'total_agents': rang_info['total_agents'],
                'note': rang_info['note'],
                'jours_travailles': rang_info.get('jours_travailles', 0),
                'taux_presence': rang_info.get('taux_presence', 0),
                'jours_3_criteres': rang_info.get('jours_3_criteres', 0),
                'jours_impertinents': rang_info.get('jours_impertinents', 0),
                'medaille': _get_medaille(rang_info['rang']),
                'message_performance': _generer_message_performance(rang_info)
            }
        
        return None
        
    except Exception as e:
        logger.error(f"[CLASSEMENT] Erreur obtention rang dashboard: {e}")
        return None


def _get_medaille(rang: int) -> str:
    """Retourne l'emoji médaille selon le rang."""
    if rang == 1:
        return "🥇"
    elif rang == 2:
        return "🥈"
    elif rang == 3:
        return "🥉"
    elif rang <= 5:
        return "⭐"
    else:
        return "📊"


def _generer_message_performance(rang_info: Dict[str, Any]) -> str:
    """Génère un message de performance encourageant."""
    rang = rang_info.get('rang', 0)
    note = rang_info.get('note', 0)
    total = rang_info.get('total_agents', 0)
    
    if rang == 1:
        return "🏆 Félicitations ! Vous êtes le meilleur agent ce mois-ci !"
    elif rang <= 3:
        return f"🌟 Excellent travail ! Top 3 sur {total} agents !"
    elif rang <= 5:
        return f"👏 Très bien ! Top 5 sur {total} agents."
    elif note >= 15:
        return f"✅ Bonne performance ({note:.1f}/20)."
    elif note >= 12:
        return f"📈 Performance correcte ({note:.1f}/20). Continuez !"
    elif note >= 10:
        return f"⚠️ Note passable ({note:.1f}/20). Amélioration possible."
    else:
        return f"❗ Note faible ({note:.1f}/20). Attention à la cohérence des données."