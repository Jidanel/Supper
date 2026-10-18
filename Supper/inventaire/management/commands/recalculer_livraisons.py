# inventaire/management/commands/recalculer_livraisons.py

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from inventaire.models_commandes import (
    DetailCommandePoste, LivraisonTickets,
)


class Command(BaseCommand):
    help = (
        "Recalcule carnets_livres/est_complet sur tous les DetailCommandePoste "
        "et le statut de leurs commandes, à partir des LivraisonTickets réellement "
        "en base. Corrige les détails restés figés 'complet' après une suppression "
        "de livraison faite avant le correctif de LivraisonTickets.delete()."
    )

    def handle(self, *args, **options):
        corriges = 0

        with transaction.atomic():
            for detail in DetailCommandePoste.objects.select_related(
                'commande', 'poste'
            ).all():
                total_carnets = LivraisonTickets.objects.filter(
                    detail_commande=detail,
                    statut__in=['en_cours', 'complete']
                ).aggregate(total=Sum('nombre_carnets_livres'))['total'] or 0

                nouvel_est_complet = total_carnets >= detail.nombre_carnets

                if (detail.carnets_livres != total_carnets
                        or detail.est_complet != nouvel_est_complet):
                    ancien_carnets = detail.carnets_livres
                    ancien_complet = detail.est_complet

                    detail.carnets_livres = total_carnets
                    detail.est_complet = nouvel_est_complet
                    detail.save(update_fields=['carnets_livres', 'est_complet'])

                    corriges += 1
                    self.stdout.write(
                        f"Corrigé: {detail.poste.nom} (commande "
                        f"#{detail.commande.numero_commande}) — "
                        f"carnets_livres {ancien_carnets}→{total_carnets}, "
                        f"est_complet {ancien_complet}→{nouvel_est_complet}"
                    )

            # Recalcule le statut de chaque commande impactée
            commandes_ids = set(
                DetailCommandePoste.objects.values_list('commande_id', flat=True)
            )
            for commande_id in commandes_ids:
                from inventaire.models_commandes import CommandeTickets
                commande = CommandeTickets.objects.get(id=commande_id)
                details_total = commande.details.count()
                details_complets = commande.details.filter(est_complet=True).count()

                if details_complets == 0:
                    nouveau_statut = 'validee'
                elif details_complets < details_total:
                    nouveau_statut = 'en_cours'
                else:
                    nouveau_statut = 'completee'

                if commande.statut != nouveau_statut:
                    commande.statut = nouveau_statut
                    commande.save(update_fields=['statut'])

        self.stdout.write(
            self.style.SUCCESS(f"{corriges} détail(s) de commande corrigé(s).")
        )