# ===================================================================
# FICHIER DE MIGRATION/VÉRIFICATION
# Fichier: inventaire/management/commands/verifier_unicite_tickets.py
# 
# Ce fichier permet de vérifier la cohérence des données existantes
# et d'identifier les tickets potentiellement dupliqués
# ===================================================================

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone
from datetime import date, datetime
from decimal import Decimal
import logging

logger = logging.getLogger('supper')


class Command(BaseCommand):
    help = 'Vérifie l\'unicité annuelle des tickets et identifie les duplications'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--annee',
            type=int,
            default=date.today().year,
            help='Année à vérifier (défaut: année en cours)'
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Tenter de corriger automatiquement les problèmes mineurs'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Affichage détaillé'
        )
    
    def handle(self, *args, **options):
        from inventaire.models import SerieTicket, CouleurTicket
        from accounts.models import Poste
        
        annee = options['annee']
        verbose = options['verbose']
        fix = options['fix']
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"VÉRIFICATION UNICITÉ TICKETS - ANNÉE {annee}")
        self.stdout.write(f"{'='*60}\n")
        
        # Définir les dates de l'année
        debut_annee = timezone.make_aware(datetime(annee, 1, 1, 0, 0, 0))
        fin_annee = timezone.make_aware(datetime(annee, 12, 31, 23, 59, 59))
        
        # 1. Récupérer toutes les séries chargées cette année
        series_chargees = SerieTicket.objects.filter(
            type_entree__in=['imprimerie_nationale', 'regularisation'],
            date_reception__range=[debut_annee, fin_annee]
        ).select_related('poste', 'couleur').order_by('couleur', 'numero_premier')
        
        total_series = series_chargees.count()
        self.stdout.write(f"Total séries chargées en {annee}: {total_series}")
        
        if total_series == 0:
            self.stdout.write(self.style.SUCCESS("Aucune série à vérifier."))
            return
        
        # 2. Grouper par couleur et vérifier les chevauchements
        couleurs = CouleurTicket.objects.filter(
            series__in=series_chargees
        ).distinct()
        
        problemes_trouves = []
        
        for couleur in couleurs:
            series_couleur = series_chargees.filter(couleur=couleur).order_by('numero_premier')
            
            if verbose:
                self.stdout.write(f"\n--- Couleur: {couleur.libelle_affichage} ---")
                for s in series_couleur:
                    self.stdout.write(
                        f"  #{s.numero_premier}-{s.numero_dernier} "
                        f"@ {s.poste.nom} ({s.get_type_entree_display()})"
                    )
            
            # Vérifier les chevauchements entre différents postes
            for i, serie1 in enumerate(series_couleur):
                for serie2 in series_couleur[i+1:]:
                    # Ignorer si même poste (pas un problème d'unicité inter-postes)
                    if serie1.poste_id == serie2.poste_id:
                        continue
                    
                    # Vérifier chevauchement
                    if (serie1.numero_premier <= serie2.numero_dernier and 
                        serie1.numero_dernier >= serie2.numero_premier):
                        
                        # Calculer la plage en conflit
                        debut_conflit = max(serie1.numero_premier, serie2.numero_premier)
                        fin_conflit = min(serie1.numero_dernier, serie2.numero_dernier)
                        
                        probleme = {
                            'couleur': couleur.libelle_affichage,
                            'serie1': {
                                'poste': serie1.poste.nom,
                                'plage': f"#{serie1.numero_premier}-{serie1.numero_dernier}",
                                'date': serie1.date_reception.strftime('%d/%m/%Y'),
                                'type': serie1.get_type_entree_display()
                            },
                            'serie2': {
                                'poste': serie2.poste.nom,
                                'plage': f"#{serie2.numero_premier}-{serie2.numero_dernier}",
                                'date': serie2.date_reception.strftime('%d/%m/%Y'),
                                'type': serie2.get_type_entree_display()
                            },
                            'conflit': f"#{debut_conflit}-{fin_conflit}",
                            'nb_tickets_conflit': fin_conflit - debut_conflit + 1
                        }
                        problemes_trouves.append(probleme)
        
        # 3. Afficher les résultats
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"RÉSULTATS DE LA VÉRIFICATION")
        self.stdout.write(f"{'='*60}\n")
        
        if not problemes_trouves:
            self.stdout.write(self.style.SUCCESS(
                f"✅ AUCUN PROBLÈME DÉTECTÉ !\n"
                f"   Toutes les séries chargées en {annee} respectent l'unicité annuelle."
            ))
        else:
            self.stdout.write(self.style.ERROR(
                f"❌ {len(problemes_trouves)} PROBLÈME(S) DÉTECTÉ(S) !\n"
            ))
            
            for i, p in enumerate(problemes_trouves, 1):
                self.stdout.write(self.style.WARNING(f"\nProblème #{i}:"))
                self.stdout.write(f"  Couleur: {p['couleur']}")
                self.stdout.write(f"  Série 1: {p['serie1']['plage']} @ {p['serie1']['poste']}")
                self.stdout.write(f"           (chargée le {p['serie1']['date']} - {p['serie1']['type']})")
                self.stdout.write(f"  Série 2: {p['serie2']['plage']} @ {p['serie2']['poste']}")
                self.stdout.write(f"           (chargée le {p['serie2']['date']} - {p['serie2']['type']})")
                self.stdout.write(self.style.ERROR(
                    f"  → CONFLIT: {p['conflit']} ({p['nb_tickets_conflit']} tickets)"
                ))
        
        # 4. Statistiques supplémentaires
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write("STATISTIQUES")
        self.stdout.write(f"{'='*60}")
        
        # Par type d'entrée
        stats_type = series_chargees.values('type_entree').annotate(count=Count('id'))
        for stat in stats_type:
            type_display = dict(SerieTicket._meta.get_field('type_entree').choices).get(
                stat['type_entree'], stat['type_entree']
            )
            self.stdout.write(f"  {type_display}: {stat['count']} séries")
        
        # Par poste
        stats_poste = series_chargees.values('poste__nom').annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        self.stdout.write(f"\nTop 10 postes par nombre de séries chargées:")
        for stat in stats_poste:
            self.stdout.write(f"  {stat['poste__nom']}: {stat['count']} séries")
        
        # Total tickets
        total_tickets = sum(s.nombre_tickets for s in series_chargees)
        self.stdout.write(f"\nTotal tickets chargés en {annee}: {total_tickets:,}")
        self.stdout.write(f"Valeur totale: {total_tickets * 500:,.0f} FCFA")
        
        self.stdout.write(f"\n{'='*60}\n")