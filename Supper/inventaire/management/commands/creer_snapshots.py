"""
Commande de management : crée les snapshots de stock (StockSnapshot)
pour les postes actifs.

Usage :
    python manage.py creer_snapshots                  # hier, tous les postes actifs
    python manage.py creer_snapshots --date 2026-11-01
    python manage.py creer_snapshots --jours 7        # rattrape les 7 derniers jours
    python manage.py creer_snapshots --poste ABC      # un seul poste (code)

Prévue pour être lancée chaque nuit par une Scheduled task PythonAnywhere.
"""
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError

from accounts.models import Poste
from inventaire.models import StockSnapshot


class Command(BaseCommand):
    help = "Crée les snapshots de stock de fin de journée pour les postes actifs."

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help="Date du snapshot au format AAAA-MM-JJ (défaut : hier).",
        )
        parser.add_argument(
            '--jours',
            type=int,
            default=1,
            help="Nombre de jours à traiter en remontant depuis la date de référence (défaut : 1).",
        )
        parser.add_argument(
            '--poste',
            type=str,
            help="Code d'un poste unique (défaut : tous les postes actifs).",
        )

    def handle(self, *args, **options):
        # --- Date de référence ---
        if options['date']:
            try:
                date_ref = datetime.strptime(options['date'], '%Y-%m-%d').date()
            except ValueError:
                raise CommandError("Format de date invalide. Utilisez AAAA-MM-JJ.")
        else:
            date_ref = date.today() - timedelta(days=1)

        if options['jours'] < 1:
            raise CommandError("--jours doit être >= 1.")

        # --- Postes concernés ---
        postes = Poste.objects.filter(is_active=True)
        if options['poste']:
            postes = postes.filter(code=options['poste'])
            if not postes.exists():
                raise CommandError(f"Aucun poste actif avec le code '{options['poste']}'.")

        dates = [date_ref - timedelta(days=i) for i in range(options['jours'])]
        dates.sort()

        ok, erreurs = 0, 0
        for jour in dates:
            for poste in postes:
                try:
                    # create_snapshot retourne (snapshot, created)
                    StockSnapshot.create_snapshot(poste, jour)
                    ok += 1
                except Exception as e:
                    erreurs += 1
                    self.stderr.write(f"Erreur {poste.nom} ({jour}) : {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Snapshots terminés : {ok} OK, {erreurs} erreur(s) "
            f"[{dates[0]} -> {dates[-1]}, {postes.count()} poste(s)]"
        ))