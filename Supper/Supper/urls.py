# ===================================================================
# Supper/urls.py - URLs principales CORRIGÉES
# ===================================================================

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from accounts.admin import admin_site  # Import du site admin personnalisé

def redirect_to_admin(request):
    """Redirection vers l'admin personnalisé"""
    return redirect('admin:index')

urlpatterns = [
    # IMPORTANT: Admin personnalisé en premier
    path('admin/', admin_site.urls),
    
    # Admin Django standard (désactivé en production)
    path('django-admin/', admin.site.urls),
    
    # Redirection racine vers admin
    path('', redirect_to_admin),
    
    # URLs des applications (à ajouter plus tard)
    # path('accounts/', include('accounts.urls')),
    # path('inventaire/', include('inventaire.urls')),
    # path('api/', include('api.urls')),
]

# Servir les fichiers média en développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# ===================================================================
# accounts/urls.py - URLs de l'application accounts
# ===================================================================

"""
# Fichier à créer : accounts/urls.py

from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Authentification
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    
    # Gestion utilisateurs
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/edit/', views.UserUpdateView.as_view(), name='user_edit'),
    
    # Gestion postes  
    path('postes/', views.PosteListView.as_view(), name='poste_list'),
    path('postes/<int:pk>/', views.PosteDetailView.as_view(), name='poste_detail'),
    
    # Journal d'audit
    path('audit/', views.JournalAuditListView.as_view(), name='audit_list'),
    path('audit/<int:pk>/', views.JournalAuditDetailView.as_view(), name='journal_detail'),
    
    # Notifications
    path('notifications/', views.NotificationListView.as_view(), name='notification_list'),
]
"""

# ===================================================================
# inventaire/urls.py - URLs de l'application inventaire  
# ===================================================================

"""
# Fichier à créer : inventaire/urls.py

from django.urls import path
from . import views

app_name = 'inventaire'

urlpatterns = [
    # Inventaires
    path('', views.InventaireListView.as_view(), name='inventaire_list'),
    path('inventaires/', views.InventaireListView.as_view(), name='inventaire_list'),
    path('inventaires/<int:pk>/', views.InventaireDetailView.as_view(), name='inventaire_detail'),
    path('inventaires/nouveau/', views.InventaireCreateView.as_view(), name='inventaire_create'),
    path('inventaires/<int:pk>/edit/', views.InventaireUpdateView.as_view(), name='inventaire_edit'),
    
    # Saisie agent
    path('saisie/', views.SaisieInventaireView.as_view(), name='saisie_inventaire'),
    path('saisie/<int:poste_id>/', views.SaisieInventaireView.as_view(), name='saisie_inventaire_poste'),
    
    # Recettes
    path('recettes/', views.RecetteListView.as_view(), name='recette_list'),
    path('recettes/<int:pk>/', views.RecetteDetailView.as_view(), name='recette_detail'),
    path('recettes/nouvelle/', views.RecetteCreateView.as_view(), name='recette_create'),
    
    # Configuration jours
    path('config-jours/', views.ConfigurationJourListView.as_view(), name='config_jour_list'),
    
    # Statistiques
    path('statistiques/', views.StatistiquesView.as_view(), name='statistiques'),
    path('statistiques/<str:periode>/', views.StatistiquesView.as_view(), name='statistiques_periode'),
    
    # Exports
    path('export/inventaires/', views.ExportInventairesView.as_view(), name='export_inventaires'),
    path('export/recettes/', views.ExportRecettesView.as_view(), name='export_recettes'),
]
"""