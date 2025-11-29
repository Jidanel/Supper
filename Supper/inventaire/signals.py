

from datetime import date
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
import logging
from .models import *

logger = logging.getLogger('supper')

# Flag pour éviter la récursion dans les signaux
_signal_processing = set()


@receiver(post_save, sender='inventaire.InventaireJournalier')
def log_inventaire_creation_modification(sender, instance, created, **kwargs):
    """Journalise la création et modification d'inventaires + recalcul recettes"""
    try:
        from accounts.models import JournalAudit
        
        if created:
            action = "Création inventaire"
            details = f"Inventaire créé pour {instance.poste.nom} - {instance.date}"
            logger.info(f"Inventaire créé: {instance.poste.nom} du {instance.date}")
        else:
            action = "Modification inventaire"
            details = f"Inventaire modifié pour {instance.poste.nom} - {instance.date}"
        
        # Journaliser si un agent est associé
        if instance.agent_saisie:
            JournalAudit.objects.create(
                utilisateur=instance.agent_saisie,
                action=action,
                details=details,
                succes=True
            )
        
        # NOUVEAU: Recalculer les recettes associées
        _recalculer_recettes_associees(instance)
            
    except Exception as e:
        logger.error(f"Erreur signal inventaire: {str(e)}")

@receiver(post_save, sender='inventaire.DetailInventairePeriode')
def recalculate_totals_on_detail_save(sender, instance, created, **kwargs):
    """Recalcule automatiquement les totaux quand un détail est sauvegardé"""
    try:
        # Recalculer les totaux de l'inventaire parent
        inventaire = instance.inventaire
        inventaire.recalculer_totaux()
        
        # NOUVEAU: Recalculer les recettes liées
        _recalculer_recettes_associees(inventaire)
        
        if created:
            logger.debug(f"Détail ajouté: {instance.periode} - {instance.nombre_vehicules} véhicules")
            
    except Exception as e:
        logger.error(f"Erreur recalcul totaux: {str(e)}")


@receiver(post_delete, sender='inventaire.DetailInventairePeriode')
def recalculate_totals_on_detail_delete(sender, instance, **kwargs):
    """Recalcule automatiquement les totaux quand un détail est supprimé"""
    try:
        # Recalculer les totaux de l'inventaire parent
        inventaire = instance.inventaire
        inventaire.recalculer_totaux()
        
        # NOUVEAU: Recalculer les recettes liées
        _recalculer_recettes_associees(inventaire)
        
        logger.debug(f"Détail supprimé: {instance.periode}")
        
    except Exception as e:
        logger.error(f"Erreur recalcul totaux après suppression: {str(e)}")


@receiver(post_delete, sender='inventaire.DetailInventairePeriode')
def recalculate_totals_on_detail_delete(sender, instance, **kwargs):
    """Recalcule automatiquement les totaux quand un détail est supprimé"""
    # Éviter la récursion
    signal_key = f"detail_delete_{instance.pk}"
    if signal_key in _signal_processing:
        return
        
    try:
        _signal_processing.add(signal_key)
        
        # Recalculer les totaux de l'inventaire parent
        inventaire = instance.inventaire
        
        # CORRECTION: Recalcul direct sans sauvegarder l'inventaire pour éviter la récursion
        details = inventaire.details_periodes.all()
        total_vehicules = sum(detail.nombre_vehicules for detail in details)
        nombre_periodes = details.count()
        
        # Mise à jour directe en base sans déclencher les signaux
        InventaireJournalier = inventaire.__class__
        InventaireJournalier.objects.filter(pk=inventaire.pk).update(
            total_vehicules=total_vehicules,
            nombre_periodes_saisies=nombre_periodes
        )
        
        logger.debug(f"Détail supprimé: {instance.periode}")
        
    except Exception as e:
        logger.error(f"Erreur recalcul totaux après suppression: {str(e)}")
    finally:
        _signal_processing.discard(signal_key)


@receiver(post_save, sender='inventaire.RecetteJournaliere')
def log_recette_creation_modification(sender, instance, created, **kwargs):
    """Journalise la création et modification de recettes"""
    try:
        from accounts.models import JournalAudit
        
        if created:
            action = "Saisie recette"
            details = f"Recette saisie: {instance.montant_declare} FCFA pour {instance.poste.nom} - {instance.date}"
            logger.info(f"Recette saisie: {instance.poste.nom} du {instance.date} - {instance.montant_declare} FCFA")
        else:
            action = "Modification recette"
            details = f"Recette modifiée: {instance.montant_declare} FCFA pour {instance.poste.nom} - {instance.date}"
            
        # Ajouter les indicateurs calculés aux détails
        if instance.taux_deperdition is not None:
            details += f" | TD: {instance.taux_deperdition:.2f}%"
            details += f" | Statut: {instance.get_statut_deperdition()}"
            details += f" | Recette potentielle: {instance.recette_potentielle} FCFA"
            details += f" | Écart: {instance.ecart} FCFA"
        
        # Journaliser si un chef de poste est associé
        if instance.chef_poste:
            JournalAudit.objects.create(
                utilisateur=instance.chef_poste,
                action=action,
                details=details,
                succes=True
            )
            
    except Exception as e:
        logger.error(f"Erreur signal recette: {str(e)}")

