# ===================================================================
# inventaire/views.py - VUES COMPLÈTES POUR LE MODULE INVENTAIRE
# Application SUPPER - Suivi des Péages et Pesages Routiers
# ===================================================================

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required,user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Avg, Count
from django.utils import timezone
from django.db import models
from datetime import datetime, date, timedelta
import json
from django.views.decorators.csrf import csrf_exempt
import logging

logger = logging.getLogger('supper')

# Import des modèles
from .models import *
from accounts.models import UtilisateurSUPPER, Poste, JournalAudit
from common.utils import *
from .forms import *

# ===================================================================
# MIXINS ET FONCTIONS UTILITAIRES
# ===================================================================

class InventaireMixin(LoginRequiredMixin):
    """Mixin de base pour les vues inventaire avec permissions"""
    
    def dispatch(self, request, *args, **kwargs):
        if not hasattr(request.user, 'peut_gerer_inventaire') or not request.user.peut_gerer_inventaire:
            messages.error(request, _("Vous n'avez pas les permissions pour accéder aux inventaires."))
            return redirect('common:dashboard')
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin pour les vues nécessitant des droits admin"""
    
    def test_func(self):
        return (self.request.user.is_superuser or 
                self.request.user.is_staff or 
                self.request.user.habilitation in [
                    'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'
                ])
    
    def handle_no_permission(self):
        messages.error(self.request, _("Accès non autorisé à cette fonctionnalité."))
        return redirect('common:dashboard')


def _check_admin_permission(user):
    """Vérifier les permissions administrateur - FONCTION CORRIGÉE"""
    return (user.is_authenticated and (
        user.is_superuser or 
        user.is_staff or 
        hasattr(user, 'habilitation') and user.habilitation in [
            'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'
        ]
    ))


def _log_inventaire_action(request, action, details=""):
    """Journaliser une action inventaire"""
    try:
        JournalAudit.objects.create(
            utilisateur=request.user,
            action=action,
            details=details,
            adresse_ip=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            session_key=request.session.session_key,
            url_acces=request.path,
            methode_http=request.method,
            succes=True
        )
        logger.info(f"INVENTAIRE - {request.user.username} - {action}")
    except Exception as e:
        logger.error(f"Erreur journalisation inventaire: {str(e)}")


# ===================================================================
# VUES PRINCIPALES D'INVENTAIRE
# ===================================================================

class InventaireListView(InventaireMixin, ListView):
    """Liste des inventaires avec filtres et recherche"""
    model = InventaireJournalier
    template_name = 'inventaire/inventaire_list.html'
    context_object_name = 'inventaires'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not hasattr(request.user, 'peut_gerer_inventaire') or not request.user.peut_gerer_inventaire:
            messages.error(request, "Vous n'avez pas les permissions pour accéder aux inventaires.")
            return redirect('common:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        queryset = InventaireJournalier.objects.select_related(
            'poste', 'agent_saisie',
        ).prefetch_related('details_periodes')
        
        # Filtrer selon les postes accessibles à l'utilisateur
        if not _check_admin_permission(self.request.user):
            if hasattr(self.request.user, 'get_postes_accessibles'):
                queryset = queryset.filter(
                    poste__in=self.request.user.get_postes_accessibles()
                )
            elif self.request.user.poste_affectation:
                queryset = queryset.filter(poste=self.request.user.poste_affectation)
            else:
                queryset = queryset.none()
        
        # Filtres de recherche
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(poste__nom__icontains=search) |
                Q(poste__code__icontains=search) |
                Q(agent_saisie__nom_complet__icontains=search)
            )
        
        # Filtre par poste
        poste_id = self.request.GET.get('poste')
        if poste_id:
            queryset = queryset.filter(poste_id=poste_id)
        
        # Filtre par date
        date_debut = self.request.GET.get('date_debut')
        date_fin = self.request.GET.get('date_fin')
        
        if date_debut:
            try:
                date_debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
                queryset = queryset.filter(date__gte=date_debut)
            except ValueError:
                pass
        
        if date_fin:
            try:
                date_fin = datetime.strptime(date_fin, '%Y-%m-%d').date()
                queryset = queryset.filter(date__lte=date_fin)
            except ValueError:
                pass
        
        
        return queryset.order_by('-date', 'poste__nom')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_admin'] = _check_admin_permission(self.request.user)
        
        # Postes accessibles pour le filtre
        if context['can_admin']:
            context['postes'] = Poste.objects.filter(is_active=True).order_by('nom')
        elif hasattr(self.request.user, 'get_postes_accessibles'):
            context['postes'] = self.request.user.get_postes_accessibles()
        else:
            context['postes'] = Poste.objects.none()
        
        # Statistiques rapides
        total_inventaires = self.get_queryset().count()
        inventaires_today = self.get_queryset().filter(date=timezone.now().date()).count()
        #inventaires_verrouilles = self.get_queryset().filter(verrouille=True).count()
        
        context.update({
            'postes': context['postes'],
            'total_inventaires': total_inventaires,
            'inventaires_today': inventaires_today,
            #'inventaires_verrouilles': inventaires_verrouilles,
            'can_admin': _check_admin_permission(self.request.user),
            'current_filters': {
                'search': self.request.GET.get('search', ''),
                'poste': self.request.GET.get('poste', ''),
                'date_debut': self.request.GET.get('date_debut', ''),
                'date_fin': self.request.GET.get('date_fin', ''),
                'statut': self.request.GET.get('statut', ''),
            }
        })
        
        return context


class InventaireDetailView(InventaireMixin, DetailView):
    """Détail d'un inventaire avec calculs et historique"""
    model = InventaireJournalier
    template_name = 'inventaire/inventaire_detail.html'
    context_object_name = 'inventaire'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        return super().dispatch(request, *args, **kwargs)
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        
        # Vérifier l'accès au poste
        if hasattr(self.request.user, 'peut_acceder_poste'):
            if not self.request.user.peut_acceder_poste(obj.poste):
                raise PermissionError("Accès non autorisé à ce poste.")
        
        return obj
    
    def get_context_data(self, **kwargs):
        """Méthode get_context_data corrigée"""
        context = super().get_context_data(**kwargs)
        
        # 🔧 CORRECTION 1 : Une seule récupération de l'objet
        inventaire = self.object()
        
        # # 🔧 CORRECTION 2 : Vérifier le statut pour la date de l'inventaire
        # try:
        #     context['jour_etait_ouvert'] = ConfigurationJour.est_jour_ouvert_pour_inventaire(
        #         date=inventaire.date,     # 🔧 Date de l'inventaire
        #         poste=inventaire.poste    # 🔧 Poste de l'inventaire
        #     )
        # except Exception as e:
        #     # 🔧 AMÉLIORATION : Log l'erreur pour debug
        #     import logging
        #     logger = logging.getLogger('supper')
        #     logger.warning(f"Erreur vérification statut jour {inventaire.date}: {str(e)}")
        #     context['jour_etait_ouvert'] = False
        
        # Détails par période
        # details_periodes = inventaire.details_periodes.all().order_by('periode')
        context['details_periodes'] = inventaire.details_periodes.all().order_by('periode')
        
        # Recette associée
        try:
            context['recette'] = RecetteJournaliere.objects.get(
                poste=inventaire.poste,
                date=inventaire.date
            )
        except RecetteJournaliere.DoesNotExist:
            context['recette'] = None
        
         # Calculs sécurisés
        try:
            context['moyenne_horaire'] = inventaire.calculer_moyenne_horaire()
            context['estimation_24h'] = inventaire.estimer_total_24h()
            context['recette_potentielle'] = inventaire.calculer_recette_potentielle()
        except Exception as e:
            logger.error(f"Erreur calculs inventaire {inventaire.pk}: {str(e)}")
            context['moyenne_horaire'] = 0
            context['estimation_24h'] = 0
            context['recette_potentielle'] = 0
        
        # Vérifier si le jour est impertinent
        try:
            config = ConfigurationJour.objects.filter(date=inventaire.date).first()
            context['jour_impertinent'] = config and config.statut == StatutJour.IMPERTINENT
        except:
            context['jour_impertinent'] = False
        
            
            import logging
            logger = logging.getLogger('supper')
            logger.error(f"Erreur calculs inventaire {inventaire.pk}: {str(e)}")
        
        # Données pour graphique par période
        try:
            details_periodes = inventaire.details_periodes.all().order_by('periode')
            graph_data = {
                'periodes': [d.get_periode_display() for d in details_periodes],
                'vehicules': [d.nombre_vehicules for d in details_periodes],
            }
            # 🔧 CORRECTION 3 : json.dumps sécurisé
            graph_data_json = json.dumps(graph_data, ensure_ascii=False)
        except Exception as e:
            # Fallback en cas d'erreur de sérialisation
            graph_data_json = '{}'
            import logging
            logger = logging.getLogger('supper')
            logger.error(f"Erreur sérialisation graph_data: {str(e)}")
        return context

class SaisieInventaireView(InventaireMixin, View):
    """Vue pour la saisie d'inventaire par les agents"""
    template_name = 'inventaire/saisie_inventaire.html'
    
    @require_permission('peut_gerer_inventaire')
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request, poste_id=None, date_str=None):
        """Affichage du formulaire de saisie"""
        
        # Déterminer le poste
        if poste_id:
            poste = get_object_or_404(Poste, id=poste_id)
        else:
            poste = request.user.poste_affectation
            if not poste:
                messages.error(request, "Aucun poste d'affectation configuré.")
                return redirect('common:dashboard')
        
        # Vérifier l'accès au poste
        if hasattr(request.user, 'peut_acceder_poste'):
            if not request.user.peut_acceder_poste(poste):
                messages.error(request, "Accès non autorisé à ce poste.")
                return redirect('inventaire:inventaire_list')
        
        # Déterminer la date
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, "Format de date invalide.")
                return redirect('inventaire:saisie_inventaire')
        else:
            target_date = timezone.now().date()
        
        # Récupérer ou créer l'inventaire
        inventaire, created = InventaireJournalier.objects.get_or_create(
            poste=poste,
            date=target_date,
            defaults={'agent_saisie': request.user}
        )
        
        # # Vérifier si l'inventaire peut être modifié
        # if hasattr(inventaire, 'verrouille') and inventaire.verrouille:
        #     messages.warning(request, "Cet inventaire est verrouillé et ne peut plus être modifié.")
        #     return redirect('inventaire:inventaire_detail', pk=inventaire.pk)
        
        # Récupérer les détails existants
        details_existants = {
            d.periode: d for d in inventaire.details_periodes.all()
        }
        
        # Préparer les données pour le template
        periodes_data = []
        for periode_choice in PeriodeHoraire.choices:
            periode_code, periode_display = periode_choice
            detail = details_existants.get(periode_code)
            periodes_data.append({
                'code': periode_code,
                'display': periode_display,
                'nombre_vehicules': detail.nombre_vehicules if detail else 0,
                'observations': detail.observations_periode if detail else '',
                'has_data': detail is not None,
            })
        
        context = {
            'inventaire': inventaire,
            'poste': poste,
            'target_date': target_date,
            'periodes_data': periodes_data,
            'is_new': created,
            'can_save': not getattr(inventaire, 'verrouille', False),
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request, poste_id=None, date_str=None):
        """Traitement de la saisie d'inventaire"""
        
        # Récupérer les paramètres
        if poste_id:
            poste = get_object_or_404(Poste, id=poste_id)
        else:
            poste = request.user.poste_affectation
        
        if date_str:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            target_date = timezone.now().date()
        
        # Vérifications de sécurité
        if hasattr(request.user, 'peut_acceder_poste'):
            if not request.user.peut_acceder_poste(poste):
                return JsonResponse({'error': 'Accès non autorisé'}, status=403)
        
        try:
            # Récupérer l'inventaire
            inventaire = InventaireJournalier.objects.get(
                poste=poste,
                date=target_date
            )
            
            # if hasattr(inventaire, 'verrouille') and inventaire.verrouille:
            #     return JsonResponse({'error': 'Inventaire verrouillé'}, status=400)
            
            # Traiter les données des périodes
            details_saved = 0
            total_vehicules = 0
            
            for periode_choice in PeriodeHoraire.choices:
                periode_code, _ = periode_choice
                
                nombre_vehicules = request.POST.get(f'periode_{periode_code}', '').strip()
                observations = request.POST.get(f'observations_{periode_code}', '').strip()
                
                if nombre_vehicules:
                    try:
                        nombre_vehicules = int(nombre_vehicules)
                        if 0 <= nombre_vehicules <= 1000:
                            detail, created = DetailInventairePeriode.objects.update_or_create(
                                inventaire=inventaire,
                                periode=periode_code,
                                defaults={
                                    'nombre_vehicules': nombre_vehicules,
                                    'observations_periode': observations,
                                }
                            )
                            details_saved += 1
                            total_vehicules += nombre_vehicules
                    except ValueError:
                        continue
            
            # Mettre à jour l'inventaire
            inventaire.total_vehicules = total_vehicules
            inventaire.nombre_periodes_saisies = details_saved
            inventaire.save()
            
            # Journaliser l'action
            log_user_action(
                request.user,
                "Saisie inventaire",
                f"Poste: {poste.nom}, Date: {target_date}, Véhicules: {total_vehicules}",
                request
            )
            
            messages.success(request, "Inventaire sauvegardé avec succès.")
            return redirect('inventaire:inventaire_detail', pk=inventaire.pk)
        
        except Exception as e:
            logger.error(f"Erreur saisie inventaire: {str(e)}")
            messages.error(request, "Erreur lors de la sauvegarde de l'inventaire.")
            return redirect('inventaire:saisie_inventaire')
        
    def get_context_data(self, **kwargs):
        """Ajouter des données au contexte"""
        context = super().get_context_data(**kwargs)
        
        # Ajouter la date d'aujourd'hui
        context['today'] = date.today()
        
        # Ajouter les postes accessibles
        if hasattr(self.request.user, 'get_postes_accessibles'):
            context['postes_accessibles'] = self.request.user.get_postes_accessibles()
        else:
            context['postes_accessibles'] = Poste.objects.filter(is_active=True)
        
        # 🔧 CORRECTION : Vérifier si aujourd'hui est ouvert - AVEC l'argument date
        try:
            today = date.today()
            context['jour_ouvert_inventaire'] = ConfigurationJour.est_jour_ouvert_pour_inventaire(
                date=today,  # 🔧 AJOUT de l'argument date manquant
                poste=None   # Configuration globale
            )
            context['message_statut_jour'] = self._get_message_statut_jour(today)
        except Exception as e:
            # En cas d'erreur, considérer comme fermé par sécurité
            context['jour_ouvert_inventaire'] = False
            context['message_statut_jour'] = f"Impossible de vérifier le statut du jour : {str(e)}"
        
        return context
    
    def _get_message_statut_jour(self, date_check):
        """
        🔧 MÉTHODE CORRIGÉE : Obtenir le message de statut du jour
        """
        try:
            # Vérifier la configuration globale
            config_globale = ConfigurationJour.objects.filter(
                date=date_check, 
                poste__isnull=True
            ).first()
            
            if config_globale:
                if config_globale.statut == 'ouvert':
                    if getattr(config_globale, 'permet_saisie_inventaire', False):
                        return "✅ Jour ouvert pour la saisie d'inventaires"
                    else:
                        return "⚠️ Jour ouvert mais saisie d'inventaires non autorisée"
                elif config_globale.statut == 'ferme':
                    return "🔒 Jour fermé pour toutes les saisies"
                elif config_globale.statut == 'impertinent':
                    return "⚠️ Jour marqué comme impertinent"
            else:
                return "❌ Aucune configuration trouvée pour ce jour - Saisie fermée par défaut"
                
        except Exception as e:
            return f"❌ Erreur lors de la vérification : {str(e)}"
    
    def get_form_kwargs(self):
        """Passer l'utilisateur au formulaire"""
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs
    
    def form_valid(self, form):
        """Traitement lors de la soumission valide du formulaire"""
        # 🔧 VALIDATION CORRIGÉE : Vérifier que le jour est ouvert AVANT la sauvegarde
        try:
            date_inventaire = form.cleaned_data.get('date', date.today())
            poste_inventaire = form.cleaned_data.get('poste')
            
            # Vérification avec les bons arguments
            if not ConfigurationJour.est_jour_ouvert_pour_inventaire(
                date=date_inventaire,  # 🔧 Argument date correct
                poste=poste_inventaire  # 🔧 Argument poste correct
            ):
                messages.error(
                    self.request, 
                    f"La saisie d'inventaire n'est pas autorisée pour le "
                    f"{date_inventaire.strftime('%d/%m/%Y')}. "
                    "Contactez un administrateur pour ouvrir ce jour."
                )
                return self.form_invalid(form)
            
            # Définir l'agent de saisie
            form.instance.agent_saisie = self.request.user
            
            # Sauvegarder
            response = super().form_valid(form)
            
            messages.success(
                self.request, 
                f'Inventaire créé avec succès pour le {date_inventaire.strftime("%d/%m/%Y")} '
                f'au poste {poste_inventaire.nom if poste_inventaire else "non spécifié"}!'
            )
            
            return response
            
        except Exception as e:
            messages.error(
                self.request, 
                f"Erreur lors de la création de l'inventaire : {str(e)}"
            )
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        """Traitement lors d'un formulaire invalide"""
        messages.error(
            self.request, 
            "Erreur dans le formulaire. Veuillez vérifier les données saisies."
        )
        return super().form_invalid(form)
    
    def get_success_url(self):
        """URL de redirection après succès"""
        return '/admin/inventaire/inventairejournalier/'

