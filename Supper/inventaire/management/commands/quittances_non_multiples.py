# Commande : python manage.py quittances_non_multiples
# Liste les quittances péage (Quittancement) et l'historique déclaré (HistoriqueQuittance) dont le montant
# n'est PAS un multiple de 500 FCFA (valeur d'un ticket).

from django.core.management.base import BaseCommand  # Base des commandes

from inventaire.models import Quittancement, HistoriqueQuittance  # Modèles contrôlés


class Command(BaseCommand):
    help = "Liste les quittances péage dont le montant n'est pas un multiple de 500."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("=== QUITTANCEMENTS ==="))
        n = 0  # Compteur
        for q in Quittancement.objects.select_related('poste', 'saisi_par').order_by('poste__nom', 'date_recette'):
            if int(q.montant) % 500 != 0:  # Reste non nul : pas un multiple de 500
                n += 1
                jour = q.date_recette or q.date_debut_decade  # Journalière ou décade
                self.stdout.write(f"{q.poste.nom:<25} N° {q.numero_quittance:<15} recette {jour} | montant {q.montant:>12,.0f} "
                                  f"| reste {int(q.montant) % 500:>3} | saisi par {q.saisi_par}")
        self.stdout.write(f"-> {n} quittance(s) non multiple(s) de 500")

        self.stdout.write(self.style.SUCCESS("\n=== HISTORIQUE QUITTANCES ==="))
        n = 0
        for h in HistoriqueQuittance.objects.select_related('poste').order_by('poste__nom'):
            if h.montant_reel is not None and int(h.montant_reel) % 500 != 0:
                n += 1
                self.stdout.write(f"{h.poste.nom:<25} N° {h.numero_historique:<15} {h.mois}/{h.annee} "
                                  f"| montant {h.montant_reel:>12,.0f} | reste {int(h.montant_reel) % 500:>3}")
        self.stdout.write(f"-> {n} ligne(s) non multiple(s) de 500")
