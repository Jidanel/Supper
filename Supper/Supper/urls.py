
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.shortcuts import redirect
from inventaire import views as inventaire_views

# Configuration des pages d'erreur personnalisées
handler404 = 'Supper.views.handler404'
handler500 = 'Supper.views.handler500'
handler403 = 'Supper.views.handler403'

# Import du site admin personnalisé SI DISPONIBLE
try:
    from accounts.admin import admin_site
    CUSTOM_ADMIN_AVAILABLE = True
except ImportError:
    CUSTOM_ADMIN_AVAILABLE = False
    admin_site = None

# ===================================================================
# FONCTIONS DE REDIRECTION INTÉGRÉES (sans import externe)
# ===================================================================

def accueil_intelligent(request):
    """Redirection intelligente selon l'état de connexion"""
    if not request.user.is_authenticated:
        return redirect('/accounts/login/')  # CORRECTION: Rediriger vers accounts/login/
    
    # Utilisateur connecté → Dashboard admin pour tous (temporaire)
    return redirect('/admin/')

def panel_avance_redirect(request):
    """Redirection pour le Panel Avancé vers l'admin Django natif"""
    if not request.user.is_authenticated:
        return redirect('/accounts/login/')
    
    # Vérifier les permissions admin
    if request.user.is_superuser or request.user.is_staff:
        return redirect('/django-admin/')
    elif hasattr(request.user, 'habilitation') and request.user.habilitation in [
        'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'
    ]:
        return redirect('/django-admin/')
    else:
        from django.contrib import messages
        messages.error(request, "Accès non autorisé au panel d'administration avancé.")
        return redirect('/admin/')

# ===================================================================
# CONFIGURATION DES URLS
# ===================================================================

urlpatterns = [
    # ================================================================
    # PAGE D'ACCUEIL AVEC REDIRECTION INTELLIGENTE
    # ================================================================
    path('', accueil_intelligent, name='accueil'),
    
    # ================================================================
    # ADMINISTRATION
    # ================================================================
    path('admin/actions/ouvrir-semaine/', inventaire_views.action_ouvrir_semaine, name='action_ouvrir_semaine'),
    path('admin/actions/fermer-anciens/', inventaire_views.action_fermer_anciens, name='action_fermer_anciens'),
    path('admin/actions/marquer-impertinent/', inventaire_views.action_marquer_impertinent, name='action_marquer_impertinent'),
       # URLs des applications avec vues vérifiées
    path('accounts/', include('accounts.urls')),
    path('inventaire/', include('inventaire.urls')),
    path('common/', include('common.urls')),
    
    # Admin personnalisé SUPPER (principal)
    path('admin/', admin_site.urls if CUSTOM_ADMIN_AVAILABLE else admin.site.urls),
    
    # Admin Django natif (panel avancé)
    path('django-admin/', admin.site.urls, name='django_admin'),
    
    # Redirection panel avancé avec vérification permissions
    path('panel-avance/', panel_avance_redirect, name='panel_avance'),
    
    # ================================================================
    # REDIRECTIONS POUR COMPATIBILITÉ
    # ================================================================
    
    # Redirection dashboard vers accueil (routage intelligent)
    path('dashboard/', accueil_intelligent, name='dashboard'),
    path('tableau-de-bord/', accueil_intelligent, name='tableau_de_bord'),
    
    # ================================================================
    # APPLICATIONS SUPPER - HARMONISÉES
    # ================================================================
    
 
    # ================================================================
    # API ET SERVICES - À DÉVELOPPER
    # ================================================================
    
    # Status et monitoring (utilise les vues dans Supper.views)
    # path('status/', views.StatusView.as_view(), name='status'),  # À décommenter quand views.py sera corrigé
    # path('health/', views.health_check, name='health_check'),    # À décommenter quand views.py sera corrigé
]

# ================================================================
# FICHIERS STATIQUES ET MÉDIA (DÉVELOPPEMENT)
# ================================================================

if settings.DEBUG:
    # Fichiers média (uploads)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    
    # Fichiers statiques (CSS, JS, images)
    if hasattr(settings, 'STATIC_ROOT') and settings.STATIC_ROOT:
        urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # Debug Toolbar si installé
    try:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass

# ================================================================
# LOGGING POUR DÉBOGAGE
# ================================================================

import logging
logger = logging.getLogger('supper')

# Log de la configuration des URLs au démarrage
logger.info("=" * 60)
logger.info("SUPPER URLs Configuration - Version Harmonisée")
logger.info(f"Admin personnalisé disponible: {CUSTOM_ADMIN_AVAILABLE}")
logger.info(f"Mode DEBUG: {settings.DEBUG}")
logger.info("URLs configurées:")
logger.info("  / → Redirection intelligente selon connexion")
logger.info("  /admin/ → Admin SUPPER ou Django selon disponibilité")
logger.info("  /django-admin/ → Admin Django natif (panel avancé)")
logger.info("  /accounts/ → Module accounts (harmonisé)")
logger.info("  /inventaire/ → Module inventaire (placeholder)")
logger.info("  /common/ → Module common (harmonisé)")
logger.info("=" * 60)

