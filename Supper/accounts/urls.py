# ===================================================================
# Fichier : accounts/urls.py - URLs gestion utilisateurs COMPLET
# Chemin : Supper/accounts/urls.py
# Routes authentification et gestion des utilisateurs
# ===================================================================

from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

# Nom de l'application pour les namespaces URL
app_name = 'accounts'

urlpatterns = [
    # ===================================================================
    # AUTHENTIFICATION DE BASE
    # ===================================================================
    
    # Connexion personnalisée avec formulaire par matricule
    path('login/', views.CustomLoginView.as_view(), name='login'),
    
    # Déconnexion standard Django
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # ===================================================================
    # GESTION DES MOTS DE PASSE
    # ===================================================================
    
    # Changement de mot de passe par l'utilisateur connecté
    path('password/change/', views.PasswordChangeView.as_view(), name='password_change'),
    
    # Réinitialisation de mot de passe par un admin (pour un autre utilisateur)
    path('password/reset/<int:pk>/', views.PasswordResetView.as_view(), name='password_reset'),
    
    # ===================================================================
    # PROFIL UTILISATEUR
    # ===================================================================
    
    # Profil personnel de l'utilisateur connecté
    path('profile/', views.ProfileView.as_view(), name='profile'),
    
    # Modification du profil personnel
    path('profile/edit/', views.ProfileEditView.as_view(), name='profile_edit'),
    
    # ===================================================================
    # GESTION DES UTILISATEURS (ADMIN UNIQUEMENT)
    # ===================================================================
    
    # Liste de tous les utilisateurs avec filtres et recherche
    path('users/', views.UserListView.as_view(), name='user_list'),
    
    # Création d'un nouvel utilisateur
    path('users/create/', views.UserCreateView.as_view(), name='user_create'),
    
    
    # Création en masse d'utilisateurs
    path('users/bulk-create/', views.UserBulkCreateView.as_view(), name='user_bulk_create'),
    
    # Détail d'un utilisateur spécifique
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    
    # Modification des informations d'un utilisateur
    path('users/<int:pk>/edit/', views.UserUpdateView.as_view(), name='user_edit'),
    
    # ===================================================================
    # API ENDPOINTS POUR AJAX
    # ===================================================================
    
    # API pour validation en temps réel des formulaires
    path('api/validate-username/', views.ValidateUsernameAPIView.as_view(), name='api_validate_username'),
    
    # API pour suggestions d'utilisateurs (autocomplete)
    path('api/users/search/', views.UserSearchAPIView.as_view(), name='api_user_search'),
]