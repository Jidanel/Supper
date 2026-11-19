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


def _appliquer_prorata(blocs, declare_complet):
    """Quittance de décade qui DÉPASSE la période choisie : seule sa part dans la période est comptée (au prorata).
    Part = recettes déclarées dans la période / recettes déclarées sur toute la décade (péage) ; à défaut de déclarations
    (pesage, ou décade sans recette déclarée) : nombre de jours dans la période / nombre de jours de la décade.
    Le montant entier reste visible (`montant_total`). Les quittances entièrement dans la période ne sont pas touchées."""
    for b in blocs:
        b['montant_total'] = b['montant']  # Montant entier de la quittance
        b['proratise'] = False
        if not b['a_cheval']:
            continue
        jours_dans, jours_tous = liste_jours(b['p'], b['d']), liste_jours(b['complet_p'], b['complet_d'])
        ratio = Decimal(len(jours_dans)) / Decimal(len(jours_tous))  # Par défaut : au prorata des jours
        if declare_complet is not None:
            total = sum((declare_complet.get(j, ZERO) for j in jours_tous), ZERO)
            if total > 0:
                ratio = sum((declare_complet.get(j, ZERO) for j in jours_dans), ZERO) / total  # Au prorata des recettes
        b['montant'] = (b['montant_total'] * ratio).quantize(Decimal('1'))  # Part dans la période
        b['ratio'] = ratio
        b['proratise'] = True


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
    # Péage comme pesage : tout jour sans quittance est « manquant » (croix rouge), qu'une recette ait été déclarée ou non.
    manquants = list(jours_trou)
    # Une case PAR JOUR : croix rouge sur les jours manquants, case vide sinon (jour sans recette déclarée en péage)
    cases = [{'jour': j, 'manquant': j in set(manquants)} for j in jours_trou]
    return {'type': 'trou', 'colspan': len(jours_trou), 'jours': jours_trou, 'manquants': manquants, 'cases': cases}


def rapport_peage(debut, fin, poste_id=None, region_id=None, seulement_ecarts=False):
    """Rapport péage : retourne (jours, lignes, totaux). Une ligne par poste ayant déclaré ou quittancé sur la période."""
    jours = liste_jours(debut, fin)
    postes = Poste.objects.filter(type='peage', is_active=True).select_related('region').order_by('nom')
    if poste_id:
        postes = postes.filter(pk=poste_id)
    if region_id:
        postes = postes.filter(region_id=region_id)
    ids = list(postes.values_list('pk', flat=True))
    quittances = {}  # poste_id -> [Quittancement]
    for q in _quittances_touchant(Quittancement, ids, debut, fin, 'poste_id__in'):  # Journalières + décades de la période
        quittances.setdefault(q.poste_id, []).append(q)
    # Déclarations lues sur la plage qui contient aussi les décades entières (nécessaire au prorata), puis limitées à la période
    plage_debut, plage_fin = debut, fin
    for lq in quittances.values():
        for q in lq:
            cov = _couverture(q, False)
            if cov:
                plage_debut, plage_fin = min(plage_debut, cov[0]), max(plage_fin, cov[1])
    declarations_completes = {}  # poste_id -> {jour: montant} sur la plage élargie
    for pid, jour, montant in RecetteJournaliere.objects.filter(poste_id__in=ids, date__range=(plage_debut, plage_fin)).values_list(
            'poste_id', 'date', 'montant_declare'):
        declarations_completes.setdefault(pid, {})[jour] = declarations_completes.get(pid, {}).get(jour, ZERO) + (montant or ZERO)
    declarations = {pid: {j: m for j, m in d.items() if debut <= j <= fin} for pid, d in declarations_completes.items()}
    lignes = []
    for poste in postes:
        declare = declarations.get(poste.pk, {})
        blocs = _quittances_poste(quittances.get(poste.pk, []), debut, fin, pesage=False)
        _appliquer_prorata(blocs, declarations_completes.get(poste.pk, {}))  # Décades à cheval : part dans la période
        cellules, chevauchements = _cellules(blocs, jours, declare, True)
        total_declare = sum(declare.values(), ZERO)
        total_quittance = sum((b['montant'] for b in blocs), ZERO)
        manquants = [j for c in cellules if c['type'] == 'trou' for j in c['manquants']]  # Déclarés non quittancés
        montant_manquant = sum((declare.get(j, ZERO) for j in manquants), ZERO)
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
    totaux['rapprochement'] = _rapprochement(lignes, Quittancement, ids, debut, fin, 'poste_id__in', 'montant')
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
        _appliquer_prorata(blocs, None)  # Décades à cheval : au prorata des jours
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
    totaux['rapprochement'] = _rapprochement(lignes, QuittancementPesage, ids, debut, fin, 'station_id__in', 'montant_quittance')
    return jours, lignes, totaux


