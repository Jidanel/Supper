# ===================================================================
# Supper/urls.py - Configuration URLs principale SUPPER (CORRIGÉE)
# ===================================================================

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.http import HttpResponse
from django.views.generic import RedirectView

# Import du site admin personnalisé
from accounts.admin import admin_site

def home_view(request):
    """Vue d'accueil - redirection intelligente"""
    if request.user.is_authenticated:
        # Rediriger les utilisateurs authentifiés vers le panel admin
        return redirect('/admin/')
    else:
        # Rediriger les visiteurs non authentifiés vers la connexion
        return redirect('/admin/login/')

# Configuration des URLs principales
urlpatterns = [
    # Page d'accueil avec redirection intelligente
    path('', home_view, name='home'),
    
    # Site admin personnalisé SUPPER
    path('admin/', admin_site.urls),
    
    # Admin Django standard (désactivé - utilisation du site personnalisé)
    # path('django-admin/', admin.site.urls),  # Garder en commentaire pour debug si nécessaire
    
    # Redirections de compatibilité
    path('dashboard/', RedirectView.as_view(url='/admin/', permanent=False), name='dashboard_redirect'),
    path('login/', RedirectView.as_view(url='/admin/login/', permanent=False), name='login_redirect'),
    path('logout/', RedirectView.as_view(url='/admin/logout/', permanent=False), name='logout_redirect'),
]

# Servir les fichiers média en développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # Page de debug pour vérifier la configuration
    def debug_info(request):
        if not settings.DEBUG:
            return HttpResponse("Debug désactivé", status=403)
            
        info = f"""
        <h1>SUPPER - Information de Debug</h1>
        <h2>Configuration Système</h2>
        <ul>
            <li><strong>Version Django:</strong> {admin.VERSION}</li>
            <li><strong>Base de données:</strong> {settings.DATABASES['default']['ENGINE']}</li>
            <li><strong>Mode DEBUG:</strong> {settings.DEBUG}</li>
            <li><strong>Langue:</strong> {settings.LANGUAGE_CODE}</li>
            <li><strong>Fuseau horaire:</strong> {settings.TIME_ZONE}</li>
            <li><strong>Utilisateur personnalisé:</strong> {settings.AUTH_USER_MODEL}</li>
        </ul>
        
        <h2>URLs disponibles</h2>
        <ul>
            <li><a href="/admin/">Panel Admin SUPPER</a></li>
            <li><a href="/admin/dashboard/">Dashboard Principal</a></li>
            <li><a href="/admin/saisie-inventaire/">Saisie Inventaire</a></li>
            <li><a href="/debug/">Cette page de debug</a></li>
        </ul>
        
        <h2>Applications installées</h2>
        <ul>
        """
        
        for app in settings.INSTALLED_APPS:
            if not app.startswith('django.'):
                info += f"<li>{app}</li>"
        
        info += """
        </ul>
        
        <p><a href="/admin/">← Retour à l'administration</a></p>
        """
        
        return HttpResponse(info)
    
    urlpatterns += [
        path('debug/', debug_info, name='debug_info'),
    ]

    try:
        import debug_toolbar
        urlpatterns += [
            path('__debug__/', include(debug_toolbar.urls)),
        ]
    except ImportError:
        pass