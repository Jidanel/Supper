# inventaire/services/evolution_service.py
from decimal import Decimal
from datetime import date, timedelta
from django.db.models import Sum, Count
from inventaire.models import RecetteJournaliere
from accounts.models import Poste
import calendar

class EvolutionService:
    
    @staticmethod
    def calculer_vente_moyenne_journaliere(poste, date_debut, date_fin):
        """Calcule la vente moyenne journalière sur une période"""
        recettes = RecetteJournaliere.objects.filter(
            poste=poste,
            date__gte=date_debut,
            date__lte=date_fin
        ).aggregate(
            total=Sum('montant_declare'),
            count=Count('id')
        )
        
        if recettes['count'] > 0:
            return Decimal(str(recettes['total'] or 0)) / recettes['count']
        return Decimal('0')
    
    @staticmethod
    def calculer_taux_evolution_mensuel(poste, mois, annee, annee_ref):
        """Calcule l'évolution pour UN SEUL mois spécifique"""
        # Recettes du mois actuel
        recettes_actuel = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee,
            date__month=mois
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        # Recettes du même mois de référence
        recettes_ref = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee_ref,
            date__month=mois
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        if recettes_ref > 0:
            taux = ((recettes_actuel - recettes_ref) / recettes_ref * 100)
            return float(taux)
        return None
    
    @staticmethod
    def calculer_evolution_annuelle_cumulee(poste, mois, annee, annee_ref):
        """Calcule l'évolution CUMULÉE du 1er janvier au mois spécifié"""
        # Du 1er janvier au dernier jour du mois pour l'année actuelle
        recettes_cumul_actuel = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee,
            date__month__lte=mois
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        # Du 1er janvier au dernier jour du mois pour l'année de référence
        recettes_cumul_ref = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee_ref,
            date__month__lte=mois
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        if recettes_cumul_ref > 0:
            taux = ((recettes_cumul_actuel - recettes_cumul_ref) / recettes_cumul_ref * 100)
            return float(taux)
        return None
    
    @staticmethod
    def calculer_risque_baisse_mensuel(poste, mois=None, annee=None):
        """
        Calcule le risque de baisse mensuel avec estimation si mois non clos
        """
        if mois is None:
            mois = date.today().month
        if annee is None:
            annee = date.today().year
            
        aujourd_hui = date.today()
        debut_mois = date(annee, mois, 1)
        dernier_jour = calendar.monthrange(annee, mois)[1]
        fin_mois = date(annee, mois, dernier_jour)
        
        # Si mois en cours non terminé
        if annee == aujourd_hui.year and mois == aujourd_hui.month and aujourd_hui < fin_mois:
            # Recettes réalisées
            recettes_realisees = RecetteJournaliere.objects.filter(
                poste=poste,
                date__gte=debut_mois,
                date__lte=aujourd_hui
            ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
            
            # Estimation pour jours restants
            if recettes_realisees > 0:
                jours_ecoules = (aujourd_hui - debut_mois).days + 1
                moyenne_jour = recettes_realisees / jours_ecoules
                jours_restants = (fin_mois - aujourd_hui).days
                estimation_reste = moyenne_jour * jours_restants
                total_estime = recettes_realisees + estimation_reste
            else:
                total_estime = Decimal('0')
        else:
            # Mois complet
            total_estime = RecetteJournaliere.objects.filter(
                poste=poste,
                date__year=annee,
                date__month=mois
            ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        # Comparaison avec N-1
        total_n1 = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee - 1,
            date__month=mois
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        taux = None
        if total_n1 > 0:
            taux = float(((total_estime - total_n1) / total_n1) * 100)
        
        return {
            'total_estime': float(total_estime),
            'total_n1': float(total_n1),
            'taux': taux,
            'en_baisse': taux < -5 if taux is not None else False
        }
    
    @staticmethod
    def calculer_risque_baisse_annuel(poste, date_analyse=None):
        """
        Calcule le risque de baisse annuel du 1er janvier à la date d'analyse
        """
        if date_analyse is None:
            date_analyse = date.today()
            
        annee = date_analyse.year
        debut_annee = date(annee, 1, 1)
        
        # Fin de période = fin du mois en cours
        dernier_jour = calendar.monthrange(annee, date_analyse.month)[1]
        fin_periode = date(annee, date_analyse.month, dernier_jour)
        
        # Recettes réalisées
        recettes_realisees = RecetteJournaliere.objects.filter(
            poste=poste,
            date__gte=debut_annee,
            date__lte=date_analyse
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        # Estimation si mois non clos
        if date_analyse < fin_periode:
            debut_mois = date(annee, date_analyse.month, 1)
            if recettes_realisees > 0:
                # Moyenne du mois en cours
                recettes_mois = RecetteJournaliere.objects.filter(
                    poste=poste,
                    date__gte=debut_mois,
                    date__lte=date_analyse
                ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
                
                if recettes_mois > 0:
                    jours_ecoules = (date_analyse - debut_mois).days + 1
                    moyenne_jour = recettes_mois / jours_ecoules
                    jours_restants = (fin_periode - date_analyse).days
                    estimation_reste = moyenne_jour * jours_restants
                else:
                    estimation_reste = Decimal('0')
            else:
                estimation_reste = Decimal('0')
                
            total_estime = recettes_realisees + estimation_reste
        else:
            total_estime = recettes_realisees
        
        # Comparaison avec même période N-1
        total_n1 = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee - 1,
            date__month__lte=date_analyse.month
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        taux = None
        if total_n1 > 0:
            taux = float(((total_estime - total_n1) / total_n1) * 100)
        
        return {
            'poste': poste,
            'total_estime': float(total_estime),
            'total_n1': float(total_n1),
            'taux': taux,
            'en_baisse': taux < -5 if taux is not None else False
        }
    
    @staticmethod
    def identifier_postes_en_baisse(type_analyse='annuel', seuil_baisse=-5):
        """Identifie tous les postes en baisse selon le critère"""
        postes_en_baisse = []
        aujourd_hui = date.today()
        
        for poste in Poste.objects.filter(is_active=True):
            if type_analyse == 'mensuel':
                # Analyse mensuelle
                resultat = EvolutionService.calculer_risque_baisse_mensuel(
                    poste, aujourd_hui.month, aujourd_hui.year
                )
                if resultat['taux'] is not None and resultat['taux'] < seuil_baisse:
                    postes_en_baisse.append({
                        'poste': poste,
                        'taux_evolution': resultat['taux'],
                        'type': 'mensuel',
                        'total_estime': resultat['total_estime'],
                        'total_n1': resultat['total_n1']
                    })
                    
            elif type_analyse == 'annuel':
                # Analyse annuelle cumulée
                resultat = EvolutionService.calculer_risque_baisse_annuel(poste)
                if resultat['taux'] is not None and resultat['taux'] < seuil_baisse:
                    postes_en_baisse.append({
                        'poste': poste,
                        'taux_evolution': resultat['taux'],
                        'type': 'annuel',
                        'total_estime': resultat['total_estime'],
                        'total_n1': resultat['total_n1']
                    })
        
        return postes_en_baisse
    
    @classmethod
    def estimer_recettes_periode(cls, poste, type_periode, annee=None):
        """Estime les recettes pour une période donnée"""
        if annee is None:
            annee = date.today().year
        
        recettes = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee
        ).aggregate(
            total=Sum('montant_declare'),
            count=Count('id')
        )
        
        if not recettes['count']:
            return Decimal('0')
        
        moyenne_jour = Decimal(str(recettes['total'] or 0)) / recettes['count']
        
        multipliers = {
            'mensuel': 30,
            'trimestriel': 90,
            'semestriel': 180,
            'annuel': 365
        }
        
        return moyenne_jour * multipliers.get(type_periode, 30)