@login_required
@require_permission('peut_gerer_inventaire')
def modifier_inventaire(request, pk):
    """
    Permet de modifier un inventaire existant
    Pas de vérification de verrouillage car plus de verrouillage
    """
    inventaire = get_object_or_404(InventaireJournalier, pk=pk)
    
    # Vérifier que l'utilisateur peut accéder à ce poste
    if not request.user.peut_acceder_poste(inventaire.poste):
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        return HttpResponseForbidden("Accès non autorisé")
    
    # Vérifier si l'utilisateur peut modifier (admin ou agent si modifiable_par_agent)
    if not inventaire.peut_etre_modifie_par(request.user):
        messages.error(request, "Vous n'avez pas la permission de modifier cet inventaire.")
        return HttpResponseForbidden("Permission insuffisante")
    
    if request.method == 'POST':
        form = InventaireJournalierForm(
            request.POST, 
            instance=inventaire,
            user=request.user
        )
        
        if form.is_valid():
            inventaire = form.save(commit=False)
            inventaire.derniere_modification_par = request.user
            inventaire.save()
            
            # Traiter les détails par période
            periodes_data = {}
            for key, value in request.POST.items():
                if key.startswith('periode_'):
                    periode = key.replace('periode_', '').replace('_', '-')
                    if value and value.isdigit():
                        periodes_data[periode] = int(value)
            
            # Mettre à jour ou créer les détails
            for periode, nombre in periodes_data.items():
                DetailInventairePeriode.objects.update_or_create(
                    inventaire=inventaire,
                    periode=periode,
                    defaults={'nombre_vehicules': nombre}
                )
            
            # Supprimer les périodes non soumises
            periodes_soumises = list(periodes_data.keys())
            inventaire.details_periodes.exclude(periode__in=periodes_soumises).delete()
            
            # Recalculer les totaux
            inventaire.recalculer_totaux()
            
            # Recalculer la recette associée si elle existe
            try:
                if hasattr(inventaire, 'recette'):
                    inventaire.recette.calculer_indicateurs()
                    inventaire.recette.save()
            except:
                pass
            
            # Journaliser l'action
            log_user_action(
                request.user,
                "Modification inventaire",
                f"Inventaire modifié: {inventaire.poste.nom} - {inventaire.date}",
                request
            )
            
            messages.success(request, "L'inventaire a été modifié avec succès.")
            return redirect('inventaire_detail', pk=inventaire.pk)
    else:
        form = InventaireJournalierForm(
            instance=inventaire,
            user=request.user
        )
        
        # Récupérer les détails existants
        details = inventaire.details_periodes.all()
        periodes_data = {d.periode: d.nombre_vehicules for d in details}
    
    context = {
        'form': form,
        'inventaire': inventaire,
        'periodes_data': periodes_data,
        'periodes_choices': [
            ('08h-09h', '08h-09h'), ('09h-10h', '09h-10h'), 
            ('10h-11h', '10h-11h'), ('11h-12h', '11h-12h'),
            ('12h-13h', '12h-13h'), ('13h-14h', '13h-14h'), 
            ('14h-15h', '14h-15h'), ('15h-16h', '15h-16h'),
            ('16h-17h', '16h-17h'), ('17h-18h', '17h-18h')
        ],
        'title': f'Modifier inventaire du {inventaire.date}'
    }
    
    return render(request, 'inventaire/modifier_inventaire.html', context)

@login_required
@require_permission('peut_gerer_inventaire')
def supprimer_inventaire(request, pk):
    """
    Permet de supprimer un inventaire
    Seuls les admins  peuvent supprimer
    """
    inventaire = get_object_or_404(InventaireJournalier, pk=pk)
    
    # Vérifier les permissions
    if not request.user.peut_acceder_poste(inventaire.poste):
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        return HttpResponseForbidden("Accès non autorisé")
    
    # Seuls admin et chef de poste peuvent supprimer
    if not (request.user.is_admin()):
        messages.error(request, "Seuls les administrateurs peuvent supprimer des inventaires.")
        return HttpResponseForbidden("Permission insuffisante")
    
    if request.method == 'POST':
        # Sauvegarder les infos pour le log
        info_inventaire = f"{inventaire.poste.nom} - {inventaire.date}"
        
        # Vérifier s'il y a une recette associée
        recette_associee = None
        try:
            recette_associee = inventaire.recette
        except:
            pass
        
        if recette_associee:
            # Dissocier la recette
            recette_associee.inventaire_associe = None
            recette_associee.recette_potentielle = None
            recette_associee.ecart = None
            recette_associee.taux_deperdition = None
            recette_associee.save()
            messages.info(request, "La recette associée a été dissociée.")
        
        # Supprimer l'inventaire et ses détails (cascade)
        inventaire.delete()
        
        # Journaliser l'action
        log_user_action(
            request.user,
            "Suppression inventaire",
            f"Inventaire supprimé: {info_inventaire}",
            request
        )
        
        messages.success(request, "L'inventaire a été supprimé avec succès.")
        return redirect('liste_inventaires')
    
    # Vérifier s'il y a une recette associée pour avertir
    has_recette = False
    try:
        has_recette = hasattr(inventaire, 'recette') and inventaire.recette is not None
    except:
        pass
    
    context = {
        'inventaire': inventaire,
        'has_recette': has_recette,
        'title': 'Confirmer la suppression'
    }
    
    return render(request, 'inventaire/confirmer_suppression.html', context)
@login_required
def saisir_recette(request):
    """
    Interface de saisie de recette pour les chefs de poste
    Pas de vérification de jour ouvert/fermé
    """
    # Vérifier que l'utilisateur peut saisir des recettes
    if not (request.user.is_chef_poste or request.user.is_admin):
        messages.error(request, "Vous n'avez pas la permission de saisir des recettes.")
        return HttpResponseForbidden("Accès non autorisé")
    
    # Déterminer les postes accessibles
    postes = request.user.get_postes_accessibles()
    
    if request.method == 'POST':
        form = RecetteJournaliereForm(request.POST, user=request.user)
        
        if form.is_valid():
            recette = form.save(commit=False)
            recette.chef_poste = request.user
            recette.derniere_modification_par = request.user
            
            # Vérifier qu'une recette n'existe pas déjà
            existing = RecetteJournaliere.objects.filter(
                poste=recette.poste,
                date=recette.date
            ).first()
            
            if existing:
                messages.warning(request, f"Une recette existe déjà pour {recette.poste.nom} le {recette.date}")
                return redirect('modifier_recette', pk=existing.pk)
            
            # Chercher l'inventaire associé automatiquement
            if form.cleaned_data.get('lier_inventaire', True):
                try:
                    inventaire = InventaireJournalier.objects.get(
                        poste=recette.poste,
                        date=recette.date
                    )
                    recette.inventaire_associe = inventaire
                except InventaireJournalier.DoesNotExist:
                    messages.info(request, "Aucun inventaire trouvé pour cette date.")
            
            # Sauvegarder (les calculs se font automatiquement)
            recette.save()
            
            # Journaliser l'action
            log_user_action(
                request.user,
                "Saisie recette",
                f"Recette saisie: {recette.montant_declare} FCFA pour {recette.poste.nom} - {recette.date}",
                request
            )
            
            # Messages selon le taux de déperdition
            if recette.taux_deperdition is not None:
                statut = recette.get_statut_deperdition()
                couleur = recette.get_couleur_alerte()
                
                if statut == 'Impertinent':
                    messages.warning(request, f"Journée marquée comme impertinente (TD: {recette.taux_deperdition:.2f}%)")
                elif couleur == 'danger':
                    messages.warning(request, f"Attention: Taux de déperdition mauvais ({recette.taux_deperdition:.2f}%)")
                elif couleur == 'warning':
                    messages.info(request, f"Taux de déperdition acceptable ({recette.taux_deperdition:.2f}%)")
                else:
                    messages.success(request, f"Bon taux de déperdition ({recette.taux_deperdition:.2f}%)")
            else:
                messages.success(request, "Recette enregistrée avec succès.")
            
            return redirect('recette_detail', pk=recette.pk)
    else:
        # Pré-remplir avec la date du jour et le poste
        initial_data = {
            'date': timezone.now().date(),
            'lier_inventaire': True
        }
        if request.user.poste_affectation:
            initial_data['poste'] = request.user.poste_affectation
            
        form = RecetteJournaliereForm(initial=initial_data, user=request.user)
    
    # Récupérer les recettes récentes
    recettes_recentes = RecetteJournaliere.objects.filter(
        chef_poste=request.user
    ).select_related('poste', 'inventaire_associe').order_by('-date')[:10]
    
    # Statistiques rapides
    stats = {}
    if recettes_recentes:
        stats = {
            'total_mois': recettes_recentes.filter(
                date__month=timezone.now().month,
                date__year=timezone.now().year
            ).aggregate(
                total=Sum('montant_declare')
            )['total'] or 0,
            'moyenne_taux': recettes_recentes.filter(
                taux_deperdition__isnull=False
            ).aggregate(
                moyenne=Avg('taux_deperdition')
            )['moyenne'] or 0
        }
    
    context = {
        'form': form,
        'postes': postes,
        'recettes_recentes': recettes_recentes,
        'stats': stats,
        'title': 'Saisir une recette journalière'
    }
    
    return render(request, 'inventaire/saisir_recette.html', context)
@login_required
def modifier_recette(request, pk):
    """
    Permet de modifier une recette existante
    """
    recette = get_object_or_404(RecetteJournaliere, pk=pk)
    
    # Vérifier les permissions
   
    is_admin = request.user.is_admin()
    can_access_poste = request.user.peut_acceder_poste(recette.poste)
    
    # Vérifier si peut modifier
    can_modify = False
    if is_admin:
        can_modify = True
    
    if not can_modify:
        messages.error(request, "Vous n'avez pas la permission de modifier cette recette.")
        return HttpResponseForbidden("Permission insuffisante")
    
    if request.method == 'POST':
        form = RecetteJournaliereForm(
            request.POST,
            instance=recette,
            user=request.user
        )
        
        if form.is_valid():
            recette = form.save(commit=False)
            recette.derniere_modification_par = request.user
            
            # Re-lier l'inventaire si demandé
            if 'lier_inventaire' in request.POST:
                try:
                    inventaire = InventaireJournalier.objects.get(
                        poste=recette.poste,
                        date=recette.date
                    )
                    recette.inventaire_associe = inventaire
                except InventaireJournalier.DoesNotExist:
                    messages.info(request, "Aucun inventaire trouvé pour cette date.")
            
            recette.save()
            
            # Journaliser
            log_user_action(
                request.user,
                "Modification recette",
                f"Recette modifiée: {recette.poste.nom} - {recette.date}",
                request
            )
            
            messages.success(request, "La recette a été modifiée avec succès.")
            return redirect('recette_detail', pk=recette.pk)
    else:
        form = RecetteJournaliereForm(
            instance=recette,
            user=request.user
        )
    
    context = {
        'form': form,
        'recette': recette,
        'title': f'Modifier recette du {recette.date}'
    }
    
    return render(request, 'inventaire/modifier_recette.html', context)

@login_required
def supprimer_recette(request, pk):
    """
    Permet de supprimer une recette
    """
    recette = get_object_or_404(RecetteJournaliere, pk=pk)
    
    # Vérifier les permissions
    if not (request.user.is_admin()):
        messages.error(request, "Seuls les administrateurs  peuvent supprimer des recettes.")
        return HttpResponseForbidden("Permission insuffisante")
    
    if not request.user.peut_acceder_poste(recette.poste):
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        return HttpResponseForbidden("Accès non autorisé")
    
    if request.method == 'POST':
        # Sauvegarder les infos
        info_recette = f"{recette.poste.nom} - {recette.date} - {recette.montant_declare} FCFA"
        
        # Supprimer
        recette.delete()
        
        # Journaliser
        log_user_action(
            request.user,
            "Suppression recette",
            f"Recette supprimée: {info_recette}",
            request
        )
        
        messages.success(request, "La recette a été supprimée avec succès.")
        return redirect('liste_recettes')
    
    context = {
        'recette': recette,
        'title': 'Confirmer la suppression'
    }
    
    return render(request, 'inventaire/confirmer_suppression_recette.html', context)

