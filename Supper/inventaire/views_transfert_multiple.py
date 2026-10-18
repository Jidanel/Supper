# ===================================================================
# inventaire/views_transfert_multiple.py - TRANSFERT MULTIPLE DE SÉRIES
# Application SUPPER - Suivi des Péages et Pesages Routiers
# Chemin: inventaire/views_transfert_multiple.py
#
# VERSION CORRIGÉE - Suppression de poste_origine_transfert (n'existe pas)
# ===================================================================

import logging
from datetime import date
from decimal import Decimal
import uuid

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse

from accounts.models import Poste
from .models import (
    SerieTicket, CouleurTicket, GestionStock,
    HistoriqueStock, StockEvent
)
from .forms import DetailSerieTransfertFormSet, TransfertMultipleBaseForm
from common.utils import log_user_action

logger = logging.getLogger('supper')


# ===================================================================
# FONCTIONS UTILITAIRES
# ===================================================================

def is_admin_user(user):
    """Vérifie si l'utilisateur est administrateur."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return getattr(user, 'habilitation', None) in [
        'admin_principal', 'coord_psrr', 'serv_info'
    ]


def peut_transferer_stock(user):
    """Vérifie si l'utilisateur peut transférer du stock."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return getattr(user, 'peut_transferer_stock_peage', False)


def user_has_acces_tous_postes(user):
    """Vérifie si l'utilisateur a accès à tous les postes."""
    HABILITATIONS_MULTI_POSTES = [
        'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission',
        'chef_ag', 'serv_controle', 'serv_ordre', 'imprimerie',
        'cisop_peage', 'cisop_pesage', 'focal_regional', 'chef_service',
    ]

    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if getattr(user, 'acces_tous_postes', False):
        return True
    return getattr(user, 'habilitation', None) in HABILITATIONS_MULTI_POSTES


def check_poste_access(user, poste):
    """Vérifie si l'utilisateur a accès à un poste."""
    if user_has_acces_tous_postes(user):
        return True
    poste_affectation = getattr(user, 'poste_affectation', None)
    if isinstance(poste, int):
        return poste_affectation and poste_affectation.id == poste
    return poste_affectation and poste_affectation.id == poste.id


def get_user_short_description(user):
    """Description courte pour les logs."""
    if not user:
        return "Utilisateur inconnu"
    nom = getattr(user, 'nom_complet', None) or user.username
    habilitation = getattr(user, 'habilitation', 'inconnu')
    return f"{nom} ({habilitation})"


def generer_numero_bordereau():
    """Génère un numéro de bordereau unique."""
    timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
    unique_id = str(uuid.uuid4())[:6].upper()
    return f"TRF-{timestamp}-{unique_id}"


# ===================================================================
# SERVICE D'EXÉCUTION DU TRANSFERT MULTIPLE
# ===================================================================