def _recalculer_recettes_associees(inventaire):
    """
    Fonction utilitaire pour recalculer les recettes associées à un inventaire
    """
    try:
        from .models import RecetteJournaliere
        
        # Chercher les recettes pour ce poste et cette date
        recettes = RecetteJournaliere.objects.filter(
            poste=inventaire.poste,
            date=inventaire.date
        )
        
        for recette in recettes:
            # Associer l'inventaire si pas déjà fait
            if not recette.inventaire_associe:
                recette.inventaire_associe = inventaire
            
            # Recalculer les indicateurs
            recette.calculer_indicateurs()
            recette.save(update_fields=[
                'inventaire_associe', 'recette_potentielle', 
                'ecart', 'taux_deperdition'
            ])
            
            logger.info(f"Recette recalculée: {recette.poste.nom} du {recette.date} - TD: {recette.taux_deperdition:.2f}%")
    
    except Exception as e:
        logger.error(f"Erreur recalcul recettes associées: {str(e)}")


# @receiver(pre_save, sender='inventaire.InventaireJournalier')
# def log_inventaire_lock(sender, instance, **kwargs):
#     """Journalise le verrouillage d'inventaires"""
#     try:
#         if instance.pk:  # Si l'objet existe déjà
#             old_instance = sender.objects.get(pk=instance.pk)
            
#             # Détecter le verrouillage
#             if not old_instance.verrouille and instance.verrouille:
#                 logger.info(f"Inventaire verrouillé: {instance.poste.nom} du {instance.date}")
                
#                 # Optionnel: Journaliser le verrouillage
#                 if instance.agent_saisie:
#                     from accounts.models import JournalAudit
#                     JournalAudit.objects.create(
#                         utilisateur=instance.agent_saisie,
#                         action="Verrouillage inventaire",
#                         details=f"Inventaire verrouillé pour {instance.poste.nom} - {instance.date}",
#                         succes=True
#                     )
                
#             # Détecter la validation
#             if not old_instance.valide and instance.valide:
#                 logger.info(f"Inventaire validé: {instance.poste.nom} du {instance.date}")
                
#                 # Optionnel: Journaliser la validation
#                 if instance.agent_saisie:
#                     from accounts.models import JournalAudit
#                     JournalAudit.objects.create(
#                         utilisateur=instance.agent_saisie,
#                         action="Validation inventaire",
#                         details=f"Inventaire validé pour {instance.poste.nom} - {instance.date}",
#                         succes=True
#                     )
                
#     except Exception as e:
#         logger.error(f"Erreur signal verrouillage: {str(e)}")


@receiver(post_save, sender='inventaire.ConfigurationJour')
def log_jour_configuration(sender, instance, created, **kwargs):
    """Journalise la configuration des jours"""
    # Éviter la récursion
    signal_key = f"config_{instance.pk}_{created}"
    if signal_key in _signal_processing:
        return
        
    try:
        _signal_processing.add(signal_key)
        
        from accounts.models import JournalAudit
        
        if created:
            action = "Configuration jour"
            details = f"Jour configuré: {instance.date} - Statut: {instance.get_statut_display()}"
            
            if instance.commentaire:
                details += f" | Commentaire: {instance.commentaire}"
            
            # Journaliser si un utilisateur est associé
            if instance.cree_par:
                JournalAudit.objects.create(
                    utilisateur=instance.cree_par,
                    action=action,
                    details=details,
                    succes=True
                )
                
            logger.info(f"Configuration jour: {instance.date} -> {instance.get_statut_display()}")
        else:
            # Modification d'une configuration existante
            action = "Modification configuration jour"
            details = f"Configuration modifiée: {instance.date} - Nouveau statut: {instance.get_statut_display()}"
            
            if instance.commentaire:
                details += f" | Commentaire: {instance.commentaire}"
                
            if instance.cree_par:
                JournalAudit.objects.create(
                    utilisateur=instance.cree_par,
                    action=action,
                    details=details,
                    succes=True
                )
            
    except Exception as e:
        logger.error(f"Erreur signal configuration jour: {str(e)}")
    finally:
        _signal_processing.discard(signal_key)


# ===================================================================
# SIGNAUX ADDITIONNELS POUR UNE MEILLEURE TRAÇABILITÉ
# ===================================================================

