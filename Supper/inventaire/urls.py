# ===================================================================
# inventaire/urls.py - URLs pour la gestion des inventaires
# ===================================================================

from django.urls import path
from . import views

app_name = 'inventaire'

urlpatterns = [
    # Saisie d'inventaire (agents)
    path('saisie/', views.SaisieInventaireView.as_view(), name='saisie_inventaire'),
    path('saisie/<int:poste_id>/<str:date>/', views.SaisieInventaireView.as_view(), name='saisie_inventaire_detail'),
    
    # Consultation des inventaires
    path('', views.InventaireListView.as_view(), name='inventaire_list'),
    path('<int:pk>/', views.InventaireDetailView.as_view(), name='inventaire_detail'),
   # path('<int:pk>/edit/', views.EditInventaireView.as_view(), name='edit_inventaire'),
   # path('<int:pk>/lock/', views.LockInventaireView.as_view(), name='lock_inventaire'),
    #path('<int:pk>/validate/', views.ValidateInventaireView.as_view(), name='validate_inventaire'),
    
    # Gestion des recettes (chefs de poste)
    # path('recettes/', views.RecetteListView.as_view(), name='recette_list'),
    # path('recettes/saisie/', views.SaisieRecetteView.as_view(), name='saisie_recette'),
    # path('recettes/<int:pk>/', views.RecetteDetailView.as_view(), name='recette_detail'),
    # path('recettes/<int:pk>/edit/', views.EditRecetteView.as_view(), name='edit_recette'),
    
    # Configuration des jours
    path('config-jours/', views.ConfigurationJourListView.as_view(), name='config_jour_list'),
    # path('config-jours/create/', views.CreateConfigurationJourView.as_view(), name='create_config_jour'),
    # path('config-jours/<int:pk>/edit/', views.EditConfigurationJourView.as_view(), name='edit_config_jour'),
    
    # Statistiques et rapports
    # path('statistiques/', views.StatistiquesView.as_view(), name='statistiques'),
    # path('statistiques/<int:poste_id>/', views.StatistiquesPosteView.as_view(), name='statistiques_poste'),
    # path('rapports/', views.RapportsView.as_view(), name='rapports'),
    # path('rapports/export/<str:format>/', views.ExportRapportView.as_view(), name='export_rapport'),
    
    # API pour les calculs en temps réel
    path('api/calcul-automatique/', views.CalculAutomatiqueAPIView.as_view(), name='api_calcul_automatique'),
    path('api/verification-jour/', views.VerificationJourAPIView.as_view(), name='api_verification_jour'),
]

