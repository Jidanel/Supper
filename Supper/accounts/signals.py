# ===================================================================
# accounts/signals.py - Signaux pour l'application accounts
# ===================================================================

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.utils import timezone
import logging

logger = logging.getLogger('supper')


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Journalise les connexions d'utilisateurs"""
    try:
        from .models import JournalAudit
        
        ip = request.META.get('REMOTE_ADDR', 'Unknown')
        user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')[:500]
        
        JournalAudit.objects.create(
            utilisateur=user,
            action="Connexion utilisateur",
            details=f"Connexion réussie depuis {ip}",
            adresse_ip=ip,
            user_agent=user_agent,
            session_key=request.session.session_key,
            url_acces='/accounts/login/',
            methode_http='POST',
            succes=True
        )
        
        logger.info(f"Connexion: {user.username} depuis {ip}")
        
    except Exception as e:
        logger.error(f"Erreur lors de la journalisation de connexion: {str(e)}")


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Journalise les déconnexions d'utilisateurs"""
    if user:
        try:
            from .models import JournalAudit
            
            ip = request.META.get('REMOTE_ADDR', 'Unknown')
            
            JournalAudit.objects.create(
                utilisateur=user,
                action="Déconnexion utilisateur",
                details=f"Déconnexion depuis {ip}",
                adresse_ip=ip,
                session_key=request.session.session_key,
                url_acces='/accounts/logout/',
                succes=True
            )
            
            logger.info(f"Déconnexion: {user.username}")
            
        except Exception as e:
            logger.error(f"Erreur lors de la journalisation de déconnexion: {str(e)}")


@receiver(post_save, sender='accounts.UtilisateurSUPPER')
def log_user_creation_modification(sender, instance, created, **kwargs):
    """Journalise la création et modification d'utilisateurs"""
    try:
        from .models import JournalAudit
        
        if created:
            action = "Création utilisateur"
            details = f"Nouvel utilisateur créé: {instance.username} ({instance.nom_complet})"
            
            # Journaliser avec l'utilisateur qui a créé le compte
            if instance.cree_par:
                JournalAudit.objects.create(
                    utilisateur=instance.cree_par,
                    action=action,
                    details=details,
                    succes=True
                )
                logger.info(f"Création utilisateur: {instance.username} par {instance.cree_par.username}")
        else:
            action = "Modification utilisateur"
            details = f"Utilisateur modifié: {instance.username} ({instance.nom_complet})"
            logger.info(f"Modification utilisateur: {instance.username}")
            
    except Exception as e:
        logger.error(f"Erreur signal utilisateur: {str(e)}")


@receiver(post_save, sender='accounts.Poste')
def log_poste_creation_modification(sender, instance, created, **kwargs):
    """Journalise la création et modification de postes"""
    try:
        if created:
            logger.info(f"Nouveau poste créé: {instance.nom} ({instance.code})")
        else:
            logger.info(f"Poste modifié: {instance.nom} ({instance.code})")
            
    except Exception as e:
        logger.error(f"Erreur signal poste: {str(e)}")