@receiver(post_delete, sender='inventaire.InventaireJournalier')
def log_inventaire_deletion(sender, instance, **kwargs):
    """Journalise la suppression d'inventaires"""
    try:
        from accounts.models import JournalAudit
        
        # Créer une entrée de journal pour la suppression
        # Note: instance.agent_saisie pourrait ne plus être disponible
        JournalAudit.objects.create(
            utilisateur=None,  # Impossible de récupérer l'utilisateur après suppression
            action="Suppression inventaire",
            details=f"Inventaire supprimé: {instance.poste.nom} du {instance.date} | Total véhicules: {instance.total_vehicules}",
            succes=True
        )
        
        logger.warning(f"Inventaire supprimé: {instance.poste.nom} du {instance.date}")
        
    except Exception as e:
        logger.error(f"Erreur signal suppression inventaire: {str(e)}")


@receiver(post_delete, sender='inventaire.RecetteJournaliere')
def log_recette_deletion(sender, instance, **kwargs):
    """Journalise la suppression de recettes"""
    try:
        from accounts.models import JournalAudit
        
        # Créer une entrée de journal pour la suppression
        JournalAudit.objects.create(
            utilisateur=None,  # Impossible de récupérer l'utilisateur après suppression
            action="Suppression recette",
            details=f"Recette supprimée: {instance.poste.nom} du {instance.date} | Montant: {instance.montant_declare} FCFA",
            succes=True
        )
        
        logger.warning(f"Recette supprimée: {instance.poste.nom} du {instance.date} - {instance.montant_declare} FCFA")
        
    except Exception as e:
        logger.error(f"Erreur signal suppression recette: {str(e)}")


# ===================================================================
# UTILITAIRES POUR LA MAINTENANCE DES SIGNAUX
# ===================================================================

def clear_signal_processing_cache():
    """Nettoie le cache des signaux en cours de traitement"""
    global _signal_processing
    _signal_processing.clear()
    logger.debug("Cache des signaux nettoyé")


def get_signal_processing_status():
    """Retourne le statut actuel des signaux en cours de traitement"""
    return dict(
        active_signals=list(_signal_processing),
        count=len(_signal_processing)
    )

@receiver(post_save, sender='inventaire.RecetteJournaliere')
def auto_link_inventaire_recette(sender, instance, created, **kwargs):
    """Lie automatiquement une recette à son inventaire correspondant"""
    if not instance.inventaire_associe:
        try:
            from .models import InventaireJournalier
            
            inventaire = InventaireJournalier.objects.get(
                poste=instance.poste,
                date=instance.date
            )
            
            instance.inventaire_associe = inventaire
            # Éviter la récursion en utilisant update_fields
            instance.save(update_fields=['inventaire_associe'])
            
            logger.info(f"Inventaire automatiquement lié à la recette: {instance.poste.nom} du {instance.date}")
            
        except InventaireJournalier.DoesNotExist:
            logger.warning(f"Aucun inventaire trouvé pour la recette: {instance.poste.nom} du {instance.date}")
        except Exception as e:
            logger.error(f"Erreur liaison auto inventaire-recette: {str(e)}")




# Variable globale pour tracker la dernière date de snapshot
_derniere_date_snapshot = None


def creer_snapshots_quotidiens():
    """
    ✅ Crée les snapshots de stock pour tous les postes actifs
    À appeler automatiquement à minuit
    """
    from accounts.models import Poste
    from inventaire.models import SnapshotStockJournalier
    import logging
    
    logger = logging.getLogger('supper')
    
    global _derniere_date_snapshot
    date_aujourdhui = date.today()
    
    # Éviter de créer plusieurs fois le même jour
    if _derniere_date_snapshot == date_aujourdhui:
        return
    
    logger.info(f"🔄 Création des snapshots de stock pour le {date_aujourdhui}")
    
    postes_actifs = Poste.objects.filter(is_active=True)
    count_success = 0
    count_error = 0
    
    for poste in postes_actifs:
        try:
            # Créer snapshot pour hier (stock de fin de journée)
            hier = date_aujourdhui - timedelta(days=1)
            snapshot = SnapshotStockJournalier.creer_snapshot(poste, hier)
            count_success += 1
            logger.debug(f"✅ Snapshot créé: {poste.nom} - {hier} - {snapshot.stock_total_quantite} tickets")
        except Exception as e:
            count_error += 1
            logger.error(f"❌ Erreur snapshot {poste.nom}: {str(e)}")
    
    _derniere_date_snapshot = date_aujourdhui
    logger.info(f"✅ Snapshots créés: {count_success} OK, {count_error} erreurs")


@receiver(post_save, sender='inventaire.SerieTicket')
def verifier_creation_snapshot_apres_mouvement(sender, instance, created, **kwargs):
    """
    ✅ Vérifie si on doit créer un snapshot après un mouvement de stock
    """
    from datetime import datetime
    
    global _derniere_date_snapshot
    date_aujourdhui = date.today()
    heure_actuelle = datetime.now().time()
    
    # Si c'est un nouveau jour ET qu'on n'a pas encore créé le snapshot
    if _derniere_date_snapshot != date_aujourdhui:
        # Créer les snapshots à partir de 00:05 (laisser 5 min de marge)
        if heure_actuelle.hour == 0 and heure_actuelle.minute >= 5:
            creer_snapshots_quotidiens()

