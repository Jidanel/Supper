# ===================================================================
# Fichier : accounts/signals.py - VERSION MISE À JOUR
# Signaux alignés avec les nouvelles habilitations granulaires
# du modèle UtilisateurSUPPER selon la matrice PDF
# ===================================================================

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.contrib.admin.models import LogEntry
from django.utils import timezone
import logging

logger = logging.getLogger('supper')


# ===================================================================
# CLASSIFICATION DES HABILITATIONS
# Alignée avec accounts/forms.py et accounts/models.py
# ===================================================================

# Administrateurs avec accès complet au système
HABILITATIONS_ADMIN = [
    'admin_principal',      # Administrateur Principal
    'coord_psrr',           # Coordonnateur PSRR
    'serv_info',            # Service Informatique
]

# Services centraux avec accès étendu
HABILITATIONS_SERVICES_CENTRAUX = [
    'serv_emission',        # Service Émission et Recouvrement
    'chef_ag',              # Chef Service Affaires Générales
    'serv_controle',        # Service Contrôle et Validation
    'serv_ordre',           # Service Ordre/Secrétariat
]

# CISOP (Cellule d'Intervention et de Suivi des Opérations)
HABILITATIONS_CISOP = [
    'cisop_peage',          # CISOP Péage
    'cisop_pesage',         # CISOP Pesage
]

# Chefs de poste
HABILITATIONS_CHEFS = [
    'chef_peage',           # Chef de Poste Péage
    'chef_station_pesage',  # Chef de Station Pesage
]

# Agents opérationnels pesage
HABILITATIONS_OPERATIONNELS_PESAGE = [
    'regisseur_pesage',     # Régisseur de Station Pesage
    'chef_equipe_pesage',   # Chef d'Équipe Pesage
]

# Autres rôles
HABILITATIONS_AUTRES = [
    'focal_regional',       # Point Focal Régional
    'chef_service',         # Chef de Service
    'regisseur',            # Régisseur Central
    'comptable_mat',        # Comptable Matières
    'imprimerie',           # Imprimerie Nationale
    'agent_inventaire',     # Agent Inventaire
    'caissier',             # Caissier
]

# Anciens noms pour rétrocompatibilité
HABILITATIONS_LEGACY = {
    'chef_ordre': 'serv_ordre',
    'chef_controle': 'serv_controle',
    'chef_pesage': 'chef_station_pesage',
}


# ===================================================================
# FONCTIONS DE CLASSIFICATION DES UTILISATEURS
# ===================================================================

def get_habilitation_normalisee(habilitation):
    """
    Normalise une habilitation en gérant les alias legacy
    """
    return HABILITATIONS_LEGACY.get(habilitation, habilitation)


def is_admin_user(user):
    """
    Détermine si un utilisateur est un administrateur système
    ADMINS : superuser, staff, admin_principal, coord_psrr, serv_info
    """
    if not user or not hasattr(user, 'is_authenticated'):
        return False
    
    if not user.is_authenticated:
        return False
    
    if user.is_superuser or user.is_staff:
        return True
    
    habilitation = get_habilitation_normalisee(getattr(user, 'habilitation', None))
    return habilitation in HABILITATIONS_ADMIN


def is_service_central(user):
    """
    Vérifie si l'utilisateur appartient à un service central
    """
    if not user or not hasattr(user, 'habilitation'):
        return False
    
    habilitation = get_habilitation_normalisee(user.habilitation)
    return habilitation in (HABILITATIONS_ADMIN + HABILITATIONS_SERVICES_CENTRAUX)


def is_cisop(user):
    """
    Vérifie si l'utilisateur est un agent CISOP
    """
    if not user or not hasattr(user, 'habilitation'):
        return False
    
    habilitation = get_habilitation_normalisee(user.habilitation)
    return habilitation in HABILITATIONS_CISOP


def is_chef_poste(user):
    """
    Vérifie si l'utilisateur est un chef de poste (péage ou pesage)
    """
    if not user or not hasattr(user, 'habilitation'):
        return False
    
    habilitation = get_habilitation_normalisee(user.habilitation)
    return habilitation in HABILITATIONS_CHEFS


def is_operationnel_pesage(user):
    """
    Vérifie si l'utilisateur est un opérationnel pesage
    """
    if not user or not hasattr(user, 'habilitation'):
        return False
    
    habilitation = get_habilitation_normalisee(user.habilitation)
    return habilitation in HABILITATIONS_OPERATIONNELS_PESAGE


