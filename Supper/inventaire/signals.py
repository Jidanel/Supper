# ===================================================================
# inventaire/signals.py - Signaux pour l'application inventaire
# ===================================================================

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
import logging

logger = logging.getLogger('supper')


@receiver(post_save, sender='inventaire.InventaireJournalier')
def log_inventaire_creation_modification(sender, instance, created, **kwargs):
    """Journalise la création et modification d'inventaires"""
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
            
    except Exception as e:
        logger.error(f"Erreur signal inventaire: {str(e)}")


@receiver(post_save, sender='inventaire.DetailInventairePeriode')
def recalculate_totals_on_detail_save(sender, instance, created, **kwargs):
    """Recalcule automatiquement les totaux quand un détail est sauvegardé"""
    try:
        # Recalculer les totaux de l'inventaire parent
        inventaire = instance.inventaire
        inventaire.recalculer_totaux()
        
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
        
        logger.debug(f"Détail supprimé: {instance.periode}")
        
    except Exception as e:
        logger.error(f"Erreur recalcul totaux après suppression: {str(e)}")


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
            details += f" | Taux déperdition: {instance.taux_deperdition}%"
            details += f" | Couleur alerte: {instance.get_couleur_alerte()}"
        
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


@receiver(pre_save, sender='inventaire.InventaireJournalier')
def log_inventaire_lock(sender, instance, **kwargs):
    """Journalise le verrouillage d'inventaires"""
    try:
        if instance.pk:  # Si l'objet existe déjà
            old_instance = sender.objects.get(pk=instance.pk)
            
            # Détecter le verrouillage
            if not old_instance.verrouille and instance.verrouille:
                logger.info(f"Inventaire verrouillé: {instance.poste.nom} du {instance.date}")
                
            # Détecter la validation
            if not old_instance.valide and instance.valide:
                logger.info(f"Inventaire validé: {instance.poste.nom} du {instance.date}")
                
    except Exception as e:
        logger.error(f"Erreur signal verrouillage: {str(e)}")


@receiver(post_save, sender='inventaire.ConfigurationJour')
def log_jour_configuration(sender, instance, created, **kwargs):
    """Journalise la configuration des jours"""
    try:
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
            
    except Exception as e:
        logger.error(f"Erreur signal configuration jour: {str(e)}")