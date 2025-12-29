# ===================================================================
# common/views.py - Vue Dashboard Index Complète
# Vue principale pour la vitrine de l'application SUPPER
# ===================================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

from common.utils import log_user_action
from .mixins import AdminRequiredMixin
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Sum, Avg, Q, Min, Max
from django.utils import timezone
from django.urls import reverse
from datetime import datetime, timedelta
import json
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
import calendar
from datetime import date

from accounts.models import *
from inventaire.models import *
import logging

logger = logging.getLogger('supper')
# ===================================================================
# IMPORTS DES NOUVELLES PERMISSIONS ET DÉCORATEURS
# ===================================================================
from common.permissions import (
    has_permission,
    has_any_permission,
    is_admin_user,
    is_service_central,
    is_cisop,
    is_chef_poste,
    is_operationnel_pesage,
    user_has_acces_tous_postes,
    get_postes_accessibles,
    get_permissions_summary,
)

from common.decorators import (
    permission_required_granular,
    inventaire_admin_required,
    liste_inventaires_admin_required,
    tracabilite_tickets_required,
    api_permission_required,
)




# ===================================================================
# common/views.py - Fonction index_dashboard CORRIGÉE
# Vue principale pour le dashboard SUPPER avec permissions granulaires
# CHEMIN: Supper/common/views.py (modifier uniquement cette fonction)
# ===================================================================

"""
INSTRUCTIONS:
1. Remplacer UNIQUEMENT la fonction index_dashboard existante par celle-ci
2. Ne pas modifier les autres fonctions du fichier
3. Vérifier que tous les imports sont présents en haut du fichier
"""

# ===================================================================
# IMPORTS REQUIS (vérifier qu'ils sont en haut du fichier)
# ===================================================================
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

from common.utils import log_user_action
from .mixins import AdminRequiredMixin
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Sum, Avg, Q, Min, Max
from django.utils import timezone
from django.urls import reverse
from datetime import datetime, timedelta
import json
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
import calendar
from datetime import date

from accounts.models import *
from inventaire.models import *
import logging

logger = logging.getLogger('supper')

from common.permissions import (
    has_permission,
    has_any_permission,
    is_admin_user,
    is_service_central,
    is_cisop,
    is_chef_poste,
    is_operationnel_pesage,
    user_has_acces_tous_postes,
    get_postes_accessibles,
    get_permissions_summary,
)