def get_user_category(user):
    """
    Retourne la catégorie de l'utilisateur pour la journalisation
    """
    if not user or not hasattr(user, 'habilitation'):
        return "INCONNU"
    
    if user.is_superuser:
        return "SUPERADMIN"
    
    habilitation = get_habilitation_normalisee(user.habilitation)
    
    if habilitation in HABILITATIONS_ADMIN:
        return "ADMINISTRATEUR"
    elif habilitation in HABILITATIONS_SERVICES_CENTRAUX:
        return "SERVICE CENTRAL"
    elif habilitation in HABILITATIONS_CISOP:
        return "CISOP"
    elif habilitation in HABILITATIONS_CHEFS:
        return "CHEF DE POSTE"
    elif habilitation in HABILITATIONS_OPERATIONNELS_PESAGE:
        return "OPÉRATIONNEL PESAGE"
    elif habilitation == 'agent_inventaire':
        return "AGENT INVENTAIRE"
    elif habilitation == 'focal_regional':
        return "POINT FOCAL RÉGIONAL"
    else:
        return "AUTRE"


def get_niveau_acces(user):
    """
    Retourne le niveau d'accès de l'utilisateur
    """
    if not user or not hasattr(user, 'habilitation'):
        return "AUCUN"
    
    if user.is_superuser:
        return "COMPLET"
    
    habilitation = get_habilitation_normalisee(user.habilitation)
    
    if habilitation in HABILITATIONS_ADMIN:
        return "COMPLET"
    elif habilitation in HABILITATIONS_SERVICES_CENTRAUX:
        return "ÉTENDU"
    elif habilitation in HABILITATIONS_CISOP:
        return "STANDARD+"
    elif habilitation in HABILITATIONS_CHEFS:
        return "STANDARD"
    elif habilitation in HABILITATIONS_OPERATIONNELS_PESAGE:
        return "OPÉRATIONNEL"
    else:
        return "LIMITÉ"


def get_redirect_url_for_user(user):
    """
    Détermine l'URL de redirection appropriée selon le rôle de l'utilisateur
    """
    if not user or not user.is_authenticated:
        return '/accounts/login/'
    
    habilitation = get_habilitation_normalisee(getattr(user, 'habilitation', None))
    
    # Administrateurs → Panel Django ou Dashboard Admin
    if user.is_superuser or user.is_staff or habilitation in HABILITATIONS_ADMIN:
        return '/admin/' if user.is_staff else '/dashboard/admin/'
    
    # Services centraux → Dashboard spécialisé
    if habilitation in HABILITATIONS_SERVICES_CENTRAUX:
        return '/dashboard/services/'
    
    # CISOP → Dashboard CISOP
    if habilitation == 'cisop_peage':
        return '/dashboard/cisop/peage/'
    elif habilitation == 'cisop_pesage':
        return '/dashboard/cisop/pesage/'
    
    # Chefs de poste → Dashboard Chef
    if habilitation == 'chef_peage':
        return '/dashboard/chef/peage/'
    elif habilitation == 'chef_station_pesage':
        return '/dashboard/chef/pesage/'
    
    # Opérationnels pesage → Dashboard Pesage
    if habilitation in HABILITATIONS_OPERATIONNELS_PESAGE:
        return '/dashboard/pesage/'
    
    # Agent inventaire → Dashboard Inventaire
    if habilitation == 'agent_inventaire':
        return '/dashboard/inventaire/'
    
    # Point focal régional → Dashboard Régional
    if habilitation == 'focal_regional':
        return '/dashboard/regional/'
    
    # Par défaut → Dashboard général
    return '/dashboard/'


def get_interface_type(user):
    """
    Détermine le type d'interface pour l'utilisateur
    """
    if not user or not user.is_authenticated:
        return "Non authentifié"
    
    if user.is_superuser or user.is_staff:
        return "Panel Django Admin"
    
    habilitation = get_habilitation_normalisee(getattr(user, 'habilitation', None))
    
    if habilitation in HABILITATIONS_ADMIN:
        return "Interface Administration"
    elif habilitation in HABILITATIONS_SERVICES_CENTRAUX:
        return "Interface Services Centraux"
    elif habilitation in HABILITATIONS_CISOP:
        return "Interface CISOP"
    elif habilitation in HABILITATIONS_CHEFS:
        return "Interface Chef de Poste"
    elif habilitation in HABILITATIONS_OPERATIONNELS_PESAGE:
        return "Interface Pesage"
    elif habilitation == 'agent_inventaire':
        return "Interface Inventaire"
    else:
        return "Interface Web Standard"


