# ===================================================================
# Fichier : Supper/common/views.py (mise à jour)
# Vues avec gestion des permissions selon les clarifications
# Agent : pas de recettes potentielles, Chef : seulement taux, Admin : tout
# ===================================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Sum, Avg, Q, Min, Max
from django.utils import timezone
from datetime import datetime, timedelta
import json

from accounts.models import UtilisateurSUPPER, Poste, JournalAudit
from inventaire.models import *
import logging

logger = logging.getLogger('supper')

# ===================================================================
# DASHBOARD ADMINISTRATEUR - ACCÈS COMPLET
# ===================================================================

class DashboardAdminView(LoginRequiredMixin, TemplateView):
    """
    Dashboard complet pour administrateurs
    CORRIGÉ - Vérification des permissions admin
    """
    template_name = 'common/dashboard_admin.html'
    
    def dispatch(self, request, *args, **kwargs):
        """Vérifier que l'utilisateur a les droits admin - LOGIQUE CORRIGÉE"""
        
        user = request.user
        
        # DEBUG: Logs pour diagnostiquer
        logger.info(
            f"VÉRIFICATION ACCÈS DASHBOARD ADMIN - "
            f"Utilisateur: {user.username} | "
            f"is_superuser: {user.is_superuser} | "
            f"is_staff: {user.is_staff} | "
            f"habilitation: {user.habilitation}"
        )
        
        # Vérifier les permissions admin
        has_admin_access = (
            user.is_superuser or 
            user.is_staff or 
            user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission']
        )
        
        if not has_admin_access:
            logger.warning(f"ACCÈS REFUSÉ DASHBOARD ADMIN - {user.username}")
            messages.error(request, _("Accès non autorisé à cette section administrative."))
            return redirect('common:dashboard_general')
        
        logger.info(f"ACCÈS AUTORISÉ DASHBOARD ADMIN - {user.username}")
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        """Ajouter toutes les données nécessaires au dashboard admin"""
        context = super().get_context_data(**kwargs)
        
        user = self.request.user
        
        # ================================================================
        # STATISTIQUES GÉNÉRALES
        # ================================================================
        
        try:
            from accounts.models import UtilisateurSUPPER, Poste
            from inventaire.models import InventaireJournalier, RecetteJournaliere
            
            # Statistiques utilisateurs
            total_utilisateurs = UtilisateurSUPPER.objects.count()
            utilisateurs_actifs = UtilisateurSUPPER.objects.filter(is_active=True).count()
            
            # Statistiques postes
            total_postes = Poste.objects.count()
            postes_peage = Poste.objects.filter(type='peage').count()
            postes_pesage = Poste.objects.filter(type='pesage').count()
            
            # Statistiques récentes (7 derniers jours)
            depuis_7_jours = timezone.now() - timedelta(days=7)
            inventaires_recents = InventaireJournalier.objects.filter(
                date_inventaire__gte=depuis_7_jours
            ).count()
            
            recettes_recentes = RecetteJournaliere.objects.filter(
                date_recette__gte=depuis_7_jours
            ).count()
            
            context.update({
                'stats_generales': {
                    'total_utilisateurs': total_utilisateurs,
                    'utilisateurs_actifs': utilisateurs_actifs,
                    'total_postes': total_postes,
                    'postes_peage': postes_peage,
                    'postes_pesage': postes_pesage,
                    'inventaires_recents': inventaires_recents,
                    'recettes_recentes': recettes_recentes,
                },
                'can_manage_users': True,  # Tous les admins peuvent gérer les utilisateurs
                'can_view_all_data': True,  # Tous les admins voient toutes les données
                'user_dashboard_title': 'Administration SUPPER - Dashboard Principal'
            })
            
        except Exception as e:
            logger.error(f"Erreur chargement données dashboard admin: {str(e)}")
            messages.error(self.request, _("Erreur lors du chargement des données."))
            context['stats_generales'] = {}
        
        return context

# ===================================================================
# DASHBOARD CHEF DE POSTE - TAUX SEULEMENT
# ===================================================================

class DashboardChefView(LoginRequiredMixin, TemplateView):
    """Dashboard chef de poste - TEMPORAIREMENT DÉSACTIVÉ"""
    template_name = 'common/dashboard_chef.html'
    
    def dispatch(self, request, *args, **kwargs):
        """Rediriger vers dashboard général en attendant le développement complet"""
        messages.info(
            request, 
            _("L'interface chef de poste est en cours de développement. "
              "Vous êtes redirigé vers le dashboard général.")
        )
        return redirect('common:dashboard_general')

