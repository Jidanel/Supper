# inventaire/services/transfert_service.py
"""
Service de transfert de tickets entre postes - VERSION CORRIGÉE
Toute la logique métier centralisée ici - AUCUNE validation dans le modèle

CORRECTION APPORTÉE:
- Les historiques incluent maintenant les champs structurés pour les tickets
- Les séries sont associées aux historiques via series_tickets_associees
- Le JSONField details_approvisionnement est rempli
"""

from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger('supper')


class TransfertTicketsService:
    """
    Service pour gérer les transferts de tickets entre postes
    """
    
    @staticmethod
    def valider_transfert(poste_origine, poste_destination, couleur, numero_premier, numero_dernier):
        """
        Valide un transfert AVANT exécution
        Utilise la méthode existante verifier_disponibilite_serie_complete
        
        Returns:
            tuple (est_valide, message_erreur, details)
        """
        from inventaire.models import SerieTicket
        
        # 1. Vérifier que les postes sont différents
        if poste_origine.id == poste_destination.id:
            return False, "Les postes origine et destination doivent être différents", {}
        
        # 2. Utiliser la méthode existante pour vérifier disponibilité
        est_disponible, message, tickets_prob = SerieTicket.verifier_disponibilite_serie_complete(
            poste_origine, couleur, numero_premier, numero_dernier
        )
        
        if not est_disponible:
            return False, message, {'tickets_problematiques': tickets_prob}
        
        # 3. Tout est OK - calculer les infos
        nombre_tickets = numero_dernier - numero_premier + 1
        montant = Decimal(nombre_tickets) * Decimal('500')
        
        return True, "Transfert autorisé", {
            'nombre_tickets': nombre_tickets,
            'montant': montant
        }
    
    @staticmethod
    @transaction.atomic
    def executer_transfert(poste_origine, poste_destination, couleur, numero_premier, numero_dernier, user, commentaire=''):
        """
        Exécute le transfert après validation
        
        VERSION CORRIGÉE:
        - Remplit les champs structurés de HistoriqueStock
        - Associe les séries via series_tickets_associees
        - Remplit le JSONField details_approvisionnement
        
        Returns:
            tuple (success, message, serie_origine, serie_destination)
        """
        from inventaire.models import SerieTicket, GestionStock, HistoriqueStock, StockEvent
        from accounts.models import NotificationUtilisateur, UtilisateurSUPPER
        
        try:
            timestamp = timezone.now()
            nombre_tickets = numero_dernier - numero_premier + 1
            montant = Decimal(nombre_tickets) * Decimal('500')
            
            logger.info(f"=== EXÉCUTION TRANSFERT ===")
            logger.info(f"De: {poste_origine.nom} vers: {poste_destination.nom}")
            logger.info(f"Série: {couleur.libelle_affichage} #{numero_premier}-{numero_dernier}")
            
            # ============================================================
            # ÉTAPE 1 : Trouver et traiter la série au poste origine
            # ============================================================
            serie_source = SerieTicket.objects.filter(
                poste=poste_origine,
                couleur=couleur,
                statut='stock',
                numero_premier__lte=numero_premier,
                numero_dernier__gte=numero_dernier
            ).first()
            
            if not serie_source:
                return False, "Série source introuvable", None, None
            
            serie_transferee = None
            
            # CAS A: Transfert de la série complète
            if (serie_source.numero_premier == numero_premier and 
                serie_source.numero_dernier == numero_dernier):
                
                logger.info("→ Transfert complet de la série")
                serie_source.statut = 'transfere'
                serie_source.date_utilisation = timestamp.date()
                serie_source.poste_destination_transfert = poste_destination
                serie_source.commentaire = f"Transféré vers {poste_destination.nom} - {commentaire}"
                serie_source.save()
                serie_transferee = serie_source
            
            # CAS B: Transfert partiel - découpage
            else:
                logger.info("→ Transfert partiel - découpage")
                
                original_premier = serie_source.numero_premier
                original_dernier = serie_source.numero_dernier
                type_entree_original = serie_source.type_entree
                responsable_original = serie_source.responsable_reception
                
                # Créer partie AVANT si nécessaire
                if original_premier < numero_premier:
                    SerieTicket.objects.create(
                        poste=poste_origine,
                        couleur=couleur,
                        numero_premier=original_premier,
                        numero_dernier=numero_premier - 1,
                        statut='stock',
                        type_entree=type_entree_original,
                        responsable_reception=responsable_original,
                        commentaire="Reste après transfert partiel"
                    )
                    logger.info(f"  Partie avant: #{original_premier}-{numero_premier - 1}")
                
                # Créer partie APRÈS si nécessaire
                if original_dernier > numero_dernier:
                    SerieTicket.objects.create(
                        poste=poste_origine,
                        couleur=couleur,
                        numero_premier=numero_dernier + 1,
                        numero_dernier=original_dernier,
                        statut='stock',
                        type_entree=type_entree_original,
                        responsable_reception=responsable_original,
                        commentaire="Reste après transfert partiel"
                    )
                    logger.info(f"  Partie après: #{numero_dernier + 1}-{original_dernier}")
                
                # Transformer la série originale en série transférée
                serie_source.numero_premier = numero_premier
                serie_source.numero_dernier = numero_dernier
                serie_source.nombre_tickets = nombre_tickets
                serie_source.valeur_monetaire = montant
                serie_source.statut = 'transfere'
                serie_source.date_utilisation = timestamp.date()
                serie_source.poste_destination_transfert = poste_destination
                serie_source.commentaire = f"Transféré vers {poste_destination.nom} - {commentaire}"
                serie_source.save()
                
                serie_transferee = serie_source
            
            # ============================================================
            # ÉTAPE 2 : Créer/fusionner série au poste destination
            # ============================================================
            serie_destination = TransfertTicketsService._creer_serie_destination(
                poste_destination, couleur, numero_premier, numero_dernier,
                user, poste_origine, commentaire, timestamp
            )
            
            # ============================================================
            # ÉTAPE 3 : Mettre à jour les stocks globaux
            # ============================================================
            stock_origine, _ = GestionStock.objects.get_or_create(
                poste=poste_origine,
                defaults={'valeur_monetaire': Decimal('0')}
            )
            stock_origine_avant = stock_origine.valeur_monetaire
            stock_origine.valeur_monetaire = max(Decimal('0'), stock_origine.valeur_monetaire - montant)
            stock_origine.save()
            
            stock_destination, _ = GestionStock.objects.get_or_create(
                poste=poste_destination,
                defaults={'valeur_monetaire': Decimal('0')}
            )
            stock_destination_avant = stock_destination.valeur_monetaire
            stock_destination.valeur_monetaire += montant
            stock_destination.save()
            
            logger.info(f"Stock {poste_origine.nom}: {stock_origine_avant} → {stock_origine.valeur_monetaire}")
            logger.info(f"Stock {poste_destination.nom}: {stock_destination_avant} → {stock_destination.valeur_monetaire}")
            
            # ============================================================
            # ÉTAPE 4 : Créer historiques avec CHAMPS STRUCTURÉS (CORRECTION)
            # ============================================================
            numero_bordereau = TransfertTicketsService._generer_bordereau()
            
            # Préparer les détails structurés pour le JSONField
            details_serie = {
                'series': [{
                    'couleur_id': couleur.id,
                    'couleur_nom': couleur.libelle_affichage,
                    'couleur_code': couleur.code_normalise,
                    'numero_premier': numero_premier,
                    'numero_dernier': numero_dernier,
                    'nombre_tickets': nombre_tickets,
                    'valeur': str(montant)
                }],
                'type_operation': 'transfert',
                'numero_bordereau': numero_bordereau,
                'poste_origine_id': poste_origine.id,
                'poste_origine_nom': poste_origine.nom,
                'poste_destination_id': poste_destination.id,
                'poste_destination_nom': poste_destination.nom
            }
            
            # Historique origine (DEBIT) - AVEC CHAMPS STRUCTURÉS
            historique_origine = HistoriqueStock.objects.create(
                poste=poste_origine,
                type_mouvement='DEBIT',
                type_stock='reapprovisionnement',
                montant=montant,
                nombre_tickets=nombre_tickets,
                stock_avant=stock_origine_avant,
                stock_apres=stock_origine.valeur_monetaire,
                effectue_par=user,
                poste_origine=poste_origine,
                poste_destination=poste_destination,
                numero_bordereau=numero_bordereau,
                # ===== NOUVEAUX CHAMPS STRUCTURÉS =====
                numero_premier_ticket=numero_premier,
                numero_dernier_ticket=numero_dernier,
                couleur_principale=couleur,
                details_approvisionnement=details_serie,
                # =====================================
                commentaire=f"Cession {couleur.libelle_affichage} #{numero_premier}-{numero_dernier} vers {poste_destination.nom}"
            )
            
            # Associer la série transférée à l'historique origine
            if serie_transferee:
                historique_origine.series_tickets_associees.add(serie_transferee)
            
            # Historique destination (CREDIT) - AVEC CHAMPS STRUCTURÉS
            historique_destination = HistoriqueStock.objects.create(
                poste=poste_destination,
                type_mouvement='CREDIT',
                type_stock='reapprovisionnement',
                montant=montant,
                nombre_tickets=nombre_tickets,
                stock_avant=stock_destination_avant,
                stock_apres=stock_destination.valeur_monetaire,
                effectue_par=user,
                poste_origine=poste_origine,
                poste_destination=poste_destination,
                numero_bordereau=numero_bordereau,
                # ===== NOUVEAUX CHAMPS STRUCTURÉS =====
                numero_premier_ticket=numero_premier,
                numero_dernier_ticket=numero_dernier,
                couleur_principale=couleur,
                details_approvisionnement=details_serie,
                # =====================================
                commentaire=f"Réception {couleur.libelle_affichage} #{numero_premier}-{numero_dernier} de {poste_origine.nom}"
            )
            
            # Associer la série destination à l'historique destination
            if serie_destination:
                historique_destination.series_tickets_associees.add(serie_destination)
            
            # ============================================================
            # ÉTAPE 5 : Events sourcing avec métadonnées complètes
            # ============================================================
            metadata = {
                'couleur': couleur.libelle_affichage,
                'couleur_id': couleur.id,
                'couleur_code': couleur.code_normalise,
                'numero_premier': numero_premier,
                'numero_dernier': numero_dernier,
                'nombre_tickets': nombre_tickets,
                'valeur': str(montant),
                'numero_bordereau': numero_bordereau,
                'serie_transferee_id': serie_transferee.id if serie_transferee else None,
                'serie_destination_id': serie_destination.id if serie_destination else None
            }
            
            StockEvent.objects.create(
                poste=poste_origine,
                event_type='TRANSFERT_OUT',
                event_datetime=timestamp,
                montant_variation=-montant,
                nombre_tickets_variation=-nombre_tickets,
                stock_resultant=stock_origine.valeur_monetaire,
                tickets_resultants=int(stock_origine.valeur_monetaire / 500),
                effectue_par=user,
                reference_id=str(historique_origine.id),
                reference_type='HistoriqueStock',
                metadata={
                    'serie': metadata, 
                    'poste_destination': {
                        'id': poste_destination.id,
                        'nom': poste_destination.nom,
                        'code': poste_destination.code
                    },
                    'historique_id': historique_origine.id
                },
                commentaire=f"Transfert vers {poste_destination.nom}"
            )
            
            StockEvent.objects.create(
                poste=poste_destination,
                event_type='TRANSFERT_IN',
                event_datetime=timestamp,
                montant_variation=montant,
                nombre_tickets_variation=nombre_tickets,
                stock_resultant=stock_destination.valeur_monetaire,
                tickets_resultants=int(stock_destination.valeur_monetaire / 500),
                effectue_par=user,
                reference_id=str(historique_destination.id),
                reference_type='HistoriqueStock',
                metadata={
                    'serie': metadata, 
                    'poste_origine': {
                        'id': poste_origine.id,
                        'nom': poste_origine.nom,
                        'code': poste_origine.code
                    },
                    'historique_id': historique_destination.id
                },
                commentaire=f"Réception depuis {poste_origine.nom}"
            )
            
            # ============================================================
            # ÉTAPE 6 : Notifications
            # ============================================================
            TransfertTicketsService._envoyer_notifications(
                poste_origine, poste_destination, couleur,
                numero_premier, numero_dernier, montant, nombre_tickets,
                numero_bordereau, user
            )
            
            logger.info(f"=== ✅ TRANSFERT RÉUSSI - Bordereau {numero_bordereau} ===")
            logger.info(f"  Historique origine ID: {historique_origine.id}")
            logger.info(f"  Historique destination ID: {historique_destination.id}")
            logger.info(f"  Champs structurés remplis: couleur={couleur.libelle_affichage}, "
                       f"tickets=#{numero_premier}-{numero_dernier}")
            
            return True, f"Transfert réussi - Bordereau {numero_bordereau}", serie_transferee, serie_destination
            
        except Exception as e:
            logger.error(f"❌ ERREUR TRANSFERT: {str(e)}", exc_info=True)
            return False, f"Erreur: {str(e)}", None, None
    
    @staticmethod
    def _creer_serie_destination(poste_destination, couleur, numero_premier, numero_dernier,
                                  user, poste_origine, commentaire, timestamp):
        """
        Crée ou fusionne la série au poste destination
        Sauvegarde directe sans validation
        """
        from inventaire.models import SerieTicket
        
        nombre_tickets = numero_dernier - numero_premier + 1
        montant = Decimal(nombre_tickets) * Decimal('500')
        
        # Chercher séries contiguës
        serie_avant = SerieTicket.objects.filter(
            poste=poste_destination,
            couleur=couleur,
            statut='stock',
            numero_dernier=numero_premier - 1
        ).first()
        
        serie_apres = SerieTicket.objects.filter(
            poste=poste_destination,
            couleur=couleur,
            statut='stock',
            numero_premier=numero_dernier + 1
        ).first()
        
        # CAS 1: Fusion triple
        if serie_avant and serie_apres:
            logger.info("→ Fusion triple au destination")
            nouveau_dernier = serie_apres.numero_dernier
            nouveau_nb = nouveau_dernier - serie_avant.numero_premier + 1
            
            serie_avant.numero_dernier = nouveau_dernier
            serie_avant.nombre_tickets = nouveau_nb
            serie_avant.valeur_monetaire = Decimal(nouveau_nb) * Decimal('500')
            serie_avant.commentaire = f"Fusion après transfert depuis {poste_origine.nom}"
            serie_avant.save()
            
            serie_apres.delete()
            return serie_avant
        
        # CAS 2: Fusion avec avant
        elif serie_avant:
            logger.info("→ Fusion avec série précédente")
            nouveau_nb = numero_dernier - serie_avant.numero_premier + 1
            
            serie_avant.numero_dernier = numero_dernier
            serie_avant.nombre_tickets = nouveau_nb
            serie_avant.valeur_monetaire = Decimal(nouveau_nb) * Decimal('500')
            serie_avant.commentaire = f"Étendue après transfert depuis {poste_origine.nom}"
            serie_avant.save()
            return serie_avant
        
        # CAS 3: Fusion avec après
        elif serie_apres:
            logger.info("→ Fusion avec série suivante")
            nouveau_nb = serie_apres.numero_dernier - numero_premier + 1
            
            serie_apres.numero_premier = numero_premier
            serie_apres.nombre_tickets = nouveau_nb
            serie_apres.valeur_monetaire = Decimal(nouveau_nb) * Decimal('500')
            serie_apres.commentaire = f"Étendue après transfert depuis {poste_origine.nom}"
            serie_apres.save()
            return serie_apres
        
        # CAS 4: Nouvelle série - création directe
        else:
            logger.info(f"→ Création nouvelle série: #{numero_premier}-{numero_dernier}")
            
            return SerieTicket.objects.create(
                poste=poste_destination,
                couleur=couleur,
                numero_premier=numero_premier,
                numero_dernier=numero_dernier,
                nombre_tickets=nombre_tickets,
                valeur_monetaire=montant,
                statut='stock',
                type_entree='transfert_recu',
                date_reception=timestamp,
                responsable_reception=user,
                commentaire=f"Reçu de {poste_origine.nom} - {commentaire}"
            )
    
    @staticmethod
    def _generer_bordereau():
        """Génère un numéro de bordereau unique"""
        from datetime import datetime
        from inventaire.models import HistoriqueStock
        
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        count_today = HistoriqueStock.objects.filter(
            type_stock='reapprovisionnement',
            date_mouvement__gte=today_start
        ).count()
        
        return f"TR-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}-{count_today+1:03d}"
    
    @staticmethod
    def _envoyer_notifications(poste_origine, poste_destination, couleur,
                               numero_premier, numero_dernier, montant, nombre_tickets,
                               numero_bordereau, user):
        """Envoie les notifications aux chefs de poste"""
        from accounts.models import NotificationUtilisateur, UtilisateurSUPPER
        
        # Chefs du poste origine
        chefs_origine = UtilisateurSUPPER.objects.filter(
            poste_affectation=poste_origine,
            habilitation__in=['chef_peage', 'chef_pesage'],
            is_active=True
        )
        
        for chef in chefs_origine:
            NotificationUtilisateur.objects.create(
                destinataire=chef,
                titre="Tickets cédés",
                message=(
                    f"Transfert de {nombre_tickets} tickets "
                    f"{couleur.libelle_affichage} #{numero_premier}-{numero_dernier} "
                    f"vers {poste_destination.nom}.\n"
                    f"Montant: {montant:,.0f} FCFA | Bordereau: {numero_bordereau}\n"
                    f"Effectué par: {user.get_full_name() or user.username}"
                ),
                type_notification='warning'
            )
        
        # Chefs du poste destination
        chefs_destination = UtilisateurSUPPER.objects.filter(
            poste_affectation=poste_destination,
            habilitation__in=['chef_peage', 'chef_pesage'],
            is_active=True
        )
        
        for chef in chefs_destination:
            NotificationUtilisateur.objects.create(
                destinataire=chef,
                titre="Tickets reçus",
                message=(
                    f"Réception de {nombre_tickets} tickets "
                    f"{couleur.libelle_affichage} #{numero_premier}-{numero_dernier} "
                    f"de {poste_origine.nom}.\n"
                    f"Montant: {montant:,.0f} FCFA | Bordereau: {numero_bordereau}\n"
                    f"Effectué par: {user.get_full_name() or user.username}"
                ),
                type_notification='success'
            )