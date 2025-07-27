# ===================================================================
# Supper/urls.py - URLs principales du projet SUPPER
# ===================================================================
# 🔄 REMPLACE le contenu existant du fichier Supper/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.http import HttpResponse
from django.template.response import TemplateResponse
from accounts.admin import admin_site

def home_redirect(request):
    """Redirection intelligente depuis la racine"""
    if request.user.is_authenticated:
        # Rediriger vers le dashboard approprié selon le rôle
        if request.user.is_admin():
            return redirect('admin:index')
        else:
            return redirect('accounts:dashboard')
    else:
        return redirect('accounts:login')

def health_check(request):
    """Point de santé pour monitoring"""
    return HttpResponse("OK - SUPPER Application Running", content_type="text/plain")

def robots_txt(request):
    """Fichier robots.txt pour les crawlers"""
    content = """User-agent: *
Disallow: /admin/
Disallow: /accounts/
Allow: /static/
"""
    return HttpResponse(content, content_type="text/plain")

urlpatterns = [
    # Page d'accueil avec redirection intelligente
    path('', home_redirect, name='home'),
    
    # Administration Django native (pour les super-admins uniquement)
    path('admin/', admin.site.urls),
    
    # Site admin personnalisé SUPPER
    path('accounts/admin/', admin_site.urls),
    
    # Application accounts (authentification + dashboards)
    path('accounts/', include('accounts.urls')),
    
    # Applications futures
    # path('inventaire/', include('inventaire.urls')),  # À activer plus tard
    # path('api/', include('api.urls')),  # API REST future
    
    # Utilitaires système
    path('health/', health_check, name='health_check'),
    path('robots.txt', robots_txt, name='robots_txt'),
]

# Configuration pour servir les fichiers média en développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # Debug toolbar si disponible
    try:
        import debug_toolbar
        urlpatterns = [
            path('__debug__/', include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass

# Gestionnaire d'erreurs personnalisés
handler404 = 'accounts.views.custom_404'
handler500 = 'accounts.views.custom_500'
handler403 = 'accounts.views.custom_403'