@login_required
@require_permission('peut_gerer_inventaire')
def liste_inventaires_mensuels(request):
    """
    Liste des inventaires mensuels programmés
    """
    # Filtrer selon les permissions
    if request.user.is_admin:
        inventaires = InventaireMensuel.objects.all()
    else:
        postes = request.user.get_postes_accessibles()
        inventaires = InventaireMensuel.objects.filter(
            poste__in=postes
        )
    
    # Filtres
    mois = request.GET.get('mois')
    annee = request.GET.get('annee')
    poste_id = request.GET.get('poste')
    motif = request.GET.get('motif')
    
    if mois:
        inventaires = inventaires.filter(mois=mois)
    if annee:
        inventaires = inventaires.filter(annee=annee)
    if poste_id:
        inventaires = inventaires.filter(poste_id=poste_id)
    if motif:
        inventaires = inventaires.filter(motif=motif)
    
    # Ordering
    inventaires = inventaires.select_related(
        'poste', 'cree_par', 'programmation'
    ).order_by('-annee', '-mois', 'poste__nom')
    
    # Statistiques
    stats = {
        'total': inventaires.count(),
        'actifs': inventaires.filter(actif=True).count(),
        'mois_courant': inventaires.filter(
            mois=str(timezone.now().month).zfill(2),
            annee=timezone.now().year
        ).count()
    }
    
    context = {
        'inventaires': inventaires,
        'stats': stats,
        'postes': Poste.objects.filter(is_active=True),
        'current_year': timezone.now().year,
        'title': 'Inventaires mensuels'
    }
    
    return render(request, 'inventaire/liste_inventaires_mensuels.html', context)


@login_required
@require_permission('peut_gerer_inventaire')
def detail_inventaire_mensuel(request, pk):
    """
    Détail d'un inventaire mensuel avec tous les inventaires journaliers associés
    """
    inventaire_mensuel = get_object_or_404(InventaireMensuel, pk=pk)
    
    # Vérifier l'accès au poste
    if not request.user.peut_acceder_poste(inventaire_mensuel.poste):
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        return HttpResponseForbidden("Accès non autorisé")
    
    # Calculer les dates du mois
    annee = inventaire_mensuel.annee
    mois = int(inventaire_mensuel.mois)
    date_debut = date(annee, mois, 1)
    dernier_jour = calendar.monthrange(annee, mois)[1]
    date_fin = date(annee, mois, dernier_jour)
    
    # Récupérer les inventaires journaliers du mois
    inventaires_journaliers = InventaireJournalier.objects.filter(
        poste=inventaire_mensuel.poste,
        date__range=[date_debut, date_fin]
    ).select_related('agent_saisie').prefetch_related('details_periodes')
    
    # Récupérer les recettes du mois
    recettes = RecetteJournaliere.objects.filter(
        poste=inventaire_mensuel.poste,
        date__range=[date_debut, date_fin]
    ).select_related('chef_poste', 'inventaire_associe')
    
    # Calculer les statistiques
    stats = {
        'total_vehicules': inventaires_journaliers.aggregate(
            total=Sum('total_vehicules')
        )['total'] or 0,
        'total_recettes_declarees': recettes.aggregate(
            total=Sum('montant_declare')
        )['total'] or Decimal('0'),
        'total_recettes_potentielles': recettes.aggregate(
            total=Sum('recette_potentielle')
        )['total'] or Decimal('0'),
        'nombre_jours_saisis': inventaires_journaliers.count(),
        'nombre_jours_impertinents': ConfigurationJour.objects.filter(
            date__range=[date_debut, date_fin],
            statut='impertinent'
        ).count()
    }
    
    # Calculer le taux moyen
    if stats['total_recettes_potentielles'] > 0:
        ecart = stats['total_recettes_declarees'] - stats['total_recettes_potentielles']
        stats['taux_deperdition_moyen'] = (ecart / stats['total_recettes_potentielles']) * 100
    else:
        stats['taux_deperdition_moyen'] = None
    
    # Créer un calendrier du mois avec les données
    cal = calendar.monthcalendar(annee, mois)
    calendrier_data = []
    
    for semaine in cal:
        semaine_data = []
        for jour in semaine:
            if jour == 0:
                semaine_data.append(None)
            else:
                date_jour = date(annee, mois, jour)
                inventaire = inventaires_journaliers.filter(date=date_jour).first()
                recette = recettes.filter(date=date_jour).first()
                config = ConfigurationJour.objects.filter(date=date_jour).first()
                
                semaine_data.append({
                    'jour': jour,
                    'date': date_jour,
                    'inventaire': inventaire,
                    'recette': recette,
                    'config': config,
                    'is_impertinent': config and config.statut == 'impertinent'
                })
        calendrier_data.append(semaine_data)
    
    context = {
        'inventaire_mensuel': inventaire_mensuel,
        'inventaires_journaliers': inventaires_journaliers,
        'recettes': recettes,
        'stats': stats,
        'calendrier': calendrier_data,
        'title': f'Inventaire mensuel - {inventaire_mensuel.get_mois_display()} {annee}'
    }
    
    return render(request, 'inventaire/detail_inventaire_mensuel.html', context)
@login_required
@require_permission('peut_gerer_inventaire')
def consolider_inventaire_mensuel(request):
    """
    Consolide les données d'un mois pour créer/mettre à jour les statistiques
    """
    if request.method != 'POST':
        return redirect('liste_inventaires_mensuels')
    
    poste_id = request.POST.get('poste_id')
    mois = request.POST.get('mois')
    annee = request.POST.get('annee')
    
    if not all([poste_id, mois, annee]):
        messages.error(request, "Paramètres manquants pour la consolidation.")
        return redirect('liste_inventaires_mensuels')
    
    try:
        poste = Poste.objects.get(pk=poste_id)
        
        # Vérifier l'accès
        if not request.user.peut_acceder_poste(poste):
            messages.error(request, "Vous n'avez pas accès à ce poste.")
            return HttpResponseForbidden("Accès non autorisé")
        
        # Calculer les dates
        annee_int = int(annee)
        mois_int = int(mois)
        date_debut = date(annee_int, mois_int, 1)
        dernier_jour = calendar.monthrange(annee_int, mois_int)[1]
        date_fin = date(annee_int, mois_int, dernier_jour)
        
        # Créer ou mettre à jour l'inventaire mensuel
        inventaire_mensuel, created = InventaireMensuel.objects.update_or_create(
            poste=poste,
            mois=str(mois_int).zfill(2),
            annee=annee_int,
            defaults={
                'titre': f"Inventaire {poste.nom} - {mois}/{annee}",
                'cree_par': request.user if created else None,
                'actif': True
            }
        )
        
        # Consolider les données
        inventaire_mensuel.consolider_donnees()
        
        # Créer les statistiques périodiques
        StatistiquesPeriodiques.calculer_statistiques_periode(
            poste=poste,
            type_periode='mensuelle',
            date_debut=date_debut,
            date_fin=date_fin
        )
        
        # Journaliser
        log_user_action(
            request.user,
            "Consolidation inventaire mensuel",
            f"Consolidation effectuée pour {poste.nom} - {mois}/{annee}",
            request
        )
        
        messages.success(request, f"Consolidation réussie pour {poste.nom} - {mois}/{annee}")
        return redirect('detail_inventaire_mensuel', pk=inventaire_mensuel.pk)
        
    except Poste.DoesNotExist:
        messages.error(request, "Poste introuvable.")
    except Exception as e:
        messages.error(request, f"Erreur lors de la consolidation: {str(e)}")
    
    return redirect('liste_inventaires_mensuels')

