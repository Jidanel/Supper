# ===================================================================
# Fichier : accounts/signals.py - VERSION CORRIGÉE FINALE
# Signaux alignés sur les champs réels du modèle
# ===================================================================

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.admin.models import LogEntry
from django.utils import timezone
import logging

logger = logging.getLogger('supper')


# ===================================================================
# SIGNAUX D'AUTHENTIFICATION
# ===================================================================

@receiver(user_logged_in)
def log_user_login_and_redirect(sender, request, user, **kwargs):
    """
    Journalise les connexions ET gère la redirection automatique
    ADMINS → Panel Django | UTILISATEURS → Interface web
    """
    try:
        from .models import JournalAudit
        
        # Obtenir l'IP du client
        ip = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:200]
        
        # Déterminer le type d'interface selon le rôle
        is_admin = is_admin_user(user)
        interface_type = "Panel Django Admin" if is_admin else "Interface Web"
        
        # Construire les détails de connexion
        details = [
            f"Connexion réussie",
            f"Rôle: {user.habilitation}",
            f"Interface: {interface_type}",
            f"Poste: {user.poste_affectation.nom if user.poste_affectation else 'Aucun'}",
            f"Dernière connexion: {user.last_login.strftime('%d/%m/%Y %H:%M') if user.last_login else 'Première connexion'}"
        ]
        
        JournalAudit.objects.create(
            utilisateur=user,
            action="CONNEXION",
            details=" | ".join(details),
            adresse_ip=ip,
            user_agent=user_agent,
            url_acces=request.path,
            methode_http=request.method,
            succes=True
        )
        
        # Log selon l'interface
        if is_admin:
            logger.info(
                f"CONNEXION ADMIN → Panel Django - {user.username} ({user.nom_complet}) - "
                f"Rôle: {user.habilitation} - IP: {ip}"
            )
        else:
            logger.info(
                f"CONNEXION UTILISATEUR → Interface Web - {user.username} ({user.nom_complet}) - "
                f"Rôle: {user.habilitation} - IP: {ip}"
            )
        
        # REDIRECTION AUTOMATIQUE - Stocker dans la session
        request.session['redirect_after_login'] = get_redirect_url_for_user(user)
        
    except Exception as e:
        logger.error(f"Erreur journalisation connexion: {str(e)}")


def is_admin_user(user):
    """
    Détermine si un utilisateur est un administrateur
    ADMINS : superuser, staff, admin_principal, coord_psrr, serv_info, serv_emission
    """
    if user.is_superuser or user.is_staff:
        return True
    
    admin_roles = [
        'admin_principal',
        'coord_psrr', 
        'serv_info',
        'serv_emission'
    ]
    
    return getattr(user, 'habilitation', None) in admin_roles


