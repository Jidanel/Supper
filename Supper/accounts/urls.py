# ===================================================================
# accounts/urls.py - URLs pour l'authentification et admin SUPPER
# ===================================================================
# 🔄 REMPLACE le contenu existant du fichier accounts/urls.py

from django.urls import path, include
from django.contrib.auth import views as auth_views
from .admin import admin_site
from . import views

app_name = 'accounts'

urlpatterns = [
    # URLs d'authentification
    path('login/', auth_views.LoginView.as_view(
        template_name='registration/login.html',
        redirect_authenticated_user=True
    ), name='login'),
    
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    path('password_change/', auth_views.PasswordChangeView.as_view(
        template_name='registration/password_change_form.html',
        success_url='/accounts/password_change/done/'
    ), name='password_change'),
    
    path('password_change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='registration/password_change_done.html'
    ), name='password_change_done'),
    
    # Site admin personnalisé
    path('admin/', admin_site.urls),
    
    # Dashboard intelligent selon rôle
    path('dashboard/', views.dashboard_redirect, name='dashboard'),
    
    # Tableaux de bord spécialisés
    path('dashboard/admin/', views.AdminDashboardView.as_view(), name='admin_dashboard'),
    path('dashboard/chef/', views.ChefPosteDashboardView.as_view(), name='chef_dashboard'),
    path('dashboard/agent/', views.AgentInventaireDashboardView.as_view(), name='agent_dashboard'),
    path('dashboard/general/', views.GeneralDashboardView.as_view(), name='general_dashboard'),
    
    # API endpoints
   # path('api/postes/', views.PostesAPIView.as_view(), name='api_postes'),
    #path('api/stats/', views.StatsAPIView.as_view(), name='api_stats'),
]