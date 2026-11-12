# inventaire/views_gel.py
# Vues de la BANQUE DE GEL : page de gel / dégel, historique et annulation d'un gel.
# Accès : administrateur, Service Informatique, Service Émissions et Recouvrement.

import datetime  # Dates d'effet
import logging  # Journal technique

from django.contrib import messages  # Messages à l'utilisateur
from django.contrib.auth.decorators import login_required  # Accès authentifié
from django.db.models import Sum  # Totaux par couleur
from django.shortcuts import render, redirect, get_object_or_404  # Raccourcis Django
from django.utils import timezone  # Date du jour
from django.views.decorators.http import require_POST  # Annulation : POST uniquement

from common.permissions import get_postes_accessibles  # Postes accessibles à l'utilisateur
from common.utils import log_user_action  # Journalisation des actions
from inventaire.models import SerieTicket, CouleurTicket  # Séries et couleurs
from inventaire.models_banque_gel import BanqueGel, StatutGel  # Banque de gel
from inventaire.services import gel_service as gs  # Logique métier
from inventaire.views_permutation import _lignes  # Lecture des lignes « couleur + plage » du formulaire

logger = logging.getLogger('supper')


def _refuser(request):
    """Message + redirection quand l'utilisateur n'a pas le droit d'utiliser la banque de gel."""
    messages.error(request, "Vous n'avez pas la permission d'utiliser la banque de gel.")
    return redirect('common:dashboard')


def _date_effet(texte):
    """Lit une date AAAA-MM-JJ ; retourne la date du jour si le champ est vide ou invalide."""
    try:
        return datetime.date.fromisoformat((texte or '').strip())
    except ValueError:
        return timezone.localdate()


@login_required
def banque_gel(request):
    """Page unique : stock du poste à geler, banque de gel disponible et formulaire de dégel."""
    user = request.user
    if not gs.peut_gerer_gel(user):
        return _refuser(request)  # Contrôle d'accès côté vue (en plus du menu)
    postes = get_postes_accessibles(user, type_poste='peage').order_by('nom')
    donnees = request.POST if request.method == 'POST' else request.GET
    source = postes.filter(pk=donnees.get('poste') or 0).first()  # Poste dont on veut geler le stock
    contexte = {'postes': postes, 'source': source, 'couleurs': CouleurTicket.objects.all().order_by('libelle_affichage'),
                'lignes_gel': [], 'lignes_degel': [], 'motif': donnees.get('motif', ''),
                'date_effet': donnees.get('date_effet') or timezone.localdate().isoformat(),
                'destination_id': donnees.get('destination', ''), 'title': 'Banque de gel'}

    if request.method == 'POST':
        action = donnees.get('action')  # 'geler' ou 'degeler'
        date_effet = _date_effet(donnees.get('date_effet'))
        try:
            if action == 'geler':
                contexte['lignes_gel'], plages = _lignes(donnees, 'gel')
                if not source:
                    raise ValueError("Choisissez d'abord le poste à geler.")
                creees = gs.geler(source, plages, date_effet, donnees.get('motif', ''), user)
                _tracer(user, request, "GEL_SERIES", f"{source.nom} : {len(creees)} plage(s) gelée(s)")
                messages.success(request, f"{sum(c.nombre_tickets for c in creees)} tickets gelés depuis {source.nom} "
                                          f"(valeur : {sum(c.montant for c in creees)} FCFA).")
                return redirect(f"{request.path}?poste={source.pk}")
            if action == 'degeler':
                contexte['lignes_degel'], plages = _lignes(donnees, 'degel')
                destination = postes.filter(pk=donnees.get('destination') or 0).first()
                if not destination:
                    raise ValueError("Choisissez le poste qui reçoit les séries dégelées.")
                degeles = gs.degeler(destination, plages, date_effet, donnees.get('motif', ''), user)
                _tracer(user, request, "DEGEL_SERIES", f"{destination.nom} : {len(degeles)} plage(s) dégelée(s)")
                messages.success(request, f"{sum(d.nombre_tickets for d in degeles)} tickets dégelés vers {destination.nom} "
                                          f"(valeur : {sum(d.montant for d in degeles)} FCFA).")
                return redirect(request.path)
        except (ValueError, gs.GelError) as exc:  # Erreur de saisie ou règle métier
            messages.error(request, str(exc))

    if not contexte['lignes_gel']:
        contexte['lignes_gel'] = [{'couleur': '', 'plage': ''}]
    if not contexte['lignes_degel']:
        contexte['lignes_degel'] = [{'couleur': '', 'plage': ''}]
    if source:  # Séries en stock du poste (à geler)
        contexte['series_stock'] = SerieTicket.objects.filter(poste=source, statut='stock').select_related(
            'couleur').order_by('couleur__libelle_affichage', 'numero_premier')
    banque = gs.disponible_en_banque()
    contexte['banque'] = banque
    contexte['banque_totaux'] = banque.values('couleur__libelle_affichage').annotate(
        t=Sum('nombre_tickets')).order_by('couleur__libelle_affichage')
    contexte['banque_total_tickets'] = sum(b.nombre_tickets for b in banque)
    return render(request, 'inventaire/banque_gel.html', contexte)


def _tracer(user, request, action, details):
    """Journalise l'action sans jamais bloquer l'opération."""
    try:
        log_user_action(user, action, details, request)
    except Exception:
        logger.exception("Journalisation impossible (%s)", action)


@login_required
def banque_gel_historique(request):
    """Historique complet de la banque de gel (filtres : statut, poste, couleur)."""
    user = request.user
    if not gs.peut_gerer_gel(user):
        return _refuser(request)
    qs = BanqueGel.objects.select_related('couleur', 'poste_origine', 'poste_destination', 'gele_par', 'degele_par')
    statut, poste_id = request.GET.get('statut') or '', request.GET.get('poste') or ''
    if statut in StatutGel.values:
        qs = qs.filter(statut=statut)
    if poste_id.isdigit():  # Poste d'origine OU destinataire
        from django.db.models import Q
        qs = qs.filter(Q(poste_origine_id=poste_id) | Q(poste_destination_id=poste_id))
    return render(request, 'inventaire/banque_gel_historique.html', {
        'lignes': qs[:500], 'statut': statut, 'poste_id': poste_id,
        'postes': get_postes_accessibles(user, type_poste='peage').order_by('nom'), 'title': 'Historique de la banque de gel'})


@login_required
@require_POST
def banque_gel_annuler(request, pk):
    """Annule le gel d'une ligne encore gelée : la série retourne au poste d'origine."""
    if not gs.peut_gerer_gel(request.user):
        return _refuser(request)
    bg = get_object_or_404(BanqueGel, pk=pk)
    try:
        gs.annuler_gel(bg, request.POST.get('motif_annulation', ''), request.user)
    except gs.GelError as exc:
        messages.error(request, str(exc))
    else:
        _tracer(request.user, request, "ANNULATION_GEL_SERIES", f"Gel #{pk} annulé ({bg})")
        messages.success(request, f"Gel #{pk} annulé : la série est revenue au poste {bg.poste_origine.nom}.")
    return redirect('inventaire:banque_gel')
