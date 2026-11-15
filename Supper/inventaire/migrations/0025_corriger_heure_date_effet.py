# Correction de la migration 0024 : les corrections déjà présentes en base avaient été datées « 1er du mois à 00:00 UTC »,
# soit 01:00 heure du Cameroun, donc APRÈS le début du 1er du mois : le CSP ne les comptait pas dans le stock de début.
# On les ramène à 00:00 heure locale (= 23:00 UTC la veille), comme le font les corrections créées par l'application.

import datetime  # Décalage d'une heure

from django.db import migrations  # Migrations

PREFIXES = ("Gel (banque de gel)", "Dégel (banque de gel)", "Annulation du gel",
            "Suppression administrative", "Modification série")  # Corrections concernées


def corriger(apps, schema_editor):
    Hist = apps.get_model('inventaire', 'HistoriqueStock')
    Event = apps.get_model('inventaire', 'StockEvent')
    une_heure = datetime.timedelta(hours=1)
    for h in Hist.objects.filter(est_correction=True, type_stock='regularisation').iterator():
        t = h.date_mouvement
        if not (h.commentaire or '').startswith(PREFIXES):
            continue  # Seules les lignes migrées sont concernées
        # Heure UTC exactement 00:00:00 : cas de la migration 0024 (une correction normale est à 23:00 UTC)
        if (t.hour, t.minute, t.second, t.microsecond) != (0, 0, 0, 0):
            continue
        Event.objects.filter(poste_id=h.poste_id, event_datetime=t).update(event_datetime=t - une_heure)  # Événement jumeau
        Hist.objects.filter(pk=h.pk).update(date_mouvement=t - une_heure)  # 00:00 heure locale


class Migration(migrations.Migration):

    dependencies = [("inventaire", "0024_historiquestock_date_effet")]

    operations = [migrations.RunPython(corriger, migrations.RunPython.noop)]
