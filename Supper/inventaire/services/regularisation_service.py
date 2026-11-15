# inventaire/services/regularisation_service.py
# RÉGULARISATION DE L'HISTORIQUE avec DATE D'EFFET LIBRE (phase 2 de la date d'effet).
# Sert à corriger l'HistoriqueStock (source du CSP) quand il diffère des séries réellement détenues :
#   - CREDIT : un chargement/stock manquant dans l'historique ;
#   - DEBIT  : un crédit en trop (série supprimée, transférée ou jamais créée).
# Ne touche JAMAIS aux séries (SerieTicket) : seul le CSP / l'historique est corrigé.
# Convention : date d'effet D = instant D 00:00:00 -> la correction fait partie du stock de début du jour D.

from decimal import Decimal  # Montants exacts

from django.db import transaction  # Tout ou rien
from django.utils import timezone  # Horodatage

from inventaire.models import GestionStock, HistoriqueStock, StockEvent  # Modèles de stock
from inventaire.services.date_effet import datetime_effet, verifier_date_effet, DateEffetError  # Date d'effet

PRIX = Decimal('500')  # Valeur d'un ticket en FCFA


class RegularisationError(Exception):
    """Régularisation refusée (message lisible par l'utilisateur)."""


@transaction.atomic
def regulariser(poste, sens, nombre_tickets, date_effet, motif, user):
    """Écrit une correction d'historique datée de `date_effet`. Retourne l'HistoriqueStock créé."""
    if sens not in ('CREDIT', 'DEBIT'):
        raise RegularisationError("Sens invalide : choisissez Crédit ou Débit.")
    if not isinstance(nombre_tickets, int) or nombre_tickets < 1:
        raise RegularisationError("Le nombre de tickets doit être un entier positif.")
    motif = (motif or '').strip()
    if len(motif) < 10:
        raise RegularisationError("Le motif est obligatoire (10 caractères minimum) : il sera conservé dans l'historique.")
    try:
        verifier_date_effet(poste, date_effet)  # Pas de futur, pas de mois signé
    except DateEffetError as exc:
        raise RegularisationError(str(exc))
    valeur = Decimal(nombre_tickets) * PRIX  # Valeur en FCFA
    effet = datetime_effet(date_effet)  # Instant comptable
    signe = -1 if sens == 'DEBIT' else 1
    stock, _c = GestionStock.objects.select_for_update().get_or_create(poste=poste, defaults={'valeur_monetaire': Decimal('0')})
    avant = stock.valeur_monetaire
    if sens == 'DEBIT' and avant < valeur:
        raise RegularisationError(f"Débit impossible : le stock actuel du poste ({avant:,.0f} FCFA) est inférieur à {valeur:,.0f} FCFA.")
    stock.valeur_monetaire = avant + signe * valeur  # Nouveau stock courant
    stock.save()
    commentaire = f"Régularisation d'historique (effet {date_effet:%d/%m/%Y}) : {motif}"[:500]
    hist = HistoriqueStock.objects.create(
        poste=poste, type_mouvement=sens, type_stock='regularisation', montant=valeur, nombre_tickets=nombre_tickets,
        stock_avant=avant, stock_apres=stock.valeur_monetaire, effectue_par=user, commentaire=commentaire,
        date_mouvement=effet, est_correction=True)  # date_saisie = vraie date de saisie (automatique)
    StockEvent.objects.create(
        poste=poste, event_type='AJUSTEMENT', event_datetime=effet,
        montant_variation=signe * valeur, nombre_tickets_variation=signe * nombre_tickets,
        stock_resultant=stock.valeur_monetaire, tickets_resultants=int(stock.valeur_monetaire / 500),
        effectue_par=user, reference_id=str(hist.pk), reference_type='RegularisationHistorique',
        metadata={'date_effet': str(date_effet), 'motif': motif}, commentaire=commentaire)
    return hist
