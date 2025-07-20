# ===================================================================
# Supper/urls.py - URLs principales du projet
# ===================================================================

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Panel d'administration Django (accès restreint)
    path('admin/', admin.site.urls),
    
    # Page d'accueil - redirection vers le dashboard approprié
    path('', views.HomeView.as_view(), name='home'),
    
    # Authentification
    path('accounts/', include('accounts.urls')),
    
    # Modules principaux
    path('dashboard/', include('common.urls')),  # Dashboards personnalisés
    #path('inventaire/', include('inventaire.urls')),
    
    # API pour les requêtes AJAX
    #path('api/', include('common.api_urls')),
]

# Configuration pour servir les fichiers média en développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)