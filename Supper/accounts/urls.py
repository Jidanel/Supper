# ===================================================================
# accounts/urls.py - URLs harmonisées avec les vues existantes
# VÉRIFIÉ : Toutes les URLs correspondent aux vues dans views.py
# ===================================================================

from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # ================================================================
    # AUTHENTIFICATION - Vues existantes vérifiées
    # ================================================================
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.CustomLogoutView.as_view(), name='logout'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change_password'),
    
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
    # API ENDPOINTS - Vues existantes vérifiées
    # ================================================================
    path('api/validate-username/', views.ValidateUsernameAPIView.as_view(), name='validate_username_api'),
    path('api/user-search/', views.UserSearchAPIView.as_view(), name='user_search_api'),
    path('api/postes/', views.postes_api, name='postes_api'),
    path('api/stats/', views.stats_api, name='stats_api'),
    
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