class DashboardAgentView(LoginRequiredMixin, TemplateView):
    """Dashboard agent inventaire - TEMPORAIREMENT DÉSACTIVÉ"""
    template_name = 'common/dashboard_agent.html'
    
    def dispatch(self, request, *args, **kwargs):
        """Rediriger vers dashboard général en attendant le développement complet"""
        messages.info(
            request, 
            _("L'interface agent inventaire est en cours de développement. "
              "Vous êtes redirigé vers le dashboard général.")
        )

# ===================================================================
# DASHBOARD GÉNÉRAL - POUR AUTRES RÔLES
# ===================================================================

class DashboardGeneralView(LoginRequiredMixin, TemplateView):
    """Dashboard général pour les utilisateurs non-admin"""
    template_name = 'common/dashboard_general.html'
    
    def get_context_data(self, **kwargs):
        """Contexte minimal pour le dashboard général"""
        context = super().get_context_data(**kwargs)
        
        user = self.request.user
        
        context.update({
            'user_dashboard_title': f'SUPPER - Espace {user.get_habilitation_display()}',
            'message_developpement': _(
                "Cette interface est en cours de développement. "
                "Les fonctionnalités spécialisées seront disponibles prochainement."
            )
        })
        
        return context
# ===================================================================
# API ENDPOINTS AVEC PERMISSIONS
# ===================================================================

@login_required
def api_stats_dashboard(request):
    """
    API pour statistiques en temps réel selon permissions utilisateur
    """
    user = request.user
    today = timezone.now().date()
    
    data = {
        'success': True,
        'timestamp': timezone.now().isoformat(),
    }
    
    # Stats selon le rôle
    if user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'] or user.is_superuser:
        # Admin : toutes les stats
        data['stats'] = {
            'inventaires_today': InventaireJournalier.objects.filter(date=today).count(),
            'recettes_today': RecetteJournaliere.objects.filter(date=today).count(),
            'taux_moyen_today': RecetteJournaliere.objects.filter(
                date=today
            ).aggregate(Avg('taux_deperdition'))['taux_deperdition__avg'] or 0,
            'postes_actifs': Poste.objects.filter(is_active=True).count(),
        }
        
        # Admin peut voir alertes déperdition
        data['alertes'] = {
            'deperdition_critique': RecetteJournaliere.objects.filter(
                date__gte=today - timedelta(days=7),
                taux_deperdition__lt=-30
            ).count()
        }
    
    elif user.habilitation in ['chef_peage', 'chef_pesage']:
        # Chef : stats de son poste seulement, sans recettes potentielles
        if user.poste_affectation:
            try:
                recette_today = RecetteJournaliere.objects.get(
                    poste=user.poste_affectation,
                    date=today
                )
                data['stats'] = {
                    'recette_today': float(recette_today.montant),
                    'taux_today': float(recette_today.taux_deperdition or 0),
                    # Pas de recette_potentielle
                }
            except RecetteJournaliere.DoesNotExist:
                data['stats'] = {
                    'recette_today': 0,
                    'taux_today': 0,
                }
    
    elif user.habilitation == 'agent_inventaire':
        # Agent : seulement ses inventaires, pas de données financières
        data['stats'] = {
            'mes_inventaires_mois': InventaireJournalier.objects.filter(
                agent=user,
                date__gte=today.replace(day=1)
            ).count(),
            'inventaire_today_exists': InventaireJournalier.objects.filter(
                agent_saisie=user,
                date=today
            ).exists(),
        }
    
    else:
        # Autres rôles : stats limitées
        data['stats'] = {
            'modules_disponibles': len([
                m for m in ['peut_gerer_peage', 'peut_gerer_pesage', 'peut_gerer_inventaire']
                if getattr(user, m, False)
            ])
        }
    
    return JsonResponse(data)


