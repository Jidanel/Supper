# ===================================================================
# accounts/apps.py - Configuration de l'application accounts
# ===================================================================

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    """Configuration de l'application de gestion des comptes utilisateur SUPPER"""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = _('Gestion des Comptes Utilisateur')
    
    def ready(self):
        """Code exécuté au démarrage de l'application"""
        import logging
        
        # Configuration du logger pour l'application accounts
        logger = logging.getLogger('supper')
        logger.info("Application Accounts SUPPER initialisée")
        
        # Import des signaux pour la journalisation automatique
        try:
            import accounts.signals
        except ImportError:
            pass