class ConfigurationJourListView(AdminRequiredMixin, ListView):
    """Liste des configurations de jours"""
    model = ConfigurationJour
    template_name = 'inventaire/config_jour_list.html'
    context_object_name = 'configurations'
    paginate_by = 31  # Un mois par page
    
    def get_queryset(self):
        queryset = ConfigurationJour.objects.select_related('cree_par')
        
        # Filtre par mois/année
        mois = self.request.GET.get('mois')
        annee = self.request.GET.get('annee')
        
        if mois and annee:
            try:
                mois = int(mois)
                annee = int(annee)
                queryset = queryset.filter(date__month=mois, date__year=annee)
            except ValueError:
                pass
        
        return queryset.order_by('-date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Dates pour le filtre
        now = timezone.now()
        context.update({
            'current_month': now.month,
            'current_year': now.year,
            'months': [
                (1, 'Janvier'), (2, 'Février'), (3, 'Mars'), (4, 'Avril'),
                (5, 'Mai'), (6, 'Juin'), (7, 'Juillet'), (8, 'Août'),
                (9, 'Septembre'), (10, 'Octobre'), (11, 'Novembre'), (12, 'Décembre')
            ],
            'years': range(now.year - 2, now.year + 2),
        })
        
        return context


# class InventaireVerrouillerView(InventaireMixin, View):
#     """Vue pour verrouiller un inventaire"""
    
#     @method_decorator(require_http_methods(["POST"]))
#     def dispatch(self, *args, **kwargs):
#         return super().dispatch(*args, **kwargs)
    
#     def post(self, request, pk):
#         """Verrouiller un inventaire"""
#         if not _check_admin_permission(request.user):
#             return JsonResponse({'error': 'Permission refusée'}, status=403)
        
#         try:
#             inventaire = get_object_or_404(InventaireJournalier, pk=pk)
            
#             if not request.user.peut_acceder_poste(inventaire.poste):
#                 return JsonResponse({'error': 'Accès non autorisé à ce poste'}, status=403)
            
#             if inventaire.verrouille:
#                 return JsonResponse({'error': 'Inventaire déjà verrouillé'}, status=400)
            
#             # Vérifier que l'inventaire est complet
#             if inventaire.nombre_periodes_saisies < 1:
#                 return JsonResponse({'error': 'Inventaire incomplet'}, status=400)
            
#             inventaire.verrouille = True
#             inventaire.date_verrouillage = timezone.now()
#             inventaire.verrouille_par = request.user
#             inventaire.save()
            
#             _log_inventaire_action(
#                 request, 
#                 "Verrouillage inventaire",
#                 f"Inventaire {inventaire.poste.nom} du {inventaire.date}"
#             )
            
#             return JsonResponse({
#                 'success': True,
#                 'message': 'Inventaire verrouillé avec succès'
#             })
            
#         except Exception as e:
#             logger.error(f"Erreur verrouillage inventaire: {str(e)}")
#             return JsonResponse({'error': 'Erreur serveur'}, status=500)


# class InventaireValiderView(InventaireMixin, View):
#     """Vue pour valider un inventaire"""
    
#     @method_decorator(require_http_methods(["POST"]))
#     def dispatch(self, *args, **kwargs):
#         return super().dispatch(*args, **kwargs)
    
#     def post(self, request, pk):
#         """Valider un inventaire"""
#         if not _check_admin_permission(request.user):
#             return JsonResponse({'error': 'Permission refusée'}, status=403)
        
#         try:
#             inventaire = get_object_or_404(InventaireJournalier, pk=pk)
            
#             if not request.user.peut_acceder_poste(inventaire.poste):
#                 return JsonResponse({'error': 'Accès non autorisé à ce poste'}, status=403)
            
#             if not inventaire.verrouille:
#                 return JsonResponse({'error': 'Inventaire non verrouillé'}, status=400)
            
#             if inventaire.valide:
#                 return JsonResponse({'error': 'Inventaire déjà validé'}, status=400)
            
#             inventaire.valide = True
#             inventaire.date_validation = timezone.now()
#             inventaire.valide_par = request.user
#             inventaire.save()
            
#             _log_inventaire_action(
#                 request, 
#                 "Validation inventaire",
#                 f"Inventaire {inventaire.poste.nom} du {inventaire.date}"
#             )
            
#             return JsonResponse({
#                 'success': True,
#                 'message': 'Inventaire validé avec succès'
#             })
            
#         except Exception as e:
#             logger.error(f"Erreur validation inventaire: {str(e)}")
#             return JsonResponse({'error': 'Erreur serveur'}, status=500)


# ===================================================================
# API VIEWS POUR LES CALCULS EN TEMPS RÉEL
# ===================================================================

class CalculAutomatiqueAPIView(InventaireMixin, View):
    """API pour les calculs automatiques d'inventaire"""
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Non authentifié'}, status=401)
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            periodes_data = data.get('periodes', {})
            
            total_vehicules = 0
            nombre_periodes = 0
            
            for periode_code, nombre_str in periodes_data.items():
                if nombre_str and nombre_str.strip():
                    try:
                        nombre = int(nombre_str)
                        if nombre > 0:
                            total_vehicules += nombre
                            nombre_periodes += 1
                    except ValueError:
                        continue
            
            moyenne_horaire = total_vehicules / nombre_periodes if nombre_periodes > 0 else 0
            estimation_24h = moyenne_horaire * 24
            
            from django.conf import settings
            config = getattr(settings, 'SUPPER_CONFIG', {})
            tarif = config.get('TARIF_VEHICULE_LEGER', 500)
            pourcentage_legers = config.get('POURCENTAGE_VEHICULES_LEGERS', 75)
            
            recette_potentielle = (estimation_24h * pourcentage_legers * tarif) / 100
            
            return JsonResponse({
                'success': True,
                'total_vehicules': total_vehicules,
                'nombre_periodes': nombre_periodes,
                'moyenne_horaire': round(moyenne_horaire, 2),
                'estimation_24h': round(estimation_24h, 2),
                'recette_potentielle': round(recette_potentielle, 2),
            })
            
        except Exception as e:
            logger.error(f"Erreur calcul automatique: {str(e)}")
            return JsonResponse({'error': 'Erreur de calcul'}, status=500)

# class VerificationJourAPIView(InventaireMixin, View):
#     """API pour vérifier le statut d'un jour"""
    
#     @method_decorator(require_http_methods(["GET"]))
#     def dispatch(self, *args, **kwargs):
#         return super().dispatch(*args, **kwargs)
    
#     def get(self, request):
#         """Vérifier si un jour est ouvert pour la saisie"""
#         date_str = request.GET.get('date')
        
#         if not date_str:
#             return JsonResponse({'error': 'Date requise'}, status=400)
        
#         try:
#             target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
#             # Vérifier la configuration
#             is_open = ConfigurationJour.est_jour_ouvert(target_date)
            
#             # Informations supplémentaires
#             try:
#                 config = ConfigurationJour.objects.get(date=target_date)
#                 config_info = {
#                     'statut': config.statut,
#                     'statut_display': config.get_statut_display(),
#                     'commentaire': config.commentaire,
#                     'cree_par': config.cree_par.nom_complet if config.cree_par else None,
#                 }
#             except ConfigurationJour.DoesNotExist:
#                 config_info = {
#                     'statut': 'ferme',
#                     'statut_display': 'Fermé par défaut',
#                     'commentaire': 'Jour non configuré',
#                     'cree_par': None,
#                 }
            
#             # Vérifier s'il y a déjà des données
#             poste = request.user.poste_affectation
#             has_inventaire = False
#             inventaire_id = None
            
#             if poste:
#                 try:
#                     inventaire = InventaireJournalier.objects.get(
#                         poste=poste,
#                         date=target_date
#                     )
#                     has_inventaire = True
#                     inventaire_id = inventaire.id
#                 except InventaireJournalier.DoesNotExist:
#                     pass
            
#             return JsonResponse({
#                 'success': True,
#                 'date': target_date.isoformat(),
#                 'is_open': is_open,
#                 'config': config_info,
#                 'has_inventaire': has_inventaire,
#                 'inventaire_id': inventaire_id,
#                 'can_edit': is_open and not (has_inventaire and InventaireJournalier.objects.filter(
#                     id=inventaire_id, verrouille=True
#                 ).exists()) if has_inventaire else is_open,
#             })
        
#         except ValueError:
#             return JsonResponse({'error': 'Format de date invalide'}, status=400)
#         except Exception as e:
#             logger.error(f"Erreur vérification jour: {str(e)}")
#             return JsonResponse({'error': 'Erreur serveur'}, status=500)


# ===================================================================
# REDIRECTIONS VERS L'ADMIN DJANGO
# ===================================================================

@login_required
def redirect_to_inventaires_admin(request):
    """Redirection vers la gestion des inventaires dans l'admin Django"""
    
    if not _check_admin_permission(request.user):
        messages.error(request, "Accès non autorisé à la gestion des inventaires.")
        return redirect('inventaire:inventaire_list')
    
    log_user_action(request.user, "Accès admin inventaires", "", request)
    messages.info(request, "Redirection vers la gestion des inventaires.")
    
    return redirect('/admin/inventaire/inventairejournalier/')


@login_required
def redirect_to_recettes_admin(request):
    """Redirection vers la gestion des recettes dans l'admin Django"""
    
    if not _check_admin_permission(request.user):
        messages.error(request, "Accès non autorisé à la gestion des recettes.")
        return redirect('inventaire:inventaire_list')
    
    log_user_action(request.user, "Accès admin recettes", "", request)
    messages.info(request, "Redirection vers la gestion des recettes.")
    
    return redirect('/admin/inventaire/recettejournaliere/')


@login_required
def redirect_to_config_jours_admin(request):
    """Redirection vers la configuration des jours dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la configuration des jours."))
        return redirect('inventaire:config_jour_list')
    
    _log_inventaire_action(request, "Accès admin configuration jours")
    messages.info(request, _("Redirection vers la configuration des jours."))
    
    return redirect('/admin/inventaire/configurationjour/')


@login_required
def redirect_to_statistiques_admin(request):
    """Redirection vers les statistiques dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé aux statistiques."))
        return redirect('inventaire:inventaire_list')
    
    _log_inventaire_action(request, "Accès admin statistiques")
    messages.info(request, _("Redirection vers les statistiques."))
    
    return redirect('/admin/inventaire/statistiquesperiodiques/')


@login_required
def redirect_to_edit_inventaire_admin(request, inventaire_id):
    """Redirection vers l'édition d'un inventaire spécifique dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à l'édition des inventaires."))
        return redirect('inventaire:inventaire_list')
    
    try:
        inventaire = InventaireJournalier.objects.get(id=inventaire_id)
        _log_inventaire_action(
            request, 
            "Édition inventaire admin", 
            f"Inventaire {inventaire.poste.nom} du {inventaire.date}"
        )
        messages.info(request, _(
            f"Redirection vers l'édition de l'inventaire {inventaire.poste.nom} du {inventaire.date}."
        ))
        
        return redirect(f'/admin/inventaire/inventairejournalier/{inventaire_id}/change/')
        
    except InventaireJournalier.DoesNotExist:
        messages.error(request, _("Inventaire non trouvé."))
        return redirect('/admin/inventaire/inventairejournalier/')


@login_required
def redirect_to_edit_recette_admin(request, recette_id):
    """Redirection vers l'édition d'une recette spécifique dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à l'édition des recettes."))
        return redirect('inventaire:inventaire_list')
    
    try:
        recette = RecetteJournaliere.objects.get(id=recette_id)
        _log_inventaire_action(
            request, 
            "Édition recette admin", 
            f"Recette {recette.poste.nom} du {recette.date}"
        )
        messages.info(request, _(
            f"Redirection vers l'édition de la recette {recette.poste.nom} du {recette.date}."
        ))
        
        return redirect(f'/admin/inventaire/recettejournaliere/{recette_id}/change/')
        
    except RecetteJournaliere.DoesNotExist:
        messages.error(request, _("Recette non trouvée."))
        return redirect('/admin/inventaire/recettejournaliere/')


@login_required
def redirect_to_add_inventaire_admin(request):
    """Redirection vers l'ajout d'inventaire dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la création d'inventaires."))
        return redirect('inventaire:inventaire_list')
    
    _log_inventaire_action(request, "Ajout inventaire admin")
    messages.info(request, _("Redirection vers l'ajout d'inventaire."))
    
    return redirect('/admin/inventaire/inventairejournalier/add/')


@login_required
def redirect_to_add_recette_admin(request):
    """Redirection vers l'ajout de recette dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la création de recettes."))
        return redirect('inventaire:inventaire_list')
    
    _log_inventaire_action(request, "Ajout recette admin")
    messages.info(request, _("Redirection vers l'ajout de recette."))
    
    return redirect('/admin/inventaire/recettejournaliere/add/')


@login_required
def redirect_to_add_config_jour_admin(request):
    """Redirection vers l'ajout de configuration de jour dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la configuration des jours."))
        return redirect('inventaire:config_jour_list')
    
    _log_inventaire_action(request, "Ajout configuration jour admin")
    messages.info(request, _("Redirection vers l'ajout de configuration de jour."))
    
    return redirect('/admin/inventaire/configurationjour/add/')


# ===================================================================
# API POUR INTÉGRATION AVEC ADMIN DJANGO ET DASHBOARD
# ===================================================================

@login_required
@require_http_methods(["GET"])
def inventaire_stats_api(request):
    """API pour les statistiques des inventaires"""
    
    if not _check_admin_permission(request.user):
        return JsonResponse({'error': 'Permission refusée'}, status=403)
    
    try:
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        stats = {
            'inventaires_today': InventaireJournalier.objects.filter(date=today).count(),
            'inventaires_week': InventaireJournalier.objects.filter(date__gte=week_ago).count(),
            'inventaires_month': InventaireJournalier.objects.filter(date__gte=month_ago).count(),
            'total_inventaires': InventaireJournalier.objects.count(),
        }
        
        return JsonResponse(stats)
        
    except Exception as e:
        logger.error(f"Erreur API inventaire stats: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)



@login_required
@require_http_methods(["GET"])
def recette_stats_api(request):
    """API pour statistiques des recettes"""
    user = request.user
    
    if not _check_admin_permission(user):
        return JsonResponse({'error': 'Permission refusée'}, status=403)
    
    try:
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Sum, Avg, Count
        
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Statistiques de base
        stats = {
            'recettes_today': RecetteJournaliere.objects.filter(date=today).count(),
            'recettes_week': RecetteJournaliere.objects.filter(date__gte=week_ago).count(),
            'recettes_month': RecetteJournaliere.objects.filter(date__gte=month_ago).count(),
            'total_recettes': RecetteJournaliere.objects.count(),
        }
        
        # Montants et taux
        week_data = RecetteJournaliere.objects.filter(date__gte=week_ago).aggregate(
            montant_total=Sum('montant_declare'),
            montant_potentiel=Sum('recette_potentielle'),
            taux_moyen=Avg('taux_deperdition'),
            nombre_jours_impertinents=Count('id', filter=Q(taux_deperdition__gte=0))
        )
        
        stats.update({
            'montant_total_week': float(week_data['montant_total'] or 0),
            'montant_potentiel_week': float(week_data['montant_potentiel'] or 0),
            'taux_moyen_week': float(week_data['taux_moyen'] or 0),
            'jours_impertinents_week': week_data['nombre_jours_impertinents'],
        })
        
        # Calcul écart
        if stats['montant_potentiel_week'] > 0:
            stats['ecart_week'] = stats['montant_total_week'] - stats['montant_potentiel_week']
            stats['pourcentage_ecart_week'] = (stats['ecart_week'] / stats['montant_potentiel_week']) * 100
        else:
            stats['ecart_week'] = 0
            stats['pourcentage_ecart_week'] = 0
        
        # Distribution par couleur d'alerte
        alerts_distribution = {
            'success': RecetteJournaliere.objects.filter(
                date__gte=week_ago, taux_deperdition__gt=-10
            ).count(),
            'warning': RecetteJournaliere.objects.filter(
                date__gte=week_ago, taux_deperdition__gte=-30, taux_deperdition__lte=-10
            ).count(),
            'danger': RecetteJournaliere.objects.filter(
                date__gte=week_ago, taux_deperdition__lt=-30
            ).count(),
        }
        
        stats['alerts_distribution'] = alerts_distribution
        
        return JsonResponse(stats)
        
    except Exception as e:
        logger.error(f"Erreur API recette stats: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)


@login_required
@require_http_methods(["GET"])
def check_day_status_api(request):
    """API pour vérifier le statut d'un jour"""
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Date requise'}, status=400)
    
    try:
        from datetime import datetime
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        try:
            config = ConfigurationJour.objects.get(date=target_date)
            status = {
                'date': target_date.isoformat(),
                'statut': config.statut,
                'statut_display': config.get_statut_display(),
                'configured': True,
                'cree_par': config.cree_par.nom_complet if config.cree_par else None,
                'commentaire': config.commentaire,
                'date_creation': config.date_creation.isoformat() if config.date_creation else None,
            }
        except ConfigurationJour.DoesNotExist:
            status = {
                'date': target_date.isoformat(),
                'statut': 'ferme',  # Par défaut fermé si pas configuré
                #'statut_display': 'Fermé - saisie verrouillée',
                'configured': False,
                'cree_par': None,
                'commentaire': 'Jour non configuré - fermé par défaut',
                'date_creation': None,
            }
        
        # Ajouter des informations sur les inventaires/recettes du jour
        inventaires_count = InventaireJournalier.objects.filter(date=target_date).count()
        recettes_count = RecetteJournaliere.objects.filter(date=target_date).count()
        
        # Détails par poste si demandé
        include_details = request.GET.get('include_details', '').lower() == 'true'
        details = {}
        
        if include_details:
            inventaires = InventaireJournalier.objects.filter(
                date=target_date
            ).select_related('poste', 'agent_saisie')
            
            details['inventaires'] = [
                {
                    'id': inv.id,
                    'poste_nom': inv.poste.nom,
                    'poste_code': inv.poste.code,
                    'total_vehicules': inv.total_vehicules,
                 #   'verrouille': inv.verrouille,
                   # 'valide': inv.valide,
                    'agent_saisie': inv.agent_saisie.nom_complet if inv.agent_saisie else None,
                }
                for inv in inventaires
            ]
            
            recettes = RecetteJournaliere.objects.filter(
                date=target_date
            ).select_related('poste', 'chef_poste')
            
            details['recettes'] = [
                {
                    'id': rec.id,
                    'poste_nom': rec.poste.nom,
                    'poste_code': rec.poste.code,
                    'montant_declare': float(rec.montant_declare),
                    'taux_deperdition': float(rec.taux_deperdition) if rec.taux_deperdition else None,
                    'couleur_alerte': rec.get_couleur_alerte(),
                    'chef_poste': rec.chef_poste.nom_complet if rec.chef_poste else None,
                }
                for rec in recettes
            ]
        
        status.update({
            'inventaires_count': inventaires_count,
            'recettes_count': recettes_count,
            'has_data': inventaires_count > 0 or recettes_count > 0,
            'details': details if include_details else None,
        })
        
        return JsonResponse(status)
        
    except ValueError:
        return JsonResponse({'error': 'Format de date invalide'}, status=400)
    except Exception as e:
        logger.error(f"Erreur API check day status: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)


# ===================================================================
# API ACTIONS RAPIDES POUR LE DASHBOARD
# ===================================================================

@login_required
def quick_action_api(request):
    """API pour les actions rapides"""
    
    if not _check_admin_permission(request.user):
        return JsonResponse({'error': 'Permission refusée'}, status=403)
    
    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        action = data.get('action')
        
        if action == 'mark_impertinent':
            date_str = data.get('date')
            commentaire = data.get('commentaire', '')
            
            if not date_str:
                return JsonResponse({'error': 'Date requise'}, status=400)
            
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            config, created = ConfigurationJour.objects.get_or_create(
                date=target_date,
                defaults={
                    'statut': StatutJour.IMPERTINENT,
                    'cree_par': request.user,
                    'commentaire': commentaire or f'Marqué impertinent par {request.user.nom_complet}'
                }
            )
            
            if not created:
                config.statut = StatutJour.IMPERTINENT
                config.commentaire = commentaire
                config.save()
            
            log_user_action(
                request.user,
                "Marquage jour impertinent",
                f"Date: {target_date}, Commentaire: {commentaire}",
                request
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Jour {target_date.strftime("%d/%m/%Y")} marqué comme impertinent'
            })
        
        else:
            return JsonResponse({'error': 'Action non reconnue'}, status=400)
            
    except Exception as e:
        logger.error(f"Erreur API quick action: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)


# ===================================================================
# VUES POUR RAPPORTS ET EXPORT
# ===================================================================

class RapportInventaireView(AdminRequiredMixin, View):
    """Vue pour générer des rapports d'inventaire"""
    
    def get(self, request):
        """Afficher la page de génération de rapports"""
        context = {
            'title': 'Génération de Rapports',
            'postes': Poste.objects.filter(is_active=True).order_by('nom'),
            'current_year': timezone.now().year,
            'years': range(timezone.now().year - 5, timezone.now().year + 1),
        }
        return render(request, 'inventaire/rapport_generation.html', context)
    
    def post(self, request):
        """Générer et télécharger un rapport"""
        try:
            # Récupération des paramètres
            type_rapport = request.POST.get('type_rapport')
            format_export = request.POST.get('format_export', 'excel')
            date_debut = request.POST.get('date_debut')
            date_fin = request.POST.get('date_fin')
            poste_ids = request.POST.getlist('postes')
            
            # Validation des dates
            if not date_debut or not date_fin:
                messages.error(request, _("Les dates de début et fin sont obligatoires."))
                return redirect('inventaire:rapport_generation')
            
            date_debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
            date_fin = datetime.strptime(date_fin, '%Y-%m-%d').date()
            
            if date_debut > date_fin:
                messages.error(request, _("La date de début ne peut pas être postérieure à la date de fin."))
                return redirect('inventaire:rapport_generation')
            
            # Construction de la requête base
            queryset = InventaireJournalier.objects.filter(
                date__gte=date_debut,
                date__lte=date_fin
            ).select_related('poste', 'agent_saisie')
            
            if poste_ids:
                queryset = queryset.filter(poste_id__in=poste_ids)
            
            # Génération selon le type de rapport
            if type_rapport == 'inventaires_detailles':
                return self._generer_rapport_inventaires_detailles(queryset, format_export)
            elif type_rapport == 'synthese_postes':
                return self._generer_rapport_synthese_postes(queryset, format_export)
            elif type_rapport == 'evolution_trafic':
                return self._generer_rapport_evolution_trafic(queryset, format_export)
            else:
                messages.error(request, _("Type de rapport non reconnu."))
                return redirect('inventaire:rapport_generation')
        
        except Exception as e:
            logger.error(f"Erreur génération rapport: {str(e)}")
            messages.error(request, _("Erreur lors de la génération du rapport."))
            return redirect('inventaire:rapport_generation')
    
    # def _generer_rapport_inventaires_detailles(self, queryset, format_export):
    #     """Générer un rapport détaillé des inventaires"""
    #     import io
    #     from django.http import HttpResponse
        
    #     if format_export == 'excel':
    #         try:
    #             import openpyxl
    #             from openpyxl.styles import Font, Alignment, PatternFill
                
    #             # Créer le workbook
    #             wb = openpyxl.Workbook()
    #             ws = wb.active
    #             ws.title = "Inventaires Détaillés"
                
    #             # En-têtes
    #             headers = [
    #                 'Date', 'Poste', 'Code Poste', 'Agent Saisie', 
    #                 'Total Véhicules', 'Périodes Saisies', 'Verrouillé', 
    #                 'Validé', 'Date Création'
    #             ]
                
    #             for col, header in enumerate(headers, 1):
    #                 cell = ws.cell(row=1, column=col, value=header)
    #                 cell.font = Font(bold=True)
    #                 cell.fill = PatternFill(start_color='CCCCCC', end_color='CCCCCC', fill_type='solid')
                
    #             # Données
    #             for row, inventaire in enumerate(queryset.order_by('date', 'poste__nom'), 2):
    #                 ws.cell(row=row, column=1, value=inventaire.date.strftime('%d/%m/%Y'))
    #                 ws.cell(row=row, column=2, value=inventaire.poste.nom)
    #                 ws.cell(row=row, column=3, value=inventaire.poste.code)
    #                 ws.cell(row=row, column=4, value=inventaire.agent_saisie.nom_complet if inventaire.agent_saisie else '')
    #                 ws.cell(row=row, column=5, value=inventaire.total_vehicules)
    #                 ws.cell(row=row, column=6, value=inventaire.nombre_periodes_saisies)
    #                 ws.cell(row=row, column=7, value='Oui' if inventaire.verrouille else 'Non')
    #                 ws.cell(row=row, column=8, value='Oui' if inventaire.valide else 'Non')
    #                 ws.cell(row=row, column=9, value=inventaire.date_creation.strftime('%d/%m/%Y %H:%M'))
                
    #             # Ajuster la largeur des colonnes
    #             for column in ws.columns:
    #                 max_length = 0
    #                 column_letter = column[0].column_letter
    #                 for cell in column:
    #                     try:
    #                         if len(str(cell.value)) > max_length:
    #                             max_length = len(str(cell.value))
    #                     except:
    #                         pass
    #                 adjusted_width = min(max_length + 2, 50)
    #                 ws.column_dimensions[column_letter].width = adjusted_width
                
    #             # Générer la réponse
    #             output = io.BytesIO()
    #             wb.save(output)
    #             output.seek(0)
                
    #             response = HttpResponse(
    #                 output.getvalue(),
    #                 content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    #             )
    #             response['Content-Disposition'] = 'attachment; filename="rapport_inventaires_detailles.xlsx"'
    #             return response
                
    #         except ImportError:
    #             # Fallback vers CSV si openpyxl n'est pas disponible
    #             format_export = 'csv'
        
    #     if format_export == 'csv':
    #         import csv
            
    #         response = HttpResponse(content_type='text/csv')
    #         response['Content-Disposition'] = 'attachment; filename="rapport_inventaires_detailles.csv"'
            
    #         writer = csv.writer(response)
    #         writer.writerow([
    #             'Date', 'Poste', 'Code Poste', 'Agent Saisie', 
    #             'Total Véhicules', 'Périodes Saisies', 'Verrouillé', 
    #             'Validé', 'Date Création'
    #         ])
            
    #         for inventaire in queryset.order_by('date', 'poste__nom'):
    #             writer.writerow([
    #                 inventaire.date.strftime('%d/%m/%Y'),
    #                 inventaire.poste.nom,
    #                 inventaire.poste.code,
    #                 inventaire.agent_saisie.nom_complet if inventaire.agent_saisie else '',
    #                 inventaire.total_vehicules,
    #                 inventaire.nombre_periodes_saisies,
    #                 'Oui' if inventaire.verrouille else 'Non',
    #                 'Oui' if inventaire.valide else 'Non',
    #                 inventaire.date_creation.strftime('%d/%m/%Y %H:%M')
    #             ])
            
    #         return response
    
    # def _generer_rapport_synthese_postes(self, queryset, format_export):
    #     """Générer un rapport de synthèse par poste"""
    #     from django.db.models import Sum, Avg, Count
        
    #     # Agrégation des données par poste
    #     synthese = queryset.values('poste__nom', 'poste__code').annotate(
    #         total_vehicules=Sum('total_vehicules'),
    #         nombre_inventaires=Count('id'),
    #         moyenne_vehicules=Avg('total_vehicules'),
    #         inventaires_verrouilles=Count('id', filter=Q(verrouille=True)),
    #         inventaires_valides=Count('id', filter=Q(valide=True))
    #     ).order_by('poste__nom')
        
    #     if format_export == 'excel':
    #         try:
    #             import openpyxl
    #             from openpyxl.styles import Font, Alignment, PatternFill
    #             import io
                
    #             wb = openpyxl.Workbook()
    #             ws = wb.active
    #             ws.title = "Synthèse par Poste"
                
    #             # En-têtes
    #             headers = [
    #                 'Poste', 'Code', 'Total Véhicules', 'Nb Inventaires',
    #                 'Moyenne Véhicules/Jour', 'Inventaires Verrouillés',
    #                 'Inventaires Validés', 'Taux Validation (%)'
    #             ]
                
    #             for col, header in enumerate(headers, 1):
    #                 cell = ws.cell(row=1, column=col, value=header)
    #                 cell.font = Font(bold=True)
    #                 cell.fill = PatternFill(start_color='CCCCCC', end_color='CCCCCC', fill_type='solid')
                
    #             # Données
    #             for row, data in enumerate(synthese, 2):
    #                 taux_validation = (data['inventaires_valides'] / data['nombre_inventaires'] * 100) if data['nombre_inventaires'] > 0 else 0
                    
    #                 ws.cell(row=row, column=1, value=data['poste__nom'])
    #                 ws.cell(row=row, column=2, value=data['poste__code'])
    #                 ws.cell(row=row, column=3, value=data['total_vehicules'] or 0)
    #                 ws.cell(row=row, column=4, value=data['nombre_inventaires'])
    #                 ws.cell(row=row, column=5, value=round(data['moyenne_vehicules'] or 0, 2))
    #                 ws.cell(row=row, column=6, value=data['inventaires_verrouilles'])
    #                 ws.cell(row=row, column=7, value=data['inventaires_valides'])
    #                 ws.cell(row=row, column=8, value=round(taux_validation, 2))
                
    #             # Ajuster les colonnes
    #             for column in ws.columns:
    #                 max_length = 0
    #                 column_letter = column[0].column_letter
    #                 for cell in column:
    #                     try:
    #                         if len(str(cell.value)) > max_length:
    #                             max_length = len(str(cell.value))
    #                     except:
    #                         pass
    #                 adjusted_width = min(max_length + 2, 50)
    #                 ws.column_dimensions[column_letter].width = adjusted_width
                
    #             output = io.BytesIO()
    #             wb.save(output)
    #             output.seek(0)
                
    #             response = HttpResponse(
    #                 output.getvalue(),
    #                 content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    #             )
    #             response['Content-Disposition'] = 'attachment; filename="rapport_synthese_postes.xlsx"'
    #             return response
                
    #         except ImportError:
    #             format_export = 'csv'
        
    #     if format_export == 'csv':
    #         import csv
            
    #         response = HttpResponse(content_type='text/csv')
    #         response['Content-Disposition'] = 'attachment; filename="rapport_synthese_postes.csv"'
            
    #         writer = csv.writer(response)
    #         writer.writerow([
    #             'Poste', 'Code', 'Total Véhicules', 'Nb Inventaires',
    #             'Moyenne Véhicules/Jour', 'Inventaires Verrouillés',
    #             'Inventaires Validés', 'Taux Validation (%)'
    #         ])
            
    #         for data in synthese:
    #             taux_validation = (data['inventaires_valides'] / data['nombre_inventaires'] * 100) if data['nombre_inventaires'] > 0 else 0
    #             writer.writerow([
    #                 data['poste__nom'],
    #                 data['poste__code'],
    #                 data['total_vehicules'] or 0,
    #                 data['nombre_inventaires'],
    #                 round(data['moyenne_vehicules'] or 0, 2),
    #                 data['inventaires_verrouilles'],
    #                 data['inventaires_valides'],
    #                 round(taux_validation, 2)
    #             ])
            
    #         return response
    
    # def _generer_rapport_evolution_trafic(self, queryset, format_export):
    #     """Générer un rapport d'évolution du trafic"""
    #     from django.db.models import Sum
    #     from collections import defaultdict
        
    #     # Agrégation par date
    #     evolution = queryset.values('date').annotate(
    #         total_vehicules=Sum('total_vehicules'),
    #         nombre_postes=Count('poste', distinct=True)
    #     ).order_by('date')
        
    #     if format_export == 'excel':
    #         try:
    #             import openpyxl
    #             from openpyxl.styles import Font, PatternFill
    #             from openpyxl.chart import LineChart, Reference
    #             import io
                
    #             wb = openpyxl.Workbook()
    #             ws = wb.active
    #             ws.title = "Evolution du Trafic"
                
    #             # En-têtes
    #             headers = ['Date', 'Total Véhicules', 'Nombre Postes', 'Moyenne par Poste']
                
    #             for col, header in enumerate(headers, 1):
    #                 cell = ws.cell(row=1, column=col, value=header)
    #                 cell.font = Font(bold=True)
    #                 cell.fill = PatternFill(start_color='CCCCCC', end_color='CCCCCC', fill_type='solid')
                
    #             # Données
    #             for row, data in enumerate(evolution, 2):
    #                 moyenne_poste = (data['total_vehicules'] / data['nombre_postes']) if data['nombre_postes'] > 0 else 0
                    
    #                 ws.cell(row=row, column=1, value=data['date'].strftime('%d/%m/%Y'))
    #                 ws.cell(row=row, column=2, value=data['total_vehicules'] or 0)
    #                 ws.cell(row=row, column=3, value=data['nombre_postes'])
    #                 ws.cell(row=row, column=4, value=round(moyenne_poste, 2))
                
    #             # Ajouter un graphique si possible
    #             if len(evolution) > 1:
    #                 chart = LineChart()
    #                 chart.title = "Evolution du trafic"
    #                 chart.y_axis.title = 'Nombre de véhicules'
    #                 chart.x_axis.title = 'Date'
                    
    #                 data_ref = Reference(ws, min_col=2, min_row=1, max_col=2, max_row=len(evolution) + 1)
    #                 chart.add_data(data_ref, titles_from_data=True)
                    
    #                 ws.add_chart(chart, "F5")
                
    #             # Ajuster les colonnes
    #             for column in ws.columns:
    #                 max_length = 0
    #                 column_letter = column[0].column_letter
    #                 for cell in column:
    #                     try:
    #                         if len(str(cell.value)) > max_length:
    #                             max_length = len(str(cell.value))
    #                     except:
    #                         pass
    #                 adjusted_width = min(max_length + 2, 50)
    #                 ws.column_dimensions[column_letter].width = adjusted_width
                
    #             output = io.BytesIO()
    #             wb.save(output)
    #             output.seek(0)
                
    #             response = HttpResponse(
    #                 output.getvalue(),
    #                 content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    #             )
    #             response['Content-Disposition'] = 'attachment; filename="rapport_evolution_trafic.xlsx"'
    #             return response
                
    #         except ImportError:
    #             format_export = 'csv'
        
    #     if format_export == 'csv':
    #         import csv
            
    #         response = HttpResponse(content_type='text/csv')
    #         response['Content-Disposition'] = 'attachment; filename="rapport_evolution_trafic.csv"'
            
    #         writer = csv.writer(response)
    #         writer.writerow(['Date', 'Total Véhicules', 'Nombre Postes', 'Moyenne par Poste'])
            
    #         for data in evolution:
    #             moyenne_poste = (data['total_vehicules'] / data['nombre_postes']) if data['nombre_postes'] > 0 else 0
    #             writer.writerow([
    #                 data['date'].strftime('%d/%m/%Y'),
    #                 data['total_vehicules'] or 0,
    #                 data['nombre_postes'],
    #                 round(moyenne_poste, 2)
    #             ])
            
    #         return response


# ===================================================================
# VUES D'AIDE ET DOCUMENTATION INVENTAIRE
# ===================================================================

@login_required
def inventaire_admin_help_view(request):
    """Vue d'aide pour l'utilisation de l'admin Django - module inventaire"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé."))
        return redirect('inventaire:inventaire_list')
    
    context = {
        'title': 'Aide - Administration Inventaires',
        'user_permissions': {
            'can_manage_inventaires': True,
            'can_manage_recettes': True,
            'can_config_jours': True,
            'can_view_statistics': True,
        },
        'help_sections': [
            {
                'title': 'Gestion des Inventaires',
                'description': 'Créer, modifier et valider les inventaires journaliers',
                'url': '/admin/inventaire/inventairejournalier/',
                'features': [
                    'Saisie par période horaire (8h-18h)',
                    'Calculs automatiques des totaux',
                    'Verrouillage et validation par responsable',
                    'Export des données en CSV/Excel',
                    'Historique complet des modifications'
                ]
            },
            {
                'title': 'Gestion des Recettes',
                'description': 'Suivi des recettes déclarées et calcul des taux de déperdition',
                'url': '/admin/inventaire/recettejournaliere/',
                'features': [
                    'Saisie des montants déclarés par les chefs de poste',
                    'Calcul automatique des taux de déperdition',
                    'Alertes visuelles par code couleur',
                    'Détection automatique des journées impertinentes',
                    'Rapports consolidés par période'
                ]
            },
            {
                'title': 'Configuration des Jours',
                'description': 'Gérer les jours ouverts/fermés pour la saisie',
                'url': '/admin/inventaire/configurationjour/',
                'features': [
                    'Ouverture/fermeture des jours de saisie',
                    'Marquage des jours impertinents',
                    'Commentaires et historique des modifications',
                    'Contrôle granulaire des accès',
                    'Planification avancée des périodes'
                ]
            },
            {
                'title': 'Statistiques et Rapports',
                'description': 'Consultation des statistiques consolidées',
                'url': '/admin/inventaire/statistiquesperiodiques/',
                'features': [
                    'Statistiques hebdomadaires, mensuelles, trimestrielles',
                    'Graphiques de tendances et évolutions',
                    'Comparaisons inter-postes',
                    'Export de rapports détaillés',
                    'Tableaux de bord personnalisés'
                ]
            }
        ],
        'quick_actions': [
            {
                'title': 'Ouvrir Jour Actuel',
                'description': 'Ouvrir le jour actuel pour la saisie',
                'action': 'open_today',
                'icon': 'fas fa-calendar-plus',
                'class': 'btn-success'
            },
            {
                'title': 'Consulter Inventaires',
                'description': 'Voir tous les inventaires récents',
                'url': '/admin/inventaire/inventairejournalier/',
                'icon': 'fas fa-list',
                'class': 'btn-primary'
            },
            {
                'title': 'Gérer Recettes',
                'description': 'Consulter et modifier les recettes',
                'url': '/admin/inventaire/recettejournaliere/',
                'icon': 'fas fa-euro-sign',
                'class': 'btn-warning'
            }
        ]
    }
    
    return render(request, 'inventaire/admin_help.html', context)


# ===================================================================
# DASHBOARD ET WIDGETS INVENTAIRE
# ===================================================================

@login_required
def inventaire_dashboard_widget(request):
    """Widget dashboard pour les inventaires"""
    if not request.user.peut_gerer_inventaire:
        return JsonResponse({'error': 'Permission refusée'}, status=403)
    
    try:
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        # Statistiques rapides
        stats = {
            'inventaires_today': InventaireJournalier.objects.filter(date=today).count(),
            'inventaires_week': InventaireJournalier.objects.filter(date__gte=week_ago).count(),
            # 'inventaires_en_attente': InventaireJournalier.objects.filter(
            #     verrouille=False, date__lte=today
            # ).count(),
            'postes_actifs_today': InventaireJournalier.objects.filter(
                date=today
            ).values('poste').distinct().count(),
        }
        
        # Derniers inventaires pour l'utilisateur
        if request.user.acces_tous_postes or _check_admin_permission(request.user):
            derniers_inventaires = InventaireJournalier.objects.select_related(
                'poste', 'agent_saisie'
            ).order_by('-date_creation')[:5]
        else:
            derniers_inventaires = InventaireJournalier.objects.filter(
                poste=request.user.poste_affectation
            ).select_related('poste', 'agent_saisie').order_by('-date_creation')[:5]
        
        inventaires_data = []
        for inv in derniers_inventaires:
            inventaires_data.append({
                'id': inv.id,
                'date': inv.date.strftime('%d/%m/%Y'),
                'poste': inv.poste.nom,
                'total_vehicules': inv.total_vehicules,
              #  'verrouille': inv.verrouille,
               # 'valide': inv.valide,
                'agent': inv.agent_saisie.nom_complet if inv.agent_saisie else 'Non défini',
                'url': f'/inventaire/{inv.id}/'
            })
        
        # Actions rapides disponibles
        actions_rapides = []
        
        if _check_admin_permission(request.user):
            actions_rapides.extend([
                {
                    'title': 'Ouvrir Aujourd\'hui',
                    'action': 'open_today',
                    'icon': 'fas fa-calendar-plus',
                    'class': 'btn-success btn-sm'
                },
                {
                    'title': 'Admin Inventaires',
                    'url': '/admin/inventaire/inventairejournalier/',
                    'icon': 'fas fa-cogs',
                    'class': 'btn-primary btn-sm'
                }
            ])
        
        if request.user.poste_affectation:
            actions_rapides.append({
                'title': 'Nouvelle Saisie',
                'url': f'/inventaire/saisie/{request.user.poste_affectation.id}/',
                'icon': 'fas fa-plus',
                'class': 'btn-info btn-sm'
            })
        
        response_data = {
            'stats': stats,
            'derniers_inventaires': inventaires_data,
            'actions_rapides': actions_rapides,
            'can_admin': _check_admin_permission(request.user),
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Erreur widget dashboard inventaire: {str(e)}")
        return JsonResponse({'error': 'Erreur serveur'}, status=500)


# ===================================================================
# GESTION DES ERREURS DE REDIRECTION INVENTAIRE
# ===================================================================

@login_required
def inventaire_redirect_error_handler(request, error_type='permission'):
    """Gestionnaire d'erreurs pour les redirections inventaire"""
    user = request.user
    
    if error_type == 'permission':
        messages.error(request, _(
            "Vous n'avez pas les permissions nécessaires pour accéder à cette section inventaire. "
            "Contactez un administrateur si vous pensez que c'est une erreur."
        ))
        
        # Journaliser la tentative d'accès non autorisée
        try:
            JournalAudit.objects.create(
                utilisateur=user,
                action="ACCÈS REFUSÉ - Redirection admin inventaire",
                details=f"Tentative d'accès non autorisée depuis {request.META.get('HTTP_REFERER', 'URL inconnue')}",
                adresse_ip=request.META.get('REMOTE_ADDR'),
                url_acces=request.path,
                methode_http=request.method,
                succes=False
            )
        except Exception as e:
            logger.error(f"Erreur journalisation tentative accès inventaire: {str(e)}")
    
    elif error_type == 'not_found':
        messages.error(request, _("L'inventaire ou la recette demandée n'a pas été trouvée."))
    
    elif error_type == 'locked':
        messages.warning(request, _("Cette ressource est verrouillée et ne peut plus être modifiée."))
    
    elif error_type == 'closed_day':
        messages.warning(request, _("Ce jour est fermé pour la saisie."))
    
    else:
        messages.error(request, _("Une erreur est survenue lors de la redirection."))
    
    # Rediriger vers la liste des inventaires
    return redirect('inventaire:inventaire_list')


# ===================================================================
# VUES POUR LA SAUVEGARDE ET RESTAURATION
# ===================================================================

@login_required
@require_http_methods(["POST"])
def backup_inventaires_api(request):
    """API pour sauvegarder les données d'inventaire"""
    user = request.user
    
    if not _check_admin_permission(user):
        return JsonResponse({'error': 'Permission refusée'}, status=403)
    
    try:
        import json
        from django.core import serializers
        from datetime import datetime
        
        # Récupération des paramètres
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        date_debut = data.get('date_debut')
        date_fin = data.get('date_fin')
        
        if not date_debut or not date_fin:
            return JsonResponse({'error': 'Dates requises'}, status=400)
        
        date_debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin = datetime.strptime(date_fin, '%Y-%m-%d').date()
        
        # Collecte des données
        inventaires = InventaireJournalier.objects.filter(
            date__gte=date_debut, date__lte=date_fin
        ).prefetch_related('details_periodes')
        
        recettes = RecetteJournaliere.objects.filter(
            date__gte=date_debut, date__lte=date_fin
        )
        
        configs = ConfigurationJour.objects.filter(
            date__gte=date_debut, date__lte=date_fin
        )
        
        # Sérialisation
        backup_data = {
            'metadata': {
                'date_creation': timezone.now().isoformat(),
                'cree_par': user.username,
                'date_debut': date_debut.isoformat(),
                'date_fin': date_fin.isoformat(),
                'version': '1.0'
            },
            'inventaires': json.loads(serializers.serialize('json', inventaires)),
            'details_periodes': [],
            'recettes': json.loads(serializers.serialize('json', recettes)),
            'configurations': json.loads(serializers.serialize('json', configs))
        }
        
        # Ajouter les détails des périodes
        for inventaire in inventaires:
            details = DetailInventairePeriode.objects.filter(inventaire=inventaire)
            backup_data['details_periodes'].extend(
                json.loads(serializers.serialize('json', details))
            )
        
        # Journaliser l'action
        _log_inventaire_action(
            request,
            "Sauvegarde données inventaire",
            f"Période: {date_debut} à {date_fin}, {len(inventaires)} inventaires"
        )
        
        # Retourner les données
        response = HttpResponse(
            json.dumps(backup_data, indent=2, ensure_ascii=False),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="backup_inventaires_{date_debut}_{date_fin}.json"'
        
        return response
        
    except Exception as e:
        logger.error(f"Erreur sauvegarde inventaires: {str(e)}")
        return JsonResponse({'error': 'Erreur lors de la sauvegarde'}, status=500)


# ===================================================================
# VUES DE MAINTENANCE ET DIAGNOSTIC
# ===================================================================

# @login_required
# def diagnostic_inventaires_view(request):
#     """Vue de diagnostic pour les inventaires"""
#     user = request.user
    
#     if not _check_admin_permission(user):
#         messages.error(request, _("Accès non autorisé au diagnostic."))
#         return redirect('inventaire:inventaire_list')
    
#     try:
#         # Statistiques de santé
#         today = timezone.now().date()
#         week_ago = today - timedelta(days=7)
#         month_ago = today - timedelta(days=30)
        
#         # Détection des anomalies
#         anomalies = []
        
#         # Inventaires sans détails
#         inventaires_vides = InventaireJournalier.objects.filter(
#             details_periodes__isnull=True
#         ).count()
#         if inventaires_vides > 0:
#             anomalies.append({
#                 'type': 'warning',
#                 'message': f'{inventaires_vides} inventaires sans détails de périodes',
#                 'action': 'Vérifier les inventaires incomplets'
#             })
        
#         # Inventaires non verrouillés anciens
#         inventaires_anciens = InventaireJournalier.objects.filter(
#             date__lt=week_ago, verrouille=False
#         ).count()
#         if inventaires_anciens > 0:
#             anomalies.append({
#                 'type': 'info',
#                 'message': f'{inventaires_anciens} inventaires de plus de 7 jours non verrouillés',
#                 'action': 'Vérifier les inventaires en attente'
#             })
        
#         # Recettes sans inventaire associé
#         recettes_orphelines = RecetteJournaliere.objects.exclude(
#             poste__in=InventaireJournalier.objects.filter(
#                 date=models.OuterRef('date')
#             ).values('poste')
#         ).count()
#         if recettes_orphelines > 0:
#             anomalies.append({
#                 'type': 'error',
#                 'message': f'{recettes_orphelines} recettes sans inventaire associé',
#                 'action': 'Créer les inventaires manquants'
#             })
        
#         # Jours sans configuration
#         jours_non_configures = 0
#         for i in range(7):
#             day = today - timedelta(days=i)
#             if not ConfigurationJour.objects.filter(date=day).exists():
#                 jours_non_configures += 1
        
#         if jours_non_configures > 0:
#             anomalies.append({
#                 'type': 'warning',
#                 'message': f'{jours_non_configures} jours récents sans configuration',
#                 'action': 'Configurer les jours manquants'
#             })
        
#         # Statistiques de performance
#         stats_performance = {
#             'inventaires_total': InventaireJournalier.objects.count(),
#             'inventaires_month': InventaireJournalier.objects.filter(date__gte=month_ago).count(),
#             'taux_verrouillage': 0,
#             'taux_validation': 0,
#             'postes_actifs': Poste.objects.filter(is_active=True).count(),
#             'derniere_saisie': None
#         }
        
#         # Calculs des taux
#         inventaires_month = InventaireJournalier.objects.filter(date__gte=month_ago)
#         if inventaires_month.exists():
#             total_month = inventaires_month.count()
#             verrouilles_month = inventaires_month.filter(verrouille=True).count()
#             valides_month = inventaires_month.filter(valide=True).count()
            
#             stats_performance['taux_verrouillage'] = round((verrouilles_month / total_month) * 100, 2)
#             stats_performance['taux_validation'] = round((valides_month / total_month) * 100, 2)
        
#         # Dernière saisie
#         derniere_saisie = InventaireJournalier.objects.order_by('-date_creation').first()
#         if derniere_saisie:
#             stats_performance['derniere_saisie'] = {
#                 'date': derniere_saisie.date_creation.strftime('%d/%m/%Y %H:%M'),
#                 'poste': derniere_saisie.poste.nom,
#                 'agent': derniere_saisie.agent_saisie.nom_complet if derniere_saisie.agent_saisie else 'Non défini'
#             }
        
#         context = {
#             'title': 'Diagnostic Inventaires',
#             'anomalies': anomalies,
#             'stats_performance': stats_performance,
#             'diagnostic_date': timezone.now().strftime('%d/%m/%Y %H:%M'),
#         }
        
#         return render(request, 'inventaire/diagnostic.html', context)
        
    except Exception as e:
        logger.error(f"Erreur diagnostic inventaires: {str(e)}")
        messages.error(request, _("Erreur lors du diagnostic."))
        return redirect('inventaire:inventaire_list')

import calendar
from datetime import date

def is_admin(user):
    """Vérifier si l'utilisateur est admin"""
    return user.is_authenticated and user.is_superuser

@login_required
@user_passes_test(is_admin)
def gerer_jours_inventaire(request, inventaire_id):
    """Vue pour gérer les jours d'activation d'un inventaire mensuel"""
    
    # Pour l'instant, utiliser l'inventaire journalier
    # (Plus tard, remplacer par InventaireMensuel quand le modèle sera créé)
    
    # Récupérer le mois et l'année depuis l'inventaire
    # Pour le test, on va utiliser le mois et année courants
    today = date.today()
    mois = today.month
    annee = today.year
    
    # Obtenir le calendrier du mois
    cal = calendar.monthcalendar(annee, mois)
    
    # Obtenir les jours actuellement ouverts
    jours_actifs = []
    nb_jours = calendar.monthrange(annee, mois)[1]
    
    for jour in range(1, nb_jours + 1):
        date_jour = date(annee, mois, jour)
        config = ConfigurationJour.objects.filter(date=date_jour).first()
        if config and config.statut == 'ouvert':
            jours_actifs.append(jour)
    
    if request.method == 'POST':
        # Traiter l'activation/désactivation des jours
        jours_a_activer = request.POST.getlist('jours_actifs')
        
        for jour in range(1, nb_jours + 1):
            date_jour = date(annee, mois, jour)
            
            if str(jour) in jours_a_activer:
                # Activer le jour
                config, created = ConfigurationJour.objects.get_or_create(
                    date=date_jour,
                    defaults={
                        'statut': 'ouvert',
                        'cree_par': request.user,
                        'commentaire': f'Activé pour inventaire du {mois}/{annee}'
                    }
                )
                if not created and config.statut != 'ouvert':
                    config.statut = 'ouvert'
                    config.save()
            else:
                # Désactiver le jour
                config, created = ConfigurationJour.objects.get_or_create(
                    date=date_jour,
                    defaults={
                        'statut': 'ferme',
                        'cree_par': request.user,
                        'commentaire': f'Fermé pour inventaire du {mois}/{annee}'
                    }
                )
                if not created and config.statut != 'ferme':
                    config.statut = 'ferme'
                    config.save()
        
        messages.success(request, f"Les jours du mois {mois}/{annee} ont été mis à jour.")
        return redirect('admin:inventaire_inventairejournalier_changelist')
    
    # Créer un objet fictif pour le template
    inventaire = {
        'id': inventaire_id,
        'titre': f'Inventaire {calendar.month_name[mois]} {annee}',
        'mois': mois,
        'annee': annee,
        'description': 'Gestion des jours d\'activation pour la saisie',
        'get_nombre_postes': lambda: 'Tous les postes'
    }
    
    context = {
        'inventaire': inventaire,
        'calendrier': cal,
        'jours_actifs': jours_actifs,
        'title': f'Gérer les jours - {calendar.month_name[mois]} {annee}',
    }
    
    return render(request, 'admin/inventaire/gerer_jours.html', context)


# # ===================================================================
# # VUES FINALES ET UTILS
# # ===================================================================

# @login_required
# def inventaire_health_check_api(request):
#     """API de vérification de santé du module inventaire"""
#     if not _check_admin_permission(request.user):
#         return JsonResponse({'error': 'Permission refusée'}, status=403)
    
#     try:
#         health_status = {
#             'status': 'ok',
#             'timestamp': timezone.now().isoformat(),
#             'checks': {}
#         }
        
#         # Vérification base de données
#         try:
#             InventaireJournalier.objects.count()
#             health_status['checks']['database'] = 'ok'
#         except Exception as e:
#             health_status['checks']['database'] = f'error: {str(e)}'
#             health_status['status'] = 'error'
        
#         # Vérification des permissions
#         try:
#             request.user.peut_gerer_inventaire
#             health_status['checks']['permissions'] = 'ok'
#         except Exception as e:
#             health_status['checks']['permissions'] = f'error: {str(e)}'
#             health_status['status'] = 'warning'
        
#         # Vérification des modèles
#         try:
#             from .models import PeriodeHoraire
#             health_status['checks']['models'] = 'ok'
#         except Exception as e:
#             health_status['checks']['models'] = f'error: {str(e)}'
#             health_status['status'] = 'error'

@login_required
@require_permission('peut_gerer_inventaire')
def liste_postes_inventaires(request):
    """
    Vue pour afficher la liste des postes avec leurs inventaires du mois en cours
    Permet de voir l'association postes-agents-inventaires
    """
    # Période actuelle (mois en cours)
    today = date.today()
    debut_mois = date(today.year, today.month, 1)
    
    # Récupérer les postes accessibles selon les permissions
    postes_accessibles = request.user.get_postes_accessibles()
    
    # Construire les données pour chaque poste
    postes_data = []
    
    for poste in postes_accessibles:
        # Inventaires du mois pour ce poste
        inventaires_mois = InventaireJournalier.objects.filter(
            poste=poste,
            date__gte=debut_mois,
            date__lte=today
        ).select_related('agent_saisie').order_by('-date')
        
        # Agent principal (le plus récent ou d'affectation)
        agent_principal = None
        if inventaires_mois.exists():
            agent_principal = inventaires_mois.first().agent_saisie
        elif poste.agents_affectes.filter(is_active=True).exists():
            agent_principal = poste.agents_affectes.filter(is_active=True).first()
        
        # Statistiques du mois
        nb_inventaires = inventaires_mois.count()
        nb_jours_travailles = inventaires_mois.filter(verrouille=True).count()
        
        # Dernière activité
        derniere_activite = inventaires_mois.first().date if inventaires_mois.exists() else None
        
        # Changements d'agents dans le mois
        agents_differents = inventaires_mois.values_list('agent_saisie__nom_complet', flat=True).distinct()
        changements_agents = len(agents_differents) > 1
        
        postes_data.append({
            'poste': poste,
            'agent_principal': agent_principal,
            'nb_inventaires': nb_inventaires,
            'nb_jours_travailles': nb_jours_travailles,
            'derniere_activite': derniere_activite,
            'changements_agents': changements_agents,
            'agents_differents': list(agents_differents),
            'inventaires_recents': inventaires_mois[:5]  # 5 plus récents
        })
    
    # Statistiques globales
    stats_globales = {
        'total_postes': postes_accessibles.count(),
        'postes_actifs': len([p for p in postes_data if p['nb_inventaires'] > 0]),
        'total_inventaires': sum(p['nb_inventaires'] for p in postes_data),
        'postes_avec_changements': len([p for p in postes_data if p['changements_agents']])
    }
    
    context = {
        'postes_data': postes_data,
        'stats_globales': stats_globales,
        'mois_actuel': debut_mois,
        'today': today,
        'title': 'Association Postes-Inventaires-Agents'
    }
    
    return render(request, 'inventaire/liste_postes_inventaires.html', context)


@login_required
@require_permission('peut_gerer_inventaire')
def detail_poste_inventaires(request, poste_id):
    """
    Vue détaillée pour un poste spécifique avec historique complet
    """
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Vérifier l'accès au poste
    if not request.user.peut_acceder_poste(poste):
        messages.error(request, "Vous n'avez pas accès aux données de ce poste.")
        return redirect('liste_postes_inventaires')
    
    # Période d'affichage (3 derniers mois par défaut)
    today = date.today()
    debut_periode = date(today.year, today.month - 2, 1) if today.month > 2 else date(today.year - 1, today.month + 10, 1)
    
    # Inventaires de la période
    inventaires = InventaireJournalier.objects.filter(
        poste=poste,
        date__gte=debut_periode
    ).select_related('agent_saisie', 'valide_par').order_by('-date')
    
    # Agents ayant travaillé sur ce poste
    agents_historique = InventaireJournalier.objects.filter(
        poste=poste,
        date__gte=debut_periode
    ).values(
        'agent_saisie__nom_complet',
        'agent_saisie__username'
    ).annotate(
        nb_inventaires=Count('id'),
        derniere_saisie=models.Max('date')
    ).order_by('-derniere_saisie')
    
    # Changements d'agents par mois
    changements_mensuels = []
    for mois in range(3):  # 3 derniers mois
        date_mois = date(today.year, today.month - mois, 1) if today.month > mois else date(today.year - 1, today.month - mois + 12, 1)
        fin_mois = date(date_mois.year, date_mois.month + 1, 1) - timedelta(days=1) if date_mois.month < 12 else date(date_mois.year, 12, 31)
        
        agents_mois = InventaireJournalier.objects.filter(
            poste=poste,
            date__gte=date_mois,
            date__lte=fin_mois
        ).values_list('agent_saisie__nom_complet', flat=True).distinct()
        
        changements_mensuels.append({
            'mois': date_mois,
            'agents': list(agents_mois),
            'nb_changements': len(agents_mois)
        })
    
    context = {
        'poste': poste,
        'inventaires': inventaires,
        'agents_historique': agents_historique,
        'changements_mensuels': changements_mensuels,
        'debut_periode': debut_periode,
        'today': today,
        'title': f'Détail inventaires - {poste.nom}'
    }
    
    return render(request, 'inventaire/detail_poste_inventaires.html', context)


@login_required
@require_permission('peut_gerer_inventaire')
def changer_agent_poste(request, poste_id):
    """
    Vue pour changer l'agent d'un poste
    """
    poste = get_object_or_404(Poste, id=poste_id)
    
    if not request.user.peut_acceder_poste(poste):
        messages.error(request, "Vous n'avez pas accès à ce poste.")
        return redirect('liste_postes_inventaires')
    
    if request.method == 'POST':
        nouvel_agent_id = request.POST.get('agent_id')
        commentaire = request.POST.get('commentaire', '')
        
        if nouvel_agent_id:
            try:
                nouvel_agent = UtilisateurSUPPER.objects.get(
                    id=nouvel_agent_id,
                    habilitation='agent_inventaire',
                    is_active=True
                )
                
                # Changer l'affectation
                ancien_agent = poste.agents_affectes.first()
                poste.agents_affectes.clear()
                nouvel_agent.poste_affectation = poste
                nouvel_agent.save()
                
                # Journaliser le changement
                log_user_action(
                    request.user,
                    "Changement agent poste",
                    f"Poste: {poste.nom} | Ancien: {ancien_agent.nom_complet if ancien_agent else 'Aucun'} "
                    f"| Nouveau: {nouvel_agent.nom_complet} | Commentaire: {commentaire}",
                    request
                )
                
                messages.success(request, f"Agent {nouvel_agent.nom_complet} affecté au poste {poste.nom}")
                return redirect('detail_poste_inventaires', poste_id=poste.id)
                
            except UtilisateurSUPPER.DoesNotExist:
                messages.error(request, "Agent sélectionné invalide.")
    
    # Agents inventaire disponibles
    agents_disponibles = UtilisateurSUPPER.objects.filter(
        habilitation='agent_inventaire',
        is_active=True
    ).exclude(
        poste_affectation=poste
    )
    
    context = {
        'poste': poste,
        'agents_disponibles': agents_disponibles,
        'title': f'Changer agent - {poste.nom}'
    }
    
    return render(request, 'inventaire/changer_agent_poste.html', context)

@login_required
@require_http_methods(["POST"])
@csrf_exempt  # Pour les appels AJAX depuis le dashboard
def action_ouvrir_semaine(request):
    """Action rapide : Ouvrir tous les jours de la semaine courante"""
    
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'success': False, 'message': 'Permission refusée'}, status=403)
    
    try:
        # Obtenir les jours de la semaine courante (lundi à vendredi)
        today = date.today()
        start_week = today - timedelta(days=today.weekday())  # Lundi
        
        jours_ouverts = 0
        
        for i in range(5):  # Lundi à vendredi
            jour = start_week + timedelta(days=i)
            
            # Ouvrir le jour globalement
            config = ConfigurationJour.ouvrir_jour_global(
                date=jour,
                admin_user=request.user,
                commentaire=f"Ouverture automatique semaine du {start_week.strftime('%d/%m/%Y')}",
                permet_inventaire=True,
                permet_recette=True
            )
            
            jours_ouverts += 1
        
        # Journaliser l'action
        _log_inventaire_action(
            request,
            "Ouverture semaine courante",
            f"Semaine du {start_week.strftime('%d/%m/%Y')} - {jours_ouverts} jours ouverts"
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Semaine courante ouverte avec succès ({jours_ouverts} jours ouvrables)'
        })
        
    except Exception as e:
        logger.error(f"Erreur ouverture semaine: {str(e)}")
        return JsonResponse({
            'success': False, 
            'message': f'Erreur lors de l\'ouverture de la semaine: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def action_fermer_anciens(request):
    """Action rapide : Fermer tous les jours antérieurs à aujourd'hui"""
    
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'success': False, 'message': 'Permission refusée'}, status=403)
    
    try:
        today = date.today()
        
        # Fermer tous les jours ouverts antérieurs à aujourd'hui
        configurations_anciennes = ConfigurationJour.objects.filter(
            date__lt=today,
            statut=StatutJour.OUVERT
        )
        
        jours_fermes = 0
        
        for config in configurations_anciennes:
            config.statut = StatutJour.FERME
            config.permet_saisie_inventaire = False
            config.permet_saisie_recette = False
            config.commentaire = f"Fermé automatiquement le {today.strftime('%d/%m/%Y')}"
            config.save()
            jours_fermes += 1
        
        # Journaliser l'action
        _log_inventaire_action(
            request,
            "Fermeture jours anciens",
            f"{jours_fermes} jours antérieurs à {today.strftime('%d/%m/%Y')} fermés"
        )
        
        return JsonResponse({
            'success': True,
            'message': f'{jours_fermes} jour(s) ancien(s) fermé(s) avec succès'
        })
        
    except Exception as e:
        logger.error(f"Erreur fermeture anciens: {str(e)}")
        return JsonResponse({
            'success': False, 
            'message': f'Erreur lors de la fermeture: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def action_marquer_impertinent(request):
    """Action rapide : Marquer un jour comme impertinent"""
    
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'success': False, 'message': 'Permission refusée'}, status=403)
    
    try:
        # Récupérer les données de la requête
        if request.content_type == 'application/json':
            data = json.loads(request.body)
        else:
            data = request.POST
        
        date_str = data.get('date')
        commentaire = data.get('commentaire', '')
        poste_id = data.get('poste_id')
        
        if not date_str:
            return JsonResponse({
                'success': False, 
                'message': 'Date requise'
            }, status=400)
        
        # Valider et parser la date
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({
                'success': False, 
                'message': 'Format de date invalide (YYYY-MM-DD requis)'
            }, status=400)
        
        # Déterminer le poste
        poste = None
        if poste_id:
            try:
                poste = Poste.objects.get(id=poste_id)
            except Poste.DoesNotExist:
                return JsonResponse({
                    'success': False, 
                    'message': 'Poste non trouvé'
                }, status=404)
        
        # Marquer comme impertinent
        config = ConfigurationJour.marquer_impertinent(
            date=target_date,
            admin_user=request.user,
            poste=poste,
            commentaire=commentaire or f"Marqué impertinent par {request.user.nom_complet}"
        )
        
        # Journaliser l'action
        poste_str = f" pour {poste.nom}" if poste else " (global)"
        _log_inventaire_action(
            request,
            "Marquage jour impertinent",
            f"Date: {target_date.strftime('%d/%m/%Y')}{poste_str} - Commentaire: {commentaire}"
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Jour {target_date.strftime("%d/%m/%Y")}{poste_str} marqué comme impertinent'
        })
        
    except Exception as e:
        logger.error(f"Erreur marquage impertinent: {str(e)}")
        return JsonResponse({
            'success': False, 
            'message': f'Erreur lors du marquage: {str(e)}'
        }, status=500)