@login_required
def api_graphique_evolution(request):
    """
    API pour graphiques d'évolution selon permissions
    """
    user = request.user
    today = timezone.now().date()
    
    # Seuls certains rôles peuvent voir les graphiques
    if user.habilitation not in [
        'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission', 
        'chef_peage', 'chef_pesage'
    ]:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    # Période : 7 derniers jours
    semaine = [today - timedelta(days=i) for i in range(6, -1, -1)]
    
    if user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission']:
        # Admin : vue globale
        evolution_taux = []
        evolution_recettes = []
        
        for jour in semaine:
            stats_jour = RecetteJournaliere.objects.filter(date=jour).aggregate(
                taux_moyen=Avg('taux_deperdition'),
                recettes_total=Sum('montant')
            )
            evolution_taux.append(round(stats_jour['taux_moyen'] or 0, 1))
            evolution_recettes.append(float(stats_jour['recettes_total'] or 0))
        
        data = {
            'dates': [jour.strftime('%d/%m') for jour in semaine],
            'taux_deperdition': evolution_taux,
            'recettes': evolution_recettes,
            'scope': 'global'
        }
    
    elif user.habilitation in ['chef_peage', 'chef_pesage'] and user.poste_affectation:
        # Chef : son poste seulement
        evolution_taux = []
        evolution_recettes = []
        
        for jour in semaine:
            try:
                recette = RecetteJournaliere.objects.get(
                    poste=user.poste_affectation,
                    date=jour
                )
                evolution_taux.append(round(recette.taux_deperdition or 0, 1))
                evolution_recettes.append(float(recette.montant))
            except RecetteJournaliere.DoesNotExist:
                evolution_taux.append(None)
                evolution_recettes.append(0)
        
        data = {
            'dates': [jour.strftime('%d/%m') for jour in semaine],
            'taux_deperdition': evolution_taux,
            'recettes': evolution_recettes,
            'scope': 'poste',
            'poste': user.poste_affectation.nom
        }
    
    else:
        return JsonResponse({'error': 'Données non disponibles'}, status=404)
    
    return JsonResponse(data)


# ===================================================================
# ACTIONS RAPIDES POUR ADMINISTRATEURS
# ===================================================================

@login_required
def ouvrir_jour_saisie(request):
    """
    Action rapide pour ouvrir un jour pour saisie
    Réservée aux administrateurs
    """
    if request.user.habilitation not in ['admin_principal', 'coord_psrr', 'serv_info']:
        messages.error(request, _("Action non autorisée."))
        return redirect('common:dashboard_general')
    
    if request.method == 'POST':
        date_str = request.POST.get('date')
        if date_str:
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                
                config_jour, created = ConfigurationJour.objects.get_or_create(
                    date=date_obj,
                    defaults={
                        'status': "ouvert",
                        'cree_par': request.user,
                        'description': f'Ouvert par {request.user.nom_complet}'
                    }
                )
                
                if not created:
                    config_jour.statut = "ouvert"
                    config_jour.save()
                
                messages.success(request, f'Jour {date_obj.strftime("%d/%m/%Y")} ouvert pour saisie.')
                
                # Journaliser l'action
                JournalAudit.objects.create(
                    utilisateur=request.user,
                    action="Ouverture jour saisie",
                    details=f"Jour {date_obj.strftime('%d/%m/%Y')} ouvert pour saisie inventaires",
                    succes=True
                )
                
            except ValueError:
                messages.error(request, _("Format de date invalide."))
        else:
            # Ouvrir aujourd'hui par défaut
            today = timezone.now().date()
            config_jour, created = ConfigurationJour.objects.get_or_create(
                date=today,
                defaults={
                    'status': "ouvert",
                    'cree_par': request.user,
                    'description': f'Ouvert par {request.user.nom_complet}'
                }
            )
            
            if not created:
                config_jour.statut = "ouvert"
                config_jour.save()
            
            messages.success(request, f'Jour {today.strftime("%d/%m/%Y")} ouvert pour saisie.')
    
    return redirect('common:dashboard_admin')


@login_required
def generer_rapport_hebdomadaire(request):
    """
    Génération de rapport hebdomadaire
    Réservée aux administrateurs et service émission
    """
    if request.user.habilitation not in [
        'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'
    ] or request.user.is_staff or request.user.is_superuser:
        messages.error(request, _("Action non autorisée."))
        return redirect('common:dashboard_general')
    
    # Logic pour générer le rapport hebdomadaire
    # À implémenter selon besoins spécifiques
    
    messages.info(request, _("Génération de rapport en cours..."))
    return redirect('common:dashboard_admin')

# ===================================================================
# Fichier : Supper/common/views.py (ajout)
# Vues pour graphiques statistiques administrateurs
# Graphiques hebdomadaires/mensuels avec classements
# ===================================================================

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Avg, Sum, Count, Q
from datetime import datetime, timedelta
import json

