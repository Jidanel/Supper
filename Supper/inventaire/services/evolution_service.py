from decimal import Decimal
from datetime import date, timedelta
from django.db.models import Sum, Avg
from inventaire.models import RecetteJournaliere
from accounts.models import Poste
from django.db import models
from django.db.models import Count

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
            count=models.Count('id')
        )
        
        if recettes['count'] > 0:
            return Decimal(str(recettes['total'] or 0)) / recettes['count']
        return Decimal('0')
    
    @staticmethod
    def estimer_recettes_periode(poste, type_periode='mensuel'):
        """Estime les recettes pour une période basée sur les ventes récentes"""
        today = date.today()
        
        # Calculer la moyenne sur les jours disponibles
        if type_periode == 'mensuel':
            # Prendre les jours du mois en cours
            debut_mois = today.replace(day=1)
            moyenne = EvolutionService.calculer_vente_moyenne_journaliere(
                poste, debut_mois, today
            )
            # Estimer pour le mois complet (30 jours)
            return moyenne * 30
            
        elif type_periode == 'trimestriel':
            # Prendre les données disponibles du trimestre
            trimestre = (today.month - 1) // 3
            debut_trim = date(today.year, trimestre * 3 + 1, 1)
            moyenne = EvolutionService.calculer_vente_moyenne_journaliere(
                poste, debut_trim, today
            )
            return moyenne * 90
            
        elif type_periode == 'semestriel':
            semestre = 1 if today.month <= 6 else 2
            debut_sem = date(today.year, 1 if semestre == 1 else 7, 1)
            moyenne = EvolutionService.calculer_vente_moyenne_journaliere(
                poste, debut_sem, today
            )
            return moyenne * 180
            
        elif type_periode == 'annuel':
            debut_annee = date(today.year, 1, 1)
            moyenne = EvolutionService.calculer_vente_moyenne_journaliere(
                poste, debut_annee, today
            )
            return moyenne * 365
    
    @staticmethod
    def calculer_taux_evolution_mensuel(poste, mois, annee, annee_ref):
        """Calcule le taux d'évolution d'un mois par rapport à une année de référence"""
        # Recettes du mois de l'année en cours
        recettes_actuel = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee,
            date__month=mois
        ).aggregate(total=Sum('montant_declare'))['total'] or 0
        
        # Recettes du même mois de l'année de référence
        recettes_ref = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee_ref,
            date__month=mois
        ).aggregate(total=Sum('montant_declare'))['total'] or 0
        
        if recettes_ref > 0:
            taux = ((Decimal(str(recettes_actuel)) - Decimal(str(recettes_ref))) 
                   / Decimal(str(recettes_ref)) * 100)
            return float(taux)
        return None
    
    @staticmethod
    def calculer_risque_baisse_annuel(poste, date_reference=None):
        """
        Calcule le risque de baisse annuel en comparant avec N-1
        Utilise les recettes réelles + estimation du reste du mois en cours
        """
        if date_reference is None:
            date_reference = date.today()
            
        annee = date_reference.year
        
        # Calculer pour l'année en cours jusqu'à aujourd'hui
        debut_annee = date(annee, 1, 1)
        recettes_realisees = RecetteJournaliere.objects.filter(
            poste=poste,
            date__gte=debut_annee,
            date__lte=date_reference
        ).aggregate(total=Sum('montant_declare'))['total'] or 0
        
        # Estimer le reste du mois en cours
        fin_mois = date_reference.replace(day=1) + timedelta(days=32)
        fin_mois = fin_mois.replace(day=1) - timedelta(days=1)
        
        jours_restants = (fin_mois - date_reference).days
        if jours_restants > 0:
            moyenne_jour = EvolutionService.calculer_vente_moyenne_journaliere(
                poste, 
                date_reference.replace(day=1), 
                date_reference
            )
            estimation_reste_mois = moyenne_jour * jours_restants
        else:
            estimation_reste_mois = 0
        
        total_estime = Decimal(str(recettes_realisees)) + estimation_reste_mois
        
        # Comparer avec la même période N-1
        recettes_n1 = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee - 1,
            date__month__lte=date_reference.month,
            date__day__lte=date_reference.day if date_reference.month == date_reference.month else 31
        ).aggregate(total=Sum('montant_declare'))['total'] or 0
        
        if recettes_n1 > 0:
            taux_evolution = ((total_estime - Decimal(str(recettes_n1))) 
                            / Decimal(str(recettes_n1)) * 100)
            return {
                'poste': poste,
                'recettes_estimees': float(total_estime),
                'recettes_n1': float(recettes_n1),
                'taux_evolution': float(taux_evolution),
                'en_baisse': taux_evolution < 0
            }
        return None
    
    @staticmethod
    def identifier_postes_en_baisse(type_analyse='mensuel', seuil_baisse=-5):
        """Identifie tous les postes en baisse selon le critère"""
        postes_en_baisse = []
        
        for poste in Poste.objects.filter(is_active=True):
            if type_analyse == 'mensuel':
                today = date.today()
                # Comparer avec N-1 et N-2
                for annee_ref in [today.year - 1, today.year - 2]:
                    taux = EvolutionService.calculer_taux_evolution_mensuel(
                        poste, today.month, today.year, annee_ref
                    )
                    if taux is not None and taux < seuil_baisse:
                        postes_en_baisse.append({
                            'poste': poste,
                            'taux_evolution': taux,
                            'annee_reference': annee_ref
                        })
            
            elif type_analyse == 'annuel':
                resultat = EvolutionService.calculer_risque_baisse_annuel(poste)
                if resultat and resultat['en_baisse']:
                    postes_en_baisse.append(resultat)
        
        return postes_en_baisse