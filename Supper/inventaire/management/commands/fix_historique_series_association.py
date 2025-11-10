"""
Commande Django pour corriger les associations manquantes entre historiques et séries de tickets
Usage: python manage.py fix_historique_series_association
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
import re
import logging

logger = logging.getLogger('supper')

class Command(BaseCommand):
    help = 'Corrige les associations manquantes entre historiques et séries de tickets'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--poste-id',
            type=int,
            help='ID du poste à corriger (optionnel, sinon tous les postes)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulation sans modification de la base de données'
        )
    
    def handle(self, *args, **options):
        from inventaire.models import (
            HistoriqueStock, SerieTicket, CouleurTicket, Poste
        )
        from django.db.models import Q
        
        poste_id = options.get('poste_id')
        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING("MODE SIMULATION - Aucune modification ne sera effectuée"))
        
        # Filtrer les historiques à traiter
        historiques_query = HistoriqueStock.objects.select_related(
            'poste', 'effectue_par'
        ).prefetch_related('series_tickets_associees')
        
        if poste_id:
            historiques_query = historiques_query.filter(poste_id=poste_id)
            self.stdout.write(f"Traitement du poste ID: {poste_id}")
        else:
            self.stdout.write("Traitement de tous les postes")
        
        # Filtrer les historiques d'approvisionnement sans séries associées
        historiques_sans_series = historiques_query.filter(
            type_mouvement='CREDIT',
            type_stock__in=['imprimerie_nationale', 'imprimerie', 'regularisation']
        ).filter(
            series_tickets_associees__isnull=True
        )
        
        total_historiques = historiques_sans_series.count()
        self.stdout.write(f"Historiques à corriger: {total_historiques}")
        
        corrections_reussies = 0
        erreurs = []
        
        with transaction.atomic():
            for historique in historiques_sans_series:
                try:
                    # Vérifier si des séries sont déjà associées
                    if historique.series_tickets_associees.exists():
                        self.stdout.write(
                            f"  Historique {historique.id} a déjà des séries associées"
                        )
                        continue
                    
                    # Essayer d'extraire les infos depuis le commentaire
                    if historique.commentaire:
                        # Pattern pour extraire "Série Couleur #premier-dernier"
                        pattern = r"Série\s+(\w+)\s+#(\d+)-(\d+)"
                        matches = re.finditer(pattern, historique.commentaire)
                        
                        series_trouvees = []
                        
                        for match in matches:
                            couleur_nom = match.group(1)
                            num_premier = int(match.group(2))
                            num_dernier = int(match.group(3))
                            
                            self.stdout.write(
                                f"  Extraction: {couleur_nom} #{num_premier}-{num_dernier}"
                            )
                            
                            # Rechercher la couleur
                            couleur = CouleurTicket.objects.filter(
                                Q(libelle_affichage__icontains=couleur_nom) |
                                Q(code_normalise__icontains=couleur_nom.lower())
                            ).first()
                            
                            if not couleur:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f"    Couleur '{couleur_nom}' non trouvée"
                                    )
                                )
                                continue
                            
                            # Rechercher la série correspondante
                            serie = SerieTicket.objects.filter(
                                poste=historique.poste,
                                couleur=couleur,
                                numero_premier=num_premier,
                                numero_dernier=num_dernier
                            ).first()
                            
                            if serie:
                                series_trouvees.append(serie)
                                self.stdout.write(
                                    self.style.SUCCESS(
                                        f"    Série trouvée: ID {serie.id}"
                                    )
                                )
                            else:
                                # Tenter de créer la série si elle n'existe pas
                                # et si on a suffisamment d'informations
                                if not dry_run and historique.date_mouvement:
                                    nombre_tickets = num_dernier - num_premier + 1
                                    valeur = Decimal(nombre_tickets * 500)
                                    
                                    # Vérifier la cohérence avec l'historique
                                    if nombre_tickets == historique.nombre_tickets:
                                        serie = SerieTicket.objects.create(
                                            couleur=couleur,
                                            numero_premier=num_premier,
                                            numero_dernier=num_dernier,
                                            nombre_tickets=nombre_tickets,
                                            valeur_monetaire=valeur,
                                            poste=historique.poste,
                                            date_reception=historique.date_mouvement,
                                            statut='en_stock',
                                            responsable_reception=historique.effectue_par
                                        )
                                        series_trouvees.append(serie)
                                        self.stdout.write(
                                            self.style.SUCCESS(
                                                f"    Série créée: ID {serie.id}"
                                            )
                                        )
                                    else:
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f"    Incohérence: {nombre_tickets} tickets "
                                                f"vs {historique.nombre_tickets} dans l'historique"
                                            )
                                        )
                        
                        # Associer les séries trouvées à l'historique
                        if series_trouvees and not dry_run:
                            historique.series_tickets_associees.set(series_trouvees)
                            historique.save()
                            
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  Historique {historique.id}: "
                                    f"{len(series_trouvees)} série(s) associée(s)"
                                )
                            )
                            corrections_reussies += 1
                        elif series_trouvees and dry_run:
                            self.stdout.write(
                                f"  [SIMULATION] Historique {historique.id}: "
                                f"{len(series_trouvees)} série(s) seraient associée(s)"
                            )
                            corrections_reussies += 1
                    else:
                        # Pas de commentaire pour extraire les infos
                        # Essayer de retrouver via la date et le montant
                        series_possibles = SerieTicket.objects.filter(
                            poste=historique.poste,
                            date_reception__date=historique.date_mouvement.date(),
                            valeur_monetaire=historique.montant
                        )
                        
                        if series_possibles.exists():
                            if not dry_run:
                                historique.series_tickets_associees.set(series_possibles)
                                historique.save()
                            
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  Historique {historique.id}: "
                                    f"{series_possibles.count()} série(s) retrouvée(s) par date/montant"
                                )
                            )
                            corrections_reussies += 1
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  Historique {historique.id}: Aucune série trouvée"
                                )
                            )
                
                except Exception as e:
                    erreur_msg = f"Erreur historique {historique.id}: {str(e)}"
                    erreurs.append(erreur_msg)
                    self.stdout.write(self.style.ERROR(f"  {erreur_msg}"))
                    logger.error(erreur_msg)
        
        # Résumé
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(f"Corrections réussies: {corrections_reussies}/{total_historiques}"))
        
        if erreurs:
            self.stdout.write(self.style.ERROR(f"Erreurs rencontrées: {len(erreurs)}"))
            for erreur in erreurs[:5]:  # Afficher les 5 premières erreurs
                self.stdout.write(f"  - {erreur}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\nMode simulation - Aucune modification effectuée"))
            self.stdout.write("Relancez sans --dry-run pour appliquer les corrections")