def get_redirect_url_for_user(user):
    """
    Retourne l'URL de redirection selon le rôle utilisateur
    ADMINS → /admin/ | UTILISATEURS → /dashboard/
    """
    if is_admin_user(user):
        # Admins vers le panel Django
        return '/admin/'
    else:
        # Utilisateurs normaux vers l'interface web selon leur rôle
        if user.habilitation in ['chef_peage', 'chef_pesage']:
            return '/dashboard/chef/'
        elif user.habilitation == 'agent_inventaire':
            return '/dashboard/agent/'
        else:
            return '/dashboard/'


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Journalise les déconnexions utilisateur"""
    try:
        from .models import JournalAudit
        
        if user and user.is_authenticated:
            ip = get_client_ip(request)
            
            # Déterminer le type d'interface utilisée
            interface_type = "Panel Django Admin" if is_admin_user(user) else "Interface Web"
            
            # Calculer la durée de la session si possible
            session_duration = "Inconnue"
            if hasattr(request, 'session') and request.session.get('_auth_user_id'):
                # Ici on pourrait calculer la durée depuis la dernière connexion
                pass
            
            details = [
                f"Déconnexion {interface_type}",
                f"Durée session: {session_duration}",
                f"Pages visitées: {request.session.get('pages_visited', 0) if request.session else 0}"
            ]
            
            JournalAudit.objects.create(
                utilisateur=user,
                action="DÉCONNEXION",
                details=" | ".join(details),
                adresse_ip=ip,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:200],
                url_acces=request.path if request else '/',
                methode_http=request.method if request else 'GET',
                succes=True
            )
            
            logger.info(f"DÉCONNEXION - {user.username} - Interface: {interface_type} - IP: {ip}")
            
    except Exception as e:
        logger.error(f"Erreur journalisation déconnexion: {str(e)}")


# ===================================================================
# SIGNAUX UTILISATEURS
# ===================================================================

@receiver(pre_save, sender='accounts.UtilisateurSUPPER')
def log_user_before_save(sender, instance, **kwargs):
    """Capturer l'état avant modification pour comparaison"""
    if instance.pk:  # Modification d'un utilisateur existant
        try:
            # Récupérer l'ancienne version
            old_instance = sender.objects.get(pk=instance.pk)
            instance._old_values = {
                'nom_complet': old_instance.nom_complet,
                'habilitation': old_instance.habilitation,
                'poste_affectation': old_instance.poste_affectation,
                'is_active': old_instance.is_active,
                'telephone': old_instance.telephone,
                'email': old_instance.email,
            }
        except sender.DoesNotExist:
            instance._old_values = {}
    else:
        instance._old_values = {}


@receiver(post_save, sender='accounts.UtilisateurSUPPER')
def log_utilisateur_creation_modification(sender, instance, created, **kwargs):
    """Journalise la création et modification d'utilisateurs avec détails"""
    try:
        from .models import JournalAudit
        
        if created:
            # Création d'un nouvel utilisateur
            action = "CRÉATION UTILISATEUR"
            details = [
                f"Nouvel utilisateur créé: {instance.username} ({instance.nom_complet})",
                f"Rôle assigné: {instance.get_habilitation_display()}",
                f"Poste d'affectation: {instance.poste_affectation.nom if instance.poste_affectation else 'Aucun'}",
                f"Téléphone: {instance.telephone}",
                f"Email: {instance.email or 'Non renseigné'}",
                f"Compte actif: {'Oui' if instance.is_active else 'Non'}"
            ]
            
            # Utiliser l'utilisateur qui a créé le compte
            utilisateur_createur = instance.cree_par if instance.cree_par else get_current_user_from_context()
            
            if utilisateur_createur:
                JournalAudit.objects.create(
                    utilisateur=utilisateur_createur,
                    action=action,
                    details=" | ".join(details),
                    succes=True
                )
            
            logger.info(f"CRÉATION UTILISATEUR - {instance.username} ({instance.nom_complet})")
            
        else:
            # Modification d'un utilisateur existant
            action = "MODIFICATION UTILISATEUR"
            
            # Détecter les changements
            changes = []
            old_values = getattr(instance, '_old_values', {})
            
            for field, old_value in old_values.items():
                new_value = getattr(instance, field)
                if old_value != new_value:
                    if field == 'poste_affectation':
                        old_str = old_value.nom if old_value else 'Aucun'
                        new_str = new_value.nom if new_value else 'Aucun'
                        changes.append(f"{field}: {old_str} → {new_str}")
                    elif field == 'habilitation':
                        changes.append(f"Rôle: {old_value} → {new_value}")
                    elif field == 'is_active':
                        status_old = 'Actif' if old_value else 'Inactif'
                        status_new = 'Actif' if new_value else 'Inactif'
                        changes.append(f"Statut: {status_old} → {status_new}")
                    else:
                        changes.append(f"{field}: {old_value} → {new_value}")
            
            if changes:
                details = [
                    f"Utilisateur modifié: {instance.username} ({instance.nom_complet})",
                    f"Modifications: {', '.join(changes)}"
                ]
            else:
                details = [f"Utilisateur consulté/sauvegardé sans modification: {instance.username}"]
            
            current_user = get_current_user_from_context()
            if current_user:
                JournalAudit.objects.create(
                    utilisateur=current_user,
                    action=action,
                    details=" | ".join(details),
                    succes=True
                )
            
            logger.info(f"MODIFICATION UTILISATEUR - {instance.username}")
            
    except Exception as e:
        logger.error(f"Erreur signal utilisateur: {str(e)}")


