# inventaire/services/gel_service.py
# Service métier de la BANQUE DE GEL (gel et dégel de séries de tickets).
#   - geler()         : séries en stock d'un poste -> banque de gel (le stock du poste diminue)
#   - degeler()       : séries de la banque -> stock d'un autre poste (son stock augmente)
#   - annuler_gel()   : remet une série gelée (non dégelée) dans son poste d'origine
# Chaque opération est atomique et journalisée dans HistoriqueStock + StockEvent. Le gel et le dégel ne figurent PAS
# dans les comptes d'emploi : la date d'effet d'un dégel indique le mois à partir duquel le poste détient les séries.

import datetime  # Dates d'effet
from decimal import Decimal  # Montants exacts

from django.db import transaction  # Atomicité : tout ou rien
from django.utils import timezone  # Horodatage

from inventaire.models import SerieTicket, GestionStock, HistoriqueStock, StockEvent  # Modèles de stock
from inventaire.models_banque_gel import BanqueGel, StatutGel  # Banque de gel
from inventaire.services.permutation_service import (  # Outils partagés avec la permutation
    _segments, _isoler, _fusionner_voisins, lire_plage, MOTIF_MIN)

PRIX = Decimal('500')  # Valeur d'un ticket en FCFA


class GelError(Exception):
    """Erreur métier : l'opération est impossible (message lisible par l'utilisateur)."""


def peut_gerer_gel(user):
    """Autorisés : administrateur, Service Informatique, Service Émissions et Recouvrement."""
    if not user or not user.is_authenticated:
        return False  # Anonyme refusé
    if user.is_superuser:
        return True  # Superutilisateur toujours autorisé
    return getattr(user, 'habilitation', None) in ('admin_principal', 'serv_info', 'serv_emission')


def _motif(motif):
    """Vérifie et nettoie le motif obligatoire."""
    motif = (motif or '').strip()
    if len(motif) < MOTIF_MIN:
        raise GelError("Le motif est obligatoire (au moins 5 caractères).")
    return motif


def _date_reception_degel(bg, date_effet):
    """Date de réception donnée aux séries dégelées : la plus ancienne entre leur réception d'origine et le 1er jour
    du mois d'effet. Ainsi elles font partie du stock du poste dès le début du mois (aucune ligne « gel/dégel »
    n'apparaît dans le compte d'emploi : tout se passe comme si le poste les avait toujours détenues)."""
    debut_mois = timezone.make_aware(datetime.datetime(date_effet.year, date_effet.month, 1, 0, 0, 0))
    origine = bg.date_reception_origine
    return min(origine, debut_mois) if origine else debut_mois


def _mouvement(poste, user, sens, valeur, nombre, commentaire, type_evenement, reference_id, metadata):
    """Met à jour le stock du poste et écrit l'historique + l'événement de stock. Retourne l'HistoriqueStock créé.
    sens = 'DEBIT' (gel) ou 'CREDIT' (dégel)."""
    stock, _cree = GestionStock.objects.select_for_update().get_or_create(
        poste=poste, defaults={'valeur_monetaire': Decimal('0')})  # Stock du poste (verrouillé)
    avant = stock.valeur_monetaire
    signe = -1 if sens == 'DEBIT' else 1
    stock.valeur_monetaire = avant + signe * valeur  # Nouveau stock en FCFA
    stock.save()
    hist = HistoriqueStock.objects.create(
        poste=poste, type_mouvement=sens, type_stock='regularisation', montant=valeur, nombre_tickets=nombre,
        stock_avant=avant, stock_apres=stock.valeur_monetaire, effectue_par=user, commentaire=commentaire[:500])
    StockEvent.objects.create(
        poste=poste, event_type=type_evenement, event_datetime=timezone.now(),
        montant_variation=signe * valeur, nombre_tickets_variation=signe * nombre,
        stock_resultant=stock.valeur_monetaire, tickets_resultants=int(stock.valeur_monetaire / 500),  # Recalculés par save()
        effectue_par=user, reference_id=str(reference_id), reference_type='BanqueGel',
        metadata=metadata, commentaire=commentaire)
    return hist


