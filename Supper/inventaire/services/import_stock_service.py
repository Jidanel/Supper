# inventaire/services/import_stock_service.py
# Service métier : IMPORT DE RECETTES AVEC STOCKS (simulation avant validation, poste par poste).
#   - lire_excel()      : lit le fichier matriciel (postes en lignes, dates en colonnes)
#   - series_disponibles(): séries en stock d'un poste, de la plus récente recharge à la plus ancienne
#   - simuler()         : calcule, sans rien écrire, quelles séries seraient vendues chaque jour
#   - completer_selection(): ajoute les séries suivantes jusqu'à couvrir le besoin
#   - executer_poste()  : crée les recettes, consomme les séries, met à jour le stock (atomique)
#   - annuler_poste()   : supprime les recettes importées et remet les tickets en stock

import datetime  # Dates
import logging  # Journal technique
from decimal import Decimal, InvalidOperation  # Montants exacts

from django.db import transaction  # Atomicité : tout ou rien
from django.utils import timezone  # Horodatage

from inventaire.models import (  # Modèles de stock et de recette
    SerieTicket, GestionStock, HistoriqueStock, StockEvent, RecetteJournaliere, DetailVenteTicket)
from inventaire.services.permutation_service import _fusionner_voisins, MOTIF_MIN  # Outils partagés
from inventaire.services.gel_service import peut_gerer_gel  # Même droit d'accès que le gel/dégel

logger = logging.getLogger('supper')  # Journal applicatif
PRIX = Decimal('500')  # Valeur d'un ticket en FCFA


class ImportStockError(Exception):
    """Erreur métier : l'opération est impossible (message lisible par l'utilisateur)."""


def peut_importer_stock(user):
    """Autorisés : administrateur, Service Informatique, Service Émissions et Recouvrement."""
    return peut_gerer_gel(user)  # Mêmes profils que la banque de gel


# ----------------------------------------------------------------------------------------------------------------------
# LECTURE DU FICHIER EXCEL
# ----------------------------------------------------------------------------------------------------------------------
def _date_colonne(col):
    """Convertit un en-tête de colonne (datetime, Timestamp ou texte) en date ; None si ce n'est pas une date."""
    if isinstance(col, datetime.datetime):
        return col.date()  # Date + heure -> date
    if isinstance(col, datetime.date):
        return col  # Déjà une date
    if isinstance(col, str):
        for fmt in ('%d/%m/%y', '%d/%m/%Y', '%Y-%m-%d'):  # Formats acceptés
            try:
                return datetime.datetime.strptime(col.strip(), fmt).date()
            except ValueError:
                continue  # Essaie le format suivant
    return None  # En-tête non reconnu


def _lire_feuille(df):
    """Lit UNE feuille (DataFrame pandas). Retourne (donnees, postes, non_trouves, dates_invalides) où
    donnees = {poste_id: {date: Decimal}} et postes = {poste_id: Poste}."""
    import re  # Nettoyage des noms
    import pandas as pd  # Détection des cellules vides
    from accounts.models import Poste  # Postes SUPPER
    from inventaire.views_import import normaliser_nom_poste, trouver_poste_flexible  # Rapprochement des noms

    colonnes = df.columns.tolist()  # En-têtes
    col_poste, cols_dates = colonnes[0], colonnes[1:]  # 1re colonne = poste, les autres = dates
    mapping_dates, dates_invalides = {}, []  # Colonnes reconnues / refusées
    for col in cols_dates:
        d = _date_colonne(col)  # Essaie de lire la date
        if d:
            mapping_dates[col] = d  # Colonne valide
        else:
            dates_invalides.append(str(col))  # Colonne ignorée
    # Dictionnaire des postes SUPPER sous plusieurs clés (même logique que l'import classique)
    postes_db = {}
    for poste in Poste.objects.filter(is_active=True):
        nom = normaliser_nom_poste(poste.nom)  # Nom normalisé
        postes_db[nom] = poste
        sans_par = ' '.join(re.sub(r'\([^)]*\)', '', nom).split())  # Nom sans parenthèses
        if sans_par and sans_par != nom:
            postes_db[sans_par] = poste
        if poste.code:
            postes_db[normaliser_nom_poste(poste.code)] = poste  # Clé par code
    donnees, postes, non_trouves = {}, {}, []  # Résultats
    for _i, row in df.iterrows():
        nom_excel = str(row[col_poste]).strip()  # Nom du poste dans le fichier
        if not nom_excel or nom_excel == 'nan':
            continue  # Ligne vide
        poste = trouver_poste_flexible(nom_excel, postes_db)  # Poste SUPPER correspondant
        if not poste:
            non_trouves.append(nom_excel)  # Poste inconnu
            continue
        jours = donnees.setdefault(poste.pk, {})  # Montants du poste
        postes[poste.pk] = poste
        for col, d in mapping_dates.items():
            brut = row[col]  # Cellule
            if pd.isna(brut):
                continue  # Cellule vide
            try:
                montant = Decimal(str(brut).replace(',', '.').replace(' ', ''))  # Montant propre
            except InvalidOperation:
                continue  # Valeur illisible : ignorée
            if montant > 0:
                jours[d] = montant  # Garde seulement les montants positifs
    return donnees, postes, non_trouves, dates_invalides