@receiver(post_delete, sender='accounts.UtilisateurSUPPER')
def log_utilisateur_suppression(sender, instance, **kwargs):
    """Journalise la suppression d'utilisateurs"""
    try:
        from .models import JournalAudit
        
        current_user = get_current_user_from_context()
        
        action = "SUPPRESSION UTILISATEUR"
        details = [
            f"Utilisateur supprimé: {instance.username} ({instance.nom_complet})",
            f"Rôle: {instance.get_habilitation_display()}",
            f"Poste: {instance.poste_affectation.nom if instance.poste_affectation else 'Aucun'}",
            f"Compte créé le: {instance.date_joined.strftime('%d/%m/%Y')}",
            f"Dernière connexion: {instance.last_login.strftime('%d/%m/%Y %H:%M') if instance.last_login else 'Jamais'}"
        ]
        
        if current_user:
            JournalAudit.objects.create(
                utilisateur=current_user,
                action=action,
                details=" | ".join(details),
                succes=True
            )
        
        logger.warning(f"SUPPRESSION UTILISATEUR - {instance.username} ({instance.nom_complet})")
        
    except Exception as e:
        logger.error(f"Erreur signal suppression utilisateur: {str(e)}")


# ===================================================================
# SIGNAUX POSTES
# ===================================================================

@receiver(pre_save, sender='accounts.Poste')
def log_poste_before_save(sender, instance, **kwargs):
    """Capturer l'état avant modification du poste"""
    if instance.pk:  # Modification d'un poste existant
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            instance._old_values = {
                'nom': old_instance.nom,
                'code': old_instance.code,
                'type': old_instance.type,
                'region': old_instance.region,
                'departement': old_instance.departement,
                'axe_routier': old_instance.axe_routier,  # CHANGEMENT : axe_routier au lieu d'arrondissement
                'description': old_instance.description,
                'is_active': old_instance.is_active,
                'latitude': old_instance.latitude,
                'longitude': old_instance.longitude,
            }
        except sender.DoesNotExist:
            instance._old_values = {}
    else:
        instance._old_values = {}

@receiver(post_save, sender='accounts.Poste')
def log_poste_creation_modification(sender, instance, created, **kwargs):
    """Journalise la création et modification de postes avec détails complets"""
    try:
        from .models import JournalAudit
        
        current_user = get_current_user_from_context()
        
        if created:
            # Création d'un nouveau poste
            action = "CRÉATION POSTE"
            details = [
                f"Nouveau poste créé: {instance.nom} (Code: {instance.code})",
                f"Type: {instance.get_type_display()}",
                f"Région: {instance.region}",
                f"Département: {instance.departement}",
                f"Axe routier: {instance.axe_routier or 'Non renseigné'}",  # CHANGEMENT
                f"Coordonnées GPS: {instance.coordonnees_gps or 'Non renseignées'}",
                f"Statut: {'Actif' if instance.is_active else 'Inactif'}"
            ]
            
        else:
            # Modification d'un poste existant
            action = "MODIFICATION POSTE"
            
            # Détecter les changements
            changes = []
            old_values = getattr(instance, '_old_values', {})
            
            for field, old_value in old_values.items():
                new_value = getattr(instance, field)
                if old_value != new_value:
                    if field == 'type':
                        old_display = dict(sender.TypePoste.choices).get(old_value, old_value)
                        new_display = instance.get_type_display()
                        changes.append(f"Type: {old_display} → {new_display}")
                    elif field == 'is_active':
                        status_old = 'Actif' if old_value else 'Inactif'
                        status_new = 'Actif' if new_value else 'Inactif'
                        changes.append(f"Statut: {status_old} → {status_new}")
                    elif field in ['latitude', 'longitude']:
                        if old_value != new_value:
                            changes.append(f"Coordonnées GPS mises à jour")
                    else:
                        changes.append(f"{field}: {old_value} → {new_value}")
            
            if changes:
                details = [
                    f"Poste modifié: {instance.nom} (Code: {instance.code})",
                    f"Modifications: {', '.join(changes)}"
                ]
            else:
                details = [f"Poste consulté/sauvegardé sans modification: {instance.nom}"]
        
        if current_user:
            JournalAudit.objects.create(
                utilisateur=current_user,
                action=action,
                details=" | ".join(details),
                succes=True
            )
        
        logger.info(f"{'CRÉATION' if created else 'MODIFICATION'} POSTE - {instance.nom} ({instance.code})")
        
    except Exception as e:
        logger.error(f"Erreur signal poste: {str(e)}")