from common.decorators import (
    permission_required_granular,
    inventaire_admin_required,
    liste_inventaires_admin_required,
    tracabilite_tickets_required,
    api_permission_required,
)
"""


@login_required
def index_dashboard(request):
    """
    Dashboard principal SUPPER avec statistiques complètes et permissions granulaires.
    Chaque section est conditionnée par les permissions de l'utilisateur.
    
    LOGS:
    - Consultation du dashboard avec nombre d'alertes
    - Permissions utilisées pour le filtrage
    """
    
    from inventaire.services.objectifs_service import ObjectifsService
    
    user = request.user
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    current_year = today.year
    
    logger.info(f"[DASHBOARD] Utilisateur {user.username} ({user.habilitation}) accède au dashboard")
    
    # ================================================================
    # 1. RÉCUPÉRER LES PERMISSIONS GRANULAIRES
    # ================================================================
    user_perms = get_permissions_summary(user)
    
    logger.debug(f"[DASHBOARD] Permissions chargées pour {user.username}")
    
    # ================================================================
    # 2. INFORMATIONS UTILISATEUR - Toujours visible
    # ================================================================
    user_stats = {
        'nom_complet': user.nom_complet,
        'habilitation': user.get_habilitation_display(),
        'habilitation_code': user.habilitation,
        'poste_affectation': user.poste_affectation,
        'is_admin': is_admin_user(user),
        'is_chef': is_chef_poste(user),
        'is_service_central': is_service_central(user),
        'is_cisop': is_cisop(user),
        'is_operationnel_pesage': is_operationnel_pesage(user),
        'derniere_connexion': user.last_login,
        'permissions': user_perms,
    }
    
    # ================================================================
    # 3. DÉTERMINER LES POSTES ACCESSIBLES
    # ================================================================
    if user_has_acces_tous_postes(user):
        postes_accessibles = Poste.objects.filter(is_active=True)
        logger.debug(f"[DASHBOARD] {user.username} a accès à tous les postes actifs")
    elif user.poste_affectation:
        postes_accessibles = Poste.objects.filter(id=user.poste_affectation.id)
        logger.debug(f"[DASHBOARD] {user.username} limité au poste: {user.poste_affectation.nom}")
    else:
        postes_accessibles = Poste.objects.none()
        logger.debug(f"[DASHBOARD] {user.username} n'a accès à aucun poste")
    
    # ================================================================
    # 4. STATISTIQUES GLOBALES - Permissions: is_admin ou voir_statistiques_globales
    # ================================================================
    stats_globales = None
    
    can_view_global_stats = (
        is_admin_user(user) or 
        has_permission(user, 'voir_statistiques_globales')
    )
    
    if can_view_global_stats:
        stats_globales = {
            'total_utilisateurs': UtilisateurSUPPER.objects.count(),
            'utilisateurs_actifs': UtilisateurSUPPER.objects.filter(is_active=True).count(),
            'total_postes': Poste.objects.filter(is_active=True).count(),
            'postes_peage': Poste.objects.filter(type='peage', is_active=True).count(),
            'postes_pesage': Poste.objects.filter(type='pesage', is_active=True).count(),
        }
        logger.debug(f"[DASHBOARD] Stats globales chargées pour {user.username}")
    
    # ================================================================
    # 5. STATISTIQUES INVENTAIRES - Permission: peut_voir_liste_inventaires
    # ================================================================
    stats_inventaires = None
    
    can_view_inventaires = (
        postes_accessibles.exists() and 
        has_any_permission(user, ['peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin'])
    )
    
    if can_view_inventaires:
        stats_inventaires = {
            'total_inventaires': InventaireJournalier.objects.filter(
                poste__in=postes_accessibles
            ).count(),
            'inventaires_today': InventaireJournalier.objects.filter(
                poste__in=postes_accessibles,
                date=today
            ).count(),
            'inventaires_semaine': InventaireJournalier.objects.filter(
                poste__in=postes_accessibles,
                date__gte=week_ago
            ).count(),
            'inventaires_mois': InventaireJournalier.objects.filter(
                poste__in=postes_accessibles,
                date__gte=month_ago
            ).count(),
        }
        logger.debug(f"[DASHBOARD] Stats inventaires chargées pour {user.username}")
    
    # ================================================================
    # 6. STATISTIQUES RECETTES PÉAGE - Permissions: peut_voir_liste_recettes_peage
    # ================================================================
    stats_recettes = None
    
    can_view_recettes_peage = (
        postes_accessibles.exists() and
        has_any_permission(user, [
            'peut_voir_liste_recettes_peage', 
            'peut_voir_stats_recettes_peage'
        ])
    )
    
    if can_view_recettes_peage:
        recettes_mois = RecetteJournaliere.objects.filter(
            poste__in=postes_accessibles,
            date__month=today.month,
            date__year=today.year
        )
        
        aggregations = recettes_mois.aggregate(
            total_montant=Sum('montant_declare'),
            total_potentiel=Sum('recette_potentielle'),
            taux_moyen=Avg('taux_deperdition'),
            nombre_recettes=Count('id')
        )
        
        montant_mois = float(aggregations['total_montant'] or 0)
        montant_potentiel = float(aggregations['total_potentiel'] or 0)
        
        # Vérifier si l'utilisateur peut voir les recettes potentielles
        can_view_potentiel = has_permission(user, 'voir_recettes_potentielles')
        
        stats_recettes = {
            'total_recettes': RecetteJournaliere.objects.filter(
                poste__in=postes_accessibles
            ).count(),
            'recettes_today': RecetteJournaliere.objects.filter(
                poste__in=postes_accessibles,
                date=today
            ).count(),
            'montant_mois': montant_mois,
            'montant_potentiel_mois': montant_potentiel if can_view_potentiel else None,
            'taux_moyen_mois': float(aggregations['taux_moyen'] or 0) if has_permission(user, 'voir_taux_deperdition') else None,
            'nombre_recettes_mois': aggregations['nombre_recettes'],
            'ecart_mois': (montant_mois - montant_potentiel) if can_view_potentiel else None,
            # Flags pour le template
            'can_view_potentiel': can_view_potentiel,
            'can_view_taux': has_permission(user, 'voir_taux_deperdition'),
        }
        logger.debug(f"[DASHBOARD] Stats recettes péage chargées pour {user.username}")
    
    # ================================================================
    # 7. OBJECTIFS ANNUELS - Permission: peut_voir_objectifs_peage
    # ================================================================
    stats_objectifs = None
    
    can_view_objectifs = has_permission(user, 'peut_voir_objectifs_peage')
    
    if can_view_objectifs:
        try:
            stats_objectifs = ObjectifsService.calculer_objectifs_annuels(
                annee=current_year,
                inclure_postes_inactifs=False
            )
            logger.debug(f"[DASHBOARD] Objectifs annuels chargés pour {user.username}")
        except Exception as e:
            logger.error(f"[DASHBOARD] Erreur calcul objectifs: {str(e)}")
            stats_objectifs = None
    
    # ================================================================
    # 8. STATISTIQUES PESAGE - Permissions pesage
    # ================================================================
    stats_pesage = None
    
    # Vérifier les permissions pesage
    has_pesage_access = has_any_permission(user, [
        'peut_voir_stats_pesage',
        'peut_lister_amendes',
        'peut_saisir_amende',
        'peut_voir_recettes_pesage',
        'peut_valider_paiement_amende',
        'peut_saisir_quittance_pesage'
    ])

    if has_pesage_access:
        try:
            from inventaire.models_pesage import AmendeEmise, PeseesJournalieres, QuittancementPesage
            import pytz
            
            CAMEROUN_TZ = pytz.timezone('Africa/Douala')
            
            # Déterminer la station accessible selon les permissions
            if user_has_acces_tous_postes(user):
                station_pesage = None
                stations_pesage_filter = Poste.objects.filter(type='pesage', is_active=True)
                amendes_base = AmendeEmise.objects.filter(station__in=stations_pesage_filter)
                pesees_base = PeseesJournalieres.objects.filter(station__in=stations_pesage_filter)
                quittancements_base = QuittancementPesage.objects.filter(station__in=stations_pesage_filter)
                label_scope = "Toutes stations"
            else:
                station_pesage = user.poste_affectation if user.poste_affectation and user.poste_affectation.type == 'pesage' else None
                
                if station_pesage:
                    amendes_base = AmendeEmise.objects.filter(station=station_pesage)
                    pesees_base = PeseesJournalieres.objects.filter(station=station_pesage)
                    quittancements_base = QuittancementPesage.objects.filter(station=station_pesage)
                    label_scope = station_pesage.nom
                else:
                    amendes_base = AmendeEmise.objects.none()
                    pesees_base = PeseesJournalieres.objects.none()
                    quittancements_base = QuittancementPesage.objects.none()
                    label_scope = "Aucune station"
            
            # Calculs pour AUJOURD'HUI (logique 9h-9h Cameroun)
            from datetime import time
            maintenant_cameroun = timezone.now().astimezone(CAMEROUN_TZ)
            HEURE_DEBUT = time(9, 0, 0)
            
            if maintenant_cameroun.time() < HEURE_DEBUT:
                jour_travail = (maintenant_cameroun - timedelta(days=1)).date()
            else:
                jour_travail = maintenant_cameroun.date()
            
            datetime_debut_jour = CAMEROUN_TZ.localize(
                datetime.combine(jour_travail, HEURE_DEBUT)
            )
            datetime_fin_jour = CAMEROUN_TZ.localize(
                datetime.combine(jour_travail + timedelta(days=1), time(8, 59, 59))
            )
            
            # Amendes émises aujourd'hui (9h-9h)
            amendes_jour = amendes_base.filter(
                date_heure_emission__gte=datetime_debut_jour,
                date_heure_emission__lte=datetime_fin_jour
            )
            
            # Amendes payées aujourd'hui (9h-9h)
            amendes_payees_jour = amendes_base.filter(
                statut='paye',
                date_paiement__gte=datetime_debut_jour,
                date_paiement__lte=datetime_fin_jour
            )
            
            # Agrégations jour
            stats_jour = amendes_jour.aggregate(
                emissions=Count('id'),
                hors_gabarit=Count('id', filter=Q(est_hors_gabarit=True)),
                montant_emis=Sum('montant_amende')
            )
            
            stats_payees_jour = amendes_payees_jour.aggregate(
                count=Count('id'),
                montant=Sum('montant_amende')
            )
            
            # Amendes non payées (global)
            amendes_non_payees = amendes_base.filter(statut='non_paye')
            stats_non_payees = amendes_non_payees.aggregate(
                count=Count('id'),
                montant=Sum('montant_amende')
            )
            
            # Pesées du jour - seulement si permission
            pesees_jour = 0
            if has_permission(user, 'peut_saisir_pesee_jour') or has_permission(user, 'peut_voir_historique_pesees'):
                pesees_jour = pesees_base.filter(date=jour_travail).aggregate(
                    total=Sum('nombre_pesees')
                )['total'] or 0
            
            # Stats du mois en cours
            premier_jour_mois = today.replace(day=1)
            amendes_mois = amendes_base.filter(
                date_heure_emission__date__gte=premier_jour_mois,
                date_heure_emission__date__lte=today
            )
            
            stats_mois = amendes_mois.aggregate(
                emissions=Count('id'),
                montant_emis=Sum('montant_amende'),
                montant_recouvre=Sum('montant_amende', filter=Q(statut='paye'))
            )
            
            montant_emis_mois = float(stats_mois['montant_emis'] or 0)
            montant_recouvre_mois = float(stats_mois['montant_recouvre'] or 0)
            taux_recouvrement_mois = (montant_recouvre_mois / montant_emis_mois * 100) if montant_emis_mois > 0 else 0
            
            stats_pesage = {
                'station': station_pesage,
                'label_scope': label_scope,
                'jour_travail': jour_travail,
                'habilitation': user.habilitation,
                'is_admin_pesage': is_admin_user(user),
                
                # Stats du jour
                'emissions_jour': stats_jour['emissions'] or 0,
                'hors_gabarit_jour': stats_jour['hors_gabarit'] or 0,
                'montant_emis_jour': float(stats_jour['montant_emis'] or 0),
                'paiements_jour': stats_payees_jour['count'] or 0,
                'montant_recouvre_jour': float(stats_payees_jour['montant'] or 0),
                'pesees_jour': pesees_jour,
                'reste_a_recouvrer_jour': float(stats_jour['montant_emis'] or 0) - float(stats_payees_jour['montant'] or 0),
                
                # Stats globales non payées
                'amendes_non_payees': stats_non_payees['count'] or 0,
                'montant_non_paye_total': float(stats_non_payees['montant'] or 0),
                
                # Stats du mois
                'emissions_mois': stats_mois['emissions'] or 0,
                'montant_emis_mois': montant_emis_mois,
                'montant_recouvre_mois': montant_recouvre_mois,
                'taux_recouvrement_mois': round(taux_recouvrement_mois, 1),
                
                # Flags de permissions pour le template
                'can_saisir_amende': has_permission(user, 'peut_saisir_amende'),
                'can_valider_paiement': has_permission(user, 'peut_valider_paiement_amende'),
                'can_saisir_quittance': has_permission(user, 'peut_saisir_quittance_pesage'),
                'can_saisir_pesee': has_permission(user, 'peut_saisir_pesee_jour'),
                'can_voir_stats': has_permission(user, 'peut_voir_stats_pesage'),
                'can_voir_historique': has_permission(user, 'peut_voir_historique_pesees'),
                'can_voir_recettes': has_permission(user, 'peut_voir_recettes_pesage'),
            }
            
            # Stats quittancements si permission
            if has_permission(user, 'peut_saisir_quittance_pesage') or has_permission(user, 'peut_voir_liste_quittancements_pesage'):
                quittancements_mois = quittancements_base.filter(
                    date_quittancement__month=today.month,
                    date_quittancement__year=today.year
                ).aggregate(
                    count=Count('id'),
                    montant=Sum('montant_quittance')
                )
                stats_pesage['quittancements_mois'] = quittancements_mois['count'] or 0
                stats_pesage['montant_quittance_mois'] = float(quittancements_mois['montant'] or 0)
                
                # Demandes de confirmation en attente
                try:
                    from inventaire.models_confirmation import DemandeConfirmationPaiement, StatutDemandeConfirmation
                    if station_pesage:
                        demandes_attente = DemandeConfirmationPaiement.objects.filter(
                            station_concernee=station_pesage,
                            statut=StatutDemandeConfirmation.EN_ATTENTE
                        ).count()
                    else:
                        demandes_attente = DemandeConfirmationPaiement.objects.filter(
                            statut=StatutDemandeConfirmation.EN_ATTENTE
                        ).count()
                    stats_pesage['demandes_confirmation_attente'] = demandes_attente
                except ImportError:
                    stats_pesage['demandes_confirmation_attente'] = 0
            
            # Stats propres saisies si l'utilisateur peut saisir des amendes
            if has_permission(user, 'peut_saisir_amende'):
                mes_saisies_jour = AmendeEmise.objects.filter(
                    saisi_par=user,
                    date_heure_emission__gte=datetime_debut_jour,
                    date_heure_emission__lte=datetime_fin_jour
                ).count()
                stats_pesage['mes_saisies_jour'] = mes_saisies_jour
            
            logger.debug(f"[DASHBOARD] Stats pesage chargées pour {user.username}")
                
        except ImportError as e:
            logger.warning(f"[DASHBOARD] Module pesage non disponible: {e}")
            stats_pesage = None
        except Exception as e:
            logger.error(f"[DASHBOARD] Erreur calcul stats pesage: {e}")
            stats_pesage = None
    
    # ================================================================
    # 9. ACTIVITÉS RÉCENTES - Permission: peut_voir_journal_audit
    # ================================================================
    if has_permission(user, 'peut_voir_journal_audit'):
        # Admin: toutes les activités
        activites_recentes = JournalAudit.objects.select_related(
            'utilisateur'
        ).order_by('-timestamp')[:10]
        logger.debug(f"[DASHBOARD] Activités globales chargées pour {user.username}")
    else:
        # Utilisateur normal: uniquement ses propres activités
        activites_recentes = JournalAudit.objects.filter(
            utilisateur=user
        ).order_by('-timestamp')[:10]
        logger.debug(f"[DASHBOARD] Activités personnelles chargées pour {user.username}")
    
    # ================================================================
    # 10. ALERTES CONTEXTUELLES - Basées sur les permissions
    # ================================================================
    alertes = []
    
    # Alertes stocks faibles - uniquement si permission stock
    if has_any_permission(user, ['peut_voir_liste_stocks_peage', 'peut_voir_mon_stock_peage']):
        if user_has_acces_tous_postes(user):
            stocks_faibles = GestionStock.objects.select_related('poste').filter(
                poste__is_active=True,
                valeur_monetaire__lt=50000
            )[:5]
        elif user.poste_affectation:
            stocks_faibles = GestionStock.objects.filter(
                poste=user.poste_affectation,
                valeur_monetaire__lt=50000
            )
        else:
            stocks_faibles = []
        
        for stock in stocks_faibles:
            alertes.append({
                'type': 'warning',
                'titre': f'Stock faible - {stock.poste.nom}',
                'message': f'Stock: {stock.valeur_monetaire:,.0f} FCFA',
                'icon': 'fas fa-exclamation-triangle',
                'date': stock.derniere_mise_a_jour,
            })
    
    # Alertes jours non configurés - uniquement si peut programmer
    if has_permission(user, 'peut_programmer_inventaire'):
        jours_futurs = [today + timedelta(days=i) for i in range(1, 8)]
        jours_non_configures = []
        
        for jour in jours_futurs:
            if not ConfigurationJour.objects.filter(date=jour).exists():
                jours_non_configures.append(jour)
        
        if jours_non_configures:
            alertes.append({
                'type': 'info',
                'titre': 'Configuration manquante',
                'message': f'{len(jours_non_configures)} jour(s) non configuré(s)',
                'icon': 'fas fa-calendar-times',
                'date': today,
            })
    
    # Alertes inventaires en attente - uniquement si peut saisir
    if has_permission(user, 'peut_saisir_inventaire_normal') and user.poste_affectation:
        inventaire_today = InventaireJournalier.objects.filter(
            poste=user.poste_affectation,
            date=today
        ).exists()
        
        if not inventaire_today:
            alertes.append({
                'type': 'warning',
                'titre': 'Inventaire en attente',
                'message': f'Aucun inventaire saisi aujourd\'hui pour {user.poste_affectation.nom}',
                'icon': 'fas fa-clipboard-check',
                'date': today,
            })
    
    # Alertes recettes en attente - uniquement si chef de poste péage
    if has_permission(user, 'peut_saisir_recette_peage') and user.poste_affectation:
        recette_today = RecetteJournaliere.objects.filter(
            poste=user.poste_affectation,
            date=today
        ).exists()
        
        if not recette_today:
            alertes.append({
                'type': 'info',
                'titre': 'Recette à saisir',
                'message': f'Recette du jour non saisie pour {user.poste_affectation.nom}',
                'icon': 'fas fa-coins',
                'date': today,
            })
    
    # ================================================================
    # 11. GRAPHIQUES - Permission: peut_voir_stats_recettes_peage
    # ================================================================
    graph_data = {}
    
    can_view_graphs = (
        postes_accessibles.exists() and
        has_any_permission(user, ['peut_voir_stats_recettes_peage', 'peut_voir_stats_deperdition'])
    )
    
    if can_view_graphs:
        jours = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
        
        labels = []
        recettes = []
        taux = []
        
        for jour in jours:
            labels.append(jour.strftime('%d/%m'))
            
            stats_jour = RecetteJournaliere.objects.filter(
                poste__in=postes_accessibles,
                date=jour
            ).aggregate(
                total=Sum('montant_declare'),
                taux_moyen=Avg('taux_deperdition')
            )
            
            recettes.append(float(stats_jour['total'] or 0))
            
            # Taux uniquement si permission
            if has_permission(user, 'voir_taux_deperdition'):
                taux.append(float(stats_jour['taux_moyen'] or 0))
            else:
                taux.append(None)
        
        graph_data['evolution_7j'] = {
            'labels': labels,
            'recettes': recettes,
            'taux': taux if has_permission(user, 'voir_taux_deperdition') else [],
            'show_taux': has_permission(user, 'voir_taux_deperdition'),
        }
        logger.debug(f"[DASHBOARD] Données graphiques chargées pour {user.username}")
    
    # ================================================================
    # 12. TOP POSTES - Permission: peut_voir_classement_peage_rendement
    # ================================================================
    top_postes = []
    
    can_view_classement = has_permission(user, 'peut_voir_classement_peage_rendement')
    
    if can_view_classement:
        top_query = RecetteJournaliere.objects.filter(
            date__gte=month_ago
        ).values(
            'poste__nom', 'poste__code'
        ).annotate(
            total_recettes=Sum('montant_declare')
        ).order_by('-total_recettes')[:5]
        
        for idx, item in enumerate(top_query):
            top_postes.append({
                'rang': idx + 1,
                'nom': item['poste__nom'],
                'code': item['poste__code'],
                'total': float(item['total_recettes'])
            })
        logger.debug(f"[DASHBOARD] Top postes chargé pour {user.username}")
    
    # ================================================================
    # 13. ACTIONS RAPIDES CONTEXTUELLES - Basées sur permissions
    # ================================================================
    actions_rapides = []
    
    # Saisie inventaire
    if has_permission(user, 'peut_saisir_inventaire_normal') and user.poste_affectation:
        actions_rapides.append({
            'titre': 'Saisir Inventaire',
            'url': reverse('inventaire:saisie_inventaire'),
            'icon': 'fas fa-clipboard-list',
            'class': 'primary'
        })
    
    # Saisie recette péage
    if has_permission(user, 'peut_saisir_recette_peage') and user.poste_affectation:
        actions_rapides.append({
            'titre': 'Saisir Recette',
            'url': reverse('inventaire:saisir_recette_avec_tickets'),
            'icon': 'fas fa-coins',
            'class': 'warning'
        })
    
    # Gestion utilisateurs
    if has_permission(user, 'peut_gerer_utilisateurs'):
        actions_rapides.append({
            'titre': 'Gérer Utilisateurs',
            'url': reverse('accounts:user_list'),
            'icon': 'fas fa-users',
            'class': 'primary'
        })
    
    # Gestion postes
    if has_permission(user, 'peut_gerer_postes'):
        actions_rapides.append({
            'titre': 'Gérer Postes',
            'url': reverse('accounts:liste_postes'),
            'icon': 'fas fa-map-marker-alt',
            'class': 'info'
        })
    
    # Programmer inventaires
    if has_permission(user, 'peut_programmer_inventaire'):
        actions_rapides.append({
            'titre': 'Programmer Inventaires',
            'url': reverse('inventaire:programmer_inventaire'),
            'icon': 'fas fa-calendar-plus',
            'class': 'success'
        })
    
    # Gérer objectifs
    if has_permission(user, 'peut_voir_objectifs_peage'):
        actions_rapides.append({
            'titre': 'Gérer Objectifs',
            'url': reverse('inventaire:gestion_objectifs_annuels'),
            'icon': 'fas fa-bullseye',
            'class': 'danger'
        })
    
    # Saisir amende pesage
    if has_permission(user, 'peut_saisir_amende'):
        actions_rapides.append({
            'titre': 'Saisir Amende',
            'url': reverse('inventaire:saisir_amende'),
            'icon': 'fas fa-balance-scale',
            'class': 'warning'
        })
    
    # Journal d'audit
    if has_permission(user, 'peut_voir_journal_audit'):
        actions_rapides.append({
            'titre': 'Journal Audit',
            'url': reverse('accounts:journal_audit'),
            'icon': 'fas fa-history',
            'class': 'secondary'
        })
    
    # ================================================================
    # 14. STATISTIQUES SYSTÈME - Permission: peut_voir_journal_audit
    # ================================================================
    stats_systeme = None
    
    if has_permission(user, 'peut_voir_journal_audit'):
        stats_systeme = {
            'actions_today': JournalAudit.objects.filter(
                timestamp__date=today
            ).count(),
            'actions_succes': JournalAudit.objects.filter(
                timestamp__date=today,
                succes=True
            ).count(),
            'derniere_saisie': InventaireJournalier.objects.order_by(
                '-date_creation'
            ).first(),
            'derniere_recette': RecetteJournaliere.objects.order_by(
                '-date_saisie'
            ).first()
        }
        logger.debug(f"[DASHBOARD] Stats système chargées pour {user.username}")
    
    # ================================================================
    # 15. RANG AGENT D'INVENTAIRE 
    # ================================================================
    rang_agent_inventaire = None
    
    # Vérifier si l'utilisateur est un agent d'inventaire
    if user.habilitation == 'agent_inventaire':
        try:
            # Essayer d'abord le service complet
            try:
                from inventaire.services.classement_service import get_rang_agent_inventaire_dashboard
                rang_agent_inventaire = get_rang_agent_inventaire_dashboard(user)
            except ImportError:
                # Fallback vers la version simplifiée
                from common.views import get_rang_agent_inventaire_pour_dashboard
                rang_agent_inventaire = get_rang_agent_inventaire_pour_dashboard(user)
            
            if rang_agent_inventaire:
                log_user_action(
                    user,
                    "Consultation rang agent inventaire",
                    f"Rang: {rang_agent_inventaire['rang']}/{rang_agent_inventaire['total_agents']} | "
                    f"Note: {rang_agent_inventaire['note']:.2f}/20 | "
                    f"Jours travaillés: {rang_agent_inventaire['jours_travailles']}",
                    request
                )
                logger.info(
                    f"[DASHBOARD] Rang agent inventaire {user.nom_complet}: "
                    f"#{rang_agent_inventaire['rang']} avec {rang_agent_inventaire['note']:.2f}/20"
                )
                
        except Exception as e:
            logger.error(f"[DASHBOARD] Erreur calcul rang agent inventaire: {e}")
            rang_agent_inventaire = None
    
    # ================================================================
    # 16. RANGS ET CLASSEMENTS
    # ================================================================
    rang_poste_peage = None
    rang_station_pesage = None
    top_postes_peage = None
    top_stations_pesage = None

    # Rang poste péage - pour chef de poste péage affecté
    if user.poste_affectation and user.poste_affectation.type == 'peage':
        if has_permission(user, 'peut_voir_classement_peage_rendement'):
            try:
                from inventaire.services.classement_service import get_rang_poste_peage
                rang_poste_peage = get_rang_poste_peage(user.poste_affectation, current_year)
                logger.debug(f"[DASHBOARD] Rang péage calculé pour {user.poste_affectation.nom}")
            except Exception as e:
                logger.error(f"[DASHBOARD] Erreur calcul rang péage: {e}")

    # Rang station pesage - pour opérationnels pesage
    if stats_pesage and stats_pesage.get('station'):
        if has_permission(user, 'peut_voir_classement_station_pesage'):
            try:
                from inventaire.views_classement_pesage import get_rang_station_pesage
                rang_station_pesage = get_rang_station_pesage(stats_pesage['station'], current_year)
                logger.debug(f"[DASHBOARD] Rang pesage calculé pour {stats_pesage['station'].nom}")
            except Exception as e:
                logger.error(f"[DASHBOARD] Erreur calcul rang pesage: {e}")

    # Tops pour les admins uniquement
    if is_admin_user(user):
        try:
            # Top postes péage
            if has_permission(user, 'peut_voir_classement_peage_rendement'):
                top_peage = RecetteJournaliere.objects.filter(
                    date__year=current_year
                ).values('poste__nom', 'poste__code').annotate(
                    total=Sum('montant_declare')
                ).order_by('-total')[:5]
                
                top_postes_peage = [
                    {'rang': i+1, 'nom': p['poste__nom'], 'code': p['poste__code'], 'total': float(p['total'])}
                    for i, p in enumerate(top_peage)
                ]
            
            # Top stations pesage
            if has_permission(user, 'peut_voir_classement_station_pesage'):
                from inventaire.views_classement_pesage import calculer_classement_pesage
                classement_pesage = calculer_classement_pesage()[:5]
                top_stations_pesage = classement_pesage
                
        except Exception as e:
            logger.error(f"[DASHBOARD] Erreur calcul tops: {e}")
    
    # ================================================================
    # CONTEXTE FINAL
    # ================================================================
    context = {
        # Informations utilisateur
        'user_stats': user_stats,
        
        # Statistiques conditionnées par permissions
        'stats_globales': stats_globales,
        'stats_inventaires': stats_inventaires,
        'stats_recettes': stats_recettes,
        'stats_objectifs': stats_objectifs,
        'stats_pesage': stats_pesage,
        'stats_systeme': stats_systeme,
        
        # Classements
        'rang_poste_peage': rang_poste_peage,
        'rang_station_pesage': rang_station_pesage,
        'top_postes_peage': top_postes_peage,
        'top_stations_pesage': top_stations_pesage,
        'top_postes': top_postes,
        'rang_agent_inventaire': rang_agent_inventaire,
        
        # Activités et alertes
        'activites_recentes': activites_recentes,
        'alertes': alertes[:5],
        
        # Données graphiques
        'graph_data_json': json.dumps(graph_data, default=str),
        
        # Actions
        'actions_rapides': actions_rapides,
        
        # Méta-données
        'today': today,
        'current_month': calendar.month_name[today.month],
        'current_year': current_year,
        'title': 'Tableau de Bord SUPPER',
        
        # Permissions pour le template (référence directe)
        'user_permissions': user_perms,
        
        # Flags de capacités pour simplifier les conditions template
        'can_view_global_stats': can_view_global_stats,
        'can_view_inventaires': can_view_inventaires,
        'can_view_recettes_peage': can_view_recettes_peage,
        'can_view_objectifs': can_view_objectifs,
        'can_view_graphs': can_view_graphs,
        'can_view_classement': can_view_classement,
        'has_pesage_access': has_pesage_access,
    }
    
    # Journalisation
    log_user_action(
        user,
        "Consultation dashboard",
        f"Dashboard consulté - Habilitation: {user.habilitation} - {len(alertes)} alertes",
        request
    )
    
    logger.info(f"[DASHBOARD] Rendu terminé pour {user.username} avec {len(actions_rapides)} actions rapides")
    
    return render(request, 'admin/index.html', context)

def get_rang_agent_inventaire_pour_dashboard(user) -> dict:
    """
    Obtient le rang de l'agent d'inventaire pour affichage dans le dashboard.
    
    Cette fonction est une alternative autonome si le service de classement
    n'est pas disponible.
    
    Args:
        user: Instance UtilisateurSUPPER
        
    Returns:
        Dict avec rang, note, et statistiques, ou None
    """
    import logging
    from datetime import date, timedelta
    from django.db.models import Count, Avg
    
    logger = logging.getLogger('supper')
    
    # Vérifier que c'est un agent d'inventaire
    if getattr(user, 'habilitation', None) != 'agent_inventaire':
        return None
    
    try:
        from inventaire.models import InventaireJournalier, RecetteJournaliere
        from accounts.models import UtilisateurSUPPER
        
        # Période: mois en cours
        today = date.today()
        date_debut = today.replace(day=1)
        date_fin = today
        
        # Compter les inventaires de l'agent ce mois
        inventaires_agent = InventaireJournalier.objects.filter(
            agent_saisie=user,
            date__range=[date_debut, date_fin]
        ).count()
        
        if inventaires_agent == 0:
            return None
        
        # Obtenir tous les agents ayant saisi des inventaires ce mois
        agents_stats = InventaireJournalier.objects.filter(
            date__range=[date_debut, date_fin],
            agent_saisie__habilitation='agent_inventaire'
        ).values('agent_saisie').annotate(
            nb_inventaires=Count('id')
        ).order_by('-nb_inventaires')
        
        # Calculer le rang de l'agent
        rang = 1
        for stats in agents_stats:
            if stats['agent_saisie'] == user.id:
                break
            rang += 1
        
        total_agents = len(agents_stats)
        
        # Calculer une note approximative basée sur la régularité
        jours_possibles = (date_fin - date_debut).days + 1
        taux_presence = (inventaires_agent / jours_possibles * 100) if jours_possibles > 0 else 0
        
        # Note basique basée sur le taux de présence
        if taux_presence >= 80:
            note_base = 16
        elif taux_presence >= 60:
            note_base = 14
        elif taux_presence >= 40:
            note_base = 12
        elif taux_presence >= 20:
            note_base = 10
        else:
            note_base = 8
        
        # Ajuster selon le rang
        bonus_rang = max(0, (total_agents - rang) / total_agents * 2)
        note_finale = min(20, note_base + bonus_rang)
        
        # Médaille selon le rang
        if rang == 1:
            medaille = "🥇"
            message = "🏆 Félicitations ! Vous êtes le meilleur agent ce mois-ci !"
        elif rang == 2:
            medaille = "🥈"
            message = f"🌟 Excellent travail ! 2ème sur {total_agents} agents !"
        elif rang == 3:
            medaille = "🥉"
            message = f"🌟 Excellent travail ! 3ème sur {total_agents} agents !"
        elif rang <= 5:
            medaille = "⭐"
            message = f"👏 Très bien ! Top 5 sur {total_agents} agents."
        else:
            medaille = "📊"
            message = f"📈 Continuez vos efforts ! Rang {rang}/{total_agents}."
        
        return {
            'rang': rang,
            'total_agents': total_agents,
            'note': note_finale,
            'jours_travailles': inventaires_agent,
            'taux_presence': taux_presence,
            'medaille': medaille,
            'message_performance': message,
            'jours_3_criteres': 0,  # À calculer si service complet disponible
            'jours_impertinents': 0  # À calculer si service complet disponible
        }
        
    except Exception as e:
        logger.error(f"[DASHBOARD] Erreur calcul rang agent: {e}")
        return None



class DashboardAdminView(LoginRequiredMixin, TemplateView):
    """
    Dashboard complet pour administrateurs avec redirections vers admin Django
    MISE À JOUR - Intégration complète avec le panel administrateur Django
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
    
    def get(self, request, *args, **kwargs):
        """
        MISE À JOUR - Gestion des requêtes GET avec redirection admin si nécessaire
        """
        
        # NOUVEAU: Gestion des redirections vers admin Django
        action = request.GET.get('action')
        
        if action:
            user = request.user
            
            # Vérifier que l'utilisateur a bien les droits admin (double vérification)
            has_admin_access = (
                user.is_superuser or 
                user.is_staff or 
                user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission']
            )
            
            if not has_admin_access:
                messages.error(request, _("Accès non autorisé au panel d'administration."))
                return redirect('common:dashboard_admin')
            
            # Journaliser l'action de redirection
            self._log_admin_redirect(request, action)
            
            # Définir les redirections selon l'action
            redirections = {
                'admin_panel': '/django-admin/',
                'manage_users': reverse('admin:accounts_utilisateursupper_changelist'),
                'manage_postes': reverse('accounts:liste_postes'),
                'manage_inventaires': '/django-admin/inventaire/inventairejournalier/',
                'manage_recettes': '/django-admin/inventaire/recettejournaliere/',
                'view_journal': reverse('admin:accounts_journalaudit_changelist'),
                'add_user': reverse('admin:accounts_utilisateursupper_add'),
                'add_poste': reverse('admin:accounts_poste_add'),
                'export_data': '/django-admin/export/',
                'system_config': '/django-admin/admin/',
            }
            
            redirect_url = redirections.get(action)
            
            if redirect_url:
                messages.success(
                    request,
                    _(f"Redirection vers {action.replace('_', ' ').title()}.")
                )
                return redirect(redirect_url)
            else:
                messages.warning(
                    request,
                    _(f"Action '{action}' non reconnue.")
                )
        
        # Comportement normal du dashboard
        return super().get(request, *args, **kwargs)
    
    def _log_admin_redirect(self, request, action):
        """Journaliser les redirections vers l'admin Django"""
        action_labels = {
            'admin_panel': 'Panel administrateur Django',
            'manage_users': 'Gestion utilisateurs',
            'manage_postes': 'Gestion postes',
            'manage_inventaires': 'Gestion inventaires',
            'manage_recettes': 'Gestion recettes',
            'view_journal': 'Journal d\'audit',
            'add_user': 'Ajout utilisateur',
            'add_poste': 'Ajout poste',
            'export_data': 'Export données',
            'system_config': 'Configuration système',
        }
        
        action_label = action_labels.get(action, action)
        
        JournalAudit.objects.create(
            utilisateur=request.user,
            action=f"Redirection admin Django - {action_label}",
            details=f"Redirection depuis dashboard SUPPER vers {action_label}",
            adresse_ip=request.META.get('REMOTE_ADDR'),
            url_acces=request.path,
            methode_http=request.method,
            succes=True
        )
        
        logger.info(
            f"REDIRECTION ADMIN DJANGO - "
            f"Utilisateur: {request.user.username} | "
            f"Action: {action_label} | "
            f"Depuis: Dashboard Admin"
        )
    
    def get_context_data(self, **kwargs):
        """
        Ajouter toutes les données nécessaires au dashboard admin + URLs admin Django
        MISE À JOUR avec nouvelles URLs de redirection
        """
        context = super().get_context_data(**kwargs)
        
        user = self.request.user
        
        # ================================================================
        # STATISTIQUES GÉNÉRALES - CONSERVER TOUT LE CODE EXISTANT
        # ================================================================
        
        try:
            
            # Statistiques utilisateurs
            total_utilisateurs = UtilisateurSUPPER.objects.count()
            utilisateurs_actifs = UtilisateurSUPPER.objects.filter(is_active=True).count()
            
            # Statistiques postes
            total_postes = Poste.objects.count()
            postes_peage = Poste.objects.filter(type_poste='peage').count()
            postes_pesage = Poste.objects.filter(type_poste='pesage').count()
            
            # Statistiques récentes (7 derniers jours)
            depuis_7_jours = timezone.now() - timedelta(days=7)
            inventaires_recents = InventaireJournalier.objects.filter(
                date__gte=depuis_7_jours
            ).count()
            
            recettes_recentes = RecetteJournaliere.objects.filter(
                date__gte=depuis_7_jours
            ).count()
            
            # NOUVEAU: URLs pour le dashboard admin avec redirections
            admin_urls = {
                # URLs de redirection principales
                'panel_advanced': f"{self.request.path}?action=admin_panel",
                'manage_users': f"{self.request.path}?action=manage_users",
                'manage_postes': f"{self.request.path}?action=manage_postes",
                'manage_inventaires': f"{self.request.path}?action=manage_inventaires",
                'manage_recettes': f"{self.request.path}?action=manage_recettes",
                'view_journal': f"{self.request.path}?action=view_journal",
                'add_user': f"{self.request.path}?action=add_user",
                'add_poste': f"{self.request.path}?action=add_poste",
                'export_data': f"{self.request.path}?action=export_data",
                'system_config': f"{self.request.path}?action=system_config",
                
                # URLs directes pour l'admin Django (backup)
                'direct_admin': '/django-admin/',
                'direct_users': reverse('admin:accounts_utilisateursupper_changelist'),
                'direct_postes': reverse('accounts:liste_postes'),
                'direct_journal': reverse('admin:accounts_journalaudit_changelist'),
            }
            
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
                'user_dashboard_title': 'Administration SUPPER - Dashboard Principal',
                # NOUVEAU: URLs pour redirection vers admin Django
                'admin_urls': admin_urls,
                # NOUVEAU: Indicateurs de permissions
                'user_permissions': {
                    'is_superuser': user.is_superuser,
                    'is_staff': user.is_staff,
                    'habilitation': user.habilitation,
                    'can_access_django_admin': True,  # Tous les utilisateurs de ce dashboard peuvent accéder à l'admin
                }
            })
            
        except Exception as e:
            logger.error(f"Erreur chargement données dashboard admin: {str(e)}")
            messages.error(self.request, _("Erreur lors du chargement des données."))
            context['stats_generales'] = {}
            context['admin_urls'] = {}
        
        return context

