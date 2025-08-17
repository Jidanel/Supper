# ===================================================================
# inventaire/urls.py - URLs pour la gestion des inventaires avec redirections admin Django
# MISE À JOUR : Ajout des redirections vers l'admin Django pour la gestion des inventaires
# ===================================================================

from django.urls import path
from . import views

app_name = 'inventaire'

urlpatterns = [
    # ================================================================
    # SAISIE D'INVENTAIRE (AGENTS) - Vues existantes
    # ================================================================
    path('saisie/', views.SaisieInventaireView.as_view(), name='saisie_inventaire'),
    path('saisie/<int:poste_id>/<str:date>/', views.SaisieInventaireView.as_view(), name='saisie_inventaire_detail'),
    
    # ================================================================
    # CONSULTATION DES INVENTAIRES - Vues existantes
    # ================================================================
    path('', views.InventaireListView.as_view(), name='inventaire_list'),
    path('<int:pk>/', views.InventaireDetailView.as_view(), name='inventaire_detail'),
    # path('<int:pk>/edit/', views.EditInventaireView.as_view(), name='edit_inventaire'),
    # path('<int:pk>/lock/', views.LockInventaireView.as_view(), name='lock_inventaire'),
    # path('<int:pk>/validate/', views.ValidateInventaireView.as_view(), name='validate_inventaire'),
    
    # ================================================================
    # CONFIGURATION DES JOURS - Vues existantes
    # ================================================================
    path('config-jours/', views.ConfigurationJourListView.as_view(), name='config_jour_list'),
    # path('config-jours/create/', views.CreateConfigurationJourView.as_view(), name='create_config_jour'),
    # path('config-jours/<int:pk>/edit/', views.EditConfigurationJourView.as_view(), name='edit_config_jour'),
    
    # URLs pour la gestion des inventaires mensuels
    path('mensuel/<int:inventaire_id>/gerer-jours/', 
         views.gerer_jours_inventaire, 
         name='gerer_jours'),
         
    # ================================================================
    # NOUVEAU: REDIRECTIONS VERS ADMIN DJANGO POUR LA GESTION
    # ================================================================
    # Redirections vers l'admin Django pour la gestion complète des inventaires
    path('admin/inventaires/', views.redirect_to_inventaires_admin, name='redirect_inventaires_admin'),
    path('admin/recettes/', views.redirect_to_recettes_admin, name='redirect_recettes_admin'),
    path('admin/config-jours/', views.redirect_to_config_jours_admin, name='redirect_config_jours_admin'),
    path('admin/statistiques/', views.redirect_to_statistiques_admin, name='redirect_statistiques_admin'),
    
    # Redirections spécifiques avec paramètres
    path('admin/inventaire/<int:inventaire_id>/', views.redirect_to_edit_inventaire_admin, name='redirect_edit_inventaire_admin'),
    path('admin/recette/<int:recette_id>/', views.redirect_to_edit_recette_admin, name='redirect_edit_recette_admin'),
    
    # Redirections pour création
    path('admin/add-inventaire/', views.redirect_to_add_inventaire_admin, name='redirect_add_inventaire_admin'),
    path('admin/add-recette/', views.redirect_to_add_recette_admin, name='redirect_add_recette_admin'),
    path('admin/add-config-jour/', views.redirect_to_add_config_jour_admin, name='redirect_add_config_jour_admin'),
    
    # ================================================================
    # GESTION DES RECETTES (CHEFS DE POSTE) - URLs commentées en attente de développement
    # ================================================================
    # path('recettes/', views.RecetteListView.as_view(), name='recette_list'),
    # path('recettes/saisie/', views.SaisieRecetteView.as_view(), name='saisie_recette'),
    # path('recettes/<int:pk>/', views.RecetteDetailView.as_view(), name='recette_detail'),
    # path('recettes/<int:pk>/edit/', views.EditRecetteView.as_view(), name='edit_recette'),
    
    # ================================================================
    # STATISTIQUES ET RAPPORTS - URLs commentées en attente de développement
    # ================================================================
    # path('statistiques/', views.StatistiquesView.as_view(), name='statistiques'),
    # path('statistiques/<int:poste_id>/', views.StatistiquesPosteView.as_view(), name='statistiques_poste'),
    # path('rapports/', views.RapportsView.as_view(), name='rapports'),
    # path('rapports/export/<str:format>/', views.ExportRapportView.as_view(), name='export_rapport'),
    
    # ================================================================
    # API POUR LES CALCULS EN TEMPS RÉEL - Vues existantes
    # ================================================================
    path('api/calcul-automatique/', views.CalculAutomatiqueAPIView.as_view(), name='api_calcul_automatique'),
    path('api/verification-jour/', views.VerificationJourAPIView.as_view(), name='api_verification_jour'),
    
    # NOUVEAU: API pour intégration avec admin Django
    path('api/inventaire-stats/', views.inventaire_stats_api, name='api_inventaire_stats'),
    path('api/recette-stats/', views.recette_stats_api, name='api_recette_stats'),
    path('api/check-day-status/', views.check_day_status_api, name='api_check_day_status'),
]