from accounts.models import UtilisateurSUPPER, Poste
from inventaire.models import RecetteJournaliere, InventaireJournalier


@login_required
def api_graphique_hebdomadaire(request):
    """
    API pour graphique hebdomadaire des taux de déperdition
    Accessible uniquement aux administrateurs
    """
    # Vérifier permissions admin
    if request.user.habilitation not in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'] or request.user.is_staff or request.user.is_superuser:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    # Calculer la semaine (lundi à dimanche)
    today = datetime.now().date()
    debut_semaine = today - timedelta(days=today.weekday())  # Lundi
    fin_semaine = debut_semaine + timedelta(days=6)  # Dimanche
    
    # Données par jour de la semaine
    jours_semaine = []
    taux_moyens = []
    recettes_totales = []
    postes_actifs = []
    
    for i in range(7):
        jour = debut_semaine + timedelta(days=i)
        
        # Statistiques du jour
        stats_jour = RecetteJournaliere.objects.filter(date=jour).aggregate(
            taux_moyen=Avg('taux_deperdition'),
            recettes_total=Sum('montant'),
            nb_postes=Count('poste', distinct=True)
        )
        
        jours_semaine.append(jour.strftime('%A %d/%m'))  # "Lundi 15/01"
        taux_moyens.append(round(stats_jour['taux_moyen'] or 0, 1))
        recettes_totales.append(float(stats_jour['recettes_total'] or 0))
        postes_actifs.append(stats_jour['nb_postes'] or 0)
    
    # Classement des postes par taux de déperdition (semaine)
    classement_postes = RecetteJournaliere.objects.filter(
        date__gte=debut_semaine,
        date__lte=fin_semaine
    ).values(
        'poste__nom',
        'poste__region'
    ).annotate(
        taux_moyen=Avg('taux_deperdition'),
        recettes_total=Sum('montant'),
        nb_jours=Count('date', distinct=True)
    ).order_by('taux_moyen')[:20]  # 20 meilleurs/pires postes
    
    data = {
        'periode': f"Semaine du {debut_semaine.strftime('%d/%m/%Y')} au {fin_semaine.strftime('%d/%m/%Y')}",
        'graphique_journalier': {
            'jours': jours_semaine,
            'taux_moyens': taux_moyens,
            'recettes_totales': recettes_totales,
            'postes_actifs': postes_actifs
        },
        'classement_postes': [
            {
                'rang': idx + 1,
                'poste': item['poste__nom'],
                'region': item['poste__region'],
                'taux_moyen': round(item['taux_moyen'] or 0, 1),
                'recettes_total': float(item['recettes_total'] or 0),
                'nb_jours_actifs': item['nb_jours'],
                'performance': 'Excellent' if (item['taux_moyen'] or 0) >= -5 
                              else 'Bon' if (item['taux_moyen'] or 0) >= -15
                              else 'Moyen' if (item['taux_moyen'] or 0) >= -25
                              else 'Critique'
            }
            for idx, item in enumerate(classement_postes)
        ],
        'resume_semaine': {
            'taux_global': round(sum(taux_moyens) / len([t for t in taux_moyens if t != 0]) if any(taux_moyens) else 0, 1),
            'recettes_totales': sum(recettes_totales),
            'postes_actifs_total': len(set(item['poste__nom'] for item in classement_postes)),
            'meilleur_jour': jours_semaine[taux_moyens.index(max(taux_moyens))] if taux_moyens else None,
            'pire_jour': jours_semaine[taux_moyens.index(min(taux_moyens))] if taux_moyens else None
        }
    }
    
    return JsonResponse(data)


