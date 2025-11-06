# inventaire/migrations/migrate_to_event_sourcing.py
# Script de migration pour convertir l'historique existant en événements

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging

logger = logging.getLogger('supper')

class Command(BaseCommand):
    help = 'Migre les données de stock existantes vers le système Event Sourcing'
    
    def handle(self, *args, **kwargs):
        """
        Migre toutes les données de stock existantes vers le nouveau système Event Sourcing
        """
        from inventaire.models import (
            HistoriqueStock, GestionStock, StockEvent, StockSnapshot,
            RecetteJournaliere, SerieTicket
        )
        from accounts.models import Poste
        
        self.stdout.write("Début de la migration vers Event Sourcing...")
        
        with transaction.atomic():
            # 1. Supprimer les événements existants (si re-migration)
            if StockEvent.objects.exists():
                confirm = input("Des événements existent déjà. Voulez-vous les supprimer ? (yes/no): ")
                if confirm.lower() == 'yes':
                    StockEvent.objects.all().delete()
                    StockSnapshot.objects.all().delete()
                    self.stdout.write(self.style.WARNING("Événements existants supprimés."))
                else:
                    self.stdout.write(self.style.ERROR("Migration annulée."))
                    return
            
            # 2. Pour chaque poste, créer l'historique complet
            postes = Poste.objects.filter(is_active=True)
            total_postes = postes.count()
            
            for idx, poste in enumerate(postes, 1):
                self.stdout.write(f"\nTraitement du poste {idx}/{total_postes}: {poste.nom}")
                
                # Récupérer tous les historiques de ce poste
                historiques = HistoriqueStock.objects.filter(
                    poste=poste
                ).order_by('date_mouvement')
                
                if not historiques.exists():
                    self.stdout.write(f"  - Aucun historique trouvé")
                    
                    # Créer un événement initial avec le stock actuel
                    stock_actuel = GestionStock.objects.filter(poste=poste).first()
                    if stock_actuel and stock_actuel.valeur_monetaire > 0:
                        StockEvent.objects.create(
                            poste=poste,
                            event_type='INITIAL',
                            event_datetime=timezone.now() - timedelta(days=365),  # 1 an dans le passé
                            montant_variation=stock_actuel.valeur_monetaire,
                            nombre_tickets_variation=stock_actuel.nombre_tickets,
                            stock_resultant=stock_actuel.valeur_monetaire,
                            tickets_resultants=stock_actuel.nombre_tickets,
                            commentaire="Stock initial (migration)"
                        )
                        self.stdout.write(f"  - Stock initial créé: {stock_actuel.valeur_monetaire} FCFA")
                    continue
                
                # Traiter chaque historique
                stock_courant = Decimal('0')
                events_created = 0
                
                for hist in historiques:
                    # Calculer la variation
                    if hist.type_mouvement == 'CREDIT':
                        variation = hist.montant
                        tickets_var = hist.nombre_tickets
                    else:  # DEBIT
                        variation = -hist.montant
                        tickets_var = -hist.nombre_tickets
                    
                    stock_courant += variation
                    
                    # Déterminer le type d'événement
                    event_type = self._determine_event_type(hist)
                    
                    # Créer les métadonnées
                    metadata = self._build_metadata(hist)
                    
                    # Créer l'événement
                    StockEvent.objects.create(
                        poste=poste,
                        event_type=event_type,
                        event_datetime=hist.date_mouvement,
                        montant_variation=variation,
                        nombre_tickets_variation=tickets_var,
                        stock_resultant=stock_courant,
                        tickets_resultants=int(stock_courant / 500),
                        effectue_par=hist.effectue_par,
                        reference_id=str(hist.id),
                        reference_type='HistoriqueStock',
                        metadata=metadata,
                        commentaire=hist.commentaire or ''
                    )
                    events_created += 1
                
                self.stdout.write(f"  - {events_created} événements créés")
                
                # Créer un snapshot mensuel
                if events_created > 0:
                    today = date.today()
                    for month_offset in range(12):  # Derniers 12 mois
                        snapshot_date = today - timedelta(days=30 * month_offset)
                        StockSnapshot.create_snapshot(poste, snapshot_date)
                    self.stdout.write(f"  - Snapshots créés")
        
        self.stdout.write(self.style.SUCCESS("\nMigration terminée avec succès !"))
    
    def _determine_event_type(self, hist):
        """Détermine le type d'événement basé sur l'historique"""
        if hist.type_mouvement == 'CREDIT':
            if hist.type_stock == 'regularisation':
                return 'REGULARISATION'
            elif hist.type_stock == 'reapprovisionnement':
                return 'TRANSFERT_IN'
            else:
                return 'CHARGEMENT'
        else:  # DEBIT
            if hist.poste_destination:
                return 'TRANSFERT_OUT'
            elif hist.reference_recette:
                return 'VENTE'
            else:
                return 'AJUSTEMENT'
    
    def _build_metadata(self, hist):
        """Construit les métadonnées pour l'événement"""
        metadata = {
            'historique_id': hist.id,
            'stock_avant': str(hist.stock_avant),
            'stock_apres': str(hist.stock_apres),
        }
        
        if hist.type_stock:
            metadata['type_stock'] = hist.type_stock
        
        if hist.poste_origine:
            metadata['poste_origine'] = {
                'id': hist.poste_origine.id,
                'nom': hist.poste_origine.nom,
                'code': hist.poste_origine.code
            }
        
        if hist.poste_destination:
            metadata['poste_destination'] = {
                'id': hist.poste_destination.id,
                'nom': hist.poste_destination.nom,
                'code': hist.poste_destination.code
            }
        
        if hist.numero_bordereau:
            metadata['numero_bordereau'] = hist.numero_bordereau
        
        if hist.reference_recette:
            metadata['recette'] = {
                'id': hist.reference_recette.id,
                'date': str(hist.reference_recette.date),
                'montant': str(hist.reference_recette.montant_declare)
            }
        
        # Ajouter les séries de tickets si disponibles
        if hasattr(hist, 'series_tickets_associees'):
            series = hist.series_tickets_associees.all()
            if series.exists():
                metadata['series'] = [
                    {
                        'couleur': s.couleur.libelle_affichage,
                        'premier': s.numero_premier,
                        'dernier': s.numero_dernier,
                        'nombre': s.nombre_tickets
                    }
                    for s in series
                ]
        
        return metadata