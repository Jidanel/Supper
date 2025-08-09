# ===================================================================
# inventaire/signals.py - Signaux pour l'application inventaire
# VERSION CORRIGÉE FINALE - REMPLACER ENTIÈREMENT LE FICHIER EXISTANT
# ===================================================================

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
import logging

logger = logging.getLogger('supper')

# Flag pour éviter la récursion dans les signaux
_signal_processing = set()


@receiver(post_save, sender='inventaire.InventaireJournalier')
def log_inventaire_creation_modification(sender, instance, created, **kwargs):
    """Journalise la création et modification d'inventaires"""
    # Éviter la récursion
    signal_key = f"inventaire_{instance.pk}_{created}"
    if signal_key in _signal_processing:
        return
    
    try:
        _signal_processing.add(signal_key)
        
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
    finally:
        _signal_processing.discard(signal_key)


@receiver(post_save, sender='inventaire.DetailInventairePeriode')
def recalculate_totals_on_detail_save(sender, instance, created, **kwargs):
    """Recalcule automatiquement les totaux quand un détail est sauvegardé"""
    # Éviter la récursion
    signal_key = f"detail_{instance.pk}_{created}"
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
        
        if created:
            logger.debug(f"Détail ajouté: {instance.periode} - {instance.nombre_vehicules} véhicules")
            
    except Exception as e:
        logger.error(f"Erreur recalcul totaux: {str(e)}")
    finally:
        _signal_processing.discard(signal_key)


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
    # Éviter la récursion
    signal_key = f"recette_{instance.pk}_{created}"
    if signal_key in _signal_processing:
        return
        
    try:
        _signal_processing.add(signal_key)
        
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
    finally:
        _signal_processing.discard(signal_key)


@receiver(pre_save, sender='inventaire.InventaireJournalier')
def log_inventaire_lock(sender, instance, **kwargs):
    """Journalise le verrouillage d'inventaires"""
    try:
        if instance.pk:  # Si l'objet existe déjà
            old_instance = sender.objects.get(pk=instance.pk)
            
            # Détecter le verrouillage
            if not old_instance.verrouille and instance.verrouille:
                logger.info(f"Inventaire verrouillé: {instance.poste.nom} du {instance.date}")
                
                # Optionnel: Journaliser le verrouillage
                if instance.agent_saisie:
                    from accounts.models import JournalAudit
                    JournalAudit.objects.create(
                        utilisateur=instance.agent_saisie,
                        action="Verrouillage inventaire",
                        details=f"Inventaire verrouillé pour {instance.poste.nom} - {instance.date}",
                        succes=True
                    )
                
            # Détecter la validation
            if not old_instance.valide and instance.valide:
                logger.info(f"Inventaire validé: {instance.poste.nom} du {instance.date}")
                
                # Optionnel: Journaliser la validation
                if instance.agent_saisie:
                    from accounts.models import JournalAudit
                    JournalAudit.objects.create(
                        utilisateur=instance.agent_saisie,
                        action="Validation inventaire",
                        details=f"Inventaire validé pour {instance.poste.nom} - {instance.date}",
                        succes=True
                    )
                
    except Exception as e:
        logger.error(f"Erreur signal verrouillage: {str(e)}")


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