# ===================================================================
# NOUVELLES VUES DE REDIRECTION DIRECTE VERS ADMIN DJANGO
# ===================================================================

@login_required
def redirect_to_django_admin(request):
    """
    Vue de redirection générale vers l'admin Django
    Vérification des permissions et journalisation
    """
    user = request.user
    
    # Vérifier permissions admin
    has_admin_access = (
        user.is_superuser or 
        user.is_staff or 
        user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission']
    )
    
    if not has_admin_access:
        messages.error(request, _("Accès non autorisé au panel d'administration Django."))
        logger.warning(f"ACCÈS REFUSÉ ADMIN DJANGO - {user.username}")
        return redirect('common:dashboard_general')
    
    # Journaliser l'accès
    JournalAudit.objects.create(
        utilisateur=user,
        action="Accès admin Django direct",
        details="Accès direct au panel d'administration Django",
        adresse_ip=request.META.get('REMOTE_ADDR'),
        url_acces=request.path,
        methode_http=request.method,
        succes=True
    )
    
    logger.info(f"ACCÈS ADMIN DJANGO DIRECT - {user.username}")
    
    messages.success(request, _("Accès autorisé au panel d'administration Django."))
    return redirect('/django-admin/')


@login_required
def redirect_to_users_admin(request):
    """Redirection vers la gestion des utilisateurs dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé."))
        return redirect('common:dashboard_general')
    
    _log_admin_access(request, "Gestion utilisateurs")
    return redirect(reverse('admin:accounts_utilisateursupper_changelist'))


# @login_required
# def redirect_to_postes_admin(request):
#     """Redirection vers la gestion des postes dans l'admin Django"""
#     user = request.user
    