@login_required
def redirect_to_dashboard(request):
    """Redirection vers le dashboard approprié selon le rôle"""
    if request.user.is_authenticated:
        return redirect('admin:index')  # Rediriger vers l'admin Django
    else:
        return redirect('accounts:login')


# ===================================================================
# AMÉLIORATION : API pour les notifications temps réel
# ===================================================================

# @login_required
# @require_http_methods(["GET"])
# def api_notifications(request):
#     """API pour récupérer les notifications utilisateur"""
#     try:
#         user = request.user
        
#         # Simuler des notifications (à remplacer par vraies notifications plus tard)
#         notifications = {
#             'unread_count': 0,
#             'new_notifications': []
#         }
        
#         # Vérifier s'il y a des inventaires en attente pour l'utilisateur
#         if user.peut_gerer_inventaire:
#             today = timezone.now().date()
            
#             # # Inventaires non verrouillés de plus de 2 jours
#             # inventaires_en_retard = InventaireJournalier.objects.filter(
#             #     date__lt=today - timedelta(days=2),
#             #     verrouille=False
#             # )
            
#             if user.poste_affectation:
#                 inventaires_en_retard = inventaires_en_retard.filter(
#                     poste=user.poste_affectation
#                 )
            
#             count_retard = inventaires_en_retard.count()
#             if count_retard > 0:
#                 notifications['unread_count'] += 1
#                 notifications['new_notifications'].append({
#                     'type': 'warning',
#                     'message': f'{count_retard} inventaire(s) en retard de verrouillage'
#                 })
        