def executer_transfert_multiple(poste_origine, poste_destination, series_data, user, commentaire=""):
    """
    Exécute le transfert de PLUSIEURS séries en une seule transaction.

    CORRECTION V4: Après création des historiques, lie chaque série
    destination à son historique source (hist_reception) pour
    traçabilité dans le compte d'emploi.

    Args:
        poste_origine: Poste émetteur
        poste_destination: Poste destinataire
        series_data: Liste de dict avec {couleur, numero_premier, numero_dernier, serie_id}
        user: Utilisateur effectuant le transfert
        commentaire: Commentaire optionnel

    Returns:
        tuple (success, message, numero_bordereau, series_transferees)
    """
    timestamp = timezone.now()
    numero_bordereau = generer_numero_bordereau()

    logger.info(
        f"🔄 DÉBUT TRANSFERT MULTIPLE | {get_user_short_description(user)} | "
        f"{poste_origine.nom} → {poste_destination.nom} | "
        f"{len(series_data)} séries | Bordereau: {numero_bordereau}"
    )

    try:
        with transaction.atomic():
            series_transferees = []
            montant_total = Decimal('0')
            nombre_tickets_total = 0

            # Récupérer les stocks
            stock_origine, _ = GestionStock.objects.get_or_create(
                poste=poste_origine,
                defaults={'valeur_monetaire': Decimal('0')}
            )
            stock_origine_avant = stock_origine.valeur_monetaire

            stock_destination, _ = GestionStock.objects.get_or_create(
                poste=poste_destination,
                defaults={'valeur_monetaire': Decimal('0')}
            )
            stock_destination_avant = stock_destination.valeur_monetaire

            # ============================================================
            # TRAITEMENT DE CHAQUE SÉRIE
            # ============================================================
            for idx, serie_info in enumerate(series_data):
                couleur = serie_info['couleur']
                numero_premier = serie_info['numero_premier']
                numero_dernier = serie_info['numero_dernier']

                nombre_tickets = numero_dernier - numero_premier + 1
                montant = Decimal(nombre_tickets) * Decimal('500')

                logger.info(
                    f"  📦 Série {idx + 1}: {couleur.libelle_affichage} "
                    f"#{numero_premier}-{numero_dernier} ({nombre_tickets} tickets = {montant:,.0f} FCFA)"
                )

                # Trouver la série source
                serie_source = SerieTicket.objects.filter(
                    poste=poste_origine,
                    couleur=couleur,
                    numero_premier__lte=numero_premier,
                    numero_dernier__gte=numero_dernier,
                    statut='stock'
                ).first()

                if not serie_source:
                    raise ValueError(
                        f"Série {couleur.libelle_affichage} #{numero_premier}-{numero_dernier} "
                        f"introuvable ou non disponible au poste {poste_origine.nom}"
                    )

                # ============================================================
                # CAS 1: Transfert de la série COMPLÈTE
                # ============================================================
                if (serie_source.numero_premier == numero_premier and
                    serie_source.numero_dernier == numero_dernier):

                    # Marquer comme transférée
                    serie_source.statut = 'transfere'
                    serie_source.date_utilisation = timestamp.date()
                    serie_source.poste_destination_transfert = poste_destination
                    serie_source.commentaire = (
                        f"Transférée vers {poste_destination.nom} le {timestamp.strftime('%d/%m/%Y')} "
                        f"(bordereau {numero_bordereau})"
                    )
                    serie_source.save()

                    # Créer la nouvelle série au poste destination
                    serie_destination = SerieTicket.objects.create(
                        poste=poste_destination,
                        couleur=couleur,
                        numero_premier=numero_premier,
                        numero_dernier=numero_dernier,
                        nombre_tickets=nombre_tickets,
                        valeur_monetaire=montant,
                        statut='stock',
                        type_entree='transfert_recu',
                        date_reception=timestamp,
                        responsable_reception=user,
                        commentaire=f"Reçue de {poste_origine.nom} (bordereau {numero_bordereau})"
                    )

                # ============================================================
                # CAS 2: Transfert PARTIEL (découpe de série)
                # ============================================================
                else:
                    # Sauvegarder les bornes originales et l'historique source
                    orig_premier = serie_source.numero_premier
                    orig_dernier = serie_source.numero_dernier
                    source_historique = serie_source.historique_source

                    # Partie AVANT la plage transférée
                    if numero_premier > orig_premier:
                        reste_avant = SerieTicket.objects.create(
                            poste=poste_origine,
                            couleur=couleur,
                            numero_premier=orig_premier,
                            numero_dernier=numero_premier - 1,
                            nombre_tickets=(numero_premier - 1) - orig_premier + 1,
                            valeur_monetaire=Decimal((numero_premier - 1) - orig_premier + 1) * Decimal('500'),
                            statut='stock',
                            type_entree=serie_source.type_entree,
                            date_reception=serie_source.date_reception,
                            responsable_reception=serie_source.responsable_reception,
                            commentaire=f"Reste après transfert partiel (bordereau {numero_bordereau})",
                            historique_source=source_historique,
                        )

                    # Partie APRÈS la plage transférée
                    if numero_dernier < orig_dernier:
                        reste_apres = SerieTicket.objects.create(
                            poste=poste_origine,
                            couleur=couleur,
                            numero_premier=numero_dernier + 1,
                            numero_dernier=orig_dernier,
                            nombre_tickets=orig_dernier - (numero_dernier + 1) + 1,
                            valeur_monetaire=Decimal(orig_dernier - (numero_dernier + 1) + 1) * Decimal('500'),
                            statut='stock',
                            type_entree=serie_source.type_entree,
                            date_reception=serie_source.date_reception,
                            responsable_reception=serie_source.responsable_reception,
                            commentaire=f"Reste après transfert partiel (bordereau {numero_bordereau})",
                            historique_source=source_historique,
                        )

                    # Marquer la série source comme transférée
                    serie_source.statut = 'transfere'
                    serie_source.numero_premier = numero_premier
                    serie_source.numero_dernier = numero_dernier
                    serie_source.nombre_tickets = nombre_tickets
                    serie_source.valeur_monetaire = montant
                    serie_source.date_utilisation = timestamp.date()
                    serie_source.poste_destination_transfert = poste_destination
                    serie_source.commentaire = (
                        f"Transférée (partiel) vers {poste_destination.nom} "
                        f"(bordereau {numero_bordereau})"
                    )
                    serie_source.save()

                    # Créer la nouvelle série au poste destination
                    serie_destination = SerieTicket.objects.create(
                        poste=poste_destination,
                        couleur=couleur,
                        numero_premier=numero_premier,
                        numero_dernier=numero_dernier,
                        nombre_tickets=nombre_tickets,
                        valeur_monetaire=montant,
                        statut='stock',
                        type_entree='transfert_recu',
                        date_reception=timestamp,
                        responsable_reception=user,
                        commentaire=f"Reçue de {poste_origine.nom} (bordereau {numero_bordereau})"
                    )

                series_transferees.append({
                    'couleur': couleur,
                    'numero_premier': numero_premier,
                    'numero_dernier': numero_dernier,
                    'nombre_tickets': nombre_tickets,
                    'montant': montant,
                    'serie_destination': serie_destination
                })

                montant_total += montant
                nombre_tickets_total += nombre_tickets

            # ============================================================
            # MISE À JOUR DES STOCKS GLOBAUX
            # ============================================================
            stock_origine.valeur_monetaire -= montant_total
            stock_origine.nombre_tickets = int(stock_origine.valeur_monetaire / 500)
            stock_origine.derniere_mise_a_jour = timestamp
            stock_origine.save()

            stock_destination.valeur_monetaire += montant_total
            stock_destination.nombre_tickets = int(stock_destination.valeur_monetaire / 500)
            stock_destination.derniere_mise_a_jour = timestamp
            stock_destination.save()

            logger.info(
                f"  📊 Stock {poste_origine.code}: {stock_origine_avant:,.0f} → "
                f"{stock_origine.valeur_monetaire:,.0f} FCFA (-{montant_total:,.0f})"
            )
            logger.info(
                f"  📊 Stock {poste_destination.code}: {stock_destination_avant:,.0f} → "
                f"{stock_destination.valeur_monetaire:,.0f} FCFA (+{montant_total:,.0f})"
            )

            # ============================================================
            # CRÉATION DES HISTORIQUES
            # ============================================================
            details_series = [
                {
                    'couleur': s['couleur'].libelle_affichage,
                    'couleur_id': s['couleur'].id,
                    'premier': s['numero_premier'],
                    'dernier': s['numero_dernier'],
                    'tickets': s['nombre_tickets'],
                    'montant': str(s['montant'])
                }
                for s in series_transferees
            ]

            # Historique DÉBIT (poste origine - cession)
            hist_cession = HistoriqueStock.objects.create(
                poste=poste_origine,
                type_mouvement='DEBIT',
                type_stock='reapprovisionnement',
                montant=montant_total,
                nombre_tickets=nombre_tickets_total,
                stock_avant=stock_origine_avant,
                stock_apres=stock_origine.valeur_monetaire,
                effectue_par=user,
                poste_origine=poste_origine,
                poste_destination=poste_destination,
                numero_bordereau=numero_bordereau,
                commentaire=commentaire or f"Transfert multiple de {len(series_transferees)} série(s)",
                details_approvisionnement={
                    'type': 'transfert_multiple',
                    'nb_series': len(series_transferees),
                    'series': details_series
                }
            )

            # Historique CRÉDIT (poste destination - réception)
            hist_reception = HistoriqueStock.objects.create(
                poste=poste_destination,
                type_mouvement='CREDIT',
                type_stock='reapprovisionnement',
                montant=montant_total,
                nombre_tickets=nombre_tickets_total,
                stock_avant=stock_destination_avant,
                stock_apres=stock_destination.valeur_monetaire,
                effectue_par=user,
                poste_origine=poste_origine,
                poste_destination=poste_destination,
                numero_bordereau=numero_bordereau,
                commentaire=commentaire or f"Réception multiple de {len(series_transferees)} série(s)",
                details_approvisionnement={
                    'type': 'transfert_multiple',
                    'nb_series': len(series_transferees),
                    'series': details_series
                }
            )

            # Associer les séries aux historiques (ManyToMany existant)
            for s in series_transferees:
                hist_cession.series_tickets_associees.add(s['serie_destination'])
                hist_reception.series_tickets_associees.add(s['serie_destination'])

            # === NOUVEAU V4: Lier chaque série destination à hist_reception ===
            for s in series_transferees:
                s['serie_destination'].historique_source = hist_reception
                s['serie_destination'].save(update_fields=['historique_source'])

            # ============================================================
            # CRÉATION DES ÉVÉNEMENTS DE STOCK
            # ============================================================
            StockEvent.objects.create(
                poste=poste_origine,
                event_type='TRANSFERT_OUT',
                event_datetime=timestamp,
                montant_variation=-montant_total,
                nombre_tickets_variation=-nombre_tickets_total,
                stock_resultant=stock_origine.valeur_monetaire,
                tickets_resultants=stock_origine.nombre_tickets,
                effectue_par=user,
                reference_id=numero_bordereau,
                reference_type='TransfertMultiple',
                metadata={
                    'poste_destination': poste_destination.code,
                    'nb_series': len(series_transferees)
                },
                commentaire=f"Transfert multiple vers {poste_destination.nom}"
            )

            StockEvent.objects.create(
                poste=poste_destination,
                event_type='TRANSFERT_IN',
                event_datetime=timestamp,
                montant_variation=montant_total,
                nombre_tickets_variation=nombre_tickets_total,
                stock_resultant=stock_destination.valeur_monetaire,
                tickets_resultants=stock_destination.nombre_tickets,
                effectue_par=user,
                reference_id=numero_bordereau,
                reference_type='TransfertMultiple',
                metadata={
                    'poste_origine': poste_origine.code,
                    'nb_series': len(series_transferees)
                },
                commentaire=f"Réception multiple de {poste_origine.nom}"
            )

            logger.info(
                f"✅ TRANSFERT MULTIPLE RÉUSSI | {get_user_short_description(user)} | "
                f"Bordereau: {numero_bordereau} | {len(series_transferees)} séries | "
                f"{nombre_tickets_total} tickets = {montant_total:,.0f} FCFA"
            )

            return (
                True,
                f"Transfert effectué avec succès. {len(series_transferees)} série(s), "
                f"{nombre_tickets_total} tickets ({montant_total:,.0f} FCFA). "
                f"Bordereau: {numero_bordereau}",
                numero_bordereau,
                series_transferees
            )

    except Exception as e:
        logger.error(
            f"❌ ERREUR TRANSFERT MULTIPLE | {get_user_short_description(user)} | "
            f"Erreur: {str(e)}",
            exc_info=True
        )
        return False, f"Erreur lors du transfert: {str(e)}", None, []


