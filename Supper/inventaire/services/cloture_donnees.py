# inventaire/services/cloture_donnees.py
# Assemblage des données des documents de clôture mensuelle :
#   - Compte d'emploi (péage)  - PV de confrontation (pesage)
# "preremplir_*" propose des valeurs modifiables ; "calculer_*" produit le dictionnaire
# FINAL figé (JSON) qui alimente le PDF.

import calendar  # Nombre de jours d'un mois
from datetime import date, timedelta  # Dates
from django.db.models import Q, Sum  # Filtres et agrégations SQL
from django.utils import timezone  # Date du jour

from inventaire.services.cloture_service import (  # Fonctions pures de calcul
    PRIX_TICKET, fusionner_intervalles, nombre_tickets, libelle_intervalles,
    soustraire_intervalles, taux_pct, calculer_rar, date_longue,
)


# ----------------------------------------------------------------------
# Utilitaires de période
# ----------------------------------------------------------------------
def bornes_mois(mois):
    """'2026-10' -> (date(2026,10,1), date(2026,10,31))."""
    annee, num = (int(x) for x in mois.split('-'))
    return date(annee, num, 1), date(annee, num, calendar.monthrange(annee, num)[1])


def mois_precedent(mois):
    """'2026-01' -> '2025-12'."""
    veille = bornes_mois(mois)[0] - timedelta(days=1)  # Dernier jour du mois précédent
    return f"{veille.year}-{veille.month:02d}"


def mois_meme_periode_annee_precedente(mois):
    """'2026-10' -> '2025-10' (base du rendement N-1)."""
    annee, num = mois.split('-')
    return f"{int(annee) - 1}-{num}"


def _jours(debut, fin):
    """Ensemble des jours de debut à fin inclus."""
    return {debut + timedelta(days=i) for i in range((fin - debut).days + 1)} if fin >= debut else set()


# ----------------------------------------------------------------------
# Titulaire (nom figé sur le document) : celui du DERNIER JOUR du mois
# ----------------------------------------------------------------------
def titulaire_fin_mois(poste, fonction, mois):
    """Retourne (nom, libellé fonction) du titulaire au dernier jour du mois.
    Ordre : AffectationPoste -> HistoriqueAffectation (chef de poste) -> compte actif actuel."""
    from inventaire.models import HistoriqueAffectation
    from inventaire.models_cloture import AffectationPoste, FonctionTitulaire
    from accounts.models import UtilisateurSUPPER

    dernier_jour = bornes_mois(mois)[1]
    libelle = FonctionTitulaire(fonction).label

    aff = AffectationPoste.titulaire_au(poste, fonction, dernier_jour)  # 1) historique dédié
    if aff and aff.nom_affiche:
        return aff.nom_affiche, libelle
    if fonction == FonctionTitulaire.CHEF_POSTE_PEAGE:  # 2) historique existant des chefs de poste
        hist = HistoriqueAffectation.get_affectation_a_date(poste, dernier_jour, 'chef_poste')
        if hist:
            return hist.utilisateur.nom_complet, libelle
    habilitation = {FonctionTitulaire.CHEF_POSTE_PEAGE: 'chef_peage',
                    FonctionTitulaire.REGISSEUR_PESAGE: 'regisseur_pesage',
                    FonctionTitulaire.CHEF_STATION_PESAGE: 'chef_station_pesage'}[fonction]
    user = UtilisateurSUPPER.objects.filter(  # 3) compte actif actuellement affecté
        poste_affectation=poste, habilitation=habilitation, is_active=True).first()
    return (user.nom_complet if user else ''), libelle


