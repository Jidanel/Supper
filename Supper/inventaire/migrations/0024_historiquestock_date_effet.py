# Migration : date d'effet des mouvements de stock.
#   - date_mouvement devient la DATE D'EFFET comptable (modifiable) ;
#   - date_saisie conserve la date RÉELLE de saisie (audit) ;
#   - les corrections déjà enregistrées (gel, dégel, annulation de gel, suppression/modification
#     administrative) sont ramenées au DÉBUT DU MOIS de leur effet, pour que CSP et compte d'emploi concordent.

import datetime
from django.db import migrations, models
from django.db.models import F
import django.utils.timezone

PREFIXES = ("Gel (banque de gel)", "Dégel (banque de gel)", "Annulation du gel",
            "Suppression administrative", "Modification série")  # Corrections déjà présentes en base


def _debut_mois(dt):
    """1er jour du mois de `dt` à 00:00:00 (fuseau conservé)."""
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def appliquer(apps, schema_editor):
    Hist = apps.get_model('inventaire', 'HistoriqueStock')
    Event = apps.get_model('inventaire', 'StockEvent')
    # 1) Date réelle de saisie = ancienne date_mouvement (rien n'est perdu)
    Hist.objects.filter(date_saisie__isnull=True).update(date_saisie=F('date_mouvement'))
    # 2) Corrections existantes -> début du mois
    ids_corrections = []
    deja = set()  # Événements déjà associés (un événement ne sert qu'une fois)
    for h in Hist.objects.filter(type_stock='regularisation').iterator():
        if not (h.commentaire or '').startswith(PREFIXES):
            continue
        effet = _debut_mois(h.date_saisie or h.date_mouvement)
        # Le gel/dégel mémorise sa date d'effet dans son événement de stock : on cherche l'événement jumeau
        # (même poste, type cohérent avec le libellé, instant le plus proche, pas déjà utilisé)
        types = ('GEL', 'DEGEL') if (h.commentaire or '').startswith(PREFIXES[:3]) else ('AJUSTEMENT',)
        t0 = h.date_saisie or h.date_mouvement
        candidats = [e for e in Event.objects.filter(
            poste_id=h.poste_id, event_type__in=types,
            event_datetime__range=(t0 - datetime.timedelta(seconds=10), t0 + datetime.timedelta(seconds=10)))
            if e.pk not in deja]
        ev = min(candidats, key=lambda e: abs((e.event_datetime - t0).total_seconds())) if candidats else None
        if ev:
            deja.add(ev.pk)
        if ev and isinstance(ev.metadata, dict) and ev.metadata.get('date_effet'):
            try:
                d = datetime.date.fromisoformat(ev.metadata['date_effet'])
                effet = effet.replace(year=d.year, month=d.month)  # Mois de la date d'effet saisie à l'époque
            except ValueError:
                pass
        Hist.objects.filter(pk=h.pk).update(date_mouvement=effet, est_correction=True)  # Début du mois + marquée correction
        if ev:
            Event.objects.filter(pk=ev.pk).update(event_datetime=effet)
        ids_corrections.append(h.pk)


def annuler(apps, schema_editor):
    Hist = apps.get_model('inventaire', 'HistoriqueStock')
    Hist.objects.filter(date_saisie__isnull=False).update(date_mouvement=F('date_saisie'))


class Migration(migrations.Migration):

    dependencies = [
        ("inventaire", "0023_alter_historiquequittance_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name='historiquestock', name='date_saisie',
            field=models.DateTimeField(auto_now_add=True, null=True, blank=True, verbose_name='Date réelle de saisie'),
        ),
        migrations.AddField(
            model_name='historiquestock', name='est_correction',
            field=models.BooleanField(default=False, verbose_name='Correction de stock'),
        ),
        migrations.AlterField(
            model_name='historiquestock', name='date_mouvement',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name="Date du mouvement (date d'effet)"),
        ),
        migrations.RunPython(appliquer, annuler),
    ]