# ===================================================================
# VUES DE TRANSFERT MULTIPLE
# ===================================================================

@login_required
def saisie_transfert_multiple(request):
    """
    Saisie des séries à transférer (interface similaire au chargement multiple).

    PERMISSIONS: peut_transferer_stock_peage
    """
    user = request.user

    # Vérification des permissions
    if not peut_transferer_stock(user):
        messages.error(request, "Vous n'avez pas la permission de transférer du stock.")
        return redirect('common:dashboard')

    # Récupérer les postes de la session
    postes_data = request.session.get('transfert_tickets')

    if not postes_data:
        messages.error(request, "Veuillez d'abord sélectionner les postes.")
        return redirect('inventaire:selection_postes_transfert_tickets')

    poste_origine = get_object_or_404(Poste, id=postes_data['origine_id'])
    poste_destination = get_object_or_404(Poste, id=postes_data['destination_id'])

    # Vérifier l'accès au poste d'origine
    if not user_has_acces_tous_postes(user) and not check_poste_access(user, poste_origine):
        messages.error(request, "Vous n'avez pas accès au poste d'origine.")
        if 'transfert_tickets' in request.session:
            del request.session['transfert_tickets']
        return redirect('inventaire:selection_postes_transfert_tickets')

    # Récupérer le stock et les séries disponibles
    stock_origine = GestionStock.objects.filter(poste=poste_origine).first()

    series_disponibles = SerieTicket.objects.filter(
        poste=poste_origine,
        statut='stock'
    ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')

    # Grouper par couleur
    series_par_couleur = {}
    for serie in series_disponibles:
        couleur_code = serie.couleur.code_normalise
        if couleur_code not in series_par_couleur:
            series_par_couleur[couleur_code] = {
                'couleur': serie.couleur,
                'series': [],
                'total_tickets': 0,
                'valeur_totale': Decimal('0')
            }

        series_par_couleur[couleur_code]['series'].append(serie)
        series_par_couleur[couleur_code]['total_tickets'] += serie.nombre_tickets
        series_par_couleur[couleur_code]['valeur_totale'] += serie.valeur_monetaire

    if request.method == 'POST':
        formset = DetailSerieTransfertFormSet(request.POST, prefix='series')
        base_form = TransfertMultipleBaseForm(request.POST)

        if formset.is_valid() and base_form.is_valid():
            # Collecter les séries valides
            series_a_transferer = []
            erreurs = []

            for idx, form in enumerate(formset):
                if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                    couleur_id = form.cleaned_data.get('couleur_id')
                    numero_premier = form.cleaned_data.get('numero_premier')
                    numero_dernier = form.cleaned_data.get('numero_dernier')

                    if couleur_id and numero_premier and numero_dernier:
                        # Récupérer la couleur
                        try:
                            couleur = CouleurTicket.objects.get(id=couleur_id)
                        except CouleurTicket.DoesNotExist:
                            erreurs.append(f"Série {idx + 1}: Couleur introuvable")
                            continue

                        # Vérifier la disponibilité
                        disponible, msg, _ = SerieTicket.verifier_disponibilite_serie_complete(
                            poste_origine, couleur, numero_premier, numero_dernier
                        )

                        if not disponible:
                            erreurs.append(f"Série {idx + 1}: {msg}")
                            continue

                        # Vérifier qu'aucun ticket n'a été vendu
                        tickets_vendus = SerieTicket.objects.filter(
                            couleur=couleur,
                            statut='vendu',
                            numero_premier__lte=numero_dernier,
                            numero_dernier__gte=numero_premier
                        ).exists()

                        if tickets_vendus:
                            erreurs.append(
                                f"Série {idx + 1}: Des tickets ont été vendus dans cette plage"
                            )
                            continue

                        series_a_transferer.append({
                            'couleur': couleur,
                            'numero_premier': numero_premier,
                            'numero_dernier': numero_dernier,
                            'nombre_tickets': numero_dernier - numero_premier + 1,
                            'montant': Decimal(numero_dernier - numero_premier + 1) * Decimal('500')
                        })

            if erreurs:
                for err in erreurs:
                    messages.error(request, err)
            elif not series_a_transferer:
                messages.error(request, "Veuillez sélectionner au moins une série à transférer.")
            else:
                # Stocker en session pour confirmation
                request.session['transfert_multiple_series'] = [
                    {
                        'couleur_id': s['couleur'].id,
                        'couleur_libelle': s['couleur'].libelle_affichage,
                        'numero_premier': s['numero_premier'],
                        'numero_dernier': s['numero_dernier'],
                        'nombre_tickets': s['nombre_tickets'],
                        'montant': str(s['montant'])
                    }
                    for s in series_a_transferer
                ]
                request.session['transfert_multiple_commentaire'] = base_form.cleaned_data.get('commentaire', '')

                log_user_action(
                    user,
                    "TRANSFERT_MULTIPLE_SAISIE",
                    f"Préparation transfert: {len(series_a_transferer)} séries de "
                    f"{poste_origine.nom} vers {poste_destination.nom}",
                    request
                )

                return redirect('inventaire:confirmation_transfert_multiple')
        else:
            messages.error(request, "Erreur dans le formulaire. Vérifiez les données saisies.")
    else:
        formset = DetailSerieTransfertFormSet(prefix='series')
        base_form = TransfertMultipleBaseForm()

    context = {
        'formset': formset,
        'base_form': base_form,
        'poste_origine': poste_origine,
        'poste_destination': poste_destination,
        'stock_origine': stock_origine,
        'series_par_couleur': series_par_couleur,
        'title': 'Saisie des Séries à Transférer'
    }

    return render(request, 'inventaire/saisie_transfert_multiple.html', context)


@login_required
def confirmation_transfert_multiple(request):
    """
    Confirmation du transfert multiple avec récapitulatif.
    """
    user = request.user

    if not peut_transferer_stock(user):
        messages.error(request, "Vous n'avez pas la permission de transférer du stock.")
        return redirect('common:dashboard')

    postes_data = request.session.get('transfert_tickets')
    series_data = request.session.get('transfert_multiple_series')
    commentaire = request.session.get('transfert_multiple_commentaire', '')

    if not postes_data or not series_data:
        messages.error(request, "Données de transfert manquantes.")
        return redirect('inventaire:selection_postes_transfert_tickets')

    poste_origine = get_object_or_404(Poste, id=postes_data['origine_id'])
    poste_destination = get_object_or_404(Poste, id=postes_data['destination_id'])

    # Reconstituer les séries avec les objets couleur
    series = []
    for s in series_data:
        couleur = get_object_or_404(CouleurTicket, id=s['couleur_id'])
        series.append({
            'couleur': couleur,
            'numero_premier': s['numero_premier'],
            'numero_dernier': s['numero_dernier'],
            'nombre_tickets': s['nombre_tickets'],
            'montant': Decimal(s['montant'])
        })

    # Calculer les totaux
    montant_total = sum(s['montant'] for s in series)
    nombre_tickets_total = sum(s['nombre_tickets'] for s in series)

    # Récupérer les stocks actuels
    stock_origine, _ = GestionStock.objects.get_or_create(
        poste=poste_origine,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    stock_destination, _ = GestionStock.objects.get_or_create(
        poste=poste_destination,
        defaults={'valeur_monetaire': Decimal('0')}
    )

    stock_origine_apres = stock_origine.valeur_monetaire - montant_total
    stock_destination_apres = stock_destination.valeur_monetaire + montant_total

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'confirmer':
            # Exécuter le transfert
            success, message, numero_bordereau, series_transferees = executer_transfert_multiple(
                poste_origine=poste_origine,
                poste_destination=poste_destination,
                series_data=series,
                user=user,
                commentaire=commentaire
            )

            if success:
                # Nettoyer la session
                del request.session['transfert_tickets']
                del request.session['transfert_multiple_series']
                if 'transfert_multiple_commentaire' in request.session:
                    del request.session['transfert_multiple_commentaire']

                log_user_action(
                    user,
                    "TRANSFERT_MULTIPLE_EXECUTE",
                    f"Transfert exécuté: {len(series_transferees)} séries, "
                    f"{nombre_tickets_total} tickets ({montant_total:,.0f} FCFA) "
                    f"de {poste_origine.nom} vers {poste_destination.nom} "
                    f"(bordereau: {numero_bordereau})",
                    request
                )

                messages.success(request, f"✅ {message}")
                return redirect('inventaire:liste_bordereaux')
            else:
                messages.error(request, f"❌ {message}")
                return redirect('inventaire:saisie_transfert_multiple')

        elif action == 'annuler':
            # Nettoyer la session
            if 'transfert_tickets' in request.session:
                del request.session['transfert_tickets']
            if 'transfert_multiple_series' in request.session:
                del request.session['transfert_multiple_series']
            if 'transfert_multiple_commentaire' in request.session:
                del request.session['transfert_multiple_commentaire']

            messages.info(request, "Transfert annulé.")
            return redirect('inventaire:selection_postes_transfert_tickets')

    context = {
        'poste_origine': poste_origine,
        'poste_destination': poste_destination,
        'series': series,
        'montant_total': montant_total,
        'nombre_tickets_total': nombre_tickets_total,
        'commentaire': commentaire,
        'stock_origine_avant': stock_origine.valeur_monetaire,
        'stock_origine_apres': stock_origine_apres,
        'stock_destination_avant': stock_destination.valeur_monetaire,
        'stock_destination_apres': stock_destination_apres,
        'title': 'Confirmation du Transfert Multiple'
    }

    return render(request, 'inventaire/confirmation_transfert_multiple.html', context)