# ===================================================================
# accounts/urls.py - URLs CORRIGÉES - Suppression redirections admin
# CORRECTION : Toutes les URLs postes pointent vers templates personnalisés
# ===================================================================

from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .forms import CustomLoginForm
from . import views_import

app_name = 'accounts'

urlpatterns = [
    # ================================================================
    # AUTHENTIFICATION
    # ================================================================
    path('login/', auth_views.LoginView.as_view(
        template_name='accounts/login.html',  
        redirect_authenticated_user=True,
        extra_context={'title': 'Connexion'}
    ), name='login'),
    
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    
    path('password/change/', auth_views.PasswordChangeView.as_view(
        template_name='accounts/password_change.html',
        success_url='/accounts/profile/',
        extra_context={'title': 'Changer le mot de passe'}
    ), name='password_change'),
    
    # ================================================================
    # GESTION DES UTILISATEURS
    # ================================================================
    path('add-user/', views.redirect_to_add_user_admin, name='add_user_redirect'),
    #path('users/', views.redirect_to_users_admin, name='users'),
    path('users/list/', views.liste_utilisateurs, name='user_list'),
    path('users/create/', views.creer_utilisateur, name='user_create'),
    path('users/bulk-create/', views.CreateBulkUsersView.as_view(), name='user_bulk_create'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/edit/', views.UserUpdateView.as_view(), name='user_edit'),
    path('users/<int:user_id>/edit-admin/', views.redirect_to_edit_user_admin, name='edit_user_admin'),
    path('users/<int:pk>/reset-password/', views.PasswordResetView.as_view(), name='password_reset'),
    
    # ================================================================
    # GESTION DES POSTES - CORRECTION COMPLÈTE
    # TOUTES CES URLs POINTENT VERS VOS TEMPLATES PERSONNALISÉS
    # ================================================================
    
    # LISTE DES POSTES - Template: accounts/liste_postes.html
    path('postes/', views.liste_postes, name='liste_postes'),
    
    # DÉTAIL D'UN POSTE - Template: accounts/detail_poste.html
    path('postes/<int:poste_id>/', views.detail_poste, name='detail_poste'),
    
    # CRÉER UN POSTE - Template: accounts/creer_poste.html
    path('postes/creer/', views.creer_poste, name='creer_poste'),
    
    # MODIFIER UN POSTE - Template: accounts/modifier_poste.html
    path('postes/<int:poste_id>/modifier/', views.modifier_poste, name='modifier_poste'),
    
    # IMPORT EXCEL POSTES
    path('postes/import/', views_import.import_postes_excel, name='import_postes'),
    path('postes/modele-excel/', views_import.telecharger_modele_postes_excel, name='telecharger_modele_postes'),
    
    # ================================================================
    # JOURNAL D'AUDIT
    # ================================================================
    path('audit/', views.journal_audit, name='journal_audit'),
    
    # ================================================================
    # PROFIL UTILISATEUR
    # ================================================================
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/edit/', views.EditProfileView.as_view(), name='profile_edit'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change_password'),
    
    # ================================================================
    # DASHBOARDS
    # ================================================================
    path('dashboard/', views.dashboard_redirect, name='dashboard_redirect'),
    path('dashboard/admin/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('dashboard/chef/', views.ChefPosteDashboardView.as_view(), name='chef_dashboard'),
    path('dashboard/agent/', views.AgentInventaireDashboardView.as_view(), name='agent_dashboard'),
    path('dashboard/general/', views.GeneralDashboardView.as_view(), name='general_dashboard'),
    
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
]

# ===================================================================
# REMARQUE IMPORTANTE :
# - Toutes les fonctions redirect_to_*_admin ont été SUPPRIMÉES
# - Les URLs 'postes/' pointent maintenant vers vos templates
# - Plus aucune redirection forcée vers /admin/accounts/poste/
# ===================================================================