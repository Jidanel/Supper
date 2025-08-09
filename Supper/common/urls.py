# ===================================================================
# common/urls.py - URLs pour les fonctions communes et dashboards
# ===================================================================

from django.urls import path
from . import views
from django.shortcuts import redirect

app_name = 'common'


def accueil_intelligent(request):
    """Redirection intelligente selon l'état de connexion"""
    if not request.user.is_authenticated:
        return redirect('/admin/login/')
    
    # Utilisateur connecté → Dashboard admin pour tous (temporaire)
    return redirect('/admin/')

urlpatterns = [
    # Dashboard principal (redirection intelligente selon rôle)
     path('dashboard/', accueil_intelligent, name='dashboard'),
    
    # Dashboards spécialisés par rôle
    path('dashboard/admin/', views.DashboardAdminView.as_view(), name='admin_dashboard'),
    path('dashboard/chef/', views.DashboardChefView.as_view(), name='chef_dashboard'),
    path('dashboard/agent/', views.DashboardAgentView.as_view(), name='agent_dashboard'),
    # path('dashboard/general/', views.GeneralDashboardView.as_view(), name='general_dashboard'),
    
    # API pour données dashboard
    # path('api/stats-generales/', views.StatsGeneralesAPIView.as_view(), name='api_stats_generales'),
    # path('api/activite-recente/', views.ActiviteRecenteAPIView.as_view(), name='api_activite_recente'),
    # path('api/graphiques/', views.GraphiquesAPIView.as_view(), name='api_graphiques'),
    
    # # Recherche globale
    # path('recherche/', views.RechercheGlobaleView.as_view(), name='recherche_globale'),
    # path('api/recherche/', views.RechercheAPIView.as_view(), name='api_recherche'),
    
    # # Exports et rapports
    # path('export/csv/', views.ExportCSVView.as_view(), name='export_csv'),
    # path('export/excel/', views.ExportExcelView.as_view(), name='export_excel'),
    # path('export/pdf/', views.ExportPDFView.as_view(), name='export_pdf'),
    
    # # Utilitaires
    # path('ajax/regions-departements/', views.RegionDepartementAjaxView.as_view(), name='ajax_regions_departements'),
    # path('ajax/postes-par-region/', views.PostesParRegionAjaxView.as_view(), name='ajax_postes_par_region'),
    
    # # Pages d'erreur personnalisées
    # path('403/', views.Error403View.as_view(), name='error_403'),
    # path('404/', views.Error404View.as_view(), name='error_404'),
    # path('500/', views.Error500View.as_view(), name='error_500'),

    path('ouvrir-jour/', views.ouvrir_jour_saisie, name='ouvrir_jour_saisie'),
    path('rapport-hebdomadaire/', views.generer_rapport_hebdomadaire, name='generer_rapport_hebdomadaire'),
]