def lire_excel(source):
    """Lit un fichier Excel : `source` est un DataFrame (une feuille) ou un dictionnaire {nom de feuille: DataFrame}
    (tous les onglets). Les montants d'un même poste provenant de plusieurs onglets sont regroupés.
    Retourne (donnees, postes, non_trouves, dates_invalides)."""
    feuilles = source.values() if isinstance(source, dict) else [source]  # Toutes les feuilles à lire
    donnees, postes, non_trouves, invalides = {}, {}, [], []  # Résultats regroupés
    for df in feuilles:
        if df is None or df.empty or len(df.columns) < 2:
            continue  # Feuille vide ou sans colonne de dates
        d, p, n, i = _lire_feuille(df)  # Lecture d'une feuille
        for pid, jours in d.items():
            donnees.setdefault(pid, {}).update(jours)  # Regroupe les jours du même poste
        postes.update(p)
        non_trouves.extend(x for x in n if x not in non_trouves)  # Sans doublons
        invalides.extend(x for x in i if x not in invalides)
    return donnees, postes, non_trouves, invalides


# ----------------------------------------------------------------------------------------------------------------------
# SÉRIES EN STOCK
# ----------------------------------------------------------------------------------------------------------------------
def series_disponibles(poste):
    """Séries en stock du poste, de la dernière recharge/réappro à la plus ancienne (ordre d'affichage)."""
    return list(SerieTicket.objects.filter(poste=poste, statut='stock').select_related('couleur')
                .order_by('-date_reception', '-numero_premier'))


def _fusionner_segments(segments):
    """Fusionne dans un même jour les plages contiguës d'une même couleur : [(couleur, p, d), ...]."""
    fusion = []  # Résultat
    for couleur, p, d in segments:
        if fusion and fusion[-1][0].pk == couleur.pk and fusion[-1][2] + 1 == p:
            fusion[-1] = (couleur, fusion[-1][1], d)  # Prolonge la plage précédente
        else:
            fusion.append((couleur, p, d))  # Nouvelle plage
    return fusion


# ----------------------------------------------------------------------------------------------------------------------
# SIMULATION
# ----------------------------------------------------------------------------------------------------------------------
def simuler(poste, montants, debut, fin, serie_ids, verrou=False):
    """Simule l'import d'un poste SANS rien écrire.
    montants = {date: Decimal}; [debut, fin] = période ; serie_ids = séries en stock choisies.
    Les tickets sont vendus jour après jour (dates croissantes), en puisant dans les séries choisies de la plus
    ancienne recharge à la plus récente. Retourne un dictionnaire détaillé (jours, besoin, stock choisi, ok...)."""
    existantes = set(RecetteJournaliere.objects.filter(poste=poste, date__range=(debut, fin))
                     .values_list('date', flat=True))  # Jours déjà saisis : jamais écrasés
    qs = SerieTicket.objects.filter(poste=poste, statut='stock', pk__in=list(serie_ids)).select_related('couleur')
    if verrou:
        qs = qs.select_for_update(of=('self',))  # Verrouille les séries pendant l'exécution
    pool = sorted(qs, key=lambda s: (s.date_reception, s.couleur_id, s.numero_premier))  # Plus ancien d'abord
    stock_choisi = Decimal(sum(s.nombre_tickets for s in pool)) * PRIX  # Valeur des séries choisies
    jours, besoin, erreurs = [], Decimal('0'), 0  # Résultats
    idx, courant, epuise = 0, None, False  # Curseur dans les séries / prochain numéro / stock épuisé
    for date in sorted(d for d in montants if debut <= d <= fin):  # Jours de la période, dans l'ordre
        montant = montants[date]
        ligne = {'date': date, 'montant': montant, 'tickets': 0, 'segments': [], 'statut': 'ok'}  # Ligne du jour
        if date in existantes:
            ligne['statut'] = 'existante'  # Recette déjà présente : ignorée
        elif montant % PRIX != 0:
            ligne['statut'] = 'non_multiple'  # Montant impossible avec des tickets de 500 F
            besoin += montant
            erreurs += 1
        else:
            besoin += montant  # Ce jour compte dans le besoin
            ligne['tickets'] = int(montant / PRIX)  # Nombre de tickets à vendre
            restant, segments = ligne['tickets'], []  # À couvrir / plages prises
            while restant > 0 and idx < len(pool):
                serie = pool[idx]  # Série en cours de consommation
                if courant is None:
                    courant = serie.numero_premier  # Début de la série
                prend = min(restant, serie.numero_dernier - courant + 1)  # Tickets pris dans cette série
                segments.append((serie.couleur, courant, courant + prend - 1))
                courant += prend
                restant -= prend
                if courant > serie.numero_dernier:
                    idx, courant = idx + 1, None  # Série épuisée : on passe à la suivante
            if restant > 0:
                ligne['statut'] = 'insuffisant'  # Pas assez de tickets dans les séries choisies
                ligne['manque'] = restant
                epuise = True
            ligne['segments'] = _fusionner_segments(segments)  # Plages du jour (fusion des contiguës)
        jours.append(ligne)
    a_importer = [j for j in jours if j['statut'] == 'ok']  # Jours qui seront créés
    manque = max(besoin - stock_choisi, Decimal('0'))  # Valeur manquante dans la sélection
    return {
        'jours': jours, 'besoin': besoin, 'stock_choisi': stock_choisi, 'manque': manque,
        'nb_a_importer': len(a_importer), 'nb_existantes': sum(1 for j in jours if j['statut'] == 'existante'),
        'nb_non_multiple': erreurs, 'insuffisant': epuise,
        'montant_a_importer': sum((j['montant'] for j in a_importer), Decimal('0')),
        'ok': bool(a_importer) and not epuise and erreurs == 0,  # Validation possible
    }