@receiver(post_delete, sender='accounts.Poste')
def log_poste_suppression(sender, instance, **kwargs):
    """Journalise la suppression de postes"""
    try:
        from .models import JournalAudit
        
        current_user = get_current_user_from_context()
        
        action = "SUPPRESSION POSTE"
        details = [
            f"Poste supprimé: {instance.nom} (Code: {instance.code})",
            f"Type: {instance.get_type_display()}",
            f"Région: {instance.region}",
            f"Département: {instance.departement}",
            f"Axe routier: {instance.axe_routier or 'Non renseigné'}",  # CHANGEMENT
            f"Créé le: {instance.date_creation.strftime('%d/%m/%Y')}"
        ]
        
        if current_user:
            JournalAudit.objects.create(
                utilisateur=current_user,
                action=action,
                details=" | ".join(details),
                succes=True
            )
        
        logger.warning(f"SUPPRESSION POSTE - {instance.nom} ({instance.code})")
        
    except Exception as e:
        logger.error(f"Erreur signal suppression poste: {str(e)}")


# ===================================================================
# EXEMPLES D'AXES ROUTIERS CAMEROUNAIS POUR RÉFÉRENCE
# ===================================================================

"""
PRINCIPAUX AXES ROUTIERS DU CAMEROUN :

AXES NORD-SUD :
- Yaoundé - Douala (A4)
- Douala - Bafoussam - Bamenda 
- Yaoundé - Sangmélima - Ebolowa
- Bertoua - Garoua-Boulaï (frontière RCA)

AXES EST-OUEST :
- Douala - Yaoundé - Bertoua - Garoua-Boulaï
- Bafoussam - Foumban - Ngaoundéré
- Bamenda - Wum - Mamfe

AXES VERS LE NORD :
- Yaoundé - Bafia - Foumban - Ngaoundéré
- Ngaoundéré - Garoua - Maroua - Kousseri
- Garoua - Mora - Mokolo

AXES VERS L'OUEST :
- Douala - Buea - Limbe
- Bamenda - Mamfe - Ekok (frontière Nigeria)
- Bafoussam - Dschang - Melong

AXES TRANSFRONTALIERS :
- Yaoundé - Ebolowa - Ambam (Guinée Équatoriale)
- Douala - Kribi - Campo (Guinée Équatoriale)
- Bertoua - Garoua-Boulaï (République Centrafricaine)
- Ngaoundéré - Moundou (Tchad)
- Maroua - Kousseri (Tchad)
- Bamenda - Mamfe - Ekok (Nigeria)
"""

# ===================================================================
# SIGNAUX NOTIFICATIONS
# ===================================================================

