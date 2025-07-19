# ===================================================================
# common/apps.py - Configuration de l'application common
# ===================================================================

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CommonConfig(AppConfig):
    """Configuration de l'application des fonctions communes SUPPER"""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'common'
    verbose_name = _('Fonctions Communes et Journalisation')
    
    def ready(self):
        """Code exécuté au démarrage de l'application"""
        import logging
        from django.conf import settings
        
        # Configuration avancée du logger SUPPER
        logger = logging.getLogger('supper')
        
        if not logger.handlers:
            # Configuration par défaut si les handlers ne sont pas encore configurés
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s | SUPPER | %(levelname)s | %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        
        logger.info("=" * 60)
        logger.info("APPLICATION SUPPER - SYSTÈME INITIALISÉ")
        logger.info("Suivi des Péages et Pesages Routiers")
        logger.info(f"Mode DEBUG: {settings.DEBUG}")
        logger.info(f"Base de données: {settings.DATABASES['default']['ENGINE']}")
        logger.info("=" * 60)
        
        # Import des utilitaires communs
        try:
            import common.utils
        except ImportError:
            pass