# ----------------------------------------------------------------------
# À jour : recettes (péage) + quittances journalières/décades ; lignes du tableau B
# (les quittances sont de type 'journaliere' ou 'decade')
# ----------------------------------------------------------------------
def _quittances_periode(type_poste, poste, debut, fin):
    """Quittances (péage ou pesage) dont la couverture touche [debut, fin]."""
    if type_poste == 'peage':
        from inventaire.models import Quittancement as M
        cle = {'poste': poste}
    else:
        from inventaire.models_pesage import QuittancementPesage as M
        cle = {'station': poste}
    return M.objects.filter(**cle).filter(
        Q(type_declaration='journaliere', date_recette__gte=debut, date_recette__lte=fin) |
        Q(type_declaration='decade', date_debut_decade__lte=fin, date_fin_decade__gte=debut))


def jours_couverts(type_poste, poste, debut, fin):
    """Jours de [debut, fin] couverts par une quittance journalière ou de décade."""
    couverts = set()
    for q in _quittances_periode(type_poste, poste, debut, fin):
        if q.type_declaration == 'journaliere':
            couverts.add(q.date_recette)
        else:  # Décade : tous les jours de l'intervalle, bornés à la période
            couverts |= _jours(max(q.date_debut_decade, debut), min(q.date_fin_decade, fin))
    return couverts


def plages_dates(dates):
    """Liste de dates -> texte compact : [1,2,3,7] d'octobre -> 'du 01/10 au 03/10, 07/10'."""
    dates = sorted(dates)
    if not dates:
        return ''
    plages, debut, prec = [], dates[0], dates[0]
    for d in dates[1:]:
        if d == prec + timedelta(days=1):
            prec = d  # La plage continue
            continue
        plages.append((debut, prec))
        debut = prec = d
    plages.append((debut, prec))
    f = lambda d: d.strftime('%d/%m')
    return ', '.join(f(a) if a == b else f"du {f(a)} au {f(b)}" for a, b in plages)


def jours_avec_recette(poste, debut, fin):
    """Jours de [debut, fin] pour lesquels une recette journalière existe (saisie ou importée)."""
    from inventaire.models import RecetteJournaliere
    return set(RecetteJournaliere.objects.filter(
        poste=poste, date__gte=debut, date__lte=fin).values_list('date', flat=True))


def statut_a_jour(type_poste, poste, mois, jusqu_au=None):
    """Règle « à jour » :
      - PÉAGE  : chaque jour du mois a une recette ET est couvert par une quittance (journalière ou décade) ;
      - PESAGE : chaque jour du mois est couvert par une quittance (journalière ou décade).
    Retourne {'a_jour', 'recettes_manquantes': [dates], 'quittances_manquantes': [dates]}."""
    debut, fin = bornes_mois(mois)
    if jusqu_au:
        fin = min(fin, jusqu_au)  # Les jours futurs ne comptent pas
    tous = _jours(debut, fin)
    sans_quittance = sorted(tous - jours_couverts(type_poste, poste, debut, fin))
    sans_recette = sorted(tous - jours_avec_recette(poste, debut, fin)) if type_poste == 'peage' else []
    return {'a_jour': not sans_quittance and not sans_recette,
            'recettes_manquantes': sans_recette, 'quittances_manquantes': sans_quittance,
            'recettes_txt': plages_dates(sans_recette), 'quittances_txt': plages_dates(sans_quittance)}


def statut_a_jour_peage(poste, mois):
    return statut_a_jour('peage', poste, mois)


def statut_a_jour_pesage(station, mois):
    return statut_a_jour('pesage', station, mois)


def historique_acct(type_poste, poste, mois):
    """Montant de l'historique ACCT du mois (montant réel du poste/de la station), ou None s'il n'existe pas.
    Péage : HistoriqueQuittance (mois 'YYYY-MM') ; pesage : HistoriquesPesage (année + mois numériques)."""
    if type_poste == 'peage':
        from inventaire.models import HistoriqueQuittance
        h = HistoriqueQuittance.objects.filter(poste=poste, mois=mois).first()
    else:
        from inventaire.models_historique_pesage import HistoriquesPesage
        annee, num = (int(x) for x in mois.split('-'))
        h = HistoriquesPesage.objects.filter(station=poste, annee=annee, mois=num).first()
    return int(h.montant_reel) if h is not None else None


