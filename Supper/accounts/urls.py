# accounts/urls.py - Version simplifiée pour test
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    # Authentification de base
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # Gestion mot de passe
    path('password/change/', views.PasswordChangeView.as_view(), name='password_change'),
    
    # Profil personnel
    path('profile/', views.ProfileView.as_view(), name='profile'),
    
    # URLs admin (à ajouter après test)
    # path('users/', views.UserListView.as_view(), name='user_list'),
    # path('users/create/', views.UserCreateView.as_view(), name='user_create'),
]