# ===================================================================
# SIGNAUX D'AUTHENTIFICATION
# ===================================================================

@receiver(user_logged_in)
def log_user_login_and_redirect(sender, request, user, **kwargs):
    """
    Journalise les connexions ET gère la redirection automatique
    selon le rôle et les permissions de l'utilisateur
    """
    try:
        from .models import JournalAudit
        
        # Obtenir l'IP du client
        ip = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:200]
        
        # Déterminer les informations de l'utilisateur
        habilitation = get_habilitation_normalisee(getattr(user, 'habilitation', 'inconnu'))
        interface_type = get_interface_type(user)
        category = get_user_category(user)
        niveau_acces = get_niveau_acces(user)
        
        # Construire les détails de connexion enrichis
        details = [
            f"Connexion réussie",
            f"Catégorie: {category}",
            f"Rôle: {user.get_habilitation_display() if hasattr(user, 'get_habilitation_display') else habilitation}",
            f"Niveau d'accès: {niveau_acces}",
            f"Interface: {interface_type}",
            f"Poste: {user.poste_affectation.nom if user.poste_affectation else 'Aucun/Multi-postes'}",
        ]
        
        # Ajouter les permissions clés actives
        permissions_actives = get_permissions_actives_resume(user)
        if permissions_actives:
            details.append(f"Permissions clés: {permissions_actives}")
        
        # Ajouter la dernière connexion
        if user.last_login:
            details.append(f"Dernière connexion: {user.last_login.strftime('%d/%m/%Y %H:%M')}")
        else:
            details.append("Première connexion")
        
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
        
        # Log détaillé selon la catégorie
        log_message = (
            f"CONNEXION {category} - {user.username} ({user.nom_complet}) - "
            f"Rôle: {habilitation} - Niveau: {niveau_acces} - "
            f"Interface: {interface_type} - IP: {ip}"
        )
        
        if is_admin_user(user):
            logger.info(f"🔐 {log_message}")
        elif is_service_central(user):
            logger.info(f"📋 {log_message}")
        elif is_cisop(user):
            logger.info(f"🔍 {log_message}")
        elif is_chef_poste(user):
            logger.info(f"👔 {log_message}")
        else:
            logger.info(f"👤 {log_message}")
        
        # REDIRECTION AUTOMATIQUE - Stocker dans la session
        redirect_url = get_redirect_url_for_user(user)
        request.session['redirect_after_login'] = redirect_url
        request.session['user_category'] = category
        request.session['user_niveau_acces'] = niveau_acces
        
    except Exception as e:
        logger.error(f"Erreur journalisation connexion: {str(e)}")


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    """
    Journalise les tentatives de connexion échouées
    """
    try:
        from .models import JournalAudit, UtilisateurSUPPER
        
        ip = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:200]
        username = credentials.get('username', 'Inconnu')
        
        # Vérifier si l'utilisateur existe
        user_exists = UtilisateurSUPPER.objects.filter(username=username.upper()).exists()
        
        if user_exists:
            # Utilisateur existe mais mauvais mot de passe
            reason = "Mot de passe incorrect"
            user = UtilisateurSUPPER.objects.get(username=username.upper())
            
            # Vérifier si le compte est actif
            if not user.is_active:
                reason = "Compte désactivé"
            
            JournalAudit.objects.create(
                utilisateur=user,
                action="TENTATIVE CONNEXION ÉCHOUÉE",
                details=f"Raison: {reason} | IP: {ip} | User-Agent: {user_agent[:100]}",
                adresse_ip=ip,
                user_agent=user_agent,
                url_acces=request.path if request else '/accounts/login/',
                methode_http='POST',
                succes=False
            )
            
            logger.warning(
                f"⚠️ CONNEXION ÉCHOUÉE - {username} - Raison: {reason} - IP: {ip}"
            )
        else:
            # Utilisateur n'existe pas - potentielle attaque
            logger.warning(
                f"🚨 TENTATIVE CONNEXION UTILISATEUR INEXISTANT - "
                f"Matricule tenté: {username} - IP: {ip} - User-Agent: {user_agent[:50]}"
            )
        
    except Exception as e:
        logger.error(f"Erreur journalisation échec connexion: {str(e)}")


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Journalise les déconnexions utilisateur avec détails enrichis"""
    try:
        from .models import JournalAudit
        
        if user and user.is_authenticated:
            ip = get_client_ip(request)
            
            # Récupérer les informations de session
            category = request.session.get('user_category', get_user_category(user))
            interface_type = get_interface_type(user)
            
            # Calculer la durée de session si possible
            session_duration = "Non calculée"
            pages_visited = request.session.get('pages_visited', 0) if request.session else 0
            
            details = [
                f"Déconnexion {interface_type}",
                f"Catégorie: {category}",
                f"Pages visitées: {pages_visited}",
                f"Durée session: {session_duration}"
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
            
            logger.info(
                f"👋 DÉCONNEXION - {user.username} ({user.nom_complet}) - "
                f"Catégorie: {category} - Interface: {interface_type} - IP: {ip}"
            )
            
    except Exception as e:
        logger.error(f"Erreur journalisation déconnexion: {str(e)}")


# ===================================================================
# SIGNAUX UTILISATEURS
# ===================================================================

@receiver(pre_save, sender='accounts.UtilisateurSUPPER')
def log_user_before_save(sender, instance, **kwargs):
    """Capturer l'état complet avant modification pour comparaison"""
    if instance.pk:  # Modification d'un utilisateur existant
        try:
            old_instance = sender.objects.get(pk=instance.pk)
            
            # Capturer tous les champs importants incluant les nouvelles permissions
            instance._old_values = {
                # Informations de base
                'nom_complet': old_instance.nom_complet,
                'habilitation': old_instance.habilitation,
                'poste_affectation': old_instance.poste_affectation,
                'is_active': old_instance.is_active,
                'telephone': old_instance.telephone,
                'email': old_instance.email,
                
                # Permissions globales
                'acces_tous_postes': old_instance.acces_tous_postes,
                'peut_saisir_peage': old_instance.peut_saisir_peage,
                'peut_saisir_pesage': old_instance.peut_saisir_pesage,
                'voir_recettes_potentielles': old_instance.voir_recettes_potentielles,
                'voir_taux_deperdition': old_instance.voir_taux_deperdition,
                'voir_statistiques_globales': old_instance.voir_statistiques_globales,
                'peut_saisir_pour_autres_postes': old_instance.peut_saisir_pour_autres_postes,
                
                # Anciennes permissions modules
                'peut_gerer_peage': old_instance.peut_gerer_peage,
                'peut_gerer_pesage': old_instance.peut_gerer_pesage,
                'peut_gerer_personnel': old_instance.peut_gerer_personnel,
                'peut_gerer_budget': old_instance.peut_gerer_budget,
                'peut_gerer_inventaire': old_instance.peut_gerer_inventaire,
                'peut_gerer_archives': old_instance.peut_gerer_archives,
                'peut_gerer_stocks_psrr': old_instance.peut_gerer_stocks_psrr,
                'peut_gerer_stock_info': old_instance.peut_gerer_stock_info,
            }
            
            # Ajouter les nouvelles permissions granulaires si elles existent
            nouvelles_permissions = [
                # Inventaires
                'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin',
                'peut_programmer_inventaire', 'peut_voir_programmation_active',
                'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
                'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin',
                'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
                
                # Recettes péage
                'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage',
                'peut_voir_stats_recettes_peage', 'peut_importer_recettes_peage',
                'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
                
                # Quittances péage
                'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage',
                'peut_comptabiliser_quittances_peage',
                
                # Pesage
                'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende',
                'peut_saisir_pesee_jour', 'peut_voir_objectifs_pesage',
                'peut_valider_paiement_amende', 'peut_lister_amendes',
                'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage',
                'peut_voir_liste_quittancements_pesage', 'peut_voir_historique_pesees',
                'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
                
                # Stock péage
                'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage',
                'peut_voir_stock_date_peage', 'peut_transferer_stock_peage',
                'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
                'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage',
                'peut_simuler_commandes_peage',
                
                # Gestion
                'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
                'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit',
                
                # Rapports
                'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
                'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
                'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
                'peut_voir_classement_agents_inventaire',
                
                # Autres
                'peut_parametrage_global', 'peut_voir_compte_emploi',
                'peut_voir_pv_confrontation', 'peut_authentifier_document',
                'peut_voir_tous_postes',
            ]
            
            for perm in nouvelles_permissions:
                if hasattr(old_instance, perm):
                    instance._old_values[perm] = getattr(old_instance, perm)
            
        except sender.DoesNotExist:
            instance._old_values = {}
    else:
        instance._old_values = {}


