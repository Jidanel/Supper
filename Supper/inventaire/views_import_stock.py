# inventaire/views_import_stock.py
# Vues de l'IMPORT DE RECETTES AVEC STOCKS : téléversement du fichier, simulation par poste, validation, historique.
# Accès : administrateur, Service Informatique, Service Émissions et Recouvrement.

import datetime  # Dates
import logging  # Journal technique
from decimal import Decimal  # Montants

import pandas as pd  # Lecture du fichier Excel
from django.contrib import messages  # Messages à l'utilisateur
from django.contrib.auth.decorators import login_required  # Accès authentifié
from django.shortcuts import render, redirect, get_object_or_404  # Raccourcis Django
from django.views.decorators.http import require_POST  # Annulation : POST uniquement

from accounts.models import Poste  # Postes
from common.utils import log_user_action  # Journalisation des actions
from inventaire.models_import_stock import ImportRecettesStock  # Lots d'import
from inventaire.services import import_stock_service as iss  # Logique métier

logger = logging.getLogger('supper')


def _refuser(request):
    """Message + redirection quand l'utilisateur n'a pas le droit d'utiliser cet outil."""
    messages.error(request, "Vous n'avez pas la permission d'importer des recettes avec stocks.")
    return redirect('common:dashboard')


def _date(texte, defaut):
    """Lit une date AAAA-MM-JJ ; retourne `defaut` si le texte est vide ou invalide."""
    try:
        return datetime.date.fromisoformat((texte or '').strip())
    except ValueError:
        return defaut


def _montants(lot, poste_id):
    """Montants d'un poste dans le lot : {date: Decimal}."""
    return {datetime.date.fromisoformat(d): Decimal(m) for d, m in lot.donnees.get(str(poste_id), {}).items()}


@login_required
def import_stock_nouveau(request):
    """Étape 1 : téléversement du fichier Excel + période (date début / date fin)."""
    if not iss.peut_importer_stock(request.user):
        return _refuser(request)
    if request.method == 'POST':
        fichier = request.FILES.get('fichier_excel')  # Fichier envoyé
        debut = _date(request.POST.get('date_debut'), None)
        fin = _date(request.POST.get('date_fin'), None)
        if not fichier or not fichier.name.lower().endswith(('.xlsx', '.xls')):
            messages.error(request, "Choisissez un fichier Excel (.xlsx ou .xls).")
        elif not debut or not fin or debut > fin:
            messages.error(request, "Indiquez une période valide (date de début ≤ date de fin).")
        else:
            try:
                donnees, postes, non_trouves, invalides = iss.lire_excel(pd.read_excel(fichier, sheet_name=None))  # Lit TOUS les onglets
            except Exception as e:  # Fichier illisible
                logger.error(f"Import stock : lecture impossible : {e}", exc_info=True)
                messages.error(request, f"Fichier illisible : {e}")
                return redirect('inventaire:import_stock_nouveau')
            # On ne garde que les jours de la période
            filtre = {str(pid): {d.isoformat(): str(m) for d, m in jours.items() if debut <= d <= fin}
                      for pid, jours in donnees.items()}
            filtre = {pid: jours for pid, jours in filtre.items() if jours}  # Postes sans donnée dans la période exclus
            if not filtre:
                toutes = [d for jours in donnees.values() for d in jours]  # Toutes les dates lues pour des postes reconnus
                if not postes:  # Aucun poste du fichier n'a été reconnu dans SUPPER
                    messages.error(request, "Aucun poste du fichier n'a été reconnu dans SUPPER. "
                                            f"Exemples de noms non reconnus : {', '.join(non_trouves[:5])}")
                elif toutes:  # Postes reconnus mais aucune date dans la période choisie
                    messages.error(request, f"Aucun montant dans la période choisie ({debut:%d/%m/%Y} → {fin:%d/%m/%Y}). "
                                            f"Le fichier contient des montants du {min(toutes):%d/%m/%Y} au {max(toutes):%d/%m/%Y}.")
                else:  # Postes reconnus mais aucune date/montant lisible
                    messages.error(request, "Aucun montant lisible dans le fichier (vérifiez les en-têtes de dates, ex. 01/01/26).")
            else:
                lot = ImportRecettesStock.objects.create(
                    fichier_nom=fichier.name, date_debut=debut, date_fin=fin, donnees=filtre,
                    postes_non_trouves=non_trouves, cree_par=request.user)  # Lot créé
                try:
                    log_user_action(request.user, "Import recettes avec stocks - fichier lu",
                                    f"Lot #{lot.pk} | {fichier.name} | {debut} → {fin} | postes: {len(filtre)}", request)
                except Exception:
                    logger.warning("log_user_action indisponible")
                if invalides:
                    messages.warning(request, f"Colonnes ignorées (pas des dates) : {', '.join(invalides[:10])}")
                return redirect('inventaire:import_stock_simulation', pk=lot.pk)
    return render(request, 'inventaire/import_stock_form.html', {'title': "Import des recettes avec stocks"})