#     if not _check_admin_permission(user):
#         messages.error(request, _("Accès non autorisé."))
#         return redirect('common:dashboard_general')
    
#     _log_admin_access(request, "Gestion postes")
#     return redirect(reverse('accounts:liste_postes'))


@login_required
def redirect_to_inventaires_admin(request):
    """Redirection vers la gestion des inventaires dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé."))
        return redirect('common:dashboard_general')
    
    _log_admin_access(request, "Gestion inventaires")
    return redirect('/django-admin/inventaire/inventairejournalier/')


@login_required
def redirect_to_recettes_admin(request):
    """Redirection vers la gestion des recettes dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé."))
        return redirect('common:dashboard_general')
    
    _log_admin_access(request, "Gestion recettes")
    return redirect('/django-admin/inventaire/recettejournaliere/')


@login_required
def redirect_to_journal_admin(request):
    """Redirection vers le journal d'audit dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé."))
        return redirect('common:dashboard_general')
    
    _log_admin_access(request, "Journal audit")
    return redirect(reverse('admin:accounts_journalaudit_changelist'))


@login_required
def redirect_to_add_user_admin(request):
    """Redirection vers l'ajout d'utilisateur dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé."))
        return redirect('common:dashboard_general')
    
    _log_admin_access(request, "Ajout utilisateur")
    return redirect(reverse('admin:accounts_utilisateursupper_add'))