@login_required
def api_graphique_mensuel(request):
    """
    API pour graphique mensuel des taux de déperdition
    Accessible uniquement aux administrateurs
    """
    # Vérifier permissions admin
    if request.user.habilitation not in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'] or request.user.is_staff or request.user.is_superuser:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    # Mois courant
    today = datetime.now().date()
    debut_mois = today.replace(day=1)
    
    # Calculer fin du mois
    if debut_mois.month == 12:
        fin_mois = debut_mois.replace(year=debut_mois.year + 1, month=1) - timedelta(days=1)
    else:
        fin_mois = debut_mois.replace(month=debut_mois.month + 1) - timedelta(days=1)
    
    # Données par semaine du mois
    semaines = []
    taux_semaines = []
    recettes_semaines = []
    
    date_courante = debut_mois
    semaine_num = 1
    
    while date_courante <= fin_mois:
        # Calculer fin de semaine (dimanche ou fin du mois)
        fin_semaine = date_courante + timedelta(days=6 - date_courante.weekday())
        if fin_semaine > fin_mois:
            fin_semaine = fin_mois
        
        # Statistiques de la semaine
        stats_semaine = RecetteJournaliere.objects.filter(
            date__gte=date_courante,
            date__lte=fin_semaine
        ).aggregate(
            taux_moyen=Avg('taux_deperdition'),
            recettes_total=Sum('montant')
        )
        
        semaines.append(f"S{semaine_num} ({date_courante.strftime('%d/%m')} - {fin_semaine.strftime('%d/%m')})")
        taux_semaines.append(round(stats_semaine['taux_moyen'] or 0, 1))
        recettes_semaines.append(float(stats_semaine['recettes_total'] or 0))
        
        # Passer à la semaine suivante (lundi)
        date_courante = fin_semaine + timedelta(days=1)
        if date_courante.weekday() != 0:  # Si pas lundi
            date_courante += timedelta(days=7 - date_courante.weekday())
        semaine_num += 1
    
    # Classement mensuel des postes avec évolution
    classement_mensuel = RecetteJournaliere.objects.filter(
        date__gte=debut_mois,
        date__lte=fin_mois
    ).values(
        'poste__nom',
        'poste__region',
        'poste__type'
    ).annotate(
        taux_moyen=Avg('taux_deperdition'),
        recettes_total=Sum('montant'),
        nb_jours=Count('date', distinct=True),
        nb_vehicules=Sum('inventaire__total_vehicules')
    ).order_by('taux_moyen')
    
    # Top 10 meilleurs et pires postes
    meilleurs_postes = list(classement_mensuel.filter(taux_moyen__gte=-10)[:10])
    pires_postes = list(classement_mensuel.filter(taux_moyen__lt=-30).order_by('taux_moyen')[:10])
    
    # Évolution hebdomadaire par région
    evolution_regions = {}
    regions = Poste.objects.values_list('region', flat=True).distinct()
    
    for region in regions:
        if not region:
            continue
            
        taux_region = []
        for i, semaine in enumerate(semaines):
            # Retrouver les dates de cette semaine
            date_debut_sem = debut_mois + timedelta(weeks=i)
            date_fin_sem = min(date_debut_sem + timedelta(days=6), fin_mois)
            
            taux_sem = RecetteJournaliere.objects.filter(
                date__gte=date_debut_sem,
                date__lte=date_fin_sem,
                poste__region=region
            ).aggregate(Avg('taux_deperdition'))['taux_deperdition__avg']
            
            taux_region.append(round(taux_sem or 0, 1))
        
        evolution_regions[region] = taux_region
    
    # Statistiques comparatives avec mois précédent
    mois_precedent_debut = (debut_mois - timedelta(days=1)).replace(day=1)
    mois_precedent_fin = debut_mois - timedelta(days=1)
    
    stats_mois_precedent = RecetteJournaliere.objects.filter(
        date__gte=mois_precedent_debut,
        date__lte=mois_precedent_fin
    ).aggregate(
        taux_moyen=Avg('taux_deperdition'),
        recettes_total=Sum('montant')
    )
    
    stats_mois_actuel = RecetteJournaliere.objects.filter(
        date__gte=debut_mois,
        date__lte=today
    ).aggregate(
        taux_moyen=Avg('taux_deperdition'),
        recettes_total=Sum('montant')
    )
    
    # Calcul évolution
    evolution_taux = 0
    evolution_recettes = 0
    
    if stats_mois_precedent['taux_moyen'] and stats_mois_actuel['taux_moyen']:
        evolution_taux = stats_mois_actuel['taux_moyen'] - stats_mois_precedent['taux_moyen']
    
    if stats_mois_precedent['recettes_total'] and stats_mois_actuel['recettes_total']:
        evolution_recettes = ((stats_mois_actuel['recettes_total'] - stats_mois_precedent['recettes_total']) / stats_mois_precedent['recettes_total']) * 100
    
    data = {
        'periode': f"Mois de {debut_mois.strftime('%B %Y')}",
        'graphique_hebdomadaire': {
            'semaines': semaines,
            'taux_moyens': taux_semaines,
            'recettes_totales': recettes_semaines
        },
        'evolution_regions': evolution_regions,
        'classement_complet': [
            {
                'rang': idx + 1,
                'poste': item['poste__nom'],
                'region': item['poste__region'],
                'type': item['poste__type'],
                'taux_moyen': round(item['taux_moyen'] or 0, 1),
                'recettes_total': float(item['recettes_total'] or 0),
                'nb_jours_actifs': item['nb_jours'],
                'total_vehicules': item['nb_vehicules'] or 0,
                'performance_color': (
                    '#28a745' if (item['taux_moyen'] or 0) >= -10 else
                    '#ffc107' if (item['taux_moyen'] or 0) >= -25 else
                    '#dc3545'
                )
            }
            for idx, item in enumerate(classement_mensuel)
        ],
        'top_performers': {
            'meilleurs': [
                {
                    'rang': idx + 1,
                    'poste': item['poste__nom'],
                    'region': item['poste__region'],
                    'taux': round(item['taux_moyen'], 1),
                    'recettes': float(item['recettes_total'])
                }
                for idx, item in enumerate(meilleurs_postes)
            ],
            'a_ameliorer': [
                {
                    'rang': idx + 1,
                    'poste': item['poste__nom'],
                    'region': item['poste__region'],
                    'taux': round(item['taux_moyen'], 1),
                    'recettes': float(item['recettes_total'])
                }
                for idx, item in enumerate(pires_postes)
            ]
        },
        'comparaison_mensuelle': {
            'mois_actuel': {
                'taux_moyen': round(stats_mois_actuel['taux_moyen'] or 0, 1),
                'recettes_total': float(stats_mois_actuel['recettes_total'] or 0)
            },
            'mois_precedent': {
                'taux_moyen': round(stats_mois_precedent['taux_moyen'] or 0, 1),
                'recettes_total': float(stats_mois_precedent['recettes_total'] or 0)
            },
            'evolution': {
                'taux': round(evolution_taux, 1),
                'recettes_pourcent': round(evolution_recettes, 1),
                'tendance_taux': 'amélioration' if evolution_taux > 0 else 'dégradation' if evolution_taux < 0 else 'stable',
                'tendance_recettes': 'hausse' if evolution_recettes > 0 else 'baisse' if evolution_recettes < 0 else 'stable'
            }
        },
        'resume_mensuel': {
            'nb_postes_total': len(classement_mensuel),
            'nb_postes_bons': len([p for p in classement_mensuel if (p['taux_moyen'] or 0) >= -10]),
            'nb_postes_critiques': len([p for p in classement_mensuel if (p['taux_moyen'] or 0) < -30]),
            'recettes_totales': sum(recettes_semaines),
            'taux_global': round(sum(taux_semaines) / len([t for t in taux_semaines if t != 0]) if any(taux_semaines) else 0, 1)
        }
    }
    
    return JsonResponse(data)