def _rapprochement(lignes, modele, ids, debut, fin, champ_poste, champ_montant):
    """Chiffres pour RAPPROCHER ce rapport (filtré par jours de RECETTE) de la liste des quittances (filtrée par date de
    REVERSEMENT) : montant entier des quittances concernées, part des décades hors période, montant reversé dans la période
    et, dans ce reversé, ce qui concerne des recettes situées hors de la période."""
    from django.db.models import Q  # Filtres combinés
    entier = sum((b['montant_total'] for l in lignes for b in l['blocs']), ZERO)  # Quittances touchant la période (montant entier)
    compte = sum((b['montant'] for l in lignes for b in l['blocs']), ZERO)  # Part comptée dans la période
    reverse = ZERO  # Reversé (date de quittancement) dans la période, tous jours de recette confondus
    reverse_hors = ZERO  # Dont : quittances dont AUCUN jour de recette n'est dans la période
    for q in modele.objects.filter(**{champ_poste: ids}, date_quittancement__range=(debut, fin)):
        montant = getattr(q, champ_montant) or ZERO
        reverse += montant
        cov = _couverture(q, False)
        if not cov or cov[1] < debut or cov[0] > fin:
            reverse_hors += montant
    return {'entier': entier, 'hors_periode_prorata': entier - compte, 'reverse': reverse, 'reverse_hors_recettes': reverse_hors}


def _quittances_touchant(modele, ids, debut, fin, champ_poste):
    """Quittances (journalières dans la période + décades qui la touchent) des postes `ids`."""
    from django.db.models import Q  # Filtres combinés
    qs = modele.objects.filter(**{champ_poste: ids}).filter(
        Q(type_declaration=TypeDeclaration.JOURNALIERE, date_recette__range=(debut, fin)) |
        Q(type_declaration=TypeDeclaration.DECADE, date_debut_decade__lte=fin, date_fin_decade__gte=debut))
    return qs.order_by('date_quittancement', 'pk')


# ----------------------------------------------------------------------------------------------------------------------
# MODE « DATES DE REVERSEMENT » : la période choisie porte sur la date de quittancement (comme la liste des quittances).
# Les montants « reversés » sont donc identiques à ceux de la liste. Le tableau jour par jour montre les JOURS DE RECETTE
# couverts par ces quittances : journalière = une colonne ; décade = un seul montant fusionné ; croix rouge = jour sans
# aucune quittance (déclaré en péage ; en pesage, tout jour sans quittance).
# ----------------------------------------------------------------------------------------------------------------------
MAX_COLONNES = 100  # Nombre maximal de jours affichés (lisibilité)