@transaction.atomic
def geler(poste, plages, date_effet, motif, user):
    """Gèle des plages en stock d'un poste : [(couleur, premier, dernier), ...]. Retourne la liste des lignes BanqueGel."""
    motif = _motif(motif)
    if not plages:
        raise GelError("Indiquez au moins une série à geler.")
    if date_effet > timezone.localdate():
        raise GelError("La date d'effet ne peut pas être dans le futur.")
    creees = []
    for couleur, p, d in plages:
        if p > d or p < 1:
            raise GelError(f"Plage invalide : {couleur} {p}-{d}.")
        segments = _segments(poste, couleur, 'stock', p, d, verrou=True)  # Doit être entièrement en stock
        if segments is None:
            raise GelError(f"Les tickets {couleur} {p} à {d} ne sont pas tous en stock dans {poste.nom}.")
        for ligne, x, y in segments:
            ligne = _isoler(ligne, x, y)  # Isole exactement la plage à geler
            bg = BanqueGel.objects.create(
                couleur=ligne.couleur, numero_premier=x, numero_dernier=y, nombre_tickets=y - x + 1,
                poste_origine=poste, date_reception_origine=ligne.date_reception,
                type_entree_origine=ligne.type_entree or '', historique_source_id=ligne.historique_source_id,
                date_effet_gel=date_effet, gele_par=user, motif_gel=motif)
            ligne.delete()  # La série quitte le stock du poste
            creees.append(bg)
    valeur = sum((Decimal(b.nombre_tickets) * PRIX for b in creees), Decimal('0'))
    nombre = sum(b.nombre_tickets for b in creees)
    _mouvement(poste, user, 'DEBIT', valeur, nombre,
               f"Gel (banque de gel) : {', '.join(f'{b.couleur} {b.numero_premier}-{b.numero_dernier}' for b in creees)}"
               f" — {motif}", 'GEL', creees[0].pk,
               {'gel_ids': [b.pk for b in creees], 'date_effet': date_effet.isoformat()})
    return creees


@transaction.atomic
def degeler(destination, selections, date_effet, motif, user):
    """Dégèle des plages de la banque vers le stock du poste `destination`.
    selections = [(couleur, premier, dernier), ...] : chaque plage doit être entièrement dans la banque (statut gelée).
    Un dégel partiel découpe la ligne de la banque ; le reste demeure gelé."""
    motif = _motif(motif)
    if not selections:
        raise GelError("Indiquez au moins une série à dégeler.")
    if date_effet > timezone.localdate():
        raise GelError("La date d'effet ne peut pas être dans le futur.")
    degeles = []
    for couleur, p, d in selections:
        courant = p  # Prochain ticket à couvrir
        lignes = BanqueGel.objects.select_for_update().filter(
            couleur=couleur, statut=StatutGel.GELE, numero_premier__lte=d, numero_dernier__gte=p).order_by('numero_premier')
        for bg in lignes:
            if bg.numero_premier > courant:
                break  # Trou dans la banque
            x, y = max(courant, bg.numero_premier), min(d, bg.numero_dernier)
            if bg.numero_premier < x:  # Reste gelé avant la plage dégelée
                BanqueGel.objects.create(**_copie(bg, bg.numero_premier, x - 1))
            if bg.numero_dernier > y:  # Reste gelé après la plage dégelée
                BanqueGel.objects.create(**_copie(bg, y + 1, bg.numero_dernier))
            bg.numero_premier, bg.numero_dernier, bg.nombre_tickets = x, y, y - x + 1
            bg.statut, bg.poste_destination = StatutGel.DEGELE, destination
            bg.date_effet_degel, bg.degele_par, bg.motif_degel = date_effet, user, motif
            bg.date_operation_degel = timezone.now()
            bg.save()
            degeles.append(bg)
            courant = y + 1
            if courant > d:
                break
        if courant <= d:
            raise GelError(f"Les tickets {couleur} {p} à {d} ne sont pas tous disponibles dans la banque de gel.")
    valeur = sum((Decimal(b.nombre_tickets) * PRIX for b in degeles), Decimal('0'))
    nombre = sum(b.nombre_tickets for b in degeles)
    hist = _mouvement(destination, user, 'CREDIT', valeur, nombre,
                      f"Dégel (banque de gel) : {', '.join(f'{b.couleur} {b.numero_premier}-{b.numero_dernier}' for b in degeles)}"
                      f" — {motif}", 'DEGEL', degeles[0].pk,
                      {'gel_ids': [b.pk for b in degeles], 'date_effet': date_effet.isoformat()})
    for bg in degeles:  # Les séries entrent dans le stock du poste destinataire
        s = SerieTicket.objects.create(
            poste=destination, couleur=bg.couleur, numero_premier=bg.numero_premier, numero_dernier=bg.numero_dernier,
            nombre_tickets=bg.nombre_tickets, valeur_monetaire=Decimal(bg.nombre_tickets) * PRIX, statut='stock',
            type_entree='regularisation', responsable_reception=user, historique_source=hist)
        SerieTicket.objects.filter(pk=s.pk).update(date_reception=_date_reception_degel(bg, date_effet))  # auto_now_add : on la fixe
        hist.series_tickets_associees.add(s)
        _fusionner_voisins(SerieTicket.objects.get(pk=s.pk))  # Évite la fragmentation du stock
    return degeles


