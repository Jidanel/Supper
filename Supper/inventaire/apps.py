# ===================================================================
# inventaire/apps.py - Configuration de l'application inventaire
# ===================================================================

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InventaireConfig(AppConfig):
    """Configuration de l'application de gestion des inventaires SUPPER"""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventaire'
    verbose_name = _('Gestion des Inventaires')
    
    def ready(self):
        """Code exécuté au démarrage de l'application"""
        import logging
        
        # Configuration du logger pour l'application inventaire
        logger = logging.getLogger('supper')
        logger.info("Application Inventaire SUPPER initialisée")
        
        # Import des signaux pour la journalisation et calculs automatiques
        try:
            import inventaire.signals
        except ImportError:
            pass