def rapport_par_reversement(type_poste, debut, fin, poste_id=None, region_id=None, seulement_ecarts=False):
    """Retourne (jours, lignes, totaux, avertissement). `debut`/`fin` = dates de REVERSEMENT."""
    pesage = type_poste == 'pesage'
    modele = QuittancementPesage if pesage else Quittancement
    champ_poste, champ_montant = ('station_id__in', 'montant_quittance') if pesage else ('poste_id__in', 'montant')
    postes = Poste.objects.filter(type=type_poste, is_active=True).select_related('region').order_by('nom')
    if poste_id:
        postes = postes.filter(pk=poste_id)
    if region_id:
        postes = postes.filter(region_id=region_id)
    ids = list(postes.values_list('pk', flat=True))
    cle_poste = (lambda q: q.station_id) if pesage else (lambda q: q.poste_id)
    # 1) Quittances REVERSÉES dans la période (identiques à la liste des quittances)
    reversees = list(modele.objects.filter(**{champ_poste: ids}, date_quittancement__range=(debut, fin)).order_by('date_quittancement', 'pk'))
    # 2) Plage de jours de recette à afficher : de la 1re à la dernière date de recette couverte par ces quittances
    span_debut = span_fin = None  # Jours de recette couverts par les quittances reversées dans la période
    for q in reversees:
        cov = _couverture(q, pesage)
        if cov:
            span_debut = cov[0] if span_debut is None else min(span_debut, cov[0])
            span_fin = cov[1] if span_fin is None else max(span_fin, cov[1])
    if span_debut is None:  # Aucune quittance reversée : on affiche les jours de la période elle-même
        span_debut, span_fin = debut, fin
    avertissement = None
    if (span_fin - span_debut).days + 1 > MAX_COLONNES:
        span_debut = span_fin - datetime.timedelta(days=MAX_COLONNES - 1)
        avertissement = f"Affichage limité aux {MAX_COLONNES} derniers jours de recette ({span_debut:%d/%m/%Y} → {span_fin:%d/%m/%Y})."
    jours = liste_jours(span_debut, span_fin)
    ids_reversees = {q.pk for q in reversees}
    # 3) Toutes les quittances qui touchent ces jours (même reversées hors période) : pour ne pas déclarer « manquant » un jour déjà quittancé
    par_poste = {}
    for q in _quittances_touchant(modele, ids, span_debut, span_fin, champ_poste):
        par_poste.setdefault(cle_poste(q), []).append(q)
    declarations = {}
    if not pesage:
        for pid, jour, montant in RecetteJournaliere.objects.filter(poste_id__in=ids, date__range=(span_debut, span_fin)).values_list(
                'poste_id', 'date', 'montant_declare'):
            declarations.setdefault(pid, {})[jour] = declarations.get(pid, {}).get(jour, ZERO) + (montant or ZERO)
    lignes = []
    for poste in postes:
        declare = declarations.get(poste.pk, {})
        blocs = _quittances_poste(par_poste.get(poste.pk, []), span_debut, span_fin, pesage)
        for b in blocs:
            b['montant_total'], b['proratise'] = b['montant'], False  # Pas de prorata dans ce mode
            b['dans_periode'] = b['quittance'].pk in ids_reversees  # Reversée dans la période choisie ?
        blocs_periode = [b for b in blocs if b['dans_periode']]
        reverse_total = sum((b['montant'] for b in blocs_periode), ZERO)  # Identique à la liste des quittances
        cellules, chevauchements = _cellules(blocs, jours, declare, not pesage)
        manquants = [j for c in cellules if c['type'] == 'trou' for j in c['manquants']]
        jours_couverts = set()  # Jours de recette couverts par les quittances REVERSÉES dans la période
        for b in blocs_periode:
            jours_couverts.update(liste_jours(b['p'], b['d']))
        declare_couvert = sum((declare.get(j, ZERO) for j in jours_couverts), ZERO)
        ligne = {
            'poste': poste, 'declare': declare, 'blocs': blocs, 'blocs_periode': blocs_periode, 'cellules': cellules,
            'cellules_declare': [{'jour': j, 'montant': declare.get(j), 'manquant': j in set(manquants)} for j in jours],
            'chevauchements': chevauchements, 'total_declare': declare_couvert, 'total_quittance': reverse_total,
            'ecart': reverse_total - declare_couvert, 'jours_manquants': manquants, 'a_cheval': False,
            'montant_manquant': sum((declare.get(j, ZERO) for j in manquants), ZERO),
            'nb_jours_couverts': len(jours) - len(manquants), 'nb_quittances': len(blocs_periode),
        }
        if pesage:
            ligne['statut'] = 'ok' if not manquants else 'ecart'
        else:
            ligne['statut'] = 'ok' if ligne['ecart'] == 0 and not manquants else 'ecart'
        if seulement_ecarts and ligne['statut'] == 'ok':
            continue
        lignes.append(ligne)
    totaux = {
        'quittance': sum((l['total_quittance'] for l in lignes), ZERO), 'declare': sum((l['total_declare'] for l in lignes), ZERO),
        'nb_postes': len(lignes), 'nb_ecarts': sum(1 for l in lignes if l['statut'] == 'ecart'),
        'nb_quittances': sum(l['nb_quittances'] for l in lignes), 'nb_jours_manquants': sum(len(l['jours_manquants']) for l in lignes),
        'montant_manquant': sum((l['montant_manquant'] for l in lignes), ZERO),
        'nb_sans_quittance': sum(1 for l in lignes if not l['blocs_periode']),
        'par_jour': [sum((l['declare'].get(j, ZERO) for l in lignes), ZERO) for j in jours],
    }
    totaux['ecart'] = totaux['quittance'] - totaux['declare']
    return jours, lignes, totaux, avertissement
