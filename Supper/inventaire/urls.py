# ===================================================================
# Fichier : inventaire/urls.py - URLs pour module inventaire complet
# Chemin : Supper/inventaire/urls.py
# Routes pour saisie inventaire et gestion recettes avec permissions
# ===================================================================

from django.urls import path
from . import views

# Nom de l'application pour les namespaces URL
app_name = 'inventaire'

urlpatterns = [
    # ===================================================================
    # SAISIE D'INVENTAIRES (AGENTS)
    # ===================================================================
    
    # Interface de saisie d'inventaire pour les agents
    path('saisie/', views.InventaireSaisieView.as_view(), name='saisie'),
    
    # Création d'un nouvel inventaire (AJAX)
    path('create/', views.InventaireCreateView.as_view(), name='create'),
    
    # Modification d'un inventaire existant (si pas verrouillé)
    path('<int:pk>/edit/', views.InventaireEditView.as_view(), name='edit'),
    
    # Verrouillage d'un inventaire (empêche modification)
    path('<int:pk>/lock/', views.InventaireLockView.as_view(), name='lock'),
    
    # ===================================================================
    # CONSULTATION DES INVENTAIRES
    # ===================================================================
    
    # Liste des inventaires avec filtres par poste, date, agent
    path('', views.InventaireListView.as_view(), name='list'),
    
    # Détail d'un inventaire avec calculs et statistiques
    path('<int:pk>/', views.InventaireDetailView.as_view(), name='detail'),
    
    # Historique des inventaires d'un poste spécifique
    path('poste/<int:poste_id>/', views.InventairePosteView.as_view(), name='poste_historique'),
    
    # ===================================================================
    # SAISIE DES RECETTES (CHEFS DE POSTE)
    # ===================================================================
    
    # Interface de saisie de recette pour les chefs de poste
    path('recettes/saisie/', views.RecetteSaisieView.as_view(), name='recette_saisie'),
    
    # Création d'une nouvelle recette avec calculs automatiques
    path('recettes/create/', views.RecetteCreateView.as_view(), name='recette_create'),
    
    # Liste des recettes avec taux de déperdition et alertes
    path('recettes/', views.RecetteListView.as_view(), name='recette_list'),
    
    # Détail d'une recette avec analyse de déperdition
    path('recettes/<int:pk>/', views.RecetteDetailView.as_view(), name='recette_detail'),
    
    # ===================================================================
    # STATISTIQUES ET RAPPORTS (ADMINS)
    # ===================================================================
    
    # Statistiques par poste avec graphiques et tendances
    path('stats/poste/<int:poste_id>/', views.StatsPosteView.as_view(), name='stats_poste'),
    
    # Statistiques globales pour les administrateurs
    path('stats/global/', views.StatsGlobalView.as_view(), name='stats_global'),
    
    # Rapport de déperdition avec analyse détaillée
    path('reports/deperdition/', views.DeperditionReportView.as_view(), name='rapport_deperdition'),
    
    # Export des données d'inventaire en CSV/Excel
    path('export/', views.InventaireExportView.as_view(), name='export'),
    
    # Export des recettes en CSV/Excel
    path('recettes/export/', views.RecetteExportView.as_view(), name='recette_export'),
    
    # ===================================================================
    # API POUR LES CALCULS EN TEMPS RÉEL
    # ===================================================================
    
    # API calcul de recette potentielle basée sur inventaire
    path('api/calcul-recette/', views.CalculRecetteAPIView.as_view(), name='api_calcul_recette'),
    
    # API validation des données d'inventaire
    path('api/validate/', views.ValidateInventaireAPIView.as_view(), name='api_validate'),
    
    # API pour suggestions de saisie basées sur l'historique
    path('api/suggestions/', views.SuggestionsAPIView.as_view(), name='api_suggestions'),
    
    # API graphiques déperdition pour admin
    path('api/deperdition-chart/', views.DeperditionChartAPIView.as_view(), name='api_deperdition_chart'),
]