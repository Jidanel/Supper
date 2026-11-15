# Commande : python manage.py verifier_coherence_stock 2026-11
# Compare, pour chaque poste péage, le STOCK DE DÉBUT du mois selon le CSP (HistoriqueStock, en FCFA) et selon le
# compte d'emploi (séries de tickets). Les deux doivent être identiques ; sinon le poste est listé.

from django.core.management.base import BaseCommand  # Base des commandes

from accounts.models import Poste  # Postes
from inventaire.services.cloture_donnees import bornes_mois, series_debut_jour, nombre_tickets  # Calculs par séries
from inventaire.views_csp import calculer_stock_debut_periode  # Calcul CSP (FCFA)


class Command(BaseCommand):
    help = "Liste les postes dont le stock de début de mois diffère entre le CSP et le compte d'emploi."

    def add_arguments(self, parser):
        parser.add_argument('mois', help="Mois au format AAAA-MM (ex. 2026-11)")

    def handle(self, *args, **options):
        debut, _fin = bornes_mois(options['mois'])  # Premier jour du mois
        ecarts = 0
        for poste in Poste.objects.filter(type='peage', is_active=True).order_by('nom'):
            csp, _t = calculer_stock_debut_periode(poste, debut)  # Début selon HistoriqueStock
            series = nombre_tickets(series_debut_jour(poste, debut)) * 500  # Début selon les séries
            if csp != series:
                ecarts += 1
                self.stdout.write(f"{poste.nom:<30} CSP = {csp:>12,.0f} | séries = {series:>12,.0f} | écart = {series - csp:>+10,.0f}")
        self.stdout.write(self.style.SUCCESS(f"Terminé : {ecarts} poste(s) incohérent(s) au {debut:%d/%m/%Y}."))
