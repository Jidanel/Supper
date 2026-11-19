# inventaire/services/rapport_reversement.py
# RAPPORT PÉRIODIQUE DE REVERSEMENT : pour une période de JOURS DE RECETTES, compare par poste ce qui a été
# DÉCLARÉ (RecetteJournaliere) et ce qui a été QUITTANCÉ (Quittancement), et ressort les jours déclarés mais non quittancés.
#   - Péage  : déclarations + quittances (comparaison, jours manquants, écart par quittance).
#   - Pesage : quittances seulement (on ne déclare pas de recette en pesage).
# Les jours utilisés sont les jours de RECETTE (pas la date de reversement, qui est seulement affichée).
# Une quittance journalière couvre 1 jour ; une quittance de décade couvre plusieurs jours avec UN SEUL montant
# (les jours sont donc fusionnés dans le tableau). N quittances d'un jour = N colonnes.

import datetime  # Dates et durées
from decimal import Decimal  # Montants exacts

from accounts.models import Poste  # Postes de péage / stations de pesage
from inventaire.models import Quittancement, RecetteJournaliere, TypeDeclaration  # Péage
from inventaire.models_pesage import QuittancementPesage  # Pesage

ZERO = Decimal('0')  # Zéro décimal


def liste_jours(debut, fin):
    """Tous les jours de la période, bornes incluses."""
    return [debut + datetime.timedelta(days=i) for i in range((fin - debut).days + 1)]


def _couverture(q, pesage):
    """(premier jour, dernier jour) de recette couverts par une quittance, ou None si les dates sont absentes."""
    if q.type_declaration == TypeDeclaration.DECADE:
        if q.date_debut_decade and q.date_fin_decade:
            return q.date_debut_decade, q.date_fin_decade
        return None
    return (q.date_recette, q.date_recette) if q.date_recette else None  # Journalière : un seul jour


def _montant(q, pesage):
    """Montant quittancé (le champ diffère entre péage et pesage)."""
    return q.montant_quittance if pesage else q.montant


def _quittances_poste(qs_poste, debut, fin, pesage):
    """Quittances d'un poste qui touchent la période : liste de dicts triés par premier jour couvert."""
    blocs = []
    for q in qs_poste:
        cov = _couverture(q, pesage)
        if not cov:
            continue
        p, d = cov
        if d < debut or p > fin:
            continue  # Hors période
        blocs.append({
            'quittance': q, 'numero': q.numero_quittance, 'montant': _montant(q, pesage), 'reversement': q.date_quittancement,
            'type': q.get_type_declaration_display(), 'complet_p': p, 'complet_d': d,
            'p': max(p, debut), 'd': min(d, fin),  # Partie visible dans la période
            'a_cheval': p < debut or d > fin,  # Décade qui dépasse la période choisie
        })
    blocs.sort(key=lambda b: (b['p'], b['d'], b['numero']))
    return blocs


def _cellules(blocs, jours, declare, avec_declare):
    """Construit la ligne « quittancé » : une cellule par quittance (colspan = nombre de jours couverts) et des cellules
    vides pour les jours sans quittance. Les quittances qui se chevauchent sont renvoyées à part (anomalie)."""
    cellules, chevauchements, curseur = [], [], jours[0]
    dernier = jours[0] - datetime.timedelta(days=1)  # Dernier jour déjà couvert
    for b in blocs:
        if b['p'] <= dernier:
            chevauchements.append(b)  # Chevauche une quittance précédente : comptée dans le total mais pas dessinée
            continue
        if b['p'] > curseur:  # Trou sans quittance avant ce bloc
            cellules.append(_trou(curseur, b['p'] - datetime.timedelta(days=1), declare, avec_declare))
        nb = (b['d'] - b['p']).days + 1  # Jours fusionnés
        jours_bloc = liste_jours(b['p'], b['d'])
        decl = sum((declare.get(j, ZERO) for j in jours_bloc), ZERO) if avec_declare else None
        b['declare_bloc'] = decl  # Déclaré sur les jours couverts
        b['ecart_bloc'] = (b['montant'] - decl) if avec_declare else None  # Quittancé - déclaré
        cellules.append({'type': 'quittance', 'colspan': nb, 'bloc': b})
        curseur = b['d'] + datetime.timedelta(days=1)
        dernier = b['d']
    if curseur <= jours[-1]:  # Trou final
        cellules.append(_trou(curseur, jours[-1], declare, avec_declare))
    return cellules, chevauchements


