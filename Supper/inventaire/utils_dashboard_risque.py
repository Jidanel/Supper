# ===================================================================
# inventaire/utils_dashboard_risque.py
# Fonction utilitaire à appeler depuis la vue du dashboard (là où
# stats_taux_chef_poste est peuplé) pour ajouter les données de
# risque de baisse au contexte.
#
# USAGE dans la vue dashboard :
#   from inventaire.utils_dashboard_risque import ajouter_risque_baisse_au_contexte
#   ajouter_risque_baisse_au_contexte(context, user)
# ===================================================================

from datetime import date
from decimal import Decimal
from django.db.models import Sum
import calendar
import logging

from accounts.models import Poste
from inventaire.models import RecetteJournaliere

logger = logging.getLogger('supper')


def ajouter_risque_baisse_au_contexte(context, user):
    """
    Ajoute au contexte du dashboard les données de risque de baisse
    pour le poste de l'utilisateur connecté (chef de poste)
    ou pour tous les postes (admin).

    Enrichit le contexte avec la clé 'risque_baisse_poste' contenant :
    - mensuel_n1 : risque baisse mois en cours vs même mois N-1
    - mensuel_n2 : risque baisse mois en cours vs même mois N-2
    - annuel_n1 : risque baisse annuel (projection 31/12) vs N-1
    - annuel_n2 : risque baisse annuel (projection 31/12) vs N-2
    - mois_nom : nom du mois en cours en français
    - annee / annee_n1 / annee_n2
    """
    MOIS_FR = [
        '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ]

    aujourd_hui = date.today()
    annee = aujourd_hui.year
    mois = aujourd_hui.month
    mois_nom = MOIS_FR[mois]
    dernier_jour_mois = calendar.monthrange(annee, mois)[1]

    # Déterminer le poste de l'utilisateur
    poste = getattr(user, 'poste', None)
    if poste is None or not poste.is_active or poste.type != 'peage':
        # Pas de poste péage => pas de données de risque
        return

    # ===============================================================
    # RISQUE MENSUEL
    # ===============================================================
    # Recettes du mois en cours
    recettes_mois = RecetteJournaliere.objects.filter(
        poste=poste,
        date__year=annee,
        date__month=mois,
        date__lte=aujourd_hui
    ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

    # Projection au dernier jour du mois
    jours_ecoules = aujourd_hui.day
    if jours_ecoules > 0 and recettes_mois > 0 and jours_ecoules < dernier_jour_mois:
        projection_mois = (recettes_mois / jours_ecoules) * dernier_jour_mois
    else:
        projection_mois = recettes_mois

    # Même mois N-1
    total_mois_n1 = RecetteJournaliere.objects.filter(
        poste=poste,
        date__year=annee - 1,
        date__month=mois
    ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

    # Même mois N-2
    total_mois_n2 = RecetteJournaliere.objects.filter(
        poste=poste,
        date__year=annee - 2,
        date__month=mois
    ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

    ecart_mois_n1 = projection_mois - total_mois_n1
    ecart_mois_n2 = projection_mois - total_mois_n2
    taux_mois_n1 = float((ecart_mois_n1 / total_mois_n1) * 100) if total_mois_n1 > 0 else None
    taux_mois_n2 = float((ecart_mois_n2 / total_mois_n2) * 100) if total_mois_n2 > 0 else None

    # ===============================================================
    # RISQUE ANNUEL (projection au 31 décembre)
    # ===============================================================
    debut_annee = date(annee, 1, 1)
    recettes_annee = RecetteJournaliere.objects.filter(
        poste=poste,
        date__gte=debut_annee,
        date__lte=aujourd_hui
    ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

    jours_annee_ecoules = (aujourd_hui - debut_annee).days + 1
    if jours_annee_ecoules > 0 and recettes_annee > 0:
        projection_31dec = (recettes_annee / jours_annee_ecoules) * Decimal('365')
    else:
        projection_31dec = Decimal('0')

    # Total annuel N-1
    total_annuel_n1 = RecetteJournaliere.objects.filter(
        poste=poste,
        date__year=annee - 1
    ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

    # Total annuel N-2
    total_annuel_n2 = RecetteJournaliere.objects.filter(
        poste=poste,
        date__year=annee - 2
    ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')

    ecart_annuel_n1 = projection_31dec - total_annuel_n1
    ecart_annuel_n2 = projection_31dec - total_annuel_n2
    taux_annuel_n1 = float((ecart_annuel_n1 / total_annuel_n1) * 100) if total_annuel_n1 > 0 else None
    taux_annuel_n2 = float((ecart_annuel_n2 / total_annuel_n2) * 100) if total_annuel_n2 > 0 else None

    context['risque_baisse_poste'] = {
        'mois_nom': mois_nom,
        'annee': annee,
        'annee_n1': annee - 1,
        'annee_n2': annee - 2,
        # Mensuel N-1
        'mensuel_n1': {
            'projection': float(projection_mois),
            'reference': float(total_mois_n1),
            'ecart': float(ecart_mois_n1),
            'taux': taux_mois_n1,
            'en_baisse': ecart_mois_n1 < 0,
            'couleur': 'danger' if ecart_mois_n1 < 0 else ('success' if taux_mois_n1 is not None else 'secondary'),
        },
        # Mensuel N-2
        'mensuel_n2': {
            'projection': float(projection_mois),
            'reference': float(total_mois_n2),
            'ecart': float(ecart_mois_n2),
            'taux': taux_mois_n2,
            'en_baisse': ecart_mois_n2 < 0,
            'couleur': 'danger' if ecart_mois_n2 < 0 else ('success' if taux_mois_n2 is not None else 'secondary'),
        },
        # Annuel N-1
        'annuel_n1': {
            'projection': float(projection_31dec),
            'reference': float(total_annuel_n1),
            'ecart': float(ecart_annuel_n1),
            'taux': taux_annuel_n1,
            'en_baisse': ecart_annuel_n1 < 0,
            'couleur': 'danger' if ecart_annuel_n1 < 0 else ('success' if taux_annuel_n1 is not None else 'secondary'),
        },
        # Annuel N-2
        'annuel_n2': {
            'projection': float(projection_31dec),
            'reference': float(total_annuel_n2),
            'ecart': float(ecart_annuel_n2),
            'taux': taux_annuel_n2,
            'en_baisse': ecart_annuel_n2 < 0,
            'couleur': 'danger' if ecart_annuel_n2 < 0 else ('success' if taux_annuel_n2 is not None else 'secondary'),
        },
    }