def mois_avec_acct(type_poste, poste, mois_liste):
    """Ensemble des mois (parmi mois_liste) qui ont un historique ACCT : une seule requête."""
    if type_poste == 'peage':
        from inventaire.models import HistoriqueQuittance
        return set(HistoriqueQuittance.objects.filter(poste=poste, mois__in=mois_liste).values_list('mois', flat=True))
    from inventaire.models_historique_pesage import HistoriquesPesage
    codes = {(int(m[:4]), int(m[5:])): m for m in mois_liste}
    qs = HistoriquesPesage.objects.filter(station=poste, annee__in={a for a, _ in codes})
    return {codes[(h.annee, h.mois)] for h in qs if (h.annee, h.mois) in codes}


def statut_complet(type_poste, poste, mois):
    """Statut d'un poste pour un mois : 'complet' si tous les jours sont renseignés (recettes pour le péage,
    quittances journalières/décades) ET l'historique ACCT existe ; sinon 'en_cours'.
    Retourne aussi le détail des manques pour l'affichage."""
    st = statut_a_jour(type_poste, poste, mois)
    acct = historique_acct(type_poste, poste, mois)
    st['acct_manquant'] = acct is None
    st['complet'] = st['a_jour'] and acct is not None
    return st


def tableau_quittances(type_poste, poste, mois):
    """Lignes du tableau B : une par quittance du mois (type journalière/décade).
    Montant collecté = montant reversé = montant de la quittance."""
    debut, fin = bornes_mois(mois)
    lignes = []
    for q in _quittances_periode(type_poste, poste, debut, fin).filter(
            Q(mois=mois) | Q(mois='')).order_by('date_quittancement', 'id'):
        montant = int(q.montant if type_poste == 'peage' else q.montant_quittance)
        lignes.append({'date': q.date_quittancement.isoformat(), 'numero': q.numero_quittance,
                       'type': q.type_declaration, 'montant_collecte': montant, 'montant_reverse': montant})
    return lignes


