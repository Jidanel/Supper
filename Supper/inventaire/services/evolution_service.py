# inventaire/services/evolution_service.py
# ===================================================================
# VERSION CORRIGÉE - Calcul des risques de baisse annuel et mensuel
# Méthode: Projection au 31 décembre (annuel) ou fin de mois (mensuel)
# Comparaison avec années N-1 ET N-2
# ===================================================================

from decimal import Decimal
from datetime import date, timedelta
from django.db.models import Sum, Count
from inventaire.models import RecetteJournaliere
from accounts.models import Poste
import calendar
import logging

logger = logging.getLogger('supper.evolution')


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

    # =================================================================
    # TAUX D'ÉVOLUTION MENSUEL (un seul mois)
    # Compare le mois sélectionné de l'année N avec le même mois de
    # l'année de référence. Si le mois N est en cours, projette au
    # dernier jour du mois.
    # =================================================================
    @staticmethod
    def calculer_taux_evolution_mensuel(poste, mois, annee, annee_ref):
        """
        Calcule l'évolution pour un mois spécifique avec projection.

        Si le mois de l'année N n'est pas clos (c'est-à-dire si
        annee == année courante ET mois == mois courant ET on n'est pas
        au dernier jour), on projette les recettes au dernier jour du mois.

        Retourne : {'taux': float|None, 'montant_n': float, 'montant_ref': float,
                    'ecart': float, 'projete': bool}
        """
        aujourd_hui = date.today()
        dernier_jour = calendar.monthrange(annee, mois)[1]
        fin_mois = date(annee, mois, dernier_jour)

        # Recettes réalisées du mois actuel
        recettes_actuel = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee,
            date__month=mois
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

        projete = False
        # Si le mois est en cours et pas terminé => projection
        if annee == aujourd_hui.year and mois == aujourd_hui.month and aujourd_hui.day < dernier_jour:
            jours_ecoules = aujourd_hui.day
            if jours_ecoules > 0 and recettes_actuel > 0:
                moyenne_jour = recettes_actuel / jours_ecoules
                recettes_actuel = moyenne_jour * dernier_jour
                projete = True

        # Recettes du même mois de l'année de référence (mois complet)
        recettes_ref = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee_ref,
            date__month=mois
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

        ecart = recettes_actuel - recettes_ref
        taux = None
        if recettes_ref > 0:
            taux = float((ecart / recettes_ref) * 100)

        return {
            'taux': taux,
            'montant_n': float(recettes_actuel),
            'montant_ref': float(recettes_ref),
            'ecart': float(ecart),
            'projete': projete,
        }

    # =================================================================
    # TAUX D'ÉVOLUTION ANNUEL CUMULÉ (1er janvier au mois spécifié)
    # Projette au 31 décembre puis compare avec le total annuel complet
    # de l'année de référence.
    # =================================================================
    @staticmethod
    def calculer_evolution_annuelle_cumulee(poste, mois, annee, annee_ref):
        """
        Calcule l'évolution annuelle :
        1. Somme des recettes du 1er janvier au dernier jour déclaré
        2. Projection au 31 décembre (moyenne journalière × 365)
        3. Comparaison avec le total consolidé de l'année de référence
           (1er janvier au 31 décembre)

        Retourne : {'taux': float|None, 'estimation_31dec': float,
                    'total_ref': float, 'ecart': float, 'realise': float}
        """
        aujourd_hui = date.today()
        debut_annee = date(annee, 1, 1)

        # Déterminer la date de fin pour les recettes réelles
        if annee == aujourd_hui.year:
            date_fin_reelle = aujourd_hui
        else:
            date_fin_reelle = date(annee, 12, 31)

        # Recettes cumulées du 1er janvier à la date de fin réelle
        recettes_realisees = RecetteJournaliere.objects.filter(
            poste=poste,
            date__gte=debut_annee,
            date__lte=date_fin_reelle
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

        # Nombre de jours écoulés dans l'année
        jours_ecoules = (date_fin_reelle - debut_annee).days + 1

        # Projection au 31 décembre
        if jours_ecoules > 0 and recettes_realisees > 0:
            moyenne_jour = recettes_realisees / jours_ecoules
            estimation_31dec = moyenne_jour * Decimal('365')
        else:
            estimation_31dec = Decimal('0')

        # Recettes consolidées de l'année de référence (1er jan au 31 déc)
        total_ref = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee_ref
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

        ecart = estimation_31dec - total_ref
        taux = None
        if total_ref > 0:
            taux = float((ecart / total_ref) * 100)

        return {
            'taux': taux,
            'estimation_31dec': float(estimation_31dec),
            'total_ref': float(total_ref),
            'ecart': float(ecart),
            'realise': float(recettes_realisees),
        }

    # =================================================================
    # RISQUE DE BAISSE MENSUEL
    # Projette au dernier jour du mois en cours, compare avec le même
    # mois complet de N-1 ET N-2.
    # =================================================================
    @staticmethod
    def calculer_risque_baisse_mensuel(poste, mois=None, annee=None):
        """
        Calcule le risque de baisse mensuel avec projection.

        Retourne un dict avec les clés :
        - total_estime : montant projeté au dernier jour du mois
        - total_n1 / total_n2 : recettes du même mois N-1 et N-2
        - ecart_n1 / ecart_n2 : estimation - référence
        - taux_n1 / taux_n2 : (écart / référence) × 100
        - en_baisse_n1 / en_baisse_n2 : True si écart < 0
        """
        if mois is None:
            mois = date.today().month
        if annee is None:
            annee = date.today().year

        aujourd_hui = date.today()
        debut_mois = date(annee, mois, 1)
        dernier_jour = calendar.monthrange(annee, mois)[1]
        fin_mois = date(annee, mois, dernier_jour)

        # --- Recettes du mois en cours ---
        recettes_realisees = RecetteJournaliere.objects.filter(
            poste=poste,
            date__gte=debut_mois,
            date__lte=min(aujourd_hui, fin_mois)
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

        # Si le mois n'est pas terminé => projection au dernier jour
        if annee == aujourd_hui.year and mois == aujourd_hui.month and aujourd_hui < fin_mois:
            jours_ecoules = (aujourd_hui - debut_mois).days + 1
            if jours_ecoules > 0 and recettes_realisees > 0:
                moyenne_jour = recettes_realisees / jours_ecoules
                total_estime = moyenne_jour * dernier_jour
            else:
                total_estime = Decimal('0')
        else:
            total_estime = recettes_realisees

        # --- Même mois N-1 (complet) ---
        total_n1 = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee - 1,
            date__month=mois
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

        # --- Même mois N-2 (complet) ---
        total_n2 = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee - 2,
            date__month=mois
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

        # Écarts et taux
        ecart_n1 = total_estime - total_n1
        ecart_n2 = total_estime - total_n2

        taux_n1 = float((ecart_n1 / total_n1) * 100) if total_n1 > 0 else None
        taux_n2 = float((ecart_n2 / total_n2) * 100) if total_n2 > 0 else None

        return {
            'total_estime': float(total_estime),
            'total_n1': float(total_n1),
            'total_n2': float(total_n2),
            'ecart_n1': float(ecart_n1),
            'ecart_n2': float(ecart_n2),
            'taux_n1': taux_n1,
            'taux_n2': taux_n2,
            'en_baisse_n1': ecart_n1 < 0,
            'en_baisse_n2': ecart_n2 < 0,
        }

    # =================================================================
    # RISQUE DE BAISSE ANNUEL
    # Projette au 31 décembre, compare avec les totaux consolidés
    # complets de N-1 ET N-2 (1er jan au 31 déc).
    # =================================================================
    @staticmethod
    def calculer_risque_baisse_annuel(poste, date_analyse=None):
        """
        Calcule le risque de baisse annuel avec estimation au 31 décembre.

        Retourne un dict avec les clés :
        - realise : somme des recettes du 1er janvier à date
        - estimation_31dec : projection au 31 décembre
        - total_n1 / total_n2 : recettes annuelles complètes N-1 et N-2
        - ecart_n1 / ecart_n2 : estimation - référence
        - taux_n1 / taux_n2 : (écart / référence) × 100
        - en_baisse_n1 / en_baisse_n2 : True si écart < 0
        """
        if date_analyse is None:
            date_analyse = date.today()

        annee = date_analyse.year
        debut_annee = date(annee, 1, 1)

        # Recettes réalisées du 1er janvier à la date d'analyse
        recettes_realisees = RecetteJournaliere.objects.filter(
            poste=poste,
            date__gte=debut_annee,
            date__lte=date_analyse
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

        # Nombre de jours écoulés dans l'année
        jours_ecoules = (date_analyse - debut_annee).days + 1

        # Estimation au 31 décembre
        if jours_ecoules > 0 and recettes_realisees > 0:
            moyenne_jour = recettes_realisees / jours_ecoules
            estimation_31dec = moyenne_jour * Decimal('365')
        else:
            estimation_31dec = Decimal('0')

        # Recettes consolidées N-1 (1er jan au 31 déc)
        total_n1 = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee - 1
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

        # Recettes consolidées N-2 (1er jan au 31 déc)
        total_n2 = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee - 2
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

        # Écarts et taux
        ecart_n1 = estimation_31dec - total_n1
        ecart_n2 = estimation_31dec - total_n2

        taux_n1 = float((ecart_n1 / total_n1) * 100) if total_n1 > 0 else None
        taux_n2 = float((ecart_n2 / total_n2) * 100) if total_n2 > 0 else None

        return {
            'poste': poste,
            'realise': float(recettes_realisees),
            'estimation_31dec': float(estimation_31dec),
            'total_n1': float(total_n1),
            'total_n2': float(total_n2),
            'ecart_n1': float(ecart_n1),
            'ecart_n2': float(ecart_n2),
            'taux_n1': taux_n1,
            'taux_n2': taux_n2,
            'en_baisse_n1': ecart_n1 < 0,
            'en_baisse_n2': ecart_n2 < 0,
        }

    # =================================================================
    # IDENTIFIER TOUS LES POSTES EN BAISSE
    # =================================================================
    @staticmethod
    def identifier_postes_en_baisse_mensuel(mois=None, annee=None):
        """
        Identifie les postes en risque de baisse mensuel par rapport à N-1 et N-2.
        Retourne deux listes triées par taux de baisse.
        """
        if mois is None:
            mois = date.today().month
        if annee is None:
            annee = date.today().year

        postes = Poste.objects.filter(is_active=True, type='peage')
        postes_baisse_n1 = []
        postes_baisse_n2 = []

        for poste in postes:
            risque = EvolutionService.calculer_risque_baisse_mensuel(poste, mois, annee)

            if risque['en_baisse_n1'] and risque['taux_n1'] is not None:
                postes_baisse_n1.append({
                    'poste': poste,
                    'total_estime': risque['total_estime'],
                    'total_ref': risque['total_n1'],
                    'ecart': risque['ecart_n1'],
                    'taux': risque['taux_n1'],
                })

            if risque['en_baisse_n2'] and risque['taux_n2'] is not None:
                postes_baisse_n2.append({
                    'poste': poste,
                    'total_estime': risque['total_estime'],
                    'total_ref': risque['total_n2'],
                    'ecart': risque['ecart_n2'],
                    'taux': risque['taux_n2'],
                })

        postes_baisse_n1.sort(key=lambda x: x['taux'])
        postes_baisse_n2.sort(key=lambda x: x['taux'])

        return postes_baisse_n1, postes_baisse_n2

    @staticmethod
    def identifier_postes_en_baisse_annuel(date_analyse=None):
        """
        Identifie les postes en risque de baisse annuel par rapport à N-1 et N-2.
        Retourne deux listes triées par taux de baisse.
        """
        if date_analyse is None:
            date_analyse = date.today()

        postes = Poste.objects.filter(is_active=True, type='peage')
        postes_baisse_n1 = []
        postes_baisse_n2 = []

        for poste in postes:
            risque = EvolutionService.calculer_risque_baisse_annuel(poste, date_analyse)

            if risque['en_baisse_n1'] and risque['taux_n1'] is not None:
                postes_baisse_n1.append({
                    'poste': poste,
                    'realise': risque['realise'],
                    'estimation_31dec': risque['estimation_31dec'],
                    'total_ref': risque['total_n1'],
                    'ecart': risque['ecart_n1'],
                    'taux': risque['taux_n1'],
                })

            if risque['en_baisse_n2'] and risque['taux_n2'] is not None:
                postes_baisse_n2.append({
                    'poste': poste,
                    'realise': risque['realise'],
                    'estimation_31dec': risque['estimation_31dec'],
                    'total_ref': risque['total_n2'],
                    'ecart': risque['ecart_n2'],
                    'taux': risque['taux_n2'],
                })

        postes_baisse_n1.sort(key=lambda x: x['taux'])
        postes_baisse_n2.sort(key=lambda x: x['taux'])

        return postes_baisse_n1, postes_baisse_n2

    # =================================================================
    # MÉTHODE LEGACY (conservée pour compatibilité)
    # =================================================================
    @staticmethod
    def identifier_postes_en_baisse(type_analyse='annuel', seuil_baisse=-5):
        """Version legacy - redirige vers les nouvelles méthodes"""
        if type_analyse == 'mensuel':
            baisse_n1, _ = EvolutionService.identifier_postes_en_baisse_mensuel()
            return [
                {
                    'poste': item['poste'],
                    'taux_evolution': item['taux'],
                    'recettes_actuelles': item['total_estime'],
                    'recettes_precedentes': item['total_ref'],
                    'pourcentage_baisse': abs(item['taux']),
                    'recettes_estimees': item['total_estime'],
                    'recettes_n1': item['total_ref'],
                }
                for item in baisse_n1 if item['taux'] < seuil_baisse
            ]
        else:
            baisse_n1, _ = EvolutionService.identifier_postes_en_baisse_annuel()
            return [
                {
                    'poste': item['poste'],
                    'taux_evolution': item['taux'],
                    'recettes_actuelles': item['realise'],
                    'recettes_precedentes': item['total_ref'],
                    'pourcentage_baisse': abs(item['taux']),
                    'recettes_estimees': item['estimation_31dec'],
                    'recettes_n1': item['total_ref'],
                }
                for item in baisse_n1 if item['taux'] < seuil_baisse
            ]

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