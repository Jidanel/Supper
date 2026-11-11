# -*- coding: utf-8 -*-
"""
Détection des « recharges fantômes » : chargements Imprimerie Nationale
dont les séries ont été supprimées (suppression administrative du stock).

Le chargement (HistoriqueStock CREDIT) reste dans l'historique pour la
traçabilité comptable, mais il ne doit plus être proposé en livraison.
"""
from inventaire.models import SerieTicket  # Modèle des séries de tickets


def _serie_existe(hist, entree):
    """True si la série décrite par `entree` (dict JSON) existe encore."""
    serie_id = entree.get('serie_id')                     # Identifiant enregistré au chargement
    if serie_id:                                          # Cas normal : on teste l'id
        return SerieTicket.objects.filter(id=serie_id).exists()
    premier = entree.get('numero_premier')                # Sinon : repli sur couleur + numéros
    dernier = entree.get('numero_dernier')
    couleur_id = entree.get('couleur_id')
    if premier and dernier and couleur_id:
        return SerieTicket.objects.filter(                # Recouvrement de plage au même poste
            poste_id=hist.poste_id, couleur_id=couleur_id,
            numero_premier__lte=dernier, numero_dernier__gte=premier,
        ).exists()
    return None                                           # Indéterminé


def recharge_est_fantome(hist):
    """True si TOUTES les séries du chargement ont été supprimées."""
    details = hist.details_approvisionnement or {}        # JSON d'approvisionnement
    entrees = details.get('series') or []                 # Séries décrites au chargement
    verdicts = [_serie_existe(hist, e) for e in entrees]  # True / False / None par série
    if verdicts:
        if any(v is True for v in verdicts):              # Au moins une série existe encore
            return False
        if all(v is False for v in verdicts):             # Toutes supprimées
            return True
        return False                                      # Indéterminé : on garde (prudence)
    # Pas de JSON exploitable : on regarde les liens en base
    if hist.series_tickets_associees.exists():
        return False
    if SerieTicket.objects.filter(historique_source=hist).exists():
        return False
    if hist.numero_premier_ticket and hist.numero_dernier_ticket and hist.couleur_principale_id:
        return not SerieTicket.objects.filter(
            poste_id=hist.poste_id, couleur_id=hist.couleur_principale_id,
            numero_premier__lte=hist.numero_dernier_ticket,
            numero_dernier__gte=hist.numero_premier_ticket,
        ).exists()
    return False                                          # Données anciennes sans trace : on garde


def ids_recharges_fantomes(queryset):
    """Retourne la liste des ids de recharges fantômes à exclure du queryset."""
    return [h.id for h in queryset if recharge_est_fantome(h)]
