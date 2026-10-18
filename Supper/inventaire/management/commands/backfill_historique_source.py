# ===================================================================
# FICHIER 5: inventaire/management/commands/backfill_historique_source.py
# ===================================================================
# Commande Django pour remplir le champ historique_source sur les
# SerieTicket existantes.
#
# UTILISATION:
#   python manage.py backfill_historique_source
#   python manage.py backfill_historique_source --dry-run
# ===================================================================

from django.core.management.base import BaseCommand
from django.db import transaction
from inventaire.models import SerieTicket, HistoriqueStock
import logging

logger = logging.getLogger('supper')


class Command(BaseCommand):
    help = (
        'Remplit le champ historique_source sur les SerieTicket existantes '
        'en utilisant le ManyToMany series_tickets_associees et le matching '
        'par poste/couleur/numéros.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simuler sans modifier la base de données',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        updated_m2m = 0
        updated_match = 0
        errors = 0

        if dry_run:
            self.stdout.write(self.style.WARNING("MODE DRY-RUN: aucune modification ne sera effectuée"))

        # ===================================================================
        # ÉTAPE 1: Via le ManyToMany existant (source la plus fiable)
        # ===================================================================
        self.stdout.write("\n=== ÉTAPE 1: Liaison via ManyToMany series_tickets_associees ===")

        historiques = HistoriqueStock.objects.prefetch_related(
            'series_tickets_associees'
        ).filter(
            series_tickets_associees__isnull=False
        ).distinct().order_by('date_mouvement')

        self.stdout.write(f"  {historiques.count()} historiques avec séries associées trouvés")

        for hist in historiques:
            series_sans_source = hist.series_tickets_associees.filter(
                historique_source__isnull=True
            )
            count = series_sans_source.count()

            if count > 0:
                if not dry_run:
                    series_sans_source.update(historique_source=hist)
                updated_m2m += count
                self.stdout.write(
                    f"  Historique #{hist.id} ({hist.get_type_mouvement_display()} "
                    f"{hist.date_mouvement.strftime('%d/%m/%Y')}): "
                    f"{count} série(s) liée(s)"
                )

        self.stdout.write(self.style.SUCCESS(f"  → {updated_m2m} séries mises à jour via ManyToMany"))

        # ===================================================================
        # ÉTAPE 2: Matching par poste + couleur + numéros pour les orphelines
        # ===================================================================
        self.stdout.write("\n=== ÉTAPE 2: Matching par poste/couleur/numéros ===")

        orphelines = SerieTicket.objects.filter(
            historique_source__isnull=True
        ).select_related('couleur', 'poste').order_by('poste__nom', 'date_reception')

        total_orphelines = orphelines.count()
        self.stdout.write(f"  {total_orphelines} séries orphelines restantes")

        for serie in orphelines:
            try:
                hist = None

                # Tentative 1: Match exact par champs structurés
                hist = HistoriqueStock.objects.filter(
                    poste=serie.poste,
                    type_mouvement='CREDIT',
                    couleur_principale=serie.couleur,
                    numero_premier_ticket__lte=serie.numero_premier,
                    numero_dernier_ticket__gte=serie.numero_dernier,
                ).order_by('-date_mouvement').first()

                # Tentative 2: Match par JSON details_approvisionnement
                if not hist:
                    hists_candidats = HistoriqueStock.objects.filter(
                        poste=serie.poste,
                        type_mouvement='CREDIT',
                        details_approvisionnement__isnull=False,
                    ).order_by('-date_mouvement')

                    for h in hists_candidats:
                        if (h.details_approvisionnement and
                                isinstance(h.details_approvisionnement, dict)):
                            for s in h.details_approvisionnement.get('series', []):
                                np = s.get('numero_premier', s.get('premier'))
                                nd = s.get('numero_dernier', s.get('dernier'))
                                if np and nd:
                                    if np <= serie.numero_premier and nd >= serie.numero_dernier:
                                        hist = h
                                        break
                        if hist:
                            break

                # Tentative 3: Pour les transferts reçus, match par poste_origine
                if not hist and serie.type_entree == 'transfert_recu':
                    hist = HistoriqueStock.objects.filter(
                        poste=serie.poste,
                        type_mouvement='CREDIT',
                        poste_origine__isnull=False,
                        date_mouvement__date=serie.date_reception.date() if serie.date_reception else None,
                    ).first()

                if hist:
                    if not dry_run:
                        serie.historique_source = hist
                        serie.save(update_fields=['historique_source'])
                    updated_match += 1
                    if updated_match <= 20:  # Limiter le log
                        self.stdout.write(
                            f"  Série #{serie.id} ({serie.couleur} "
                            f"#{serie.numero_premier}-{serie.numero_dernier} "
                            f"@ {serie.poste.nom}) → Historique #{hist.id}"
                        )

            except Exception as e:
                errors += 1
                logger.error(f"Erreur backfill série {serie.id}: {e}")
                if errors <= 5:
                    self.stdout.write(self.style.ERROR(f"  Erreur série #{serie.id}: {e}"))

        if updated_match > 20:
            self.stdout.write(f"  ... et {updated_match - 20} autres")

        self.stdout.write(self.style.SUCCESS(f"  → {updated_match} séries mises à jour via matching"))

        # ===================================================================
        # RÉSUMÉ
        # ===================================================================
        self.stdout.write(f"\n{'=' * 60}")
        total_updated = updated_m2m + updated_match

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"DRY-RUN: {total_updated} séries AURAIENT été mises à jour, {errors} erreurs"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Backfill terminé: {total_updated} mises à jour, {errors} erreurs"
            ))

        # Stats finales
        total = SerieTicket.objects.count()
        avec_source = SerieTicket.objects.filter(historique_source__isnull=False).count()
        sans_source = total - avec_source

        self.stdout.write(f"\nÉtat final:")
        self.stdout.write(f"  Total séries: {total}")
        self.stdout.write(f"  Avec historique_source: {avec_source} ({avec_source * 100 // max(total, 1)}%)")
        self.stdout.write(f"  Sans historique_source: {sans_source}")

        if sans_source > 0:
            self.stdout.write(self.style.WARNING(
                f"\n  ⚠️ {sans_source} séries n'ont pas pu être liées. "
                f"Elles seront comptées dans 'Stock de début' dans le compte d'emploi."
            ))