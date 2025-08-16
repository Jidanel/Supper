# ===================================================================
# accounts/urls.py - URLs harmonisées avec redirections admin Django
# MISE À JOUR : Ajout des redirections vers l'admin Django natif
# ===================================================================

from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .forms import CustomLoginForm


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
    
    # ================================================================
    # GESTION DU PROFIL - Vues existantes vérifiées
    # ================================================================
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('profile/edit/', views.EditProfileView.as_view(), name='edit_profile'),
    
    # ================================================================
    # GESTION DES UTILISATEURS (ADMIN) - Vues existantes vérifiées
    # ================================================================
    path('users/', views.UserListView.as_view(), name='user_list'),
    path('users/create/', views.CreateUserView.as_view(), name='create_user'),
    path('users/create-bulk/', views.CreateBulkUsersView.as_view(), name='create_bulk_users'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/edit/', views.UserUpdateView.as_view(), name='edit_user'),
    
    # ================================================================
    # RESET PASSWORD - Vue existante vérifiée
    # ================================================================
    path('users/<int:pk>/reset-password/', views.PasswordResetView.as_view(), name='reset_password'),
    
    # ================================================================
    # DASHBOARDS - Vues existantes vérifiées
    # ================================================================
    path('dashboard-redirect/', views.dashboard_redirect, name='dashboard_redirect'),
    path('admin/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('chef/', views.ChefPosteDashboardView.as_view(), name='chef_dashboard'),
    path('agent/', views.AgentInventaireDashboardView.as_view(), name='agent_dashboard'),
    path('general/', views.GeneralDashboardView.as_view(), name='general_dashboard'),
    
    # ================================================================
    # NOUVEAU: REDIRECTIONS VERS ADMIN DJANGO
    # ================================================================
    # Redirections directes vers l'admin Django avec vérifications de permissions
    path('redirect/django-admin/', views.redirect_to_django_admin, name='redirect_django_admin'),
    path('redirect/users-admin/', views.redirect_to_users_admin, name='redirect_users_admin'),
    path('redirect/postes-admin/', views.redirect_to_postes_admin, name='redirect_postes_admin'),
    path('redirect/inventaires-admin/', views.redirect_to_inventaires_admin, name='redirect_inventaires_admin'),
    path('redirect/recettes-admin/', views.redirect_to_recettes_admin, name='redirect_recettes_admin'),
    path('redirect/journal-admin/', views.redirect_to_journal_admin, name='redirect_journal_admin'),
    path('redirect/add-user-admin/', views.redirect_to_add_user_admin, name='redirect_add_user_admin'),
    
    # Redirections avec paramètres
    path('redirect/edit-user-admin/<int:user_id>/', views.redirect_to_edit_user_admin, name='redirect_edit_user_admin'),
    path('redirect/edit-poste-admin/<int:poste_id>/', views.redirect_to_edit_poste_admin, name='redirect_edit_poste_admin'),
    
    # ================================================================
    # API ENDPOINTS - Vues existantes vérifiées
    # ================================================================
    path('api/validate-username/', views.ValidateUsernameAPIView.as_view(), name='validate_username_api'),
    path('api/user-search/', views.UserSearchAPIView.as_view(), name='user_search_api'),
    path('api/postes/', views.postes_api, name='postes_api'),
    path('api/stats/', views.stats_api, name='stats_api'),
    
    # NOUVEAU: API pour vérifier les permissions admin
    path('api/check-admin-permission/', views.check_admin_permission_api, name='check_admin_permission_api'),
    
    # ================================================================
    # URLS COMMENTÉES - Vues non encore créées
    # ================================================================
    # path('users/<int:pk>/toggle-active/', views.ToggleUserActiveView.as_view(), name='toggle_user_active'),
    # path('postes/', views.PosteListView.as_view(), name='poste_list'),
    # path('postes/create/', views.CreatePosteView.as_view(), name='create_poste'),
    # path('postes/<int:pk>/', views.PosteDetailView.as_view(), name='poste_detail'),
    # path('postes/<int:pk>/edit/', views.EditPosteView.as_view(), name='edit_poste'),
    # path('audit/', views.AuditLogView.as_view(), name='audit_log'),
    # path('audit/<int:pk>/', views.AuditDetailView.as_view(), name='audit_detail'),
    # path('notifications/', views.NotificationListView.as_view(), name='notifications'),
    # path('notifications/<int:pk>/mark-read/', views.MarkNotificationReadView.as_view(), name='mark_notification_read'),
    # path('notifications/mark-all-read/', views.MarkAllNotificationsReadView.as_view(), name='mark_all_notifications_read'),
]