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



def log_user_action(user, action, details="", request=None):
    """
    Fonction pour journaliser manuellement une action utilisateur
    VERSION CORRIGÉE : Gère correctement les cas sans request
    """
    try:
        from accounts.models import JournalAudit
        
        ip = None
        session = None
        user_agent = ""
        url = ""
        
        if request:
            ip = request.META.get('REMOTE_ADDR')
            # CORRECTION : Récupérer session_key seulement si elle existe
            if hasattr(request, 'session') and request.session.session_key:
                session = request.session.session_key
            else:
                session = 'no-session'  # Valeur par défaut
            
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
            url = request.path
        else:
            # Pas de request fournie (cas des fonctions internes)
            session = 'internal-action'
            ip = '127.0.0.1'
        
        JournalAudit.objects.create(
            utilisateur=user,
            action=action,
            details=details,
            adresse_ip=ip,
            user_agent=user_agent,
            session_key=session,  # Toujours fourni maintenant
            url_acces=url,
            succes=True
        )
        
        logger.info(f"Action manuelle journalisée: {action} | Utilisateur: {user.username}")
        
    except Exception as e:
        # Ne pas bloquer l'opération si le logging échoue
        logger.error(f"Erreur journalisation manuelle (non bloquante): {str(e)}")