@receiver(post_save, sender='accounts.NotificationUtilisateur')
def log_notification_creation(sender, instance, created, **kwargs):
    """Journalise la création et modification de notifications"""
    try:
        from .models import JournalAudit
        
        if created:
            action = "CRÉATION NOTIFICATION"
            details = [
                f"Nouvelle notification: {instance.titre}",
                f"Destinataire: {instance.destinataire.nom_complet}",
                f"Expéditeur: {instance.cree_par.nom_complet if instance.cree_par else 'Système'}",
                f"Type: {instance.get_type_notification_display()}",
                f"Message: {instance.message[:100]}{'...' if len(instance.message) > 100 else ''}"
            ]
            
            current_user = get_current_user_from_context()
            if current_user:
                JournalAudit.objects.create(
                    utilisateur=current_user,
                    action=action,
                    details=" | ".join(details),
                    succes=True
                )
            
            logger.info(f"CRÉATION NOTIFICATION - {instance.titre} → {instance.destinataire.nom_complet}")
        
    except Exception as e:
        logger.error(f"Erreur signal notification: {str(e)}")


# ===================================================================
# SIGNAUX PANEL ADMIN DJANGO
# ===================================================================

@receiver(post_save, sender=LogEntry)
def log_admin_actions(sender, instance, created, **kwargs):
    """Journalise les actions effectuées dans le panel admin Django"""
    try:
        from .models import JournalAudit
        
        if created and instance.user:
            action = f"ADMIN PANEL - {instance.get_action_flag_display().upper()}"
            
            # Construire les détails de l'action
            object_name = str(instance.object_repr) if instance.object_repr else "Objet"
            model_name = instance.content_type.model if instance.content_type else "Modèle"
            app_name = instance.content_type.app_label if instance.content_type else "App"
            
            details = [
                f"Action admin: {instance.get_action_flag_display()}",
                f"Application: {app_name}",
                f"Modèle: {model_name}",
                f"Objet: {object_name}"
            ]
            
            if instance.change_message:
                details.append(f"Modifications: {instance.change_message}")
            
            JournalAudit.objects.create(
                utilisateur=instance.user,
                action=action,
                details=" | ".join(details),
                succes=True
            )
            
            logger.info(f"ADMIN ACTION - {instance.user.username} - {action} - {object_name}")
            
    except Exception as e:
        logger.error(f"Erreur journalisation action admin: {str(e)}")


# ===================================================================
# FONCTIONS UTILITAIRES
# ===================================================================

def get_client_ip(request):
    """Obtenir l'adresse IP réelle du client"""
    if not request:
        return None
    
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_current_user_from_context():
    """
    Essayer de récupérer l'utilisateur actuel du contexte
    Fallback vers un administrateur si pas disponible
    """
    try:
        # Essayer d'importer et utiliser le middleware de contexte
        from common.middleware import get_current_user
        user = get_current_user()
        if user and user.is_authenticated:
            return user
    except ImportError:
        pass
    
    # Fallback : utiliser un administrateur par défaut
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin_user = User.objects.filter(is_superuser=True).first()
        return admin_user
    except Exception:
        return None


def get_model_changes(old_instance, new_instance, fields_to_check):
    """
    Utilitaire pour détecter les changements entre deux instances d'un modèle
    """
    changes = []
    
    for field in fields_to_check:
        old_value = getattr(old_instance, field, None)
        new_value = getattr(new_instance, field, None)
        
        if old_value != new_value:
            changes.append({
                'field': field,
                'old_value': old_value,
                'new_value': new_value
            })
    
    return changes


def format_change_message(changes):
    """
    Formater les changements en message lisible
    """
    if not changes:
        return "Aucune modification"
    
    messages = []
    for change in changes:
        field = change['field']
        old = change['old_value']
        new = change['new_value']
        
        messages.append(f"{field}: {old} → {new}")
    
    return ", ".join(messages)