# ===================================================================
# FONCTIONS UTILITAIRES POUR LES REDIRECTIONS
# ===================================================================

def _check_admin_permission(user):
    """Vérifier les permissions administrateur"""
    return (user.is_superuser or 
            user.is_staff or 
            user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'])


def _log_admin_access(request, action):
    """Journaliser l'accès aux sections admin"""
    JournalAudit.objects.create(
        utilisateur=request.user,
        action=f"Accès admin Django - {action}",
        details=f"Redirection depuis SUPPER vers {action}",
        adresse_ip=request.META.get('REMOTE_ADDR'),
        url_acces=request.path,
        methode_http=request.method,
        succes=True
    )
    
    logger.info(f"REDIRECTION ADMIN DJANGO - {request.user.username} -> {action}")


# ===================================================================
# DASHBOARD CHEF DE POSTE - TAUX SEULEMENT (TEMPORAIREMENT DÉSACTIVÉ)
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
        return redirect('common:dashboard_general')


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
        
        # NOUVEAU: Lien vers admin Django si l'utilisateur a les permissions
        has_admin_access = _check_admin_permission(user)
        
        context.update({
            'user_dashboard_title': f'SUPPER - Espace {user.get_habilitation_display()}',
            'message_developpement': _(
                "Cette interface est en cours de développement. "
                "Les fonctionnalités spécialisées seront disponibles prochainement."
            ),
            # NOUVEAU: Accès admin si autorisé
            'has_admin_access': has_admin_access,
            'admin_url': '/admin/dashboard/?action=admin_panel' if has_admin_access else None,
        })
        
        return context


# ===================================================================
# API ENDPOINTS AVEC PERMISSIONS (CONSERVÉES)
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
        try:
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
        except Exception as e:
            logger.error(f"Erreur API stats admin: {str(e)}")
            data['stats'] = {}
            data['alertes'] = {}
    
    elif user.habilitation in ['chef_peage', 'chef_pesage']:
        # Chef : stats de son poste seulement, sans recettes potentielles
        if user.poste_affectation:
            try:
                recette_today = RecetteJournaliere.objects.get(
                    poste=user.poste_affectation,
                    date=today
                )
                data['stats'] = {
                    'recette_today': float(recette_today.montant_declare),
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
        try:
            data['stats'] = {
                'mes_inventaires_mois': InventaireJournalier.objects.filter(
                    agent_saisie=user,
                    date__gte=today.replace(day=1)
                ).count(),
                'inventaire_today_exists': InventaireJournalier.objects.filter(
                    agent_saisie=user,
                    date=today
                ).exists(),
            }
        except Exception as e:
            logger.error(f"Erreur API stats agent: {str(e)}")
            data['stats'] = {}
    
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
    
    try:
        if user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission']:
            # Admin : vue globale
            evolution_taux = []
            evolution_recettes = []
            
            for jour in semaine:
                stats_jour = RecetteJournaliere.objects.filter(date=jour).aggregate(
                    taux_moyen=Avg('taux_deperdition'),
                    recettes_total=Sum('montant_declare')
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
                    evolution_recettes.append(float(recette.montant_declare))
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
    
    except Exception as e:
        logger.error(f"Erreur API graphique évolution: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)
    
    return JsonResponse(data)


# ===================================================================
# ACTIONS RAPIDES POUR ADMINISTRATEURS (CONSERVÉES)
# ===================================================================

@login_required
def ouvrir_jour_saisie(request):
    """
    Action rapide pour ouvrir un jour pour saisie
    Réservée aux administrateurs
    """
    if not _check_admin_permission(request.user):
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
                        'statut': "ouvert",
                        'cree_par': request.user,
                        'commentaire': f'Ouvert par {request.user.nom_complet}'
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
                    'statut': "ouvert",
                    'cree_par': request.user,
                    'commentaire': f'Ouvert par {request.user.nom_complet}'
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
    if not _check_admin_permission(request.user):
        messages.error(request, _("Action non autorisée."))
        return redirect('common:dashboard_general')
    
    # Logic pour générer le rapport hebdomadaire
    # À implémenter selon besoins spécifiques
    
    messages.info(request, _("Génération de rapport en cours..."))
    return redirect('common:dashboard_admin')


# ===================================================================
# API GRAPHIQUES ADMINISTRATEURS (CONSERVÉES INTÉGRALEMENT)
# ===================================================================

@login_required
def api_graphique_hebdomadaire(request):
    """
    API pour graphique hebdomadaire des taux de déperdition
    Accessible uniquement aux administrateurs
    """
    # Vérifier permissions admin
    if not _check_admin_permission(request.user):
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    # Calculer la semaine (lundi à dimanche)
    today = datetime.now().date()
    debut_semaine = today - timedelta(days=today.weekday())  # Lundi
    fin_semaine = debut_semaine + timedelta(days=6)  # Dimanche
    
    try:
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
                recettes_total=Sum('montant_declare'),
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
            recettes_total=Sum('montant_declare'),
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
    
    except Exception as e:
        logger.error(f"Erreur API graphique hebdomadaire: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)
    
    return JsonResponse(data)


@login_required
def api_graphique_mensuel(request):
    """
    API pour graphique mensuel des taux de déperdition
    Accessible uniquement aux administrateurs
    """
    # Vérifier permissions admin
    if not _check_admin_permission(request.user):
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    # Mois courant
    today = datetime.now().date()
    debut_mois = today.replace(day=1)
    
    # Calculer fin du mois
    if debut_mois.month == 12:
        fin_mois = debut_mois.replace(year=debut_mois.year + 1, month=1) - timedelta(days=1)
    else:
        fin_mois = debut_mois.replace(month=debut_mois.month + 1) - timedelta(days=1)
    
    try:
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
                recettes_total=Sum('montant_declare')
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
            'poste__type_poste'
        ).annotate(
            taux_moyen=Avg('taux_deperdition'),
            recettes_total=Sum('montant_declare'),
            nb_jours=Count('date', distinct=True),
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
            recettes_total=Sum('montant_declare')
        )
        
        stats_mois_actuel = RecetteJournaliere.objects.filter(
            date__gte=debut_mois,
            date__lte=today
        ).aggregate(
            taux_moyen=Avg('taux_deperdition'),
            recettes_total=Sum('montant_declare')
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
                    'type': item['poste__type_poste'],
                    'taux_moyen': round(item['taux_moyen'] or 0, 1),
                    'recettes_total': float(item['recettes_total'] or 0),
                    'nb_jours_actifs': item['nb_jours'],
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
    
    except Exception as e:
        logger.error(f"Erreur API graphique mensuel: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)
    
    return JsonResponse(data)


@login_required
def api_statistiques_postes_ordonnes(request):
    """
    API pour statistiques détaillées avec classement par performance
    Permet tri par différents critères
    """
    # Vérifier permissions admin
    if not _check_admin_permission(request.user):
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    # Paramètres de filtrage
    periode = request.GET.get('periode', 'mois')  # semaine, mois, trimestre
    tri_par = request.GET.get('tri', 'taux')      # taux, recettes, vehicules
    ordre = request.GET.get('ordre', 'asc')      # asc, desc
    region = request.GET.get('region', '')       # filtrage par région
    
    try:
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
            'poste__type_poste'
        ).annotate(
            taux_moyen=Avg('taux_deperdition'),
            taux_min=Min('taux_deperdition'),
            taux_max=Max('taux_deperdition'),
            recettes_total=Sum('montant_declare'),
            recettes_moyenne=Avg('montant_declare'),
            nb_jours=Count('date', distinct=True),
        )
        
        # Tri selon critère
        if tri_par == 'recettes':
            field_tri = 'recettes_total'
        elif tri_par == 'jours':
            field_tri = 'nb_jours'
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
            
            score = max(0, min(100, score))  # Limiter entre 0 et 100
            
            postes_ordonnes.append({
                'rang': idx + 1,
                'poste_id': poste['poste__id'],
                'nom': poste['poste__nom'],
                'code': poste['poste__code'],
                'region': poste['poste__region'],
                'type': poste['poste__type_poste'],
                'statistiques': {
                    'taux_moyen': round(taux, 1),
                    'taux_min': round(poste['taux_min'] or 0, 1),
                    'taux_max': round(poste['taux_max'] or 0, 1),
                    'recettes_total': float(poste['recettes_total'] or 0),
                    'recettes_moyenne': round(float(poste['recettes_moyenne'] or 0), 0),
                    'nb_jours_actifs': poste['nb_jours'],
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
    
    except Exception as e:
        logger.error(f"Erreur API statistiques postes: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)
    
    return JsonResponse(data)

# ===================================================================
# AJOUT aux vues manquantes dans common/views.py
# Correction des erreurs NoReverseMatch - Ajouter à la fin du fichier
# ===================================================================

from django.views.generic import ListView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.http import JsonResponse, HttpResponse
from django.template.response import TemplateResponse

# ===================================================================
# VUES MANQUANTES POUR ÉVITER NoReverseMatch
# ===================================================================

class GeneralDashboardView(LoginRequiredMixin, TemplateView):
    """
    Dashboard général - CORRECTION pour éviter NoReverseMatch
    Interface temporaire en attendant le développement complet
    """
    template_name = 'common/dashboard_general.html'
    
    def get_context_data(self, **kwargs):
        """Contexte minimal pour éviter les erreurs de template"""
        context = super().get_context_data(**kwargs)
        
        user = self.request.user
        
        # Lien vers admin Django si l'utilisateur a les permissions
        has_admin_access = _check_admin_permission(user)
        
        context.update({
            'user_dashboard_title': f'SUPPER - Espace {user.get_habilitation_display()}',
            'message_developpement': _(
                "Cette interface est en cours de développement. "
                "Les fonctionnalités spécialisées seront disponibles prochainement."
            ),
            'has_admin_access': has_admin_access,
            'admin_url': '/admin/' if has_admin_access else None,
            'current_user': user,
            'page_title': 'Dashboard Général',
        })
        
        return context


class JourListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """
    Liste des jours configurés - CORRECTION pour éviter NoReverseMatch
    Accessible uniquement aux administrateurs
    """
    template_name = 'common/jour_list.html'
    context_object_name = 'jours'
    paginate_by = 30
    
    def get_queryset(self):
        """Récupérer les configurations de jours"""
        try:
            from inventaire.models import ConfigurationJour
            return ConfigurationJour.objects.all().order_by('-date')
        except ImportError:
            # Si le modèle n'existe pas encore, retourner queryset vide
            from django.db.models import QuerySet
            return QuerySet().none()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'page_title': 'Gestion des Jours',
            'can_add': True,
            'can_modify': True,
        })
        return context


class AuditLogView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """
    Journal d'audit - CORRECTION pour éviter NoReverseMatch
    Affichage des logs système pour les administrateurs
    """
    model = JournalAudit
    template_name = 'accounts/journal_audit.html'
    context_object_name = 'logs'
    paginate_by = 50
    ordering = ['-timestamp']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'page_title': 'Journal d\'Audit',
            'total_logs': JournalAudit.objects.count(),
        })
        return context


class SystemHealthView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Santé du système - CORRECTION pour éviter NoReverseMatch
    Monitoring et diagnostic système pour les administrateurs
    """
    template_name = 'common/system_health.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Statistiques système de base
        try:
            system_stats = {
                'database_status': 'Connectée',
                'total_users': UtilisateurSUPPER.objects.count(),
                'active_users': UtilisateurSUPPER.objects.filter(is_active=True).count(),
                'total_postes': Poste.objects.count(),
                'logs_count': JournalAudit.objects.count(),
                'server_time': timezone.now(),
            }
        except Exception as e:
            system_stats = {
                'database_status': f'Erreur: {str(e)}',
                'error': True,
            }
        
        context.update({
            'page_title': 'Santé du Système',
            'system_stats': system_stats,
        })
        return context


# ===================================================================
# VUES D'ERREUR PERSONNALISÉES (pour éviter les erreurs 500)
# ===================================================================

@login_required
def error_403_view(request, exception=None):
    """Page 403 personnalisée"""
    return TemplateResponse(request, 'errors/403.html', {
        'title': 'Accès interdit',
        'message': 'Vous n\'avez pas les permissions nécessaires.',
    }, status=403)


@login_required  
def error_404_view(request, exception=None):
    """Page 404 personnalisée"""
    return TemplateResponse(request, 'errors/404.html', {
        'title': 'Page non trouvée',
        'message': 'La page que vous cherchez n\'existe pas.',
    }, status=404)


def error_500_view(request):
    """Page 500 personnalisée"""
    return TemplateResponse(request, 'errors/500.html', {
        'title': 'Erreur serveur',
        'message': 'Une erreur interne s\'est produite.',
    }, status=500)


# ===================================================================
# VUES TEMPORAIRES DE DÉVELOPPEMENT (éviter les erreurs 404)
# ===================================================================

@login_required
def placeholder_view(request, feature_name="cette fonctionnalité"):
    """
    Vue placeholder pour les fonctionnalités en développement
    Évite les erreurs 404 pendant le développement
    """
    messages.info(
        request, 
        f"{feature_name.title()} est en cours de développement et sera disponible prochainement."
    )
    
    # Redirection vers le dashboard approprié
    user = request.user
    if _check_admin_permission(user):
        return redirect('/admin/')
    else:
        return redirect('common:dashboard_general')


@login_required
def coming_soon_view(request):
    """Vue générique 'Bientôt disponible'"""
    return TemplateResponse(request, 'common/coming_soon.html', {
        'title': 'Fonctionnalité en développement',
        'message': 'Cette section sera disponible dans une prochaine version.',
        'user': request.user,
    })


# ===================================================================
# API DE MONITORING (pour diagnostiquer les problèmes)
# ===================================================================

@login_required
def api_system_status(request):
    """API pour vérifier le statut du système"""
    if not _check_admin_permission(request.user):
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    try:
        # Tests de base
        users_count = UtilisateurSUPPER.objects.count()
        postes_count = Poste.objects.count()
        logs_count = JournalAudit.objects.count()
        
        # Test de la base de données
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            db_test = cursor.fetchone()[0] == 1
        
        status = {
            'status': 'OK',
            'timestamp': timezone.now().isoformat(),
            'database': 'Connected' if db_test else 'Error',
            'counts': {
                'users': users_count,
                'postes': postes_count,
                'logs': logs_count,
            },
            'version': '1.0',
        }
        
    except Exception as e:
        status = {
            'status': 'ERROR',
            'error': str(e),
            'timestamp': timezone.now().isoformat(),
        }
    
    return JsonResponse(status)


@login_required 
def api_check_urls(request):
    """API pour vérifier les URLs disponibles (debug)"""
    if not _check_admin_permission(request.user):
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    from django.urls import get_resolver
    from django.conf import settings
    
    try:
        # Récupérer toutes les URLs configurées
        resolver = get_resolver()
        
        available_urls = []
        for pattern in resolver.url_patterns:
            if hasattr(pattern, 'name') and pattern.name:
                available_urls.append({
                    'name': pattern.name,
                    'pattern': str(pattern.pattern),
                })
        
        # URLs spécifiques à common
        common_urls = [url for url in available_urls if 'common:' in str(url)]
        
        return JsonResponse({
            'status': 'OK',
            'total_urls': len(available_urls),
            'common_urls': common_urls,
            'debug_mode': settings.DEBUG,
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'ERROR',
            'error': str(e),
        })


# ===================================================================
# FONCTIONS UTILITAIRES POUR ÉVITER LES ERREURS
# ===================================================================

def safe_reverse(url_name, args=None, kwargs=None):
    """
    Fonction sécurisée pour résoudre les URLs
    Retourne une URL par défaut si la résolution échoue
    """
    try:
        from django.urls import reverse
        return reverse(url_name, args=args, kwargs=kwargs)
    except Exception:
        # Fallback vers admin Django
        return '/admin/'


def get_user_dashboard_url(user):
    """
    Retourne l'URL de dashboard appropriée pour un utilisateur
    Gère les erreurs de résolution d'URL
    """
    try:
        if _check_admin_permission(user):
            return safe_reverse('common:admin_dashboard')
        elif user.habilitation in ['chef_peage', 'chef_pesage']:
            return safe_reverse('common:chef_dashboard')
        elif user.habilitation == 'agent_inventaire':
            return safe_reverse('common:agent_dashboard')
        else:
            return safe_reverse('common:dashboard_general')
    except Exception:
        # Fallback ultime
        return '/admin/'


# ===================================================================
# GESTIONNAIRE D'ERREURS GLOBAL (si nécessaire)
# ===================================================================

def handle_url_error(request, exception=None):
    """
    Gestionnaire global pour les erreurs d'URL
    Évite les crashes lors de NoReverseMatch
    """
    logger.warning(f"Erreur URL: {exception} pour l'utilisateur {request.user.username}")
    
    messages.warning(
        request,
        "Une erreur de navigation s'est produite. Vous avez été redirigé vers la page principale."
    )
    
    # Redirection sécurisée
    return redirect('/admin/')

@login_required
def gerer_jours(request, inventaire_id):
    """
    Vue pour gérer l'activation des jours d'un inventaire mensuel
    """
    try:
        inventaire = get_object_or_404(InventaireMensuel, id=inventaire_id)
    except ImportError:
        messages.error(request, "Le modèle InventaireMensuel n'est pas disponible")
        return redirect('admin:index')
    
    # Vérifier les permissions
    if not request.user.is_admin:
        messages.error(request, "Accès refusé - Permission administrateur requise")
        return redirect('admin:index')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'ouvrir_semaine':
            # Ouvrir la semaine courante
            inventaire.activer_jours_ouvres()
            messages.success(request, f"Semaine courante activée pour {inventaire.titre}")
            
        elif action == 'fermer_ancien':
            # Fermer tous les jours anciens
            from datetime import date
            
            today = date.today()
            jours_fermes = ConfigurationJour.objects.filter(
                date__lt=today,
                statut=StatutJour.OUVERT
            ).update(statut=StatutJour.FERME)
            
            messages.success(request, f"{jours_fermes} jours anciens fermés")
            
        elif action == 'ouvrir_date':
            # Ouvrir une date spécifique
            date_str = request.POST.get('date_specifique')
            if date_str:
                try:
                    from datetime import datetime
                    
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    
                    config, created = ConfigurationJour.objects.get_or_create(
                        date=date_obj,
                        defaults={
                            'statut': StatutJour.OUVERT,
                            'cree_par': request.user,
                            'commentaire': 'Ouverture manuelle'
                        }
                    )
                    
                    if not created:
                        config.statut = StatutJour.OUVERT
                        config.save()
                    
                    messages.success(request, f"Date {date_obj.strftime('%d/%m/%Y')} ouverte")
                    
                except ValueError:
                    messages.error(request, "Format de date invalide")
            
        elif action == 'changer_statut':
            # Changer le statut d'un jour spécifique
            jour_id = request.POST.get('jour_id')
            nouveau_statut = request.POST.get('nouveau_statut')
            
            if jour_id and nouveau_statut:
                try:
                    
                    config = ConfigurationJour.objects.get(id=jour_id)
                    config.statut = nouveau_statut
                    config.save()
                    
                    messages.success(request, f"Statut du {config.date.strftime('%d/%m/%Y')} changé")
                    
                except ConfigurationJour.DoesNotExist:
                    messages.error(request, "Configuration de jour introuvable")
        
        elif action == 'update_jours':
            # Mettre à jour les jours actifs de l'inventaire mensuel
            jours_selectionnes = request.POST.getlist('jours_actifs')
            jours_int = [int(j) for j in jours_selectionnes if j.isdigit()]
            
            inventaire.jours_actifs = jours_int
            inventaire.save()
            
            # Générer les configurations de jours
            configs_creees = inventaire.generer_configurations_jours()
            
            messages.success(
                request, 
                f"Inventaire mis à jour - {len(jours_int)} jours actifs, "
                f"{len(configs_creees)} nouvelles configurations créées"
            )
        
        return redirect('gerer_jours', inventaire_id=inventaire.id)
    
    # GET - Afficher l'interface
    
    # Récupérer les jours configurés récents
    from datetime import date, timedelta
    
    date_limite = date.today() - timedelta(days=30)
    jours = ConfigurationJour.objects.filter(
        date__gte=date_limite
    ).order_by('-date')[:50]
    
    # Générer le calendrier du mois
    calendrier = inventaire.get_calendrier_mois()
    jours_actifs = inventaire.jours_actifs
    
    context = {
        'title': f'Gestion des Jours - {inventaire.titre}',
        'inventaire': inventaire,
        'calendrier': calendrier,
        'jours_actifs': jours_actifs,
        'jours': jours,
    }
    
    return render(request, 'admin/inventaire/gerer_jours.html', context)

@login_required
@require_http_methods(["POST"])
def ouvrir_semaine_courante(request):
    """
    Action rapide : Ouvrir tous les jours de la semaine courante
    Référencée dans base_site.html ligne 392 - fonction ouvrirSemaineEnCours()
    """
    user = request.user
    
    if not _check_admin_permission(user):
        return JsonResponse({'success': False, 'message': 'Permission refusée'}, status=403)
    
    try:
        # Calculer la semaine courante (lundi à vendredi)
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        jours_ouverts = 0
        
        for i in range(5):  # Lundi à vendredi
            jour = monday + timedelta(days=i)
            
            config, created = ConfigurationJour.objects.get_or_create(
                date=jour,
                defaults={
                    'statut': 'ouvert',
                    'cree_par': user,
                    'commentaire': f'Ouvert automatiquement - semaine courante par {user.nom_complet}'
                }
            )
            
            if not created and config.statut != 'ouvert':
                config.statut = 'ouvert'
                config.commentaire = f'Réouvert automatiquement - semaine courante par {user.nom_complet}'
                config.save()
            
            jours_ouverts += 1
        
        # Journaliser l'action
        JournalAudit.objects.create(
            utilisateur=user,
            action="Ouverture semaine courante",
            details=f"Semaine du {monday.strftime('%d/%m/%Y')} - {jours_ouverts} jours ouverts",
            adresse_ip=request.META.get('REMOTE_ADDR'),
            url_acces=request.path,
            methode_http=request.method,
            succes=True
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Semaine courante ouverte : {jours_ouverts} jours de travail activés'
        })
        
    except Exception as e:
        logger.error(f"Erreur ouverture semaine courante: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'Erreur lors de l\'ouverture de la semaine'
        }, status=500)

@login_required
@require_http_methods(["POST"])
def fermer_jours_anciens(request):
    """
    Action rapide : Fermer tous les jours antérieurs à aujourd'hui
    Référencée dans base_site.html ligne 414 - fonction fermerJoursAnciens()
    """
    user = request.user
    
    if not _check_admin_permission(user):
        return JsonResponse({'success': False, 'message': 'Permission refusée'}, status=403)
    
    try:
        today = date.today()
        # Fermer tous les jours jusqu'à hier
        jours_fermes = 0
        
        # Récupérer tous les jours ouverts antérieurs à aujourd'hui
        configs_a_fermer = ConfigurationJour.objects.filter(
            date__lt=today,
            statut='ouvert'
        )
        
        for config in configs_a_fermer:
            config.statut = 'ferme'
            config.commentaire = f'Fermé automatiquement - jours anciens par {user.nom_complet}'
            config.save()
            jours_fermes += 1
        
        # Journaliser l'action
        JournalAudit.objects.create(
            utilisateur=user,
            action="Fermeture jours anciens",
            details=f"Fermeture automatique de {jours_fermes} jours antérieurs à {today.strftime('%d/%m/%Y')}",
            adresse_ip=request.META.get('REMOTE_ADDR'),
            url_acces=request.path,
            methode_http=request.method,
            succes=True
        )
        
        return JsonResponse({
            'success': True,
            'message': f'{jours_fermes} jours anciens fermés automatiquement'
        })
        
    except Exception as e:
        logger.error(f"Erreur fermeture jours anciens: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'Erreur lors de la fermeture des jours anciens'
        }, status=500)


@staff_member_required
@require_http_methods(["POST"])
def action_ouvrir_semaine(request):
    """
    Action rapide pour ouvrir tous les jours ouvrables de la semaine courante
    """
    try:
        
        # Calculer le lundi de la semaine courante
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        
        jours_ouverts = 0
        for i in range(5):  # Lundi à Vendredi
            jour = monday + timedelta(days=i)
            
            config, created = ConfigurationJour.objects.get_or_create(
                date=jour,
                defaults={
                    'statut': StatutJour.OUVERT,
                    'cree_par': request.user,
                    'commentaire': 'Ouverture automatique semaine courante'
                }
            )
            
            if not created and config.statut != StatutJour.OUVERT:
                config.statut = StatutJour.OUVERT
                config.save()
                jours_ouverts += 1
            elif created:
                jours_ouverts += 1
        
        return JsonResponse({
            'success': True,
            'message': _(f'{jours_ouverts} jours ouverts pour la semaine du {monday.strftime("%d/%m/%Y")}')
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': _(f'Erreur: {str(e)}')
        })


@staff_member_required
@require_http_methods(["POST"])
def action_fermer_anciens(request):
    """
    Action rapide pour fermer tous les jours antérieurs à aujourd'hui
    """
    try:
        
        today = date.today()
        
        # Fermer tous les jours ouverts antérieurs à aujourd'hui
        jours_fermes = ConfigurationJour.objects.filter(
            date__lt=today,
            statut=StatutJour.OUVERT
        ).update(statut=StatutJour.FERME)
        
        return JsonResponse({
            'success': True,
            'message': _(f'{jours_fermes} jours anciens fermés')
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': _(f'Erreur: {str(e)}')
        })


@staff_member_required
@require_http_methods(["POST"])
def action_marquer_impertinent(request):
    """
    Action rapide pour marquer un jour comme impertinent
    """
    try:
        
        data = json.loads(request.body)
        date_str = data.get('date')
        commentaire = data.get('commentaire', '')
        
        if not date_str:
            return JsonResponse({
                'success': False,
                'message': _('Date manquante')
            })
        
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({
                'success': False,
                'message': _('Format de date invalide')
            })
        
        config, created = ConfigurationJour.objects.get_or_create(
            date=date_obj,
            defaults={
                'statut': StatutJour.IMPERTINENT,
                'cree_par': request.user,
                'commentaire': commentaire or 'Marqué impertinent manuellement'
            }
        )
        
        if not created:
            config.statut = StatutJour.IMPERTINENT
            if commentaire:
                config.commentaire = commentaire
            config.save()
        
        action_text = 'créé' if created else 'mis à jour'
        
        return JsonResponse({
            'success': True,
            'message': _(f'Jour {date_obj.strftime("%d/%m/%Y")} marqué comme impertinent ({action_text})')
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': _(f'Erreur: {str(e)}')
        })


@staff_member_required
@require_http_methods(["GET"])
def api_notifications(request):
    """
    API pour récupérer les notifications de l'utilisateur
    """
    try:
        from accounts.models import NotificationUtilisateur
        
        # Compter les notifications non lues
        unread_count = NotificationUtilisateur.objects.filter(
            destinataire=request.user,
            lue=False
        ).count()
        
        # Récupérer les dernières notifications
        recent_notifications = NotificationUtilisateur.objects.filter(
            destinataire=request.user
        ).order_by('-date_creation')[:5]
        
        notifications_data = []
        for notif in recent_notifications:
            notifications_data.append({
                'id': notif.id,
                'title': notif.titre,
                'message': notif.message,
                'type': notif.type_notification,
                'read': notif.lue,
                'created': notif.date_creation.isoformat(),
            })
        
        return JsonResponse({
            'success': True,
            'unread_count': unread_count,
            'notifications': notifications_data,
            'new_notifications': []  # À implémenter pour les notifications en temps réel
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': _(f'Erreur: {str(e)}'),
            'unread_count': 0,
            'notifications': []
        })
    
@login_required
@require_http_methods(["POST"])
def marquer_jour_impertinent(request):
    """
    Action rapide : Marquer un jour comme impertinent
    Référencée dans base_site.html ligne 436 - fonction marquerJourImpertinent()
    """
    user = request.user
    
    if not _check_admin_permission(user):
        return JsonResponse({'success': False, 'message': 'Permission refusée'}, status=403)
    
    try:
        data = json.loads(request.body)
        date_str = data.get('date')
        commentaire = data.get('commentaire', '')
        
        if not date_str:
            return JsonResponse({'success': False, 'message': 'Date requise'}, status=400)
        
        from datetime import datetime
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        config, created = ConfigurationJour.objects.get_or_create(
            date=target_date,
            defaults={
                'statut': 'impertinent',
                'cree_par': user,
                'commentaire': commentaire or f'Marqué impertinent par {user.nom_complet}'
            }
        )
        
        if not created:
            config.statut = 'impertinent'
            config.commentaire = commentaire or f'Marqué impertinent par {user.nom_complet}'
            config.save()
        
        # Journaliser l'action
        JournalAudit.objects.create(
            utilisateur=user,
            action="Marquage jour impertinent",
            details=f"Jour {target_date.strftime('%d/%m/%Y')} marqué impertinent - Commentaire: {commentaire}",
            adresse_ip=request.META.get('REMOTE_ADDR'),
            url_acces=request.path,
            methode_http=request.method,
            succes=True
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Jour {target_date.strftime("%d/%m/%Y")} marqué comme impertinent'
        })
        
    except ValueError:
        return JsonResponse({'success': False, 'message': 'Format de date invalide'}, status=400)
    except Exception as e:
        logger.error(f"Erreur marquage jour impertinent: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'Erreur lors du marquage'
        }, status=500)
    
urlpatterns_js = [
    ('ouvrir-semaine', ouvrir_semaine_courante),
    ('fermer-anciens', fermer_jours_anciens),
    ('marquer-impertinent', marquer_jour_impertinent),
]
