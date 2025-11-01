# ===================================================================
# common/utils.py - Fonctions utilitaires pour SUPPER
# ===================================================================

from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.http import HttpResponseForbidden
from functools import wraps
import logging

logger = logging.getLogger('supper')


def log_action(action_name, include_params=False):
    """
    Décorateur pour journaliser des actions spécifiques
    
    Usage:
    @log_action("Création utilisateur", include_params=True)
    def create_user(request):
        ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if hasattr(request, 'user') and request.user.is_authenticated:
                details = f"Action: {action_name}"
                if include_params and args:
                    details += f" | Paramètres: {args}"
                
                try:
                    # Exécuter la vue
                    response = view_func(request, *args, **kwargs)
                    
                    # Journaliser le succès
                    log_user_action(
                        request.user,
                        action_name,
                        details,
                        request
                    )
                    
                    return response
                    
                except Exception as e:
                    # Journaliser l'erreur
                    log_user_action(
                        request.user,
                        f"ERREUR - {action_name}",
                        f"{details} | Erreur: {str(e)}",
                        request
                    )
                    raise
            else:
                return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def log_user_action_detailed(user, action, details, request=None):
    """
    Fonction améliorée pour journaliser manuellement une action utilisateur avec détails
    
    Usage:
    log_user_action_detailed(
        request.user, 
        "Modification inventaire",
        f"L'administrateur {request.user.nom_complet} a modifié l'inventaire du poste X du jour Y",
        request
    )
    """
    try:
        from accounts.models import JournalAudit
        
        ip = None
        session = None
        user_agent = ""
        url = ""
        
        if request:
            ip = request.META.get('REMOTE_ADDR')
            session = request.session.session_key
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
            url = request.path
        
        JournalAudit.objects.create(
            utilisateur=user,
            action=action,
            details=details,
            adresse_ip=ip,
            user_agent=user_agent,
            session_key=session,
            url_acces=url,
            succes=True
        )
        
        logger.info(f"Action détaillée: {action} | {details} | Utilisateur: {user.username}")
        
    except Exception as e:
        logger.error(f"Erreur journalisation détaillée: {str(e)}")


def require_permission(permission_field):
    """
    Décorateur pour vérifier les permissions SUPPER
    
    Usage:
    @require_permission('peut_gerer_inventaire')
    def ma_vue(request):
        ...
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not hasattr(request.user, permission_field):
                log_user_action(
                    request.user,
                    f"ACCÈS REFUSÉ - Permission manquante: {permission_field}",
                    f"URL: {request.path}",
                    request
                )
                return HttpResponseForbidden("Permission insuffisante")
            
            if not getattr(request.user, permission_field):
                log_user_action(
                    request.user,
                    f"ACCÈS REFUSÉ - Permission {permission_field} désactivée",
                    f"URL: {request.path}",
                    request
                )
                return HttpResponseForbidden("Permission insuffisante")
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def require_poste_access(view_func):
    """
    Décorateur pour vérifier l'accès au poste
    Vérifie que l'utilisateur peut accéder aux données du poste demandé
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        # Récupérer l'ID du poste depuis les paramètres URL
        poste_id = kwargs.get('poste_id') or request.GET.get('poste_id')
        
        if poste_id:
            try:
                from accounts.models import Poste
                poste = Poste.objects.get(id=poste_id)
                
                if not request.user.peut_acceder_poste(poste):
                    log_user_action(
                        request.user,
                        f"ACCÈS REFUSÉ - Poste non autorisé: {poste.nom}",
                        f"URL: {request.path}",
                        request
                    )
                    return HttpResponseForbidden("Accès au poste non autorisé")
                
            except Poste.DoesNotExist:
                return HttpResponseForbidden("Poste inexistant")
        
        return view_func(request, *args, **kwargs)
    
    return wrapper


class AuditMixin:
    """
    Mixin pour les vues basées sur les classes
    Ajoute automatiquement la journalisation
    """
    audit_action = None
    required_permission = None
    
    def dispatch(self, request, *args, **kwargs):
        # Vérifier les permissions si spécifiées
        if self.required_permission and request.user.is_authenticated:
            if not hasattr(request.user, self.required_permission) or \
               not getattr(request.user, self.required_permission):
                log_user_action(
                    request.user,
                    f"ACCÈS REFUSÉ - Permission manquante: {self.required_permission}",
                    f"Vue: {self.__class__.__name__}",
                    request
                )
                return HttpResponseForbidden("Permission insuffisante")
        
        # Journaliser l'action si spécifiée
        if self.audit_action and request.user.is_authenticated:
            log_user_action(
                request.user,
                self.audit_action,
                f"Vue: {self.__class__.__name__}",
                request
            )
        
        return super().dispatch(request, *args, **kwargs)


def is_admin_user(user):
    """Fonction de test pour vérifier si l'utilisateur est administrateur"""
    return user.is_authenticated and user.is_admin


def is_chef_poste(user):
    """Fonction de test pour vérifier si l'utilisateur est chef de poste"""
    return user.is_authenticated and user.is_chef_poste()