#         # Vérifier les jours fermés pour aujourd'hui
#         if not ConfigurationJour.est_jour_ouvert_pour_inventaire(timezone.now().date()):
#             notifications['unread_count'] += 1
#             notifications['new_notifications'].append({
#                 'type': 'info',
#                 'message': 'Jour actuel fermé pour la saisie'
#             })
        
#         return JsonResponse(notifications)
        
#     except Exception as e:
#         logger.error(f"Erreur API notifications: {str(e)}")
#         return JsonResponse({'unread_count': 0, 'new_notifications': []})

# def verifier_jour_ouvert_inventaire(date_check, poste=None):
#     """
#     Fonction utilitaire pour vérifier si un jour est ouvert pour inventaire
#     🔧 AVEC gestion d'erreurs et arguments corrects
#     """
#     try:
#         return ConfigurationJour.est_jour_ouvert_pour_inventaire(
#             date=date_check,  # Argument positionnel correct
#             poste=poste       # Argument positionnel correct
#         )
#     except Exception as e:
#         # Log l'erreur pour debug
#         import logging
#         logger = logging.getLogger('supper')
#         logger.error(f"Erreur vérification jour ouvert : {str(e)}")
        
#         # Par défaut : fermé pour sécurité
#         return False


# def verifier_jour_ouvert_recette(date_check, poste=None):
#     """
#     Fonction utilitaire pour vérifier si un jour est ouvert pour recette
#     🔧 AVEC gestion d'erreurs et arguments corrects
#     """
#     try:
#         return ConfigurationJour.est_jour_ouvert_pour_recette(
#             date=date_check,  # Argument positionnel correct
#             poste=poste       # Argument positionnel correct
#         )
#     except Exception as e:
#         # Log l'erreur pour debug
#         import logging
#         logger = logging.getLogger('supper')
#         logger.error(f"Erreur vérification jour ouvert recette : {str(e)}")
        