def completer_selection(poste, montants, debut, fin, serie_ids):
    """Ajoute, dans l'ordre d'affichage (de la plus récente à la plus ancienne), les séries suivantes jusqu'à ce que
    le stock choisi couvre le besoin. Retourne la nouvelle liste d'identifiants."""
    ids = [int(i) for i in serie_ids]  # Sélection actuelle
    besoin = simuler(poste, montants, debut, fin, ids)['besoin']  # Besoin de la période
    total = Decimal(sum(s.nombre_tickets for s in SerieTicket.objects.filter(pk__in=ids))) * PRIX  # Stock choisi
    for serie in series_disponibles(poste):
        if total >= besoin:
            break  # Le besoin est couvert
        if serie.pk not in ids:
            ids.append(serie.pk)  # On puise dans la série suivante
            total += Decimal(serie.nombre_tickets) * PRIX
    return ids


# ----------------------------------------------------------------------------------------------------------------------
# EXÉCUTION
# ----------------------------------------------------------------------------------------------------------------------
@transaction.atomic
def executer_poste(lot, poste, montants, debut, fin, serie_ids, user):
    """Crée les recettes du poste en consommant les séries choisies. Tout ou rien."""
    sim = simuler(poste, montants, debut, fin, serie_ids, verrou=True)  # Recalcul sous verrou
    if sim['nb_non_multiple']:
        raise ImportStockError(f"{poste.nom} : des montants ne sont pas des multiples de 500 F.")
    if sim['insuffisant']:
        raise ImportStockError(f"{poste.nom} : le stock choisi est insuffisant (manque {sim['manque']:,.0f} F).")
    if not sim['nb_a_importer']:
        raise ImportStockError(f"{poste.nom} : aucune recette à importer sur cette période.")
    stock, _c = GestionStock.objects.select_for_update().get_or_create(
        poste=poste, defaults={'valeur_monetaire': Decimal('0')})  # Stock global du poste
    recettes, total, nb_tickets, plages = [], Decimal('0'), 0, []  # Compteurs
    for j in sim['jours']:
        if j['statut'] != 'ok':
            continue  # Jours ignorés
        recette = RecetteJournaliere.objects.create(
            poste=poste, date=j['date'], montant_declare=j['montant'], chef_poste=user, modifiable_par_chef=False,
            observations=f"Importé Excel avec stock — lot #{lot.pk}")  # Recette du jour
        vendues = []  # Séries vendues ce jour
        for ordre, (couleur, p, d) in enumerate(j['segments'], 1):
            DetailVenteTicket.objects.create(recette=recette, couleur=couleur, numero_premier=p,
                                             numero_dernier=d, ordre=ordre)  # Détail de vente
            ok, msg, series = SerieTicket.consommer_serie(poste, couleur, p, d, recette)  # Séries -> vendues
            if not ok:
                raise ImportStockError(f"{poste.nom} {j['date']:%d/%m/%Y} : {msg}")
            vendues.extend(series)
            plages.append(f"{couleur.libelle_affichage} {p}-{d}")
        avant = stock.valeur_monetaire  # Stock avant la vente
        stock.valeur_monetaire = avant - j['montant']  # Stock après la vente
        stock.save()
        hist = HistoriqueStock.objects.create(
            poste=poste, type_mouvement='DEBIT', montant=j['montant'], nombre_tickets=j['tickets'],
            stock_avant=avant, stock_apres=stock.valeur_monetaire, effectue_par=user, reference_recette=recette,
            commentaire=f"Import avec stock (lot #{lot.pk}) — vente du {j['date']:%d/%m/%Y}")
        if vendues:
            hist.associer_series_tickets(vendues)  # Lien historique <-> séries vendues
        StockEvent.objects.create(
            poste=poste, event_type='VENTE', event_datetime=timezone.now(),
            montant_variation=-j['montant'], nombre_tickets_variation=-j['tickets'],
            stock_resultant=stock.valeur_monetaire, tickets_resultants=int(stock.valeur_monetaire / 500),
            effectue_par=user, reference_id=str(recette.pk), reference_type='RecetteJournaliere',
            metadata={'import_lot': lot.pk, 'date_recette': j['date'].isoformat(),
                      'series_vendues': [f"{c.libelle_affichage} {p}-{d}" for c, p, d in j['segments']]},
            commentaire=f"Import avec stock (lot #{lot.pk}) — vente du {j['date']:%d/%m/%Y}")
        recettes.append(recette.pk)
        total += j['montant']
        nb_tickets += j['tickets']
    lot.resultats[str(poste.pk)] = {  # Mémorise le résultat pour l'annulation et l'historique
        'poste': poste.nom, 'recette_ids': recettes, 'nb_recettes': len(recettes), 'montant': str(total),
        'nb_tickets': nb_tickets, 'debut': debut.isoformat(), 'fin': fin.isoformat(),
        'date_execution': timezone.now().isoformat(), 'par': getattr(user, 'nom_complet', str(user)),
        'annule': False}
    lot.save(update_fields=['resultats'])
    return lot.resultats[str(poste.pk)]