def _copie(bg, premier, dernier):
    """Champs pour créer une ligne de banque identique à `bg` mais sur une autre plage (découpage)."""
    return dict(couleur=bg.couleur, numero_premier=premier, numero_dernier=dernier, nombre_tickets=dernier - premier + 1,
                poste_origine=bg.poste_origine, date_reception_origine=bg.date_reception_origine,
                type_entree_origine=bg.type_entree_origine, historique_source_id=bg.historique_source_id,
                date_effet_gel=bg.date_effet_gel, gele_par=bg.gele_par, motif_gel=bg.motif_gel, statut=StatutGel.GELE)


@transaction.atomic
def annuler_gel(bg, motif, user):
    """Annule le gel d'une ligne encore gelée : la série retourne dans son poste d'origine."""
    motif = _motif(motif)
    bg = BanqueGel.objects.select_for_update().get(pk=bg.pk)
    if bg.statut != StatutGel.GELE:
        raise GelError("Cette série n'est plus dans la banque de gel (déjà dégelée ou annulée).")
    if SerieTicket.objects.filter(poste=bg.poste_origine, couleur=bg.couleur, numero_premier__lte=bg.numero_dernier,
                                  numero_dernier__gte=bg.numero_premier).exists():
        raise GelError("Annulation impossible : ces numéros existent déjà dans le poste d'origine.")
    hist = _mouvement(bg.poste_origine, user, 'CREDIT', Decimal(bg.nombre_tickets) * PRIX, bg.nombre_tickets,
                      f"Annulation du gel #{bg.pk} ({bg.couleur} {bg.numero_premier}-{bg.numero_dernier}) — {motif}",
                      'DEGEL', bg.pk, {'annulation_gel': bg.pk})
    s = SerieTicket.objects.create(
        poste=bg.poste_origine, couleur=bg.couleur, numero_premier=bg.numero_premier, numero_dernier=bg.numero_dernier,
        nombre_tickets=bg.nombre_tickets, valeur_monetaire=Decimal(bg.nombre_tickets) * PRIX, statut='stock',
        type_entree=bg.type_entree_origine or 'regularisation', responsable_reception=user, historique_source=hist)
    if bg.date_reception_origine:  # Restitue la date de réception d'origine
        SerieTicket.objects.filter(pk=s.pk).update(date_reception=bg.date_reception_origine)
    hist.series_tickets_associees.add(s)
    _fusionner_voisins(SerieTicket.objects.get(pk=s.pk))
    bg.statut, bg.motif_degel, bg.degele_par = StatutGel.ANNULE, f"Gel annulé : {motif}", user
    bg.date_operation_degel = timezone.now()
    bg.save()
    return bg


def disponible_en_banque():
    """Séries gelées disponibles, triées par couleur puis numéro."""
    return BanqueGel.objects.filter(statut=StatutGel.GELE).select_related('couleur', 'poste_origine').order_by(
        'couleur__libelle_affichage', 'numero_premier')