#         # Par défaut : fermé pour sécurité
#         return False

@login_required
@require_permission('peut_gerer_inventaire')
def programmer_inventaire(request):
    """Vue pour programmer des inventaires sans JavaScript"""
    import logging
    logger = logging.getLogger('supper')
    
    context = {
        'mois_disponibles': [
            (date.today() + timedelta(days=30*i)).strftime('%Y-%m')
            for i in range(0, 6)
        ]
    }
    
    # Récupérer le mois sélectionné
    mois_str = request.GET.get('mois') or request.POST.get('mois')
    logger.debug(f"[DEBUG] Mois sélectionné: {mois_str}")
    
    if mois_str:
        context['mois_selectionne'] = mois_str
        try:
            mois = datetime.strptime(mois_str, '%Y-%m').date()
            context['mois'] = mois
        except Exception as e:
            logger.error(f"[ERROR] Format de mois invalide: {e}")
            messages.error(request, "Format de mois invalide")
            return render(request, 'inventaire/programmer_inventaire.html', context)
    
    # Si on clique sur "Générer" pour un motif
    if request.method == 'POST' and 'generer' in request.POST:
        motif = request.POST.get('motif')
        logger.info(f"[INFO] Génération pour motif: {motif}, mois: {mois_str}")
        context['motif_selectionne'] = motif
        
        try:
            if motif == 'risque_baisse':
                postes_data = ProgrammationInventaire.get_postes_avec_risque_baisse()
                context['postes_risque_baisse'] = postes_data
                logger.debug(f"[DEBUG] Postes risque baisse trouvés: {len(postes_data)}")
                
            elif motif == 'grand_stock':
                postes_data = ProgrammationInventaire.get_postes_avec_grand_stock()
                context['postes_grand_stock'] = postes_data
                logger.debug(f"[DEBUG] Postes grand stock trouvés: {len(postes_data)}")
                
            elif motif == 'taux_deperdition':
                # Récupérer TOUS les postes actifs d'abord
                tous_postes = Poste.objects.filter(is_active=True)
                logger.debug(f"[DEBUG] Total postes actifs: {tous_postes.count()}")
                
                # Récupérer les postes avec taux
                postes_taux = []
                for poste in tous_postes:
                    # Chercher le dernier taux de déperdition
                    derniere_recette = RecetteJournaliere.objects.filter(
                        poste=poste,
                        taux_deperdition__isnull=False
                    ).order_by('-date').first()
                    
                    if derniere_recette:
                        postes_taux.append({
                            'poste': poste,
                            'taux_deperdition': derniere_recette.taux_deperdition,
                            'date_calcul': derniere_recette.date,
                            'alerte': derniere_recette.get_couleur_alerte()
                        })
                        logger.debug(f"[DEBUG] Poste {poste.nom}: taux={derniere_recette.taux_deperdition}")
                
                # Les autres postes sans taux
                postes_avec_taux_ids = [p['poste'].id for p in postes_taux]
                autres_postes = tous_postes.exclude(id__in=postes_avec_taux_ids)
                
                context['postes_taux'] = postes_taux
                context['autres_postes'] = autres_postes
                
                logger.info(f"[INFO] Postes avec taux: {len(postes_taux)}, Sans taux: {autres_postes.count()}")
                
                # Si aucun poste trouvé
                if not postes_taux and not autres_postes.exists():
                    context['aucun_poste'] = True
                    messages.warning(request, "Aucun poste actif trouvé dans le système")
            
            # Vérifier les programmations existantes
            if mois_str and motif:
                prog_existantes = ProgrammationInventaire.objects.filter(
                    mois=mois,
                    motif=motif,
                    actif=True
                ).values_list('poste_id', flat=True)
                context['programmations_existantes'] = list(prog_existantes)
                logger.debug(f"[DEBUG] Programmations existantes: {len(prog_existantes)}")
                
        except Exception as e:
            logger.error(f"[ERROR] Erreur lors de la génération: {str(e)}")
            messages.error(request, f"Erreur lors de la génération: {str(e)}")
    
    # Si on soumet le formulaire final
    if request.method == 'POST' and 'programmer' in request.POST:
        motif = request.POST.get('motif')
        postes_ids = request.POST.getlist('postes')
        logger.info(f"[INFO] Programmation finale - Motif: {motif}, Postes: {len(postes_ids)}")
        
        if not postes_ids:
            messages.error(request, "Veuillez sélectionner au moins un poste")
        else:
            postes_programmes = []
            postes_deja_programmes = []
            
            for poste_id in postes_ids:
                try:
                    poste = Poste.objects.get(id=poste_id)
                    
                    if ProgrammationInventaire.objects.filter(
                        poste=poste,
                        mois=mois,
                        motif=motif,
                        actif=True
                    ).exists():
                        postes_deja_programmes.append(poste.nom)
                        continue
                    
                    prog = ProgrammationInventaire.objects.create(
                        poste=poste,
                        mois=mois,
                        motif=motif,
                        cree_par=request.user,
                        actif=True
                    )
                    
                    if motif == MotifInventaire.GRAND_STOCK:
                        stock_key = f'stock_{poste_id}'
                        if stock_key in request.POST:
                            prog.stock_restant = int(request.POST[stock_key])
                    elif motif == MotifInventaire.TAUX_DEPERDITION:
                        taux_key = f'taux_{poste_id}'
                        if taux_key in request.POST:
                            prog.taux_deperdition_precedent = Decimal(request.POST[taux_key])
                    
                    prog.save()
                    postes_programmes.append(poste.nom)
                    logger.info(f"[INFO] Programmation créée pour: {poste.nom}")
                    
                except Exception as e:
                    logger.error(f"[ERROR] Erreur pour poste {poste_id}: {str(e)}")
                    messages.error(request, f"Erreur pour le poste: {str(e)}")
            
            if postes_programmes:
                messages.success(request, f"✅ {len(postes_programmes)} programmation(s) créée(s)")
            if postes_deja_programmes:
                messages.warning(request, f"⚠️ {len(postes_deja_programmes)} poste(s) déjà programmé(s)")
            
            return redirect('inventaire:liste_programmations')
    
    # Log final du contexte
    logger.debug(f"[DEBUG] Contexte final: motif={context.get('motif_selectionne')}, "
                f"postes_taux={len(context.get('postes_taux', []))}, "
                f"autres_postes={context.get('autres_postes').count() if 'autres_postes' in context else 0}")
    
    return render(request, 'inventaire/programmer_inventaire.html', context)


