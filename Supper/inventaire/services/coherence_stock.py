"""
Contrôle de cohérence du stock : compare, pour chaque poste péage, le stock de DÉBUT de mois selon
le CSP (HistoriqueStock, en FCFA) et selon le compte d'emploi (séries de tickets, SerieTicket).
Utilisé par la page admin « Cohérence des stocks » et par la commande verifier_coherence_stock.
"""
from datetime import date, datetime  # Dates de début de mois
from django.db.models import Q, Sum, Count  # Agrégations SQL
from django.utils import timezone  # Dates aware

from accounts.models import Poste  # Postes
from inventaire.services.cloture_donnees import bornes_mois, series_debut_jour, nombre_tickets  # Calculs par séries
from inventaire.views_csp import calculer_stock_debut_periode  # Calcul CSP (FCFA)

PRIX_TICKET = 500  # Valeur d'un ticket en FCFA


def ecart_poste(poste, debut):
    """Retourne (csp, series, ecart) pour un poste au début du jour `debut` ; ecart = séries - CSP."""
    csp, _t = calculer_stock_debut_periode(poste, debut)  # Début selon HistoriqueStock
    series = nombre_tickets(series_debut_jour(poste, debut)) * PRIX_TICKET  # Début selon les séries
    return csp, series, series - csp


def ecarts_mois(mois):
    """Liste de dicts pour TOUS les postes péage actifs au début du mois 'AAAA-MM' (triée : plus gros écart d'abord)."""
    debut, _fin = bornes_mois(mois)
    lignes = []
    for poste in Poste.objects.filter(type='peage', is_active=True).order_by('nom'):
        csp, series, ecart = ecart_poste(poste, debut)
        lignes.append({'poste': poste, 'csp': csp, 'series': series, 'ecart': ecart, 'coherent': ecart == 0})
    lignes.sort(key=lambda l: (l['coherent'], -abs(l['ecart'])))  # Incohérents d'abord, plus gros écart en tête
    return debut, lignes


def _mois_precedents(debut, n):
    """Liste des n premiers jours de mois jusqu'à `debut` inclus (du plus ancien au plus récent)."""
    jours, a, m = [], debut.year, debut.month
    for _ in range(n):
        jours.append(date(a, m, 1))
        m -= 1
        if m == 0:
            a, m = a - 1, 12
    return list(reversed(jours))


def detail_poste(poste, debut, nb_mois=12):
    """Diagnostic d'un poste : évolution de l'écart, mouvements regroupés, gros mouvements, séries par couleur."""
    from inventaire.models import HistoriqueStock, SerieTicket
    limite = timezone.make_aware(datetime.combine(debut, datetime.min.time()))
    # 1. Évolution mensuelle de l'écart : le premier mois en écart indique QUAND il est apparu
    evolution = []
    for jour in _mois_precedents(debut, nb_mois):
        csp, series, ecart = ecart_poste(poste, jour)
        evolution.append({'mois': jour, 'csp': csp, 'series': series, 'ecart': ecart})
    # 2. Mouvements de l'historique, regroupés
    base = HistoriqueStock.objects.filter(poste=poste, date_mouvement__lte=limite)
    groupes = list(base.values('type_mouvement', 'type_stock', 'est_correction').annotate(
        n=Count('id'), tickets=Sum('nombre_tickets'), montant=Sum('montant')).order_by('type_mouvement', 'type_stock'))
    # 3. Les 15 plus gros mouvements hors ventes
    gros = list(base.filter(reference_recette__isnull=True).select_related('effectue_par').order_by('-montant')[:15])
    # 4. Séries détenues au début du mois, par couleur
    qs = SerieTicket.objects.filter(poste=poste, date_reception__lte=limite).filter(
        Q(statut='stock') | Q(statut='vendu', date_utilisation__gte=debut))
    couleurs = [{'couleur': r['couleur__libelle_affichage'], 'series': r['n'], 'tickets': r['t'] or 0, 'valeur': (r['t'] or 0) * PRIX_TICKET}
                for r in qs.values('couleur__libelle_affichage').annotate(n=Count('id'), t=Sum('nombre_tickets'))]
    # 5. Séries en stock sans CREDIT de même taille dans l'historique (piste : chargement non historisé)
    credits = list(base.filter(type_mouvement='CREDIT').values_list('nombre_tickets', flat=True))
    sans_credit = []
    for sr in qs.filter(statut='stock').select_related('couleur').order_by('-nombre_tickets')[:500]:
        if sr.nombre_tickets in credits:
            credits.remove(sr.nombre_tickets)  # Appariée
        else:
            sans_credit.append(sr)
    # 6. Crédits de l'historique restant sans série de même taille (piste : série supprimée ou transférée sans débit)
    return {'evolution': evolution, 'groupes': groupes, 'gros': gros, 'couleurs': couleurs,
            'sans_credit': sans_credit[:30], 'nb_sans_credit': len(sans_credit),
            'credits_sans_serie': len(credits), 'tickets_credits_sans_serie': sum(credits)}
