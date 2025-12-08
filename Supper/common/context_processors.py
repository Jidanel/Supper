# ===================================================================
# common/context_processors.py - Context processors pour les templates
# NOUVEAU FICHIER : Fournit des données globales aux templates
# ===================================================================

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

def admin_context(request):
    """
    Context processor pour l'interface admin
    Fournit des données communes à tous les templates admin
    """
    context = {}
    
    # Données utilisateur uniquement si connecté
    if hasattr(request, 'user') and request.user.is_authenticated:
        user = request.user
        
        # Notifications non lues
        try:
            unread_count = user.notifications_recues.filter(lue=False).count()
            recent_notifications = user.notifications_recues.order_by('-date_creation')[:5]
            total_notifications = user.notifications_recues.count()
            
            context.update({
                'unread_notifications_count': unread_count,
                'recent_notifications': recent_notifications,
                'total_notifications_count': total_notifications,
            })
        except Exception:
            # Si le modèle NotificationUtilisateur n'existe pas encore
            context.update({
                'unread_notifications_count': 0,
                'recent_notifications': [],
                'total_notifications_count': 0,
            })
        
        # Statistiques rapides pour la sidebar
        try:
            # Compter les utilisateurs
            users_count = User.objects.filter(is_active=True).count()
            
            # Compter les inventaires d'aujourd'hui
            from inventaire.models import InventaireJournalier
            today = timezone.now().date()
            inventaires_today = InventaireJournalier.objects.filter(date=today).count()
            
            # Compter les recettes d'aujourd'hui
            from inventaire.models import RecetteJournaliere
            recettes_today = RecetteJournaliere.objects.filter(date=today).count()
            
            context.update({
                'users_count': users_count,
                'inventaires_today': inventaires_today,
                'recettes_today': recettes_today,
            })
            
        except Exception:
            # Si les modèles n'existent pas encore
            context.update({
                'users_count': 0,
                'inventaires_today': 0,
                'recettes_today': 0,
            })
    
    return context


def supper_globals(request):
    """
    Context processor global pour SUPPER
    Variables disponibles dans tous les templates
    """
    return {
        'SUPPER_VERSION': '1.0.0',
        'SUPPER_NAME': 'Suivi des  Péages et Pesages Routiers',
        'CURRENT_YEAR': timezone.now().year,
        'DEBUG_MODE': hasattr(request, 'user') and request.user.is_superuser,
    }