@login_required
@require_http_methods(["GET"])
def api_get_postes_par_motif(request):
    """API pour récupérer les postes selon le motif sélectionné"""
    
    motif = request.GET.get('motif')
    mois = request.GET.get('mois')
    
    if not motif:
        return JsonResponse({'error': 'Motif requis'}, status=400)
    
    # Convertir le mois si fourni
    mois_date = None
    if mois:
        try:
            mois_date = datetime.strptime(mois, '%Y-%m').date()
        except:
            pass
    
    data = {
        'postes': [],
        'postes_sugeres': [],
        'total_postes': 0
    }
    
    if motif == MotifInventaire.RISQUE_BAISSE:
        # Récupérer les postes avec risque de baisse
        postes_risque = ProgrammationInventaire.get_postes_avec_risque_baisse()
        
        for item in postes_risque:
            # Vérifier si déjà programmé pour ce mois/motif
            deja_programme = False
            if mois_date:
                deja_programme = ProgrammationInventaire.objects.filter(
                    poste=item['poste'],
                    mois=mois_date,
                    motif=motif,
                    actif=True
                ).exists()
            
            data['postes_sugeres'].append({
                'id': item['poste'].id,
                'nom': item['poste'].nom,
                'code': item['poste'].code,
                'region': item['poste'].get_region_display(),
                'recettes_actuelles': float(item['recettes_actuelles']),
                'recettes_precedentes': float(item['recettes_precedentes']),
                'pourcentage_baisse': float(item['pourcentage_baisse']),
                'selectionne': True,  # Pré-sélectionné
                'deja_programme': deja_programme
            })
    
    elif motif == MotifInventaire.GRAND_STOCK:
        # Récupérer les postes avec grand stock
        postes_stock = ProgrammationInventaire.get_postes_avec_grand_stock()
        
        for item in postes_stock:
            deja_programme = False
            if mois_date:
                deja_programme = ProgrammationInventaire.objects.filter(
                    poste=item['poste'],
                    mois=mois_date,
                    motif=motif,
                    actif=True
                ).exists()
            
            data['postes_sugeres'].append({
                'id': item['poste'].id,
                'nom': item['poste'].nom,
                'code': item['poste'].code,
                'region': item['poste'].get_region_display(),
                'stock_restant': item['stock_restant'],
                'date_epuisement': item['date_epuisement'].strftime('%d/%m/%Y'),
                'jours_restants': item['jours_restants'],
                'selectionne': True,  # Pré-sélectionné
                'deja_programme': deja_programme
            })
    
    elif motif == MotifInventaire.TAUX_DEPERDITION:
        # Récupérer TOUS les postes avec leur taux si disponible
        postes_taux = ProgrammationInventaire.get_postes_avec_taux_deperdition()
        postes_avec_taux_ids = [item['poste'].id for item in postes_taux]
        
        # Postes avec taux (pré-sélectionnés)
        for item in postes_taux:
            deja_programme = False
            if mois_date:
                deja_programme = ProgrammationInventaire.objects.filter(
                    poste=item['poste'],
                    mois=mois_date,
                    motif=motif,
                    actif=True
                ).exists()
            
            data['postes_sugeres'].append({
                'id': item['poste'].id,
                'nom': item['poste'].nom,
                'code': item['poste'].code,
                'region': item['poste'].get_region_display(),
                'taux_deperdition': float(item['taux_deperdition']),
                'date_calcul': item['date_calcul'].strftime('%d/%m/%Y'),
                'alerte': item['alerte'],
                'selectionne': float(item['taux_deperdition']) < -10,  # Sélectionné si taux < -10%
                'deja_programme': deja_programme
            })
        
        # Ajouter les autres postes (non sélectionnés)
        autres_postes = Poste.objects.filter(
            is_active=True
        ).exclude(id__in=postes_avec_taux_ids)
        
        for poste in autres_postes:
            deja_programme = False
            if mois_date:
                deja_programme = ProgrammationInventaire.objects.filter(
                    poste=poste,
                    mois=mois_date,
                    motif=motif,
                    actif=True
                ).exists()
            
            data['postes'].append({
                'id': poste.id,
                'nom': poste.nom,
                'code': poste.code,
                'region': poste.get_region_display(),
                'taux_deperdition': None,
                'selectionne': False,
                'deja_programme': deja_programme
            })
    
    data['total_postes'] = len(data['postes']) + len(data['postes_sugeres'])
    
    return JsonResponse(data)


@login_required
def liste_programmations(request):
    """Vue pour afficher la liste des programmations groupées par poste"""
    
    # Récupérer toutes les programmations actives
    if request.user.is_admin:
        programmations = ProgrammationInventaire.objects.filter(actif=True)
    else:
        programmations = ProgrammationInventaire.objects.filter(
            actif=True,
            poste__in=request.user.get_postes_accessibles()
        )
    
    # Grouper par poste et mois
    programmations_groupees = {}
    
    for prog in programmations.select_related('poste', 'cree_par'):
        key = f"{prog.poste.id}_{prog.mois.strftime('%Y-%m')}"
        
        if key not in programmations_groupees:
            programmations_groupees[key] = {
                'poste': prog.poste,
                'mois': prog.mois,
                'motifs': [],
                'cree_par': prog.cree_par,
                'date_creation': prog.date_creation
            }
        
        # Ajouter les détails du motif
        motif_detail = {
            'type': prog.motif,
            'display': prog.get_motif_display()
        }
        
        if prog.motif == MotifInventaire.TAUX_DEPERDITION:
            motif_detail['taux'] = prog.taux_deperdition_precedent
        elif prog.motif == MotifInventaire.RISQUE_BAISSE:
            motif_detail['pourcentage_baisse'] = prog.pourcentage_baisse
        elif prog.motif == MotifInventaire.GRAND_STOCK:
            motif_detail['stock_restant'] = prog.stock_restant
            motif_detail['date_epuisement'] = prog.date_epuisement_prevu
        
        programmations_groupees[key]['motifs'].append(motif_detail)
    
    # Trier par mois décroissant et poste
    programmations_liste = sorted(
        programmations_groupees.values(),
        key=lambda x: (x['mois'], x['poste'].nom),
        reverse=True
    )
    
    context = {
        'programmations': programmations_liste,
        'user_role': request.user.get_habilitation_display()
    }
    
    return render(request, 'inventaire/liste_programmations.html', context)


@login_required
@require_permission('peut_gerer_inventaire')
@require_http_methods(["POST"])
def desactiver_programmation(request, poste_id, mois, motif):
    """Désactive une programmation spécifique"""
    
    try:
        mois_date = datetime.strptime(mois, '%Y-%m').date()
        
        prog = get_object_or_404(
            ProgrammationInventaire,
            poste_id=poste_id,
            mois=mois_date,
            motif=motif,
            actif=True
        )
        
        prog.actif = False
        prog.save()
        
        messages.success(
            request,
            f"Programmation désactivée pour {prog.poste.nom} - {prog.get_motif_display()}"
        )
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_permission('peut_gerer_inventaire')
@require_http_methods(["DELETE"])
def supprimer_programmation(request, poste_id, mois, motif):
    """Supprime définitivement une programmation"""
    
    try:
        mois_date = datetime.strptime(mois, '%Y-%m').date()
        
        prog = get_object_or_404(
            ProgrammationInventaire,
            poste_id=poste_id,
            mois=mois_date,
            motif=motif
        )
        
        poste_nom = prog.poste.nom
        motif_display = prog.get_motif_display()
        
        prog.delete()
        
        messages.success(
            request,
            f"Programmation supprimée pour {poste_nom} - {motif_display}"
        )
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)