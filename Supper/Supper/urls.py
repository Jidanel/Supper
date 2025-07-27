# ===================================================================
# Fichier : Supper/urls.py - URLs MISES À JOUR
# Configuration des URLs avec redirection automatique
# ===================================================================

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.http import HttpResponse
from . import views

# Configuration du site admin
admin.site.site_header = "Administration SUPPER - Dashboard Intégré"
admin.site.site_title = "SUPPER Admin"
admin.site.index_title = "Tableau de Bord Administrateur"

# URLs principales de l'application SUPPER
urlpatterns = [
    # ===================================================================
    # ADMINISTRATION DJANGO (ACCÈS RESTREINT AUX ADMINS)
    # ===================================================================
    
    # Panel d'administration Django - ADMINS UNIQUEMENT
    # Le middleware AdminRedirectMiddleware contrôle l'accès
    path('admin/', admin.site.urls),
    
    # ===================================================================
    # PAGE D'ACCUEIL ET REDIRECTION INTELLIGENTE
    # ===================================================================
    
    # Page d'accueil avec redirection automatique selon le rôle
    # ADMINS → /admin/ | UTILISATEURS → /dashboard/
    # La redirection est gérée par AdminRedirectMiddleware
    path('', views.HomeView.as_view(), name='home'),
    
    # ===================================================================
    # MODULES PRINCIPAUX DE L'APPLICATION
    # ===================================================================
    
    # Module d'authentification et gestion des utilisateurs
    # Inclut : login, logout, profil, gestion users (admin dans le panel Django)
    path('accounts/', include('accounts.urls')),
    
    # Module des dashboards et fonctions communes
    # UTILISATEURS NORMAUX UNIQUEMENT (agents, chefs, etc.)
    # Les admins sont automatiquement redirigés vers /admin/
    path('dashboard/', include('common.urls')),
    
    # Module de gestion des inventaires et recettes  
    # Interface pour utilisateurs normaux uniquement
    # path('inventaire/', include('inventaire.urls')),  # À activer plus tard
    
    # ===================================================================
    # APIs ET SERVICES
    # ===================================================================
    
    # API publique pour statut système (monitoring externe)
    path('api/status/', views.StatusView.as_view(), name='api_status'),
    
    # ===================================================================
    # PAGES UTILITAIRES
    # ===================================================================
    
    # Page de santé système (accessible à tous les connectés)
    #path('health/', views.HealthCheckView.as_view(), name='health_check'),
    
    # Page d'information sur l'application
    #path('about/', views.AboutView.as_view(), name='about'),
]

# ===================================================================
# GESTION DES ERREURS PERSONNALISÉES
# ===================================================================

# Vues d'erreur personnalisées
#handler403 = 'Supper.views.error_403_view'
#handler404 = 'Supper.views.error_404_view'
#handler500 = 'Supper.views.error_500_view'

# ===================================================================
# CONFIGURATION DÉVELOPPEMENT
# ===================================================================

if settings.DEBUG:
    # Servir les fichiers média en développement
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # Debug toolbar si disponible
    try:
        import debug_toolbar
        urlpatterns += [
            path('__debug__/', include(debug_toolbar.urls)),
        ]
    except ImportError:
        pass
    
    # URLs de développement supplémentaires
    urlpatterns += [
        # Test de redirection
       # path('test-redirect/', views.TestRedirectView.as_view(), name='test_redirect'),
        
        # Simulation d'erreurs pour tests
       # path('test-403/', views.Test403View.as_view(), name='test_403'),
       # path('test-404/', views.Test404View.as_view(), name='test_404'),
        #path('test-500/', views.Test500View.as_view(), name='test_500'),
    ]

# ===================================================================
# DOCUMENTATION DES REDIRECTIONS
# ===================================================================

"""
LOGIQUE DE REDIRECTION AUTOMATIQUE SUPPER :

1. UTILISATEUR SE CONNECTE
   └── Signal user_logged_in déclenché
       └── Stockage de redirect_after_login en session

2. MIDDLEWARE AdminRedirectMiddleware
   ├── Vérification redirect_after_login en session
   │   └── Redirection automatique selon le rôle
   │
   ├── Contrôle d'accès croisé :
   │   ├── ADMIN tente /dashboard/ → Redirection vers /admin/
   │   └── USER tente /admin/ → Redirection vers /dashboard/
   │
   └── Redirection racine (/) selon le rôle :
       ├── ADMIN → /admin/
       └── USER → /dashboard/chef/ ou /dashboard/agent/ ou /dashboard/

3. RÔLES ET INTERFACES :
   ├── ADMINS (Panel Django) :
   │   ├── admin_principal
   │   ├── coord_psrr  
   │   ├── serv_info
   │   ├── serv_emission
   │   ├── is_superuser
   │   └── is_staff
   │
   └── UTILISATEURS (Interface Web) :
       ├── chef_peage → /dashboard/chef/
       ├── chef_pesage → /dashboard/chef/
       ├── agent_inventaire → /dashboard/agent/
       └── autres → /dashboard/

4. SÉCURITÉ :
   ├── Journalisation complète des accès
   ├── Blocage des tentatives d'accès croisé
   ├── Détection des activités suspectes
   └── Limitation des tentatives de connexion

5. AVANTAGES :
   ├── Séparation claire des interfaces
   ├── Sécurité renforcée (admins isolés)
   ├── Expérience utilisateur optimisée
   ├── Maintenance facilitée
   └── Évolutivité assurée
"""