# Décorateurs pré-configurés
admin_required = user_passes_test(is_admin_user)
chef_poste_required = user_passes_test(is_chef_poste)


def get_user_postes_accessibles(user):
    """
    Retourne la liste des postes accessibles pour un utilisateur
    """
    if user.is_authenticated:
        return user.get_postes_accessibles()
    else:
        from accounts.models import Poste
        return Poste.objects.none()


def can_user_access_poste(user, poste):
    """
    Vérifie si un utilisateur peut accéder à un poste donné
    """
    if user.is_authenticated:
        return user.peut_acceder_poste(poste)
    return False


def format_montant_fcfa(montant):
    """
    Formate un montant en FCFA avec séparateurs de milliers
    """
    if montant is None:
        return "0 FCFA"
    
    try:
        # Convertir en entier pour l'affichage
        montant_int = int(montant)
        # Formater avec séparateurs de milliers
        return f"{montant_int:,} FCFA".replace(',', ' ')
    except (ValueError, TypeError):
        return "0 FCFA"


def calculer_couleur_alerte(taux_deperdition):
    """
    Détermine la couleur d'alerte selon le taux de déperdition
    """
    if taux_deperdition is None:
        return 'secondary'
    
    from django.conf import settings
    config = getattr(settings, 'SUPPER_CONFIG', {})
    seuil_orange = config.get('SEUIL_ALERTE_ORANGE', -10)
    seuil_rouge = config.get('SEUIL_ALERTE_ROUGE', -30)
    
    if taux_deperdition > seuil_orange:
        return 'success'  # Vert
    elif taux_deperdition >= seuil_rouge:
        return 'warning'  # Orange
    else:
        return 'danger'   # Rouge


def get_periodes_inventaire():
    """
    Retourne la liste des périodes horaires pour l'inventaire
    """
    from django.conf import settings
    config = getattr(settings, 'SUPPER_CONFIG', {})
    return config.get('PERIODES_INVENTAIRE', [
        '08h-09h', '09h-10h', '10h-11h', '11h-12h',
        '12h-13h', '13h-14h', '14h-15h', '15h-16h',
        '16h-17h', '17h-18h'
    ])


def valider_numero_telephone(numero):
    """
    Valide un numéro de téléphone camerounais
    """
    import re
    pattern = r'^\+?237?[0-9]{8,9}$'
                
    return re.match(pattern, str(numero)) is not None


def generer_code_poste(nom_poste, region):
    """
    Génère automatiquement un code de poste basé sur le nom et la région
    """
    # Prendre les 3 premières lettres du nom en majuscules
    nom_code = ''.join(c for c in nom_poste.upper() if c.isalpha())[:3]
    
    # Prendre les 2 premières lettres de la région
    region_code = ''.join(c for c in region.upper() if c.isalpha())[:2]
    
    # Générer un numéro séquentiel
    from accounts.models import Poste
    existing_codes = Poste.objects.filter(
        code__startswith=f"{nom_code}-{region_code}"
    ).count()
    
    numero = str(existing_codes + 1).zfill(2)
    
    return f"{nom_code}-{region_code}-{numero}"


def exporter_donnees_csv(queryset, champs, nom_fichier="export"):
    """
    Exporte un queryset en CSV
    """
    import csv
    from django.http import HttpResponse
    from django.utils import timezone
    
    # Créer la réponse HTTP
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{nom_fichier}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    # Ajouter le BOM UTF-8 pour Excel
    response.write('\ufeff')
    
    writer = csv.writer(response, delimiter=';')
    
    # Écrire l'en-tête
    writer.writerow([field.verbose_name for field in champs])
    
    # Écrire les données
    for obj in queryset:
        row = []
        for field in champs:
            value = getattr(obj, field.name, '')
            if hasattr(value, 'strftime'):  # Date/DateTime
                value = value.strftime('%d/%m/%Y %H:%M') if hasattr(value, 'hour') else value.strftime('%d/%m/%Y')
            elif callable(value):
                value = value()
            row.append(str(value) if value is not None else '')
        writer.writerow(row)
    
    return response


def nettoyer_donnees_anciennes(model_class, champ_date, jours_retention):
    """
    Supprime les données anciennes selon une politique de rétention
    """
    from django.utils import timezone
    from datetime import timedelta
    
    date_limite = timezone.now() - timedelta(days=jours_retention)
    
    # Construire la requête de suppression
    filter_kwargs = {f"{champ_date}__lt": date_limite}
    objets_a_supprimer = model_class.objects.filter(**filter_kwargs)
    
    count = objets_a_supprimer.count()
    if count > 0:
        objets_a_supprimer.delete()
        logger.info(f"Nettoyage {model_class.__name__}: {count} objets supprimés")
    
    return count



# ===================================================================
# REMPLACER LA FONCTION log_user_action DANS common/utils.py
# ===================================================================