@login_required
def api_statistiques_postes_ordonnes(request):
    """
    API pour statistiques détaillées avec classement par performance
    Permet tri par différents critères
    """
    # Vérifier permissions admin
    if request.user.habilitation not in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission']:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    # Paramètres de filtrage
    periode = request.GET.get('periode', 'mois')  # semaine, mois, trimestre
    tri_par = request.GET.get('tri', 'taux')      # taux, recettes, vehicules
    ordre = request.GET.get('ordre', 'asc')      # asc, desc
    region = request.GET.get('region', '')       # filtrage par région
    
    # Définir la période
    today = datetime.now().date()
    
    if periode == 'semaine':
        debut_periode = today - timedelta(days=today.weekday())
        fin_periode = debut_periode + timedelta(days=6)
    elif periode == 'trimestre':
        # Trimestre actuel
        trimestre = ((today.month - 1) // 3) + 1
        debut_periode = datetime(today.year, (trimestre - 1) * 3 + 1, 1).date()
        if trimestre == 4:
            fin_periode = datetime(today.year, 12, 31).date()
        else:
            fin_periode = datetime(today.year, trimestre * 3 + 1, 1).date() - timedelta(days=1)
    else:  # mois par défaut
        debut_periode = today.replace(day=1)
        fin_periode = today
    
    # Requête de base
    queryset = RecetteJournaliere.objects.filter(
        date__gte=debut_periode,
        date__lte=fin_periode
    )
    
    # Filtrage par région si spécifié
    if region:
        queryset = queryset.filter(poste__region=region)
    
    # Agrégation par poste
    stats_postes = queryset.values(
        'poste__id',
        'poste__nom',
        'poste__code',
        'poste__region',
        'poste__type'
    ).annotate(
        taux_moyen=Avg('taux_deperdition'),
        taux_min=Min('taux_deperdition'),
        taux_max=Max('taux_deperdition'),
        recettes_total=Sum('montant'),
        recettes_moyenne=Avg('montant'),
        nb_jours=Count('date', distinct=True),
        total_vehicules=Sum('inventaire__total_vehicules'),
        nb_journees_impertinentes=Count('id', filter=Q(journee_impertinente=True))
    )
    
    # Tri selon critère
    if tri_par == 'recettes':
        field_tri = 'recettes_total'
    elif tri_par == 'vehicules':
        field_tri = 'total_vehicules'
    else:  # taux par défaut
        field_tri = 'taux_moyen'
    
    if ordre == 'desc':
        field_tri = f'-{field_tri}'
    
    stats_postes = stats_postes.order_by(field_tri)
    
    # Formater les données pour le frontend
    postes_ordonnes = []
    
    for idx, poste in enumerate(stats_postes):
        # Calcul du score de performance global (0-100)
        taux = poste['taux_moyen'] or 0
        if taux >= -5:
            score = 100
        elif taux >= -10:
            score = 80
        elif taux >= -20:
            score = 60
        elif taux >= -30:
            score = 40
        else:
            score = 20
        
        # Ajustement selon régularité
        if poste['nb_jours'] >= 20:  # Très régulier
            score += 10
        elif poste['nb_jours'] >= 10:  # Régulier
            score += 5
        
        # Pénalité journées impertinentes
        if poste['nb_journees_impertinentes'] > 0:
            score -= (poste['nb_journees_impertinentes'] * 5)
        
        score = max(0, min(100, score))  # Limiter entre 0 et 100
        
        postes_ordonnes.append({
            'rang': idx + 1,
            'poste_id': poste['poste__id'],
            'nom': poste['poste__nom'],
            'code': poste['poste__code'],
            'region': poste['poste__region'],
            'type': poste['poste__type'],
            'statistiques': {
                'taux_moyen': round(taux, 1),
                'taux_min': round(poste['taux_min'] or 0, 1),
                'taux_max': round(poste['taux_max'] or 0, 1),
                'recettes_total': float(poste['recettes_total'] or 0),
                'recettes_moyenne': round(float(poste['recettes_moyenne'] or 0), 0),
                'total_vehicules': poste['total_vehicules'] or 0,
                'nb_jours_actifs': poste['nb_jours'],
                'nb_journees_impertinentes': poste['nb_journees_impertinentes']
            },
            'performance': {
                'score': score,
                'niveau': (
                    'Excellent' if score >= 80 else
                    'Bon' if score >= 60 else
                    'Moyen' if score >= 40 else
                    'Critique'
                ),
                'couleur': (
                    '#28a745' if score >= 80 else
                    '#20c997' if score >= 60 else
                    '#ffc107' if score >= 40 else
                    '#dc3545'
                )
            }
        })
    
    # Statistiques globales de la période
    stats_globales = {
        'periode': f"{debut_periode.strftime('%d/%m/%Y')} - {fin_periode.strftime('%d/%m/%Y')}",
        'nb_postes_total': len(postes_ordonnes),
        'taux_global': round(
            sum([p['statistiques']['taux_moyen'] for p in postes_ordonnes]) / len(postes_ordonnes)
            if postes_ordonnes else 0, 1
        ),
        'recettes_globales': sum([p['statistiques']['recettes_total'] for p in postes_ordonnes]),
        'vehicules_globaux': sum([p['statistiques']['total_vehicules'] for p in postes_ordonnes]),
        'repartition_niveaux': {
            'excellent': len([p for p in postes_ordonnes if p['performance']['score'] >= 80]),
            'bon': len([p for p in postes_ordonnes if 60 <= p['performance']['score'] < 80]),
            'moyen': len([p for p in postes_ordonnes if 40 <= p['performance']['score'] < 60]),
            'critique': len([p for p in postes_ordonnes if p['performance']['score'] < 40])
        }
    }
    
    data = {
        'postes_ordonnes': postes_ordonnes,
        'statistiques_globales': stats_globales,
        'parametres': {
            'periode': periode,
            'tri_par': tri_par,
            'ordre': ordre,
            'region': region
        }
    }
    
    return JsonResponse(data)


