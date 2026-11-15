# Règle métier : toute correction (gel, dégel, annulation de gel, suppression administrative, modification de série)
# prend effet au 1er jour du mois (00:00 heure locale). Seuls les chargements de l'Imprimerie Nationale et les
# transferts directs entre postes sont des mouvements réels datés du jour.
# Cette migration ramène au 1er du mois les corrections déjà saisies avec une date d'effet en cours de mois
# (hors mois déjà signé pour le poste concerné, qui ne doit jamais changer).

import datetime  # Dates

from django.db import migrations  # Migrations
from django.utils import timezone  # Fuseau horaire

PREFIXES = ("Gel (banque de gel)", "Dégel (banque de gel)", "Annulation du gel",
            "Suppression administrative", "Modification série")  # Corrections concernées


def _debut_mois_local(t):
    """1er jour du mois de `t` (heure locale) à 00:00:00 local."""
    local = timezone.localtime(t)
    return timezone.make_aware(datetime.datetime(local.year, local.month, 1, 0, 0, 0))


def _signe(Cloture, poste_id, instant):
    """Le mois de `instant` est-il signé pour ce poste ?"""
    mois = timezone.localtime(instant).strftime('%Y-%m')
    return Cloture.objects.filter(poste_id=poste_id, mois=mois, statut='signe').exists()


def appliquer(apps, schema_editor):
    Hist = apps.get_model('inventaire', 'HistoriqueStock')
    Event = apps.get_model('inventaire', 'StockEvent')
    Banque = apps.get_model('inventaire', 'BanqueGel')
    Cloture = apps.get_model('inventaire', 'ClotureMensuelle')
    Serie = apps.get_model('inventaire', 'SerieTicket')
    for h in Hist.objects.filter(est_correction=True, type_stock='regularisation').iterator():
        if not (h.commentaire or '').startswith(PREFIXES):
            continue  # Régularisations manuelles et autres : non concernées
        ancien = h.date_mouvement
        nouveau = _debut_mois_local(ancien)
        if nouveau == ancien or _signe(Cloture, h.poste_id, ancien):
            continue  # Déjà au 1er du mois, ou mois signé : on ne touche pas
        Event.objects.filter(poste_id=h.poste_id, event_datetime=ancien).update(event_datetime=nouveau)  # Événement jumeau
        for s in h.series_tickets_associees.all():  # Séries créées par un dégel : entrent au début du mois
            if s.date_reception == ancien:
                Serie.objects.filter(pk=s.pk).update(date_reception=nouveau)
        Hist.objects.filter(pk=h.pk).update(date_mouvement=nouveau)
    for bg in Banque.objects.all().iterator():  # Dates d'effet affichées dans la banque de gel
        champs = {}
        if bg.date_effet_gel and bg.date_effet_gel.day != 1 and not _signe(Cloture, bg.poste_origine_id, timezone.make_aware(
                datetime.datetime(bg.date_effet_gel.year, bg.date_effet_gel.month, 1, 12))):
            champs['date_effet_gel'] = bg.date_effet_gel.replace(day=1)
        if bg.date_effet_degel and bg.date_effet_degel.day != 1 and bg.poste_destination_id and not _signe(
                Cloture, bg.poste_destination_id, timezone.make_aware(datetime.datetime(bg.date_effet_degel.year, bg.date_effet_degel.month, 1, 12))):
            champs['date_effet_degel'] = bg.date_effet_degel.replace(day=1)
        if champs:
            Banque.objects.filter(pk=bg.pk).update(**champs)


class Migration(migrations.Migration):

    dependencies = [("inventaire", "0025_corriger_heure_date_effet")]

    operations = [migrations.RunPython(appliquer, migrations.RunPython.noop)]