@transaction.atomic
def annuler_poste(lot, poste_id, user, motif):
    """Annule l'import d'un poste : supprime les recettes créées et remet les tickets en stock."""
    motif = (motif or '').strip()  # Motif obligatoire
    if len(motif) < MOTIF_MIN:
        raise ImportStockError("Le motif est obligatoire (au moins 5 caractères).")
    info = lot.resultats.get(str(poste_id))  # Résultat enregistré
    if not info or info.get('annule'):
        raise ImportStockError("Cet import de poste n'existe pas ou est déjà annulé.")
    from accounts.models import Poste  # Poste concerné
    poste = Poste.objects.get(pk=poste_id)
    stock, _c = GestionStock.objects.select_for_update().get_or_create(
        poste=poste, defaults={'valeur_monetaire': Decimal('0')})  # Stock du poste
    rendu, nb_tickets = Decimal('0'), 0  # Valeur et nombre de tickets remis en stock
    for rid in info['recette_ids']:
        recette = RecetteJournaliere.objects.filter(pk=rid).first()  # Recette importée
        if not recette:
            continue  # Déjà supprimée à la main
        for serie in SerieTicket.objects.select_for_update().filter(reference_recette=recette):
            serie.statut, serie.reference_recette, serie.date_utilisation = 'stock', None, None  # Redevient en stock
            serie.save()
            nb_tickets += serie.nombre_tickets
            _fusionner_voisins(serie)  # Évite la fragmentation du stock
        montant = recette.montant_declare  # Valeur rendue
        HistoriqueStock.objects.filter(reference_recette=recette).update(reference_recette=None)  # Dissocie
        avant = stock.valeur_monetaire
        stock.valeur_monetaire = avant + montant
        stock.save()
        HistoriqueStock.objects.create(
            poste=poste, type_mouvement='CREDIT', montant=montant, nombre_tickets=int(montant / 500),
            stock_avant=avant, stock_apres=stock.valeur_monetaire, effectue_par=user,
            commentaire=f"Annulation import (lot #{lot.pk}) du {recette.date:%d/%m/%Y} — {motif}"[:500])
        StockEvent.objects.create(
            poste=poste, event_type='REGULARISATION', event_datetime=timezone.now(),
            montant_variation=montant, nombre_tickets_variation=int(montant / 500),
            stock_resultant=stock.valeur_monetaire, tickets_resultants=int(stock.valeur_monetaire / 500),
            effectue_par=user, reference_id=str(lot.pk), reference_type='ImportRecettesStock',
            metadata={'annulation_import': lot.pk, 'date_recette': recette.date.isoformat()},
            commentaire=f"Annulation import (lot #{lot.pk}) — {motif}")
        rendu += montant
        recette.delete()  # Supprime la recette (et ses détails de vente)
    info.update({'annule': True, 'motif_annulation': motif, 'annule_par': getattr(user, 'nom_complet', str(user)),
                 'date_annulation': timezone.now().isoformat()})  # Trace de l'annulation
    lot.resultats[str(poste_id)] = info
    lot.save(update_fields=['resultats'])
    return rendu, nb_tickets