def _trou(p, d, declare, avec_declare):
    """Cellule(s) de jours SANS quittance. Un jour déclaré mais non quittancé est « manquant »."""
    jours_trou = liste_jours(p, d)
    # Péage : manquant = jour DÉCLARÉ sans quittance. Pesage (aucune déclaration) : tout jour sans quittance est manquant.
    manquants = [j for j in jours_trou if (declare.get(j, ZERO) > 0 if avec_declare else True)]
    return {'type': 'trou', 'colspan': len(jours_trou), 'jours': jours_trou, 'manquants': manquants}


def rapport_peage(debut, fin, poste_id=None, region_id=None, seulement_ecarts=False):
    """Rapport péage : retourne (jours, lignes, totaux). Une ligne par poste ayant déclaré ou quittancé sur la période."""
    jours = liste_jours(debut, fin)
    postes = Poste.objects.filter(type='peage', is_active=True).select_related('region').order_by('nom')
    if poste_id:
        postes = postes.filter(pk=poste_id)
    if region_id:
        postes = postes.filter(region_id=region_id)
    ids = list(postes.values_list('pk', flat=True))
    declarations = {}  # poste_id -> {jour: montant}
    for pid, jour, montant in RecetteJournaliere.objects.filter(poste_id__in=ids, date__range=(debut, fin)).values_list(
            'poste_id', 'date', 'montant_declare'):
        declarations.setdefault(pid, {})[jour] = declarations.get(pid, {}).get(jour, ZERO) + (montant or ZERO)
    quittances = {}  # poste_id -> [Quittancement]
    for q in _quittances_touchant(Quittancement, ids, debut, fin, 'poste_id__in'):  # Journalières + décades de la période
        quittances.setdefault(q.poste_id, []).append(q)
    lignes = []
    for poste in postes:
        declare = declarations.get(poste.pk, {})
        blocs = _quittances_poste(quittances.get(poste.pk, []), debut, fin, pesage=False)
        if not declare and not blocs:
            continue  # Poste sans activité sur la période
        cellules, chevauchements = _cellules(blocs, jours, declare, True)
        total_declare = sum(declare.values(), ZERO)
        total_quittance = sum((b['montant'] for b in blocs), ZERO)
        manquants = [j for c in cellules if c['type'] == 'trou' for j in c['manquants']]  # Déclarés non quittancés
        montant_manquant = sum((declare[j] for j in manquants), ZERO)
        ecart = total_quittance - total_declare  # Négatif = quittancé de moins que déclaré
        manquants_set = set(manquants)  # Pour marquer les jours déclarés non quittancés
        ligne = {
            'poste': poste, 'declare': declare, 'blocs': blocs,
            'cellules_declare': [{'jour': j, 'montant': declare.get(j), 'manquant': j in manquants_set} for j in jours],
            'cellules': cellules, 'chevauchements': chevauchements, 'total_declare': total_declare,
            'total_quittance': total_quittance, 'ecart': ecart, 'jours_manquants': manquants,
            'montant_manquant': montant_manquant, 'a_cheval': any(b['a_cheval'] for b in blocs),
            'statut': 'ok' if ecart == 0 and not manquants else 'ecart',
        }
        if seulement_ecarts and ligne['statut'] == 'ok':
            continue
        lignes.append(ligne)
    totaux = {
        'declare': sum((l['total_declare'] for l in lignes), ZERO), 'quittance': sum((l['total_quittance'] for l in lignes), ZERO),
        'nb_postes': len(lignes), 'nb_ecarts': sum(1 for l in lignes if l['statut'] == 'ecart'),
        'nb_jours_manquants': sum(len(l['jours_manquants']) for l in lignes),
        'montant_manquant': sum((l['montant_manquant'] for l in lignes), ZERO),
        'par_jour': [sum((l['declare'].get(j, ZERO) for l in lignes), ZERO) for j in jours],  # Déclaré total par jour
    }
    totaux['ecart'] = totaux['quittance'] - totaux['declare']
    return jours, lignes, totaux