def log_user_action(user, action, details="", request=None, **extra_data):
    """
    Fonction AMÉLIORÉE pour journaliser manuellement une action utilisateur
    
    NOUVEAUTÉS :
    - Détecte automatiquement si middleware a déjà journalisé
    - Enrichit automatiquement avec contexte utilisateur
    - Supporte données extra structurées
    - Évite les duplications
    
    Args:
        user: Utilisateur effectuant l'action
        action: Nom de l'action (ex: "Saisie recette confirmée")
        details: Détails de l'action (ex: "Recette: 500000 FCFA")
        request: Objet request Django (optionnel mais recommandé)
        **extra_data: Données supplémentaires structurées (montant=500000, poste_id=12, etc.)
    
    Usage:
        # Simple
        log_user_action(request.user, "Saisie recette", "Montant: 500000 FCFA", request)
        
        # Avec données structurées
        log_user_action(
            request.user, 
            "Saisie recette confirmée",
            "Recette saisie avec succès",
            request,
            montant=500000,
            poste_id=12,
            date="2025-01-15"
        )
    """
    try:
        from accounts.models import JournalAudit
        from datetime import timedelta
        import time
        
        # ===================================================================
        # ANTI-DUPLICATION : Marquer que cette requête a un log manuel
        # ===================================================================
        if request:
            if hasattr(request, '_has_manual_log'):
                # Un log manuel existe déjà pour cette requête, ne pas dupliquer
                logger.debug(f"Log manuel déjà présent pour {request.path}, skip")
                return
            
            # Marquer cette requête comme ayant un log manuel
            request._has_manual_log = True
        
        # ===================================================================
        # ENRICHISSEMENT AUTOMATIQUE DES INFORMATIONS
        # ===================================================================
        ip = None
        session_key = ''
        user_agent = ""
        url = ""
        method = ""
        duration = None
        
        if request:
            # IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
            else:
                ip = request.META.get('REMOTE_ADDR')
            
            # Session
            session_key = getattr(request.session, 'session_key', '') or ''
            
            # User agent
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
            
            # URL et méthode
            url = request.path[:500]
            method = request.method[:10]
            
            # Durée (si middleware a marqué le début)
            if hasattr(request, '_audit_start_time'):
                duration_seconds = time.time() - request._audit_start_time
                duration = timedelta(seconds=duration_seconds)
        
        # ===================================================================
        # ENRICHISSEMENT DES DÉTAILS
        # ===================================================================
        # Format : [Nom Complet (Rôle)] | Détails originaux | Extras
        
        enriched_details = f"{user.nom_complet} ({user.get_habilitation_display()})"
        
        if details:
            enriched_details += f" | {details}"
        
        # Ajouter les données extra structurées
        if extra_data:
            extra_parts = []
            for key, value in extra_data.items():
                # Formater joliment les clés (snake_case -> Title Case)
                formatted_key = key.replace('_', ' ').title()
                extra_parts.append(f"{formatted_key}: {value}")
            
            if extra_parts:
                enriched_details += f" | {' | '.join(extra_parts)}"
        
        # ===================================================================
        # CRÉATION DE L'ENTRÉE DE JOURNAL
        # ===================================================================
        JournalAudit.objects.create(
            utilisateur=user,
            action=action,
            details=enriched_details,
            adresse_ip=ip,
            user_agent=user_agent,
            session_key=session_key,
            url_acces=url,
            methode_http=method,
            succes=True,
            statut_reponse=200,
            duree_execution=duration
        )
        
        # Log dans le fichier système aussi
        logger.info(f"Action manuelle : {action} | {user.username} | {details}")
        
    except Exception as e:
        # Ne pas interrompre l'application si le logging échoue
        logger.error(f"Erreur journalisation manuelle: {str(e)}")


# # ===================================================================
# # EXEMPLE D'UTILISATION DANS VOS VUES
# # ===================================================================

# # AVANT (votre code actuel - fonctionne toujours) :
# def saisir_recette(request):
#     # ... code métier ...
#     montant = 500000
#     poste = get_object_or_404(Poste, id=12)
#     date_recette = "2025-01-15"
    
#     log_user_action(
#         request.user,
#         "Saisie recette confirmée",
#         f"Recette: {montant:.0f} FCFA pour {poste.nom} - {date_recette}",
#         request
#     )
#     return redirect('...')

# # APRÈS (nouvelle syntaxe avec données structurées - optionnel) :
# def saisir_recette(request):
#     # ... code métier ...
#     montant = 500000
#     poste = get_object_or_404(Poste, id=12)
#     date_recette = "2025-01-15"
    
#     log_user_action(
#         request.user,
#         "Saisie recette confirmée",
#         f"Recette saisie pour {poste.nom}",
#         request,
#         montant=f"{montant:.0f} FCFA",
#         poste=poste.nom,
#         date=date_recette,
#         type_poste=poste.get_type_poste_display()
#     )
#     return redirect('...')

# # RÉSULTAT DANS LE JOURNAL :
# # Action: "Saisie recette confirmée"
# # Détails: "Jean DUPONT (Chef de Poste Péage) | Recette saisie pour Péage de Douala | 
# #           Montant: 500000 FCFA | Poste: Péage de Douala | Date: 2025-01-15 | 
# #           Type Poste: Poste de Péage"