@receiver(post_save, sender='accounts.UtilisateurSUPPER')
def log_utilisateur_creation_modification(sender, instance, created, **kwargs):
    """Journalise la création et modification d'utilisateurs avec détails complets"""
    try:
        from .models import JournalAudit
        
        habilitation = get_habilitation_normalisee(instance.habilitation)
        category = get_user_category(instance)
        niveau_acces = get_niveau_acces(instance)
        
        if created:
            # Création d'un nouvel utilisateur
            action = "CRÉATION UTILISATEUR"
            details = [
                f"Nouvel utilisateur créé: {instance.username} ({instance.nom_complet})",
                f"Catégorie: {category}",
                f"Rôle assigné: {instance.get_habilitation_display()}",
                f"Niveau d'accès: {niveau_acces}",
                f"Poste d'affectation: {instance.poste_affectation.nom if instance.poste_affectation else 'Aucun/Multi-postes'}",
                f"Téléphone: {instance.telephone}",
                f"Email: {instance.email or 'Non renseigné'}",
                f"Compte actif: {'Oui' if instance.is_active else 'Non'}"
            ]
            
            # Ajouter un résumé des permissions clés
            perms_resume = get_permissions_actives_resume(instance)
            if perms_resume:
                details.append(f"Permissions clés: {perms_resume}")
            
            # Utiliser l'utilisateur qui a créé le compte
            utilisateur_createur = instance.cree_par if instance.cree_par else get_current_user_from_context()
            
            if utilisateur_createur:
                JournalAudit.objects.create(
                    utilisateur=utilisateur_createur,
                    action=action,
                    details=" | ".join(details),
                    succes=True
                )
            
            logger.info(
                f"✅ CRÉATION UTILISATEUR - {instance.username} ({instance.nom_complet}) - "
                f"Catégorie: {category} - Rôle: {habilitation}"
            )
            
        else:
            # Modification d'un utilisateur existant
            action = "MODIFICATION UTILISATEUR"
            
            # Détecter les changements
            changes = []
            permissions_changes = []
            old_values = getattr(instance, '_old_values', {})
            
            # Champs principaux
            champs_principaux = ['nom_complet', 'telephone', 'email', 'habilitation', 
                                 'poste_affectation', 'is_active', 'acces_tous_postes']
            
            for field, old_value in old_values.items():
                new_value = getattr(instance, field, None)
                if old_value != new_value:
                    if field == 'poste_affectation':
                        old_str = old_value.nom if old_value else 'Aucun'
                        new_str = new_value.nom if new_value else 'Aucun'
                        changes.append(f"Poste: {old_str} → {new_str}")
                    elif field == 'habilitation':
                        old_display = dict(sender._meta.get_field('habilitation').choices).get(old_value, old_value)
                        new_display = instance.get_habilitation_display()
                        changes.append(f"Rôle: {old_display} → {new_display}")
                    elif field == 'is_active':
                        status_old = 'Actif' if old_value else 'Inactif'
                        status_new = 'Actif' if new_value else 'Inactif'
                        changes.append(f"Statut: {status_old} → {status_new}")
                    elif field.startswith('peut_') or field.startswith('voir_'):
                        # Changement de permission
                        perm_label = field.replace('_', ' ').replace('peut ', '').capitalize()
                        old_perm = 'Oui' if old_value else 'Non'
                        new_perm = 'Oui' if new_value else 'Non'
                        permissions_changes.append(f"{perm_label}: {old_perm}→{new_perm}")
                    elif field in champs_principaux:
                        changes.append(f"{field}: {old_value} → {new_value}")
            
            if changes or permissions_changes:
                details = [
                    f"Utilisateur modifié: {instance.username} ({instance.nom_complet})",
                    f"Catégorie: {category}"
                ]
                
                if changes:
                    details.append(f"Modifications: {', '.join(changes)}")
                
                if permissions_changes:
                    # Limiter le nombre de permissions affichées
                    if len(permissions_changes) > 5:
                        details.append(f"Permissions modifiées ({len(permissions_changes)}): {', '.join(permissions_changes[:5])}...")
                    else:
                        details.append(f"Permissions modifiées: {', '.join(permissions_changes)}")
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
            
            # Log avec indication des changements importants
            if changes:
                logger.info(
                    f"📝 MODIFICATION UTILISATEUR - {instance.username} - "
                    f"Changements: {', '.join(changes[:3])}"
                )
            if permissions_changes:
                logger.info(
                    f"🔑 MODIFICATION PERMISSIONS - {instance.username} - "
                    f"{len(permissions_changes)} permission(s) modifiée(s)"
                )
            
    except Exception as e:
        logger.error(f"Erreur signal utilisateur: {str(e)}")