@login_required
def import_stock_simulation(request, pk):
    """Étape 2 : simulation par poste (choix des séries, ajustement des jours) puis validation poste par poste."""
    if not iss.peut_importer_stock(request.user):
        return _refuser(request)
    lot = get_object_or_404(ImportRecettesStock, pk=pk)  # Lot en cours
    postes = {p.pk: p for p in Poste.objects.filter(pk__in=[int(i) for i in lot.donnees])}  # Postes du lot
    post = request.method == 'POST'
    action = request.POST.get('action', '') if post else ''  # Bouton cliqué
    lignes = []  # Une entrée par poste pour le gabarit
    a_valider = []  # Postes à valider (ids)
    if action.startswith('valider_') and action != 'valider_coches':
        a_valider = [int(action.split('_', 1)[1])]  # Bouton « Valider ce poste »
    elif action == 'valider_coches':
        a_valider = [int(i) for i in request.POST.getlist('choisis')]  # Postes cochés
    for pid in sorted(postes, key=lambda i: postes[i].nom):
        poste = postes[pid]
        montants = _montants(lot, pid)  # Montants lus
        inclus = (not post) or (str(pid) in request.POST.getlist('inclus'))  # Poste retenu ?
        debut = _date(request.POST.get(f'debut_{pid}'), lot.date_debut) if post else lot.date_debut
        fin = _date(request.POST.get(f'fin_{pid}'), lot.date_fin) if post else lot.date_fin
        ids = [int(i) for i in request.POST.getlist(f'series_{pid}') if i.isdigit()] if post else []  # Séries choisies
        if post and action == f'suivante_{pid}':
            ids = iss.completer_selection(poste, montants, debut, fin, ids)  # Puise dans les séries suivantes
        deja = lot.resultats.get(str(pid))  # Résultat si déjà validé
        erreur, resultat = None, None
        if pid in a_valider and inclus and not (deja and not deja.get('annule')):
            try:
                resultat = iss.executer_poste(lot, poste, montants, debut, fin, ids, request.user)  # Validation
                messages.success(request, f"{poste.nom} : {resultat['nb_recettes']} recette(s) importée(s) "
                                          f"({Decimal(resultat['montant']):,.0f} F).")
                try:
                    log_user_action(request.user, "Import recettes avec stocks - validation",
                                    f"Lot #{lot.pk} | {poste.nom} | {resultat['nb_recettes']} recettes | "
                                    f"{resultat['montant']} F | {debut} → {fin}", request)
                except Exception:
                    logger.warning("log_user_action indisponible")
            except iss.ImportStockError as e:
                erreur = str(e)
                messages.error(request, erreur)
            except Exception as e:  # Erreur inattendue : tout est annulé pour ce poste
                logger.error(f"Import stock {poste.nom}: {e}", exc_info=True)
                erreur = f"Erreur : {e}"
                messages.error(request, f"{poste.nom} : {erreur}")
        deja = lot.resultats.get(str(pid))  # Relit après validation éventuelle
        valide = bool(deja and not deja.get('annule'))  # Poste déjà importé et non annulé
        sim = None if (valide or not inclus) else iss.simuler(poste, montants, debut, fin, ids)  # Simulation
        series = iss.series_disponibles(poste) if (inclus and not valide) else []  # Séries proposées
        lignes.append({
            'poste': poste, 'inclus': inclus, 'debut': debut, 'fin': fin, 'sim': sim, 'valide': valide,
            'resultat': deja, 'series': [{'s': s, 'choisie': s.pk in ids} for s in series],
            'nb_jours_fichier': len(montants), 'erreur': erreur})
    return render(request, 'inventaire/import_stock_simulation.html', {
        'title': "Simulation de l'import", 'lot': lot, 'lignes': lignes})


@login_required
def import_stock_historique(request):
    """Liste des lots d'import avec le résultat de chaque poste et le bouton d'annulation."""
    if not iss.peut_importer_stock(request.user):
        return _refuser(request)
    lots = []
    for lot in ImportRecettesStock.objects.select_related('cree_par')[:50]:
        lots.append({'lot': lot, 'postes': sorted(
            ({'id': pid, **info} for pid, info in lot.resultats.items()), key=lambda x: x['poste'])})
    return render(request, 'inventaire/import_stock_historique.html', {'title': "Historique des imports", 'lots': lots})


@login_required
@require_POST
def import_stock_annuler(request, pk, poste_id):
    """Annule l'import d'un poste : les recettes disparaissent, les tickets retournent en stock."""
    if not iss.peut_importer_stock(request.user):
        return _refuser(request)
    lot = get_object_or_404(ImportRecettesStock, pk=pk)
    try:
        rendu, nb = iss.annuler_poste(lot, poste_id, request.user, request.POST.get('motif'))
        messages.success(request, f"Import annulé : {nb} ticket(s) remis en stock ({rendu:,.0f} F).")
        try:
            log_user_action(request.user, "Import recettes avec stocks - annulation",
                            f"Lot #{lot.pk} | poste {poste_id} | {rendu} F remis en stock", request)
        except Exception:
            logger.warning("log_user_action indisponible")
    except iss.ImportStockError as e:
        messages.error(request, str(e))
    return redirect('inventaire:import_stock_historique')
