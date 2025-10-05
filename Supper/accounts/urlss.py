# ===================================================================
# accounts/urls.py - URLs harmonisées avec redirections admin Django
# MISE À JOUR : Ajout des redirections vers l'admin Django natif
# ===================================================================

from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .forms import CustomLoginForm
from . import views_import


app_name = 'accounts'

urlpatterns = [
    # ================================================================
    # AUTHENTIFICATION - Vues existantes vérifiées
    # ================================================================
    path('login/', auth_views.LoginView.as_view(
        template_name='accounts/login.html',  
        redirect_authenticated_user=True,
        extra_context={'title': 'Connexion'}
    ), name='login'),
    
    # Vue de déconnexion personnalisée
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    
    path('password/change/', auth_views.PasswordChangeView.as_view(
        template_name='accounts/password_change.html',
        success_url='/accounts/profile/',
        extra_context={'title': 'Changer le mot de passe'}
    ), name='password_change'),
    
  # URL : {% url 'admin:accounts_utilisateursupper_add' %}
    path('add-user/', views.redirect_to_add_user_admin, name='add_user_redirect'),
    
    # URL : {% url 'admin:accounts_utilisateursupper_changelist' %}
    path('users/', views.redirect_to_users_admin, name='users'),
    path('users/list/', views.liste_utilisateurs, name='user_list'),
    path('users/create/', views.creer_utilisateur, name='user_create'),
    path('users/bulk-create/', views.CreateBulkUsersView.as_view(), name='user_bulk_create'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/edit/', views.UserUpdateView.as_view(), name='user_edit'),
    path('users/<int:user_id>/edit-admin/', views.redirect_to_edit_user_admin, name='edit_user_admin'),
    path('users/<int:pk>/reset-password/', views.PasswordResetView.as_view(), name='password_reset'),
    
    # ================================================================
    # GESTION DES POSTES (référencées dans base_site.html)
    # ================================================================
    # URL : {% url 'admin:accounts_poste_changelist' %}
    #path('postes/', views.redirect_to_postes_admin, name='postes'),
    #path('postes/<int:poste_id>/edit-admin/', views.redirect_to_edit_poste_admin, name='edit_poste_admin'),
    
    # ================================================================
    # JOURNAL D'AUDIT (référencé dans base_site.html)
    # ================================================================
    # URL : {% url 'admin:accounts_journalaudit_changelist' %}
    # Journal d'audit
    path('audit/', views.journal_audit, name='journal_audit'),
    
    # ================================================================
    # PROFIL UTILISATEUR
    # ================================================================
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/edit/', views.EditProfileView.as_view(), name='profile_edit'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change_password'),
    
    # ================================================================
    # DASHBOARDS ET REDIRECTIONS
    # ================================================================
    path('dashboard/', views.dashboard_redirect, name='dashboard_redirect'),
    path('dashboard/admin/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('dashboard/chef/', views.ChefPosteDashboardView.as_view(), name='chef_dashboard'),
    path('dashboard/agent/', views.AgentInventaireDashboardView.as_view(), name='agent_dashboard'),
    path('dashboard/general/', views.GeneralDashboardView.as_view(), name='general_dashboard'),
    
    # ================================================================
    # REDIRECTIONS ADMIN DJANGO (pour base_site.html)
    # ================================================================
    #path('admin-redirect/', views.redirect_to_django_admin, name='admin_redirect'),
    #path('admin-help/', views.admin_help_view, name='admin_help'),
    
    # ================================================================
    # API ENDPOINTS
    # ================================================================
    path('api/validate-username/', views.ValidateUsernameAPIView.as_view(), name='api_validate_username'),
    path('api/search-users/', views.UserSearchAPIView.as_view(), name='api_search_users'),
    path('api/postes/', views.postes_api, name='api_postes'),
    path('api/stats/', views.stats_api, name='api_stats'),
    path('api/check-admin-permission/', views.check_admin_permission_api, name='api_check_admin'),
    path('api/departements/', views.api_departements, name='api_departements'),
    # ================================================================
    # GESTION DES ERREURS
    # ================================================================
    path('error/<str:error_type>/', views.redirect_error_handler, name='error_handler'),
    path('postes/import/', views_import.import_postes_excel, name='import_postes'),
    path('postes/modele-excel/', views_import.telecharger_modele_postes_excel, name='telecharger_modele_postes'),

    # Gestion des postes
    path('postes/', views.liste_postes, name='liste_postes'),
    path('postes/<int:poste_id>/', views.detail_poste, name='detail_poste'),
    path('postes/creer/', views.creer_poste, name='creer_poste'),
    path('postes/<int:poste_id>/modifier/', views.modifier_poste, name='modifier_poste'),

]