@receiver(post_delete, sender='accounts.UtilisateurSUPPER')
def log_utilisateur_suppression(sender, instance, **kwargs):
    """Journalise la suppression d'utilisateurs avec détails complets"""
    try:
        from .models import JournalAudit
        
        current_user = get_current_user_from_context()
        category = get_user_category(instance)
        
        action = "SUPPRESSION UTILISATEUR"
        details = [
            f"Utilisateur supprimé: {instance.username} ({instance.nom_complet})",
            f"Catégorie: {category}",
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
        
        logger.warning(
            f"🗑️ SUPPRESSION UTILISATEUR - {instance.username} ({instance.nom_complet}) - "
            f"Catégorie: {category}"
        )
        
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
                'axe_routier': getattr(old_instance, 'axe_routier', None),
                'description': getattr(old_instance, 'description', None),
                'is_active': old_instance.is_active,
                'latitude': old_instance.latitude,
                'longitude': old_instance.longitude,
                'nouveau': getattr(old_instance, 'nouveau', False),
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
        type_poste = "Péage" if instance.type == 'peage' else "Pesage"
        
        if created:
            # Création d'un nouveau poste
            action = "CRÉATION POSTE"
            details = [
                f"Nouveau poste créé: {instance.nom} (Code: {instance.code})",
                f"Type: {type_poste}",
                f"Région: {instance.region}",
                f"Département: {instance.departement}",
                f"Axe routier: {getattr(instance, 'axe_routier', 'Non renseigné') or 'Non renseigné'}",
                f"Coordonnées GPS: {instance.latitude}, {instance.longitude}" if instance.latitude else "GPS: Non renseignées",
                f"Statut: {'Actif' if instance.is_active else 'Inactif'}",
                f"Nouveau poste: {'Oui' if getattr(instance, 'nouveau', False) else 'Non'}"
            ]
            
            log_icon = "🚗" if instance.type == 'peage' else "⚖️"
            logger.info(
                f"{log_icon} CRÉATION POSTE {type_poste.upper()} - "
                f"{instance.nom} ({instance.code}) - Région: {instance.region}"
            )
            
        else:
            # Modification d'un poste existant
            action = "MODIFICATION POSTE"
            
            # Détecter les changements
            changes = []
            old_values = getattr(instance, '_old_values', {})
            
            for field, old_value in old_values.items():
                new_value = getattr(instance, field, None)
                if old_value != new_value:
                    if field == 'type':
                        old_display = "Péage" if old_value == 'peage' else "Pesage"
                        new_display = type_poste
                        changes.append(f"Type: {old_display} → {new_display}")
                    elif field == 'is_active':
                        status_old = 'Actif' if old_value else 'Inactif'
                        status_new = 'Actif' if new_value else 'Inactif'
                        changes.append(f"Statut: {status_old} → {status_new}")
                    elif field in ['latitude', 'longitude']:
                        if old_value != new_value:
                            changes.append("Coordonnées GPS mises à jour")
                    elif field == 'nouveau':
                        changes.append(f"Marqueur nouveau: {'Oui' if new_value else 'Non'}")
                    else:
                        changes.append(f"{field}: {old_value or 'Vide'} → {new_value or 'Vide'}")
            
            if changes:
                details = [
                    f"Poste modifié: {instance.nom} (Code: {instance.code})",
                    f"Type: {type_poste}",
                    f"Modifications: {', '.join(changes)}"
                ]
            else:
                details = [f"Poste consulté/sauvegardé sans modification: {instance.nom}"]
            
            log_icon = "🚗" if instance.type == 'peage' else "⚖️"
            logger.info(
                f"{log_icon} MODIFICATION POSTE {type_poste.upper()} - "
                f"{instance.nom} ({instance.code})"
            )
        
        if current_user:
            JournalAudit.objects.create(
                utilisateur=current_user,
                action=action,
                details=" | ".join(details),
                succes=True
            )
        
    except Exception as e:
        logger.error(f"Erreur signal poste: {str(e)}")


@receiver(post_delete, sender='accounts.Poste')
def log_poste_suppression(sender, instance, **kwargs):
    """Journalise la suppression de postes"""
    try:
        from .models import JournalAudit
        
        current_user = get_current_user_from_context()
        type_poste = "Péage" if instance.type == 'peage' else "Pesage"
        
        action = "SUPPRESSION POSTE"
        details = [
            f"Poste supprimé: {instance.nom} (Code: {instance.code})",
            f"Type: {type_poste}",
            f"Région: {instance.region}",
            f"Département: {instance.departement}",
            f"Axe routier: {getattr(instance, 'axe_routier', 'Non renseigné') or 'Non renseigné'}",
            f"Créé le: {instance.date_creation.strftime('%d/%m/%Y')}"
        ]
        
        if current_user:
            JournalAudit.objects.create(
                utilisateur=current_user,
                action=action,
                details=" | ".join(details),
                succes=True
            )
        
        log_icon = "🚗" if instance.type == 'peage' else "⚖️"
        logger.warning(
            f"{log_icon} 🗑️ SUPPRESSION POSTE {type_poste.upper()} - "
            f"{instance.nom} ({instance.code})"
        )
        
    except Exception as e:
        logger.error(f"Erreur signal suppression poste: {str(e)}")


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
            
            # Déterminer la catégorie du destinataire
            dest_category = get_user_category(instance.destinataire)
            
            details = [
                f"Nouvelle notification: {instance.titre}",
                f"Destinataire: {instance.destinataire.nom_complet} ({dest_category})",
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
            
            logger.info(
                f"📨 NOTIFICATION - {instance.titre} → "
                f"{instance.destinataire.nom_complet} ({dest_category})"
            )
        
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
            
            # Déterminer l'icône selon l'action
            action_icons = {
                1: "➕",  # Addition
                2: "✏️",  # Change
                3: "🗑️",  # Deletion
            }
            icon = action_icons.get(instance.action_flag, "📋")
            
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
            
            logger.info(
                f"{icon} ADMIN ACTION - {instance.user.username} - "
                f"{instance.get_action_flag_display()} - {app_name}.{model_name} - {object_name}"
            )
            
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


def get_permissions_actives_resume(user):
    """
    Retourne un résumé des permissions clés actives pour un utilisateur
    """
    if not user:
        return ""
    
    permissions_cles = []
    
    # Permissions globales importantes
    if getattr(user, 'acces_tous_postes', False):
        permissions_cles.append("Multi-postes")
    if getattr(user, 'peut_saisir_peage', False):
        permissions_cles.append("Saisie Péage")
    if getattr(user, 'peut_saisir_pesage', False):
        permissions_cles.append("Saisie Pesage")
    if getattr(user, 'voir_taux_deperdition', False):
        permissions_cles.append("Taux Déperdition")
    if getattr(user, 'voir_recettes_potentielles', False):
        permissions_cles.append("Recettes Potentielles")
    
    # Permissions gestion
    if getattr(user, 'peut_gerer_utilisateurs', False):
        permissions_cles.append("Gestion Users")
    if getattr(user, 'peut_gerer_postes', False):
        permissions_cles.append("Gestion Postes")
    if getattr(user, 'peut_voir_journal_audit', False):
        permissions_cles.append("Audit")
    
    # Permissions inventaire
    if getattr(user, 'peut_programmer_inventaire', False):
        permissions_cles.append("Prog. Inventaire")
    
    # Permissions stock
    if getattr(user, 'peut_charger_stock_peage', False):
        permissions_cles.append("Stock Péage")
    
    # Limiter à 5 permissions maximum
    if len(permissions_cles) > 5:
        return f"{', '.join(permissions_cles[:5])} (+{len(permissions_cles)-5})"
    
    return ', '.join(permissions_cles) if permissions_cles else "Permissions par défaut"


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


def count_active_permissions(user):
    """
    Compte le nombre de permissions actives pour un utilisateur
    """
    if not user:
        return 0
    
    count = 0
    permission_fields = [
        'acces_tous_postes', 'peut_saisir_peage', 'peut_saisir_pesage',
        'voir_recettes_potentielles', 'voir_taux_deperdition', 'voir_statistiques_globales',
        'peut_saisir_pour_autres_postes', 'peut_gerer_peage', 'peut_gerer_pesage',
        'peut_gerer_personnel', 'peut_gerer_budget', 'peut_gerer_inventaire',
        'peut_gerer_archives', 'peut_gerer_stocks_psrr', 'peut_gerer_stock_info',
        'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin',
        'peut_programmer_inventaire', 'peut_voir_programmation_active',
        'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
        'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin',
        'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage',
        'peut_voir_stats_recettes_peage', 'peut_importer_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage',
        'peut_comptabiliser_quittances_peage', 'peut_voir_historique_vehicule_pesage',
        'peut_saisir_amende', 'peut_saisir_pesee_jour', 'peut_voir_objectifs_pesage',
        'peut_valider_paiement_amende', 'peut_lister_amendes',
        'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage',
        'peut_voir_liste_quittancements_pesage', 'peut_voir_historique_pesees',
        'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage',
        'peut_voir_stock_date_peage', 'peut_transferer_stock_peage',
        'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage',
        'peut_simuler_commandes_peage', 'peut_gerer_postes', 'peut_ajouter_poste',
        'peut_creer_poste_masse', 'peut_gerer_utilisateurs', 'peut_creer_utilisateur',
        'peut_voir_journal_audit', 'peut_voir_rapports_defaillants_peage',
        'peut_voir_rapports_defaillants_pesage', 'peut_voir_rapport_inventaires',
        'peut_voir_classement_peage_rendement', 'peut_voir_classement_station_pesage',
        'peut_voir_classement_peage_deperdition', 'peut_voir_classement_agents_inventaire',
        'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
        'peut_authentifier_document', 'peut_voir_tous_postes',
    ]
    
    for field in permission_fields:
        if getattr(user, field, False):
            count += 1
    
    return count


# ===================================================================
# SIGNAUX POUR LES CHANGEMENTS DE PERMISSIONS EN MASSE
# ===================================================================

def log_bulk_permission_change(users, permission_field, new_value, changed_by):
    """
    Journalise les changements de permissions en masse
    """
    try:
        from .models import JournalAudit
        
        action = f"MODIFICATION PERMISSION EN MASSE"
        perm_label = permission_field.replace('_', ' ').replace('peut ', '').capitalize()
        
        details = [
            f"Permission modifiée: {perm_label}",
            f"Nouvelle valeur: {'Activée' if new_value else 'Désactivée'}",
            f"Utilisateurs concernés: {len(users)}",
            f"Liste: {', '.join([u.username for u in users[:10]])}{'...' if len(users) > 10 else ''}"
        ]
        
        if changed_by:
            JournalAudit.objects.create(
                utilisateur=changed_by,
                action=action,
                details=" | ".join(details),
                succes=True
            )
        
        logger.info(
            f"🔑 MODIFICATION PERMISSION EN MASSE - {perm_label} → "
            f"{'Activée' if new_value else 'Désactivée'} pour {len(users)} utilisateurs"
        )
        
    except Exception as e:
        logger.error(f"Erreur journalisation modification permission en masse: {str(e)}")


def log_role_change(user, old_role, new_role, changed_by):
    """
    Journalise spécifiquement les changements de rôle (habilitation)
    """
    try:
        from .models import JournalAudit
        
        old_category = get_user_category_by_habilitation(old_role)
        new_category = get_user_category_by_habilitation(new_role)
        
        action = "CHANGEMENT DE RÔLE"
        details = [
            f"Utilisateur: {user.username} ({user.nom_complet})",
            f"Ancien rôle: {old_role} ({old_category})",
            f"Nouveau rôle: {new_role} ({new_category})",
            f"Impact: Les permissions ont été recalculées automatiquement"
        ]
        
        if changed_by:
            JournalAudit.objects.create(
                utilisateur=changed_by,
                action=action,
                details=" | ".join(details),
                succes=True
            )
        
        logger.info(
            f"🔄 CHANGEMENT RÔLE - {user.username}: {old_role} ({old_category}) → "
            f"{new_role} ({new_category})"
        )
        
    except Exception as e:
        logger.error(f"Erreur journalisation changement de rôle: {str(e)}")


def get_user_category_by_habilitation(habilitation):
    """
    Retourne la catégorie d'un utilisateur basé sur son habilitation
    """
    habilitation = get_habilitation_normalisee(habilitation)
    
    if habilitation in HABILITATIONS_ADMIN:
        return "ADMINISTRATEUR"
    elif habilitation in HABILITATIONS_SERVICES_CENTRAUX:
        return "SERVICE CENTRAL"
    elif habilitation in HABILITATIONS_CISOP:
        return "CISOP"
    elif habilitation in HABILITATIONS_CHEFS:
        return "CHEF DE POSTE"
    elif habilitation in HABILITATIONS_OPERATIONNELS_PESAGE:
        return "OPÉRATIONNEL PESAGE"
    elif habilitation == 'agent_inventaire':
        return "AGENT INVENTAIRE"
    elif habilitation == 'focal_regional':
        return "POINT FOCAL RÉGIONAL"
    else:
        return "AUTRE"