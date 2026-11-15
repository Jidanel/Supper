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
        parser.add_argument('--poste', help="Détail d'UN poste (nom, partie du nom) : mouvements et séries expliquant l'écart")

    def handle(self, *args, **options):
        debut, _fin = bornes_mois(options['mois'])  # Premier jour du mois
        if options.get('poste'):
            return self.detail(options['poste'], debut)  # Mode diagnostic d'un poste
        ecarts = 0
        for poste in Poste.objects.filter(type='peage', is_active=True).order_by('nom'):
            csp, _t = calculer_stock_debut_periode(poste, debut)  # Début selon HistoriqueStock
            series = nombre_tickets(series_debut_jour(poste, debut)) * 500  # Début selon les séries
            if csp != series:
                ecarts += 1
                self.stdout.write(f"{poste.nom:<30} CSP = {csp:>12,.0f} | séries = {series:>12,.0f} | écart = {series - csp:>+10,.0f}")
        self.stdout.write(self.style.SUCCESS(f"Terminé : {ecarts} poste(s) incohérent(s) au {debut:%d/%m/%Y}."))

    def detail(self, nom, debut):
        """Affiche, pour un poste, ce qui compose le stock CSP (HistoriqueStock) et le stock séries (SerieTicket)."""
        from datetime import datetime
        from django.db.models import Q, Sum, Count
        from django.utils import timezone
        from inventaire.models import HistoriqueStock, SerieTicket
        poste = Poste.objects.filter(type='peage', nom__icontains=nom).first()
        if not poste:
            return self.stdout.write(self.style.ERROR(f"Aucun poste péage ne correspond à « {nom} »."))
        limite = timezone.make_aware(datetime.combine(debut, datetime.min.time()))
        self.stdout.write(self.style.SUCCESS(f"=== {poste.nom} — stock au début du {debut:%d/%m/%Y} ==="))
        # 1. Mouvements HistoriqueStock comptés dans le CSP, regroupés par type
        base = HistoriqueStock.objects.filter(poste=poste, date_mouvement__lte=limite)
        self.stdout.write("\n-- HistoriqueStock (CSP), regroupé par type de mouvement / de stock / correction --")
        for r in base.values('type_mouvement', 'type_stock', 'est_correction').annotate(n=Count('id'), t=Sum('nombre_tickets'), m=Sum('montant')).order_by('type_mouvement'):
            self.stdout.write(f"  {r['type_mouvement']:<7} {str(r['type_stock'] or '-'):<22} correction={str(r['est_correction']):<5} "
                              f"lignes={r['n']:>4} tickets={r['t'] or 0:>8,} montant={r['m'] or 0:>14,.0f}")
        # 2. Les 12 plus gros mouvements sans recette liée (chargements, corrections, transferts)
        self.stdout.write("\n-- Plus gros mouvements (hors ventes) --")
        for h in base.filter(reference_recette__isnull=True).order_by('-montant')[:12]:
            self.stdout.write(f"  #{h.pk} {h.date_mouvement:%d/%m/%Y %H:%M} {h.type_mouvement:<6} {h.nombre_tickets:>7,} tickets "
                              f"{h.montant:>13,.0f} FCFA | {h.type_stock or '-'} | bordereau {h.numero_bordereau or '-'} | {(h.commentaire or '')[:70]}")
        # 3. Séries réellement détenues (SerieTicket) à ce moment
        self.stdout.write("\n-- Séries détenues (SerieTicket) au début du mois, par couleur --")
        qs = SerieTicket.objects.filter(poste=poste, date_reception__lte=limite).filter(
            Q(statut='stock') | Q(statut='vendu', date_utilisation__gte=debut))
        for r in qs.values('couleur__libelle_affichage').annotate(n=Count('id'), t=Sum('nombre_tickets')):
            self.stdout.write(f"  {r['couleur__libelle_affichage']:<15} séries={r['n']:>4} tickets={r['t'] or 0:>8,}  = {(r['t'] or 0) * 500:>14,.0f} FCFA")
        # 4. Séries SANS mouvement d'historique correspondant (même numéro de bordereau absent) : pistes d'oubli
        self.stdout.write("\n-- Séries chargées sans ligne CREDIT équivalente dans l'historique (même nombre de tickets) --")
        credits = list(base.filter(type_mouvement='CREDIT').values_list('nombre_tickets', flat=True))
        manquantes = 0
        for sr in qs.filter(statut='stock').order_by('-nombre_tickets')[:400]:
            if sr.nombre_tickets in credits:
                credits.remove(sr.nombre_tickets)  # Appariée
            else:
                manquantes += 1
                if manquantes <= 15:
                    self.stdout.write(f"  Série {sr.couleur} {sr.numero_premier}-{sr.numero_dernier} ({sr.nombre_tickets:,} tickets) chargée le {sr.date_reception:%d/%m/%Y %H:%M} — aucun CREDIT de cette taille")
        self.stdout.write(f"  Total non appariées : {manquantes}")
