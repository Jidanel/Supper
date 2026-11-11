# -*- coding: utf-8 -*-
"""
Export des postes par commande et par série de tickets déjà livrés
(chargements Imprimerie Nationale).
"""
import csv                                              # Écriture du fichier CSV
from django.contrib import messages                     # Messages utilisateur
from django.contrib.auth.decorators import login_required  # Accès réservé aux connectés
from django.http import HttpResponse                    # Réponse HTTP (CSV)
from django.shortcuts import render, redirect           # Rendu de template / redirection
from django.utils.translation import gettext as _       # Traduction FR/EN

from inventaire.models_commandes import CommandeTickets, LivraisonTickets  # Modèles commandes
from inventaire.views_commandes import peut_gerer_livraisons               # Contrôle de permission existant
from common.utils import log_user_action                                   # Journalisation des actions
from inventaire.services_recharges import recharge_est_fantome            # Ignore les chargements supprimés

# Types de stock considérés comme « chargement Imprimerie Nationale »
TYPES_IMPRIMERIE = ['imprimerie_nationale', 'imprimerie']


def _extraire_series(hist):
    """Retourne la liste des séries d'un historique (3 sources, par ordre de fiabilité)."""
    details = hist.details_approvisionnement or {}               # JSON d'approvisionnement
    series = []                                                  # Résultat
    for s in details.get('series', []) or []:                    # 1) JSON détaillé
        series.append({
            'couleur': s.get('couleur_nom', ''),
            'premier': s.get('numero_premier'),
            'dernier': s.get('numero_dernier'),
            'nombre': s.get('nombre_tickets') or 0,
        })
    if series:                                                   # Si trouvé, on s'arrête
        return series
    for st in hist.series_tickets_associees.all():               # 2) Séries liées en base
        series.append({
            'couleur': st.couleur.libelle_affichage if st.couleur_id else '',
            'premier': st.numero_premier, 'dernier': st.numero_dernier,
            'nombre': st.nombre_tickets,
        })
    if series:
        return series
    if hist.numero_premier_ticket and hist.numero_dernier_ticket:  # 3) Champs simples
        series.append({
            'couleur': hist.couleur_principale.libelle_affichage if hist.couleur_principale_id else '',
            'premier': hist.numero_premier_ticket,
            'dernier': hist.numero_dernier_ticket,
            'nombre': hist.nombre_tickets or 0,
        })
    return series


def _construire_lignes(commande_id=None, poste_id=None, date_debut=None, date_fin=None):
    """Construit une ligne par (commande, poste, série livrée)."""
    qs = LivraisonTickets.objects.select_related(
        'commande', 'poste', 'poste__region'
    ).prefetch_related(
        'historiques_associes', 'historiques_associes__couleur_principale',
        'historiques_associes__series_tickets_associees',
        'historiques_associes__series_tickets_associees__couleur',
    ).order_by('commande_id', 'poste__nom', 'date_livraison')   # Tri commande > poste > date
    if commande_id:
        qs = qs.filter(commande_id=commande_id)                 # Filtre commande
    if poste_id:
        qs = qs.filter(poste_id=poste_id)                       # Filtre poste
    if date_debut:
        qs = qs.filter(date_livraison__gte=date_debut)          # Date livraison min
    if date_fin:
        qs = qs.filter(date_livraison__lte=date_fin)            # Date livraison max
    lignes = []                                                 # Résultat final
    for liv in qs:
        for hist in liv.historiques_associes.all():             # Chaque chargement lié
            if hist.type_stock not in TYPES_IMPRIMERIE:         # Uniquement Imprimerie Nationale
                continue
            if recharge_est_fantome(hist):                      # Chargement dont les séries ont été supprimées
                continue
            for s in _extraire_series(hist):                    # Chaque série du chargement
                lignes.append({
                    'commande': liv.commande,
                    'poste': liv.poste,
                    'region': getattr(liv.poste.region, 'nom', '') if liv.poste.region_id else '',
                    'couleur': s['couleur'], 'premier': s['premier'],
                    'dernier': s['dernier'], 'nombre': s['nombre'],
                    'montant': s['nombre'] * 500,               # Ticket = 500 FCFA
                    'date_chargement': hist.date_mouvement,
                    'date_livraison': liv.date_livraison,
                })
    return lignes


@login_required
def export_series_livrees(request):
    """Page + export CSV (?export=csv) des séries livrées par commande et par poste."""
    if not peut_gerer_livraisons(request.user):                 # Contrôle d'accès
        messages.error(request, _("Vous n'avez pas la permission d'accéder à cette fonctionnalité."))
        return redirect('common:dashboard')

    g = request.GET                                              # Paramètres de filtre
    lignes = _construire_lignes(
        g.get('commande') or None, g.get('poste') or None,
        g.get('date_debut') or None, g.get('date_fin') or None)

    if g.get('export') == 'csv':                                 # Export CSV demandé
        log_user_action(request.user, "Export CSV séries livrées",
                        f"{len(lignes)} ligne(s)", request)      # Trace dans le journal
        rep = HttpResponse(content_type='text/csv; charset=utf-8')
        rep['Content-Disposition'] = 'attachment; filename="series_livrees_par_commande.csv"'
        rep.write('﻿')                                      # BOM unique pour Excel
        w = csv.writer(rep, delimiter=';')
        w.writerow([_('Commande'), _('Région'), _('Poste'), _('Code poste'), _('Couleur'),
                    _('Premier ticket'), _('Dernier ticket'), _('Nombre de tickets'),
                    _('Montant (FCFA)'), _('Date chargement'), _('Date livraison')])
        for l in lignes:
            w.writerow([l['commande'], l['region'], l['poste'].nom, l['poste'].code,
                        l['couleur'], l['premier'], l['dernier'], l['nombre'], l['montant'],
                        l['date_chargement'].strftime('%d/%m/%Y') if l['date_chargement'] else '',
                        l['date_livraison'].strftime('%d/%m/%Y') if l['date_livraison'] else ''])
        return rep

    log_user_action(request.user, "Consultation séries livrées",
                    f"{len(lignes)} ligne(s)", request)          # Trace de la consultation
    return render(request, 'inventaire/commandes/livraisons/export_series.html', {
        'lignes': lignes,
        'commandes': CommandeTickets.objects.all().order_by('-id'),
        'filtres': g,
        'total_tickets': sum(l['nombre'] for l in lignes),
        'total_montant': sum(l['montant'] for l in lignes),
        'title': _("Séries livrées par commande"),
    })