def rapport_pesage(debut, fin, poste_id=None, region_id=None, seulement_ecarts=False):
    """Rapport pesage : quittances seulement (pas de déclaration). Une ligne par station ACTIVE (même sans quittance) ;
    les jours de la période non couverts par une quittance sont les JOURS MANQUANTS. Retourne (jours, lignes, totaux)."""
    jours = liste_jours(debut, fin)
    postes = Poste.objects.filter(type='pesage', is_active=True).select_related('region').order_by('nom')
    if poste_id:
        postes = postes.filter(pk=poste_id)
    if region_id:
        postes = postes.filter(region_id=region_id)
    ids = list(postes.values_list('pk', flat=True))
    quittances = {}
    for q in _quittances_touchant(QuittancementPesage, ids, debut, fin, 'station_id__in'):
        quittances.setdefault(q.station_id, []).append(q)
    lignes = []
    for poste in postes:
        blocs = _quittances_poste(quittances.get(poste.pk, []), debut, fin, pesage=True)
        cellules, chevauchements = _cellules(blocs, jours, {}, False)
        manquants = [j for c in cellules if c['type'] == 'trou' for j in c['manquants']]  # Jours sans quittance
        ligne = {'poste': poste, 'blocs': blocs, 'cellules': cellules, 'chevauchements': chevauchements,
                 'total_quittance': sum((b['montant'] for b in blocs), ZERO), 'jours_manquants': manquants,
                 'nb_jours_couverts': len(jours) - len(manquants), 'a_cheval': any(b['a_cheval'] for b in blocs),
                 'statut': 'ok' if not manquants else 'ecart'}
        if seulement_ecarts and ligne['statut'] == 'ok':
            continue
        lignes.append(ligne)
    totaux = {'quittance': sum((l['total_quittance'] for l in lignes), ZERO), 'nb_postes': len(lignes),
              'nb_quittances': sum(len(l['blocs']) for l in lignes),
              'nb_jours_manquants': sum(len(l['jours_manquants']) for l in lignes),
              'nb_ecarts': sum(1 for l in lignes if l['statut'] == 'ecart'),
              'nb_sans_quittance': sum(1 for l in lignes if not l['blocs'])}
    return jours, lignes, totaux


def periode_alignee(lignes, debut, fin):
    """Si des quittances de décade dépassent la période choisie, retourne la période ÉLARGIE qui les contient en entier
    (sinon la même période). Évite de comparer une quittance entière à une partie seulement des recettes."""
    nouveau_debut, nouvelle_fin = debut, fin
    for l in lignes:
        for b in l['blocs']:
            nouveau_debut = min(nouveau_debut, b['complet_p'])
            nouvelle_fin = max(nouvelle_fin, b['complet_d'])
    return nouveau_debut, nouvelle_fin


def _quittances_touchant(modele, ids, debut, fin, champ_poste):
    """Quittances (journalières dans la période + décades qui la touchent) des postes `ids`."""
    from django.db.models import Q  # Filtres combinés
    qs = modele.objects.filter(**{champ_poste: ids}).filter(
        Q(type_declaration=TypeDeclaration.JOURNALIERE, date_recette__range=(debut, fin)) |
        Q(type_declaration=TypeDeclaration.DECADE, date_debut_decade__lte=fin, date_fin_decade__gte=debut))
    return qs.order_by('date_quittancement', 'pk')
