# inventaire/management/commands/migrate_approvisionnement_data.py

"""
Commande pour migrer les données existantes d'approvisionnement
vers les nouveaux champs structurés du modèle HistoriqueStock
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from decimal import Decimal
import re
import json
import logging

logger = logging.getLogger('supper')

class Command(BaseCommand):
    help = 'Migre les données d\'approvisionnement existantes vers les champs structurés'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--poste-id',
            type=int,
            help='ID du poste à migrer (optionnel, sinon tous les postes)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulation sans modification de la base de données'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Affichage détaillé'
        )
    
    def handle(self, *args, **options):
        from inventaire.models import HistoriqueStock, SerieTicket, CouleurTicket
        
        poste_id = options.get('poste_id')
        dry_run = options.get('dry_run', False)
        verbose = options.get('verbose', False)
        
        if dry_run:
            self.stdout.write(self.style.WARNING("MODE SIMULATION - Aucune modification"))
        
        # Filtrer les historiques d'approvisionnement
        historiques_query = HistoriqueStock.objects.filter(
            type_mouvement='CREDIT',
            type_stock__in=['imprimerie_nationale', 'imprimerie', 'regularisation']
        ).select_related('poste', 'effectue_par').prefetch_related(
            'series_tickets_associees',
            'series_tickets_associees__couleur'
        )
        
        # Filtrer uniquement ceux qui n'ont pas encore les champs structurés remplis
        historiques_query = historiques_query.filter(
            Q(numero_premier_ticket__isnull=True) |
            Q(numero_dernier_ticket__isnull=True) |
            Q(couleur_principale__isnull=True)
        )
        
        if poste_id:
            historiques_query = historiques_query.filter(poste_id=poste_id)
        
        total = historiques_query.count()
        self.stdout.write(f"Historiques à migrer: {total}")
        
        migres = 0
        erreurs = []
        
        with transaction.atomic():
            for hist in historiques_query:
                try:
                    migration_effectuee = False
                    details_approvisionnement = hist.details_approvisionnement or {}
                    
                    # Priorité 1: Utiliser les séries associées
                    series_associees = hist.series_tickets_associees.all()
                    
                    if series_associees.exists():
                        # Prendre la première série comme série principale
                        serie_principale = series_associees.first()
                        
                        hist.numero_premier_ticket = serie_principale.numero_premier
                        hist.numero_dernier_ticket = serie_principale.numero_dernier
                        hist.couleur_principale = serie_principale.couleur
                        
                        # Construire le JSON des détails si plusieurs séries
                        if not details_approvisionnement.get('series'):
                            details_approvisionnement['series'] = []
                            
                            for serie in series_associees:
                                details_approvisionnement['series'].append({
                                    'couleur_id': serie.couleur.id,
                                    'couleur_nom': serie.couleur.libelle_affichage,
                                    'couleur_code': serie.couleur.code_normalise,
                                    'numero_premier': serie.numero_premier,
                                    'numero_dernier': serie.numero_dernier,
                                    'nombre_tickets': serie.nombre_tickets,
                                    'valeur': str(serie.valeur_monetaire),
                                    'serie_id': serie.id
                                })
                        
                        migration_effectuee = True
                        
                        if verbose:
                            self.stdout.write(
                                f"  Historique {hist.id}: Migration depuis séries associées"
                            )
                    
                    # Priorité 2: Parser le commentaire
                    elif hist.commentaire and '#' in hist.commentaire:
                        pattern = r"Série\s+(\w+)\s+#(\d+)-(\d+)"
                        match = re.search(pattern, hist.commentaire)
                        
                        if match:
                            couleur_nom = match.group(1)
                            num_premier = int(match.group(2))
                            num_dernier = int(match.group(3))
                            
                            # Rechercher la couleur
                            couleur = CouleurTicket.objects.filter(
                                Q(libelle_affichage__icontains=couleur_nom) |
                                Q(code_normalise__icontains=couleur_nom.lower())
                            ).first()
                            
                            if couleur:
                                hist.numero_premier_ticket = num_premier
                                hist.numero_dernier_ticket = num_dernier
                                hist.couleur_principale = couleur
                                
                                # Ajouter aux détails JSON
                                if not details_approvisionnement.get('series'):
                                    details_approvisionnement['series'] = []
                                
                                nombre_tickets = num_dernier - num_premier + 1
                                details_approvisionnement['series'].append({
                                    'couleur_id': couleur.id,
                                    'couleur_nom': couleur.libelle_affichage,
                                    'couleur_code': couleur.code_normalise,
                                    'numero_premier': num_premier,
                                    'numero_dernier': num_dernier,
                                    'nombre_tickets': nombre_tickets,
                                    'valeur': str(Decimal(nombre_tickets * 500))
                                })
                                
                                migration_effectuee = True
                                
                                if verbose:
                                    self.stdout.write(
                                        f"  Historique {hist.id}: Migration depuis commentaire"
                                    )
                                
                                # Essayer de créer/retrouver la série
                                if not series_associees.exists() and not dry_run:
                                    serie = SerieTicket.objects.filter(
                                        poste=hist.poste,
                                        couleur=couleur,
                                        numero_premier=num_premier,
                                        numero_dernier=num_dernier
                                    ).first()
                                    
                                    if not serie:
                                        # Créer la série manquante
                                        serie = SerieTicket.objects.create(
                                            couleur=couleur,
                                            numero_premier=num_premier,
                                            numero_dernier=num_dernier,
                                            nombre_tickets=nombre_tickets,
                                            valeur_monetaire=Decimal(nombre_tickets * 500),
                                            poste=hist.poste,
                                            date_reception=hist.date_mouvement,
                                            statut='stock',
                                            type_entree='imprimerie_nationale',
                                            commentaire=f"Série reconstruite depuis historique #{hist.id}"
                                        )
                                    
                                    # Associer la série
                                    hist.series_tickets_associees.add(serie)
                                    details_approvisionnement['series'][0]['serie_id'] = serie.id
                    
                    # Sauvegarder si des modifications ont été faites
                    if migration_effectuee:
                        hist.details_approvisionnement = details_approvisionnement
                        
                        if not dry_run:
                            hist.save()
                            migres += 1
                        else:
                            migres += 1
                            self.stdout.write(
                                f"  [SIMULATION] Historique {hist.id} serait migré"
                            )
                    else:
                        if verbose:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  Historique {hist.id}: Pas de données à migrer"
                                )
                            )
                
                except Exception as e:
                    erreur_msg = f"Erreur historique {hist.id}: {str(e)}"
                    erreurs.append(erreur_msg)
                    logger.error(erreur_msg, exc_info=True)
                    if verbose:
                        self.stdout.write(self.style.ERROR(f"  {erreur_msg}"))
            
            # En cas d'erreurs en mode non dry-run
            if not dry_run and erreurs:
                if input("\nDes erreurs sont survenues. Annuler les modifications ? (yes/no): ").lower() == 'yes':
                    raise Exception("Annulation suite aux erreurs")
        
        # Résumé
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(f"Migration terminée: {migres}/{total} historiques migrés"))
        
        if erreurs:
            self.stdout.write(self.style.ERROR(f"Erreurs rencontrées: {len(erreurs)}"))
            for err in erreurs[:5]:
                self.stdout.write(f"  - {err}")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\nMode simulation - Relancez sans --dry-run pour appliquer"))