# ----------------------------------------------------------------------
# Défaillants : postes non à jour sur une période
# ----------------------------------------------------------------------
def _mois_de_intervalle(debut, fin):
    """Mois 'YYYY-MM' touchés par l'intervalle [debut, fin]."""
    mois, a, m = [], debut.year, debut.month
    while (a, m) <= (fin.year, fin.month):
        mois.append(f"{a}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return mois


def liste_defaillants(type_poste, postes, date_debut, date_fin, criteres=('recettes', 'quittances', 'acct')):
    """Postes en défaut entre deux dates (jusqu'à aujourd'hui au plus). `criteres` = ensemble parmi :
      'recettes'   : jours sans recette (péage seulement) ;
      'quittances' : jours non couverts par une quittance (journalière ou décade) ;
      'acct'       : mois TERMINÉS sans historique ACCT (un mois en cours n'est pas compté).
    Un poste est listé s'il manque l'un des critères retenus. Détail regroupé par mois."""
    criteres = set(criteres)
    if type_poste != 'peage':
        criteres.discard('recettes')  # Pesage : pas de recettes journalières
    aujourdhui = timezone.localdate()
    fin_p = min(date_fin, aujourdhui)
    resultat = []
    if date_debut > fin_p or not criteres:
        return resultat
    mois_liste = _mois_de_intervalle(date_debut, fin_p)
    for poste in postes:
        couverts = jours_couverts(type_poste, poste, date_debut, fin_p) if 'quittances' in criteres else set()
        avec_recette = jours_avec_recette(poste, date_debut, fin_p) if 'recettes' in criteres else set()
        avec_acct = mois_avec_acct(type_poste, poste, mois_liste) if 'acct' in criteres else set()
        en_defaut = []
        for m in mois_liste:
            d, f = bornes_mois(m)
            tous = _jours(max(d, date_debut), min(f, fin_p))
            sans_quittance = (tous - couverts) if 'quittances' in criteres else set()
            sans_recette = (tous - avec_recette) if 'recettes' in criteres else set()
            sans_acct = 'acct' in criteres and f < aujourdhui and m not in avec_acct  # Mois terminé sans ACCT
            manque = sorted(sans_quittance | sans_recette)
            if manque or sans_acct:
                en_defaut.append({'mois': m, 'nb_jours': len(manque), 'premier': manque[0] if manque else None,
                                  'dernier': manque[-1] if manque else None,
                                  'nb_sans_quittance': len(sans_quittance), 'nb_sans_recette': len(sans_recette),
                                  'sans_acct': sans_acct,
                                  'quittances_txt': plages_dates(sans_quittance),
                                  'recettes_txt': plages_dates(sans_recette)})
        if en_defaut:
            resultat.append({'poste': poste, 'mois': en_defaut,
                             'total_jours': sum(x['nb_jours'] for x in en_defaut),
                             'total_sans_quittance': sum(x['nb_sans_quittance'] for x in en_defaut),
                             'total_sans_recette': sum(x['nb_sans_recette'] for x in en_defaut),
                             'total_sans_acct': sum(1 for x in en_defaut if x['sans_acct'])})
    # Les plus en retard d'abord (jours en défaut, puis mois sans ACCT)
    return sorted(resultat, key=lambda r: (-r['total_jours'], -r['total_sans_acct']))


# ----------------------------------------------------------------------
# Rendement N-1 (pré-rempli, modifiable ; 0 si inconnu)
# ----------------------------------------------------------------------
ANNEE_DERNIERE_RECETTES = 2025  # Jusqu'à cette année (incluse) la référence N-1 = recettes importées


def rendement_n1_peage(poste, mois):
    """Rendement du même mois l'an dernier (péage).
    - année de référence <= 2025 : total des recettes journalières déclarées (importées) ;
    - année de référence >= 2026 : total des quittances du mois (règle à partir de 2027)."""
    from inventaire.models import Quittancement, RecetteJournaliere
    mois_n1 = mois_meme_periode_annee_precedente(mois)
    annee, num = (int(x) for x in mois_n1.split('-'))
    if annee <= ANNEE_DERNIERE_RECETTES:
        total = RecetteJournaliere.objects.filter(
            poste=poste, date__year=annee, date__month=num).aggregate(t=Sum('montant_declare'))['t']
    else:
        total = Quittancement.objects.filter(poste=poste, mois=mois_n1).aggregate(t=Sum('montant'))['t']
    return int(total or 0)


def rendement_n1_pesage(station, mois):
    """Rendement du même mois l'an dernier (pesage) : uniquement les quittances du mois N-1."""
    from inventaire.models_pesage import QuittancementPesage
    total = QuittancementPesage.objects.filter(
        station=station, mois=mois_meme_periode_annee_precedente(mois)).aggregate(t=Sum('montant_quittance'))['t']
    return int(total or 0)


# ----------------------------------------------------------------------
# COMPTE D'EMPLOI (péage)
# ----------------------------------------------------------------------
def series_au(poste, jour):
    """Séries détenues par le poste à la fin du jour donné, reconstituées depuis SerieTicket
    (reçues au plus tard ce jour, et encore en stock ou vendues après ce jour).
    La banque de gel ne laisse AUCUNE trace dans le compte d'emploi : une série gelée n'est plus au poste
    (comme si elle n'y avait jamais été) et une série dégelée y entre au plus tard au début du mois d'effet."""
    from inventaire.models import SerieTicket
    qs = SerieTicket.objects.filter(poste=poste, date_reception__date__lte=jour).filter(
        Q(statut='stock') | Q(statut='vendu', date_utilisation__gt=jour))
    return fusionner_intervalles([(s.numero_premier, s.numero_dernier) for s in qs])


def _series_details(details):
    """Extrait les intervalles des détails d'approvisionnement/transfert du calcul existant."""
    resultat = []
    for det in details:
        for s in det.get('series', []):
            resultat.append((int(s['numero_premier']), int(s['numero_dernier'])))
    return fusionner_intervalles(resultat)


def series_ouverture(poste, mois):
    """Ouverture = stock SUPPER détenu par le poste la veille du 1er jour du mois (plus aucune déclaration du chef)."""
    return series_au(poste, bornes_mois(mois)[0] - timedelta(days=1))


def preremplir_compte_emploi(poste, mois):
    """Éléments du compte d'emploi calculés par SUPPER (stock début, approv., réappro, stock fin), en intervalles de tickets.
    Le chef de poste ne déclare plus que les abonnements et le rendement N-1."""
    from inventaire.views_rapports import calculer_donnees_compte_emploi_v2
    debut, fin = bornes_mois(mois)
    d = calculer_donnees_compte_emploi_v2(poste, debut, fin)  # Calcul SUPPER existant
    return {
        'series_ouverture': series_ouverture(poste, mois),
        'series_approv': _series_details(d['approv_imprimerie']['details']),
        'series_recu': _series_details(d['reapprov_recu']['details']),
        'series_cede': _series_details(d['reapprov_cede']['details']),
        'series_fin': series_au(poste, fin),  # Stock de fin = stock SUPPER à la fin du mois
        'abonnements': 0,
        'rendement_n1': rendement_n1_peage(poste, mois),
    }


def series_fin_disponibles(poste, mois):
    """Séries proposées en cases à cocher pour le stock de fin (celles que SUPPER connaît)."""
    return series_au(poste, bornes_mois(mois)[1])


def calculer_compte_emploi(poste, mois, manuel):
    """Dictionnaire FINAL du compte d'emploi. Le stock vendu est déduit des séries :
    vendu = (ouverture + approv + reçu) - cédé - fin."""
    ouv, app, rec, ced, fin = (fusionner_intervalles(manuel[k]) for k in (
        'series_ouverture', 'series_approv', 'series_recu', 'series_cede', 'series_fin'))
    base = fusionner_intervalles(ouv + app + rec)  # Tout ce qui a été détenu dans le mois
    vendu = soustraire_intervalles(soustraire_intervalles(base, ced), fin)
    fin_hors_base = soustraire_intervalles(fin, base)  # Séries de fin inconnues du mois : anomalie

    def ligne(series):
        n = nombre_tickets(series) if series else 0
        return {'tickets': n, 'valeur': n * PRIX_TICKET, 'series': [list(i) for i in series],
                'libelle': libelle_intervalles(series) if series else ''}

    lignes_b = tableau_quittances('peage', poste, mois)
    total_reverse = sum(l['montant_reverse'] for l in lignes_b)
    abonnements = int(manuel['abonnements'])
    attendu = ligne(vendu)['valeur'] + abonnements  # Contrôle : reversé = vendu + abonnements
    rend = int(manuel['rendement_n1'])
    ecart = total_reverse - rend
    pct = taux_pct(ecart, rend)
    nom, fonction = titulaire_fin_mois(poste, 'chef_poste_peage', mois)
    acct = historique_acct('peage', poste, mois)  # Historique ACCT du mois (None si absent)
    return {
        'historique_acct': acct, 'ecart_acct': (acct - total_reverse) if acct is not None else None,
        'mois': mois, 'poste': poste.nom, 'poste_code': poste.code,
        'stock_ouverture': ligne(ouv), 'approv': ligne(app), 'reappro_recu': ligne(rec),
        'reappro_cede': ligne(ced), 'stock_vendu': ligne(vendu), 'abonnements': abonnements,
        'stock_fin': ligne(fin), 'tableau_b': lignes_b, 'total_reverse': total_reverse,
        'controle_reverse_ok': total_reverse == attendu, 'ecart_controle': total_reverse - attendu,
        'fin_hors_base': [list(i) for i in fin_hors_base],
        'rendement_n1': rend, 'ecart_rendement': ecart,
        'indice_pct': str(pct) if pct is not None else None,
        'signataire_nom': nom, 'signataire_fonction': 'Chef de poste',
        'date_fait': date_longue(timezone.localdate()),
        'manuel': {k: ([list(i) for i in v] if isinstance(v, list) else v) for k, v in manuel.items()},
    }


# ----------------------------------------------------------------------
# PV DE CONFRONTATION (pesage)
# ----------------------------------------------------------------------
def rar_precedent_pesage(station, mois):
    """RAR à fin du mois précédent : PV précédent s'il existe, sinon amendes non payées avant le mois."""
    from inventaire.models_cloture import ClotureMensuelle
    from inventaire.models_pesage import AmendeEmise
    prec = ClotureMensuelle.objects.filter(
        poste=station, type_document='pv_confrontation', mois=mois_precedent(mois)
    ).exclude(statut='remplace').order_by('-version').first()
    if prec:
        return int(prec.donnees['rar_mois'])
    debut = bornes_mois(mois)[0]
    emis = AmendeEmise.objects.filter(station=station, date_heure_emission__date__lt=debut
                                      ).aggregate(t=Sum('montant_amende'))['t'] or 0
    paye = AmendeEmise.objects.filter(station=station, statut='paye', date_paiement__date__lt=debut
                                      ).aggregate(t=Sum('montant_amende'))['t'] or 0
    return int(emis - paye)


def preremplir_pv(station, mois):
    """Valeurs proposées pour le PV (modifiables)."""
    from inventaire.models_pesage import AmendeEmise, PeseesJournalieres
    debut, fin = bornes_mois(mois)
    amendes = AmendeEmise.objects.filter(
        station=station, date_heure_emission__date__gte=debut, date_heure_emission__date__lte=fin)
    return {
        'nombre_pesees': int(PeseesJournalieres.objects.filter(
            station=station, date__gte=debut, date__lte=fin).aggregate(t=Sum('nombre_pesees'))['t'] or 0),
        'nombre_infractions': amendes.count(),
        'emissions': int(amendes.aggregate(t=Sum('montant_amende'))['t'] or 0),
        'rar_precedent': rar_precedent_pesage(station, mois),
        'rendement_n1': rendement_n1_pesage(station, mois),
    }


def calculer_pv(station, mois, manuel):
    """Dictionnaire FINAL du PV : recouvré = total des quittances du mois."""
    lignes_b = tableau_quittances('pesage', station, mois)
    recouvre = sum(l['montant_reverse'] for l in lignes_b)
    rar = calculer_rar(manuel['emissions'], manuel['rar_precedent'], recouvre)  # émissions + RAR préc. - recouvré
    rend = int(manuel['rendement_n1'])
    ecart = recouvre - rend
    pct = taux_pct(ecart, rend)
    nom, fonction = titulaire_fin_mois(station, 'regisseur_pesage', mois)  # Régisseur du dernier jour
    acct = historique_acct('pesage', station, mois)  # Historique ACCT du mois (None si absent)
    return {
        'historique_acct': acct, 'ecart_acct': (acct - recouvre) if acct is not None else None,
        'mois': mois, 'poste': station.nom, 'poste_code': station.code,
        'nombre_pesees': int(manuel['nombre_pesees']), 'nombre_infractions': int(manuel['nombre_infractions']),
        'emissions': int(manuel['emissions']), 'rar_precedent': int(manuel['rar_precedent']),
        'recouvre': recouvre, 'rar_mois': int(rar), 'tableau_b': lignes_b, 'total_reverse': recouvre,
        'rendement_n1': rend, 'ecart_rendement': ecart,
        'indice_pct': str(pct) if pct is not None else None,
        'signataire_nom': nom, 'signataire_fonction': 'Le Régisseur des Recettes',
        'chef_station_nom': '',  # Laissé vide : le chef de station écrit son nom
        'date_fait': date_longue(timezone.localdate()), 'manuel': dict(manuel),
    }
