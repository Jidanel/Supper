# ===================================================================
# accounts/views.py - VERSION COMPLÈTE avec toutes les fonctions
# CORRECTION : Intégration de toutes les vues de redirection admin
# Support bilingue FR/EN intégré, commentaires détaillés
# ===================================================================

from django.contrib.auth.views import LoginView, PasswordChangeView as DjangoPasswordChangeView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView, View
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib import messages
from django.urls import reverse_lazy
from django.db import transaction
from django.db.models import Q, Count  # Ajout des imports manquants
from django.http import JsonResponse, HttpResponseRedirect, HttpResponseForbidden
from django.utils.translation import gettext_lazy as _  # Support bilingue FR/EN
from django.contrib.auth import login, authenticate, logout
from django.core.exceptions import ValidationError
from django.utils import timezone  # Ajout import manquant
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from datetime import datetime, timedelta
from django.conf import settings
from django.views.decorators.http import require_http_methods
import logging
import json

# Import des modèles SUPPER
from .models import UtilisateurSUPPER, Poste, JournalAudit, NotificationUtilisateur
from .forms import *

# Import des utilitaires communs avec journalisation
from common.utils import log_user_action
from common.mixins import AuditMixin, AdminRequiredMixin, BilingualMixin

logger = logging.getLogger('supper')


# ===================================================================
# FONCTIONS UTILITAIRES POUR L'ADMIN DJANGO
# ===================================================================

def _check_admin_permission(user):
    """Vérifier les permissions administrateur"""
    return (user.is_superuser or 
            user.is_staff or 
            user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission'])


def _log_admin_access(request, action):
    """Journaliser l'accès aux sections admin"""
    try:
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
        
    except Exception as e:
        logger.error(f"Erreur journalisation admin access: {str(e)}")


# ===================================================================
# VUES D'AUTHENTIFICATION
# ===================================================================

class CustomLoginView(BilingualMixin, LoginView):
    """
    Vue de connexion personnalisée avec journalisation automatique
    Support bilingue et redirection intelligente selon le rôle utilisateur
    """
    
    template_name = 'registration/login.html'
    redirect_authenticated_user = True
    
    def form_valid(self, form):
        """
        Traitement du formulaire de connexion valide - CORRIGÉ
        Redirection vers l'admin Django pour tous les utilisateurs
        """
        # Effectuer la connexion standard Django
        response = super().form_valid(form)
        
        # Récupérer l'utilisateur connecté
        user = self.request.user
        
        # Message de bienvenue
        messages.success(
            self.request,
            f"Bienvenue {user.nom_complet} ! Connexion réussie."
        )
        
        # Journaliser la connexion
        log_user_action(
            user=user,
            action="Connexion réussie",
            details=f"Connexion depuis {self.request.META.get('REMOTE_ADDR', 'IP inconnue')}",
            request=self.request
        )
        
        # REDIRECTION CORRIGÉE : Tous vers l'admin Django
        return redirect('/admin/')
    
    def form_invalid(self, form):
        """
        Traitement du formulaire de connexion invalide
        """
        username = form.cleaned_data.get('username', 'Inconnu')
        
        # Journaliser la tentative échouée si utilisateur existe
        try:
            user = UtilisateurSUPPER.objects.get(username=username.upper())
            log_user_action(
                user=user,
                action="TENTATIVE CONNEXION ÉCHOUÉE",
                details=f"Mot de passe incorrect depuis {self.request.META.get('REMOTE_ADDR', 'IP inconnue')}",
                request=self.request
            )
        except UtilisateurSUPPER.DoesNotExist:
            pass
        
        # Message d'erreur générique
        messages.error(
            self.request,
            "Matricule ou mot de passe incorrect. Veuillez réessayer."
        )
        
        return super().form_invalid(form)


class CustomLogoutView(View):
    """Vue personnalisée pour la déconnexion avec journalisation"""
    
    def get(self, request):
        return self.logout_user(request)
    
    def post(self, request):
        return self.logout_user(request)
    
    def logout_user(self, request):
        if request.user.is_authenticated:
            # Journaliser la déconnexion
            log_user_action(
                request.user,
                "Déconnexion volontaire",
                f"Utilisateur {request.user.username} s'est déconnecté",
                request
            )
            
            # Message de confirmation
            messages.success(request, _("Vous avez été déconnecté avec succès."))
            
            # Déconnecter l'utilisateur
            logout(request)
        
        # Rediriger vers la page de connexion
        return redirect('accounts:login')


# ===================================================================
# VUES DE REDIRECTION VERS ADMIN DJANGO
# ===================================================================

@login_required
def redirect_to_django_admin(request):
    """Redirection générale vers l'admin Django principal"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé au panel d'administration Django."))
        logger.warning(f"ACCÈS REFUSÉ ADMIN DJANGO - {user.username}")
        return redirect('accounts:dashboard_redirect')
    
    _log_admin_access(request, "Panel administrateur principal")
    messages.success(request, _("Accès autorisé au panel d'administration Django."))
    
    return redirect('/admin/')


@login_required
def redirect_to_users_admin(request):
    """Redirection vers la gestion des utilisateurs dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la gestion des utilisateurs."))
        return redirect('accounts:dashboard_redirect')
    
    _log_admin_access(request, "Gestion utilisateurs")
    messages.info(request, _("Redirection vers la gestion des utilisateurs."))
    
    return redirect('/admin/accounts/utilisateursupper/')


@login_required
def redirect_to_postes_admin(request):
    """Redirection vers la gestion des postes dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la gestion des postes."))
        return redirect('accounts:dashboard_redirect')
    
    _log_admin_access(request, "Gestion postes")
    messages.info(request, _("Redirection vers la gestion des postes."))
    
    return redirect('/admin/accounts/poste/')


@login_required
def redirect_to_inventaires_admin(request):
    """Redirection vers la gestion des inventaires dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la gestion des inventaires."))
        return redirect('accounts:dashboard_redirect')
    
    _log_admin_access(request, "Gestion inventaires")
    messages.info(request, _("Redirection vers la gestion des inventaires."))
    
    return redirect('/admin/inventaire/inventairejournalier/')


@login_required
def redirect_to_recettes_admin(request):
    """Redirection vers la gestion des recettes dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la gestion des recettes."))
        return redirect('accounts:dashboard_redirect')
    
    _log_admin_access(request, "Gestion recettes")
    messages.info(request, _("Redirection vers la gestion des recettes."))
    
    return redirect('/admin/inventaire/recettejournaliere/')


@login_required
def redirect_to_journal_admin(request):
    """Redirection vers le journal d'audit dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé au journal d'audit."))
        return redirect('accounts:dashboard_redirect')
    
    _log_admin_access(request, "Journal d'audit")
    messages.info(request, _("Redirection vers le journal d'audit."))
    
    return redirect('/admin/accounts/journalaudit/')


@login_required
def redirect_to_add_user_admin(request):
    """Redirection vers l'ajout d'utilisateur dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la création d'utilisateurs."))
        return redirect('accounts:dashboard_redirect')
    
    _log_admin_access(request, "Ajout utilisateur")
    messages.info(request, _("Redirection vers l'ajout d'utilisateur."))
    
    return redirect('/admin/accounts/utilisateursupper/add/')


# ===================================================================
# REDIRECTIONS AVEC PARAMÈTRES
# ===================================================================

@login_required
def redirect_to_edit_user_admin(request, user_id):
    """Redirection vers l'édition d'un utilisateur spécifique dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à l'édition des utilisateurs."))
        return redirect('accounts:dashboard_redirect')
    
    # Vérifier que l'utilisateur existe
    try:
        target_user = UtilisateurSUPPER.objects.get(id=user_id)
        _log_admin_access(request, f"Édition utilisateur {target_user.username}")
        messages.info(request, f"Redirection vers l'édition de {target_user.nom_complet}.")
        
        return redirect(f'/admin/accounts/utilisateursupper/{user_id}/change/')
        
    except UtilisateurSUPPER.DoesNotExist:
        messages.error(request, _("Utilisateur non trouvé."))
        return redirect('/admin/accounts/utilisateursupper/')


@login_required
def redirect_to_edit_poste_admin(request, poste_id):
    """Redirection vers l'édition d'un poste spécifique dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à l'édition des postes."))
        return redirect('accounts:dashboard_redirect')
    
    # Vérifier que le poste existe
    try:
        poste = Poste.objects.get(id=poste_id)
        _log_admin_access(request, f"Édition poste {poste.nom}")
        messages.info(request, f"Redirection vers l'édition du poste {poste.nom}.")
        
        return redirect(f'/admin/accounts/poste/{poste_id}/change/')
        
    except Poste.DoesNotExist:
        messages.error(request, _("Poste non trouvé."))
        return redirect('/admin/accounts/poste/')


# ===================================================================
# VUES DE REDIRECTION POUR LE MODULE INVENTAIRE
# ===================================================================

@login_required
def redirect_to_config_jours_admin(request):
    """Redirection vers la configuration des jours dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la configuration des jours."))
        return redirect('accounts:dashboard_redirect')
    
    _log_admin_access(request, "Configuration jours")
    messages.info(request, _("Redirection vers la configuration des jours."))
    
    return redirect('/admin/inventaire/configurationjour/')


@login_required
def redirect_to_add_inventaire_admin(request):
    """Redirection vers l'ajout d'inventaire dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la création d'inventaires."))
        return redirect('accounts:dashboard_redirect')
    
    _log_admin_access(request, "Ajout inventaire")
    messages.info(request, _("Redirection vers l'ajout d'inventaire."))
    
    return redirect('/admin/inventaire/inventairejournalier/add/')


@login_required
def redirect_to_add_recette_admin(request):
    """Redirection vers l'ajout de recette dans l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé à la création de recettes."))
        return redirect('accounts:dashboard_redirect')
    
    _log_admin_access(request, "Ajout recette")
    messages.info(request, _("Redirection vers l'ajout de recette."))
    
    return redirect('/admin/inventaire/recettejournaliere/add/')


# ===================================================================
# GESTION DES MOTS DE PASSE
# ===================================================================

class ChangePasswordView(LoginRequiredMixin, BilingualMixin, AuditMixin, DjangoPasswordChangeView):
    """
    Vue pour permettre aux utilisateurs de changer leur mot de passe
    Validation simplifiée (4 caractères minimum) selon les specs
    """
    
    template_name = 'accounts/password_change.html'
    form_class = PasswordChangeForm
    success_url = reverse_lazy('accounts:profile')
    audit_action = _("Changement de mot de passe")
    
    def form_valid(self, form):
        """
        Traitement du changement de mot de passe réussi
        """
        response = super().form_valid(form)
        
        messages.success(
            self.request, 
            _("Votre mot de passe a été modifié avec succès.")
        )
        
        return response


class PasswordResetView(LoginRequiredMixin, AdminRequiredMixin, BilingualMixin, AuditMixin, View):
    """
    Vue pour la réinitialisation de mot de passe par un administrateur
    """
    
    template_name = 'accounts/password_reset.html'
    audit_action = _("Réinitialisation mot de passe")
    
    def get(self, request, pk):
        """Affichage du formulaire de réinitialisation"""
        user_to_reset = get_object_or_404(UtilisateurSUPPER, pk=pk)
        
        context = {
            'user_to_reset': user_to_reset,
            'form': PasswordResetForm(),
            'title': _('Réinitialiser le mot de passe de %(nom)s') % {
                'nom': user_to_reset.nom_complet
            }
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request, pk):
        """Traitement de la réinitialisation de mot de passe"""
        user_to_reset = get_object_or_404(UtilisateurSUPPER, pk=pk)
        form = PasswordResetForm(request.POST)
        
        if form.is_valid():
            new_password = form.cleaned_data['nouveau_mot_de_passe']
            
            user_to_reset.set_password(new_password)
            user_to_reset.save()
            
            messages.success(
                request,
                _("Mot de passe de %(nom)s réinitialisé avec succès.") % {
                    'nom': user_to_reset.nom_complet
                }
            )
            
            log_user_action(
                user=request.user,
                action=_("Réinitialisation mot de passe administrateur"),
                details=_("Mot de passe réinitialisé pour %(username)s (%(nom)s)") % {
                    'username': user_to_reset.username,
                    'nom': user_to_reset.nom_complet
                },
                request=request
            )
            
            return redirect('accounts:user_list')
        
        context = {
            'user_to_reset': user_to_reset,
            'form': form,
        }
        
        return render(request, self.template_name, context)


# ===================================================================
# GESTION DES UTILISATEURS
# ===================================================================

class UserListView(LoginRequiredMixin, AdminRequiredMixin, BilingualMixin, AuditMixin, ListView):
    """Liste des utilisateurs du système - accès administrateur uniquement"""
    
    model = UtilisateurSUPPER
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'
    paginate_by = 25
    audit_action = _("Consultation liste utilisateurs")
    
    def get_queryset(self):
        """Récupérer la liste des utilisateurs avec optimisations et filtres"""
        queryset = UtilisateurSUPPER.objects.select_related('poste_affectation').order_by('nom_complet')
        
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(username__icontains=search_query) |
                Q(nom_complet__icontains=search_query) |
                Q(telephone__icontains=search_query)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        """Ajouter des statistiques au contexte"""
        context = super().get_context_data(**kwargs)
        
        context.update({
            'total_users': UtilisateurSUPPER.objects.count(),
            'active_users': UtilisateurSUPPER.objects.filter(is_active=True).count(),
        })
        
        return context


class CreateUserView(LoginRequiredMixin, AdminRequiredMixin, BilingualMixin, AuditMixin, CreateView):
    """Création d'un nouvel utilisateur - accès administrateur uniquement"""
    
    model = UtilisateurSUPPER
    form_class = UserCreateForm
    template_name = 'accounts/user_create.html'
    success_url = reverse_lazy('accounts:user_list')
    audit_action = _("Création utilisateur")
    
    def form_valid(self, form):
        """Traitement de la création d'utilisateur réussie"""
        form.instance.cree_par = self.request.user
        response = super().form_valid(form)
        
        messages.success(
            self.request,
            _("Utilisateur %(username)s (%(nom)s) créé avec succès.") % {
                'username': form.instance.username,
                'nom': form.instance.nom_complet
            }
        )
        
        return response


class CreateBulkUsersView(LoginRequiredMixin, AdminRequiredMixin, BilingualMixin, AuditMixin, TemplateView):
    """Création en masse d'utilisateurs avec paramètres communs"""
    
    template_name = 'accounts/user_bulk_create.html'
    audit_action = _("Création utilisateurs en masse")
    
    def get_context_data(self, **kwargs):
        """Préparer le contexte pour le formulaire de création en masse"""
        context = super().get_context_data(**kwargs)
        
        context.update({
            'form': BulkUserCreateForm(),
            'title': _('Création en masse d\'utilisateurs'),
            'postes': Poste.objects.filter(is_active=True).order_by('region', 'nom'),
        })
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Traitement de la création en masse"""
        form = BulkUserCreateForm(request.POST)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    users_created = form.create_users(created_by=request.user)
                    
                    messages.success(
                        request,
                        _("%(count)d utilisateurs créés avec succès.") % {
                            'count': len(users_created)
                        }
                    )
                    
                    return redirect('accounts:user_list')
                    
            except Exception as e:
                messages.error(request, _("Erreur système lors de la création."))
        
        return self.render_to_response({'form': form})


class UserDetailView(LoginRequiredMixin, AdminRequiredMixin, BilingualMixin, DetailView):
    """Affichage détaillé d'un utilisateur avec historique d'actions"""
    
    model = UtilisateurSUPPER
    template_name = 'accounts/user_detail.html'
    context_object_name = 'user_detail'
    
    def get_context_data(self, **kwargs):
        """Enrichir le contexte avec informations détaillées"""
        context = super().get_context_data(**kwargs)
        user_detail = self.object
        
        recent_actions = JournalAudit.objects.filter(
            utilisateur=user_detail
        ).order_by('-timestamp')[:10]
        
        context.update({
            'recent_actions': recent_actions,
            'permissions_list': user_detail.get_permissions_list(),
        })
        
        return context


class UserUpdateView(LoginRequiredMixin, AdminRequiredMixin, BilingualMixin, UpdateView):
    """Modification des informations d'un utilisateur"""
    
    model = UtilisateurSUPPER
    form_class = UserUpdateForm
    template_name = 'accounts/user_edit.html'
    
    def get_success_url(self):
        """Redirection vers le détail de l'utilisateur modifié"""
        return reverse_lazy('accounts:user_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        """Traitement de la modification réussie"""
        response = super().form_valid(form)
        
        messages.success(
            self.request,
            _("Informations de %(nom)s mises à jour avec succès.") % {
                'nom': self.object.nom_complet
            }
        )
        
        return response


# ===================================================================
# GESTION DU PROFIL
# ===================================================================

class ProfileView(LoginRequiredMixin, BilingualMixin, AuditMixin, TemplateView):
    """Vue du profil utilisateur personnel"""
    
    template_name = 'accounts/profile.html'
    audit_action = _("Consultation profil personnel")
    
    def get_context_data(self, **kwargs):
        """Préparer les données du profil utilisateur"""
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context.update({
            'user': user,
            'permissions': user.get_permissions_list(),
            'poste_affectation': user.poste_affectation,
            
            'recent_actions': JournalAudit.objects.filter(
                utilisateur=user
            ).order_by('-timestamp')[:5],
            
            'account_info': {
                'created_date': user.date_creation,
                'last_modified': user.date_modification,
                'account_age_days': (timezone.now() - user.date_creation).days,
            }
        })
        
        return context


class EditProfileView(LoginRequiredMixin, UpdateView):
    """Vue pour permettre à un utilisateur de modifier son profil"""
    
    model = UtilisateurSUPPER
    form_class = ProfileEditForm
    template_name = 'accounts/profile_edit.html'
    success_url = reverse_lazy('accounts:profile')
    
    def get_object(self):
        """Retourne l'utilisateur connecté"""
        return self.request.user
    
    def form_valid(self, form):
        """Traitement après validation du formulaire"""
        messages.success(
            self.request, 
            _("Votre profil a été mis à jour avec succès.")
        )
        
        JournalAudit.objects.create(
            utilisateur=self.request.user,
            action="Modification profil",
            details=f"Profil mis à jour: {self.request.user.username}",
            succes=True
        )
        
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        """Ajouter des données au contexte"""
        context = super().get_context_data(**kwargs)
        context['page_title'] = _("Modifier mon profil")
        return context


# ===================================================================
# REDIRECTION INTELLIGENTE SELON RÔLE
# ===================================================================

@login_required
def dashboard_redirect(request):
    """Redirection intelligente vers le bon dashboard selon le rôle - TEMPORAIRE"""
    user = request.user
    
    # Message d'information
    messages.info(
        request, 
        f"Bonjour {user.nom_complet}! Vous êtes redirigé vers l'interface d'administration."
    )
    
    # CORRECTION : Tous les utilisateurs vont vers l'admin Django temporairement
    return redirect('/admin/')


# ===================================================================
# DASHBOARDS SPÉCIALISÉS (TEMPORAIREMENT DÉSACTIVÉS)
# ===================================================================

@method_decorator(login_required, name='dispatch')
class AdminDashboardView(TemplateView):
    """Dashboard pour les administrateurs"""
    template_name = 'admin/dashboard.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not _check_admin_permission(request.user):
            return HttpResponseForbidden("Accès réservé aux administrateurs")
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stats'] = self._get_admin_stats()
        context['recent_actions'] = JournalAudit.objects.select_related('utilisateur').order_by('-timestamp')[:10]
        return context
    
    def _get_admin_stats(self):
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        return {
            'users_total': UtilisateurSUPPER.objects.count(),
            'users_active': UtilisateurSUPPER.objects.filter(is_active=True).count(),
            'users_this_week': UtilisateurSUPPER.objects.filter(date_creation__gte=week_ago).count(),
            'postes_total': Poste.objects.count(),
            'postes_active': Poste.objects.filter(is_active=True).count(),
            'actions_today': JournalAudit.objects.filter(timestamp__date=today).count(),
            'actions_week': JournalAudit.objects.filter(timestamp__gte=week_ago).count(),
        }


@method_decorator(login_required, name='dispatch')
class ChefPosteDashboardView(TemplateView):
    """Dashboard pour les chefs de poste"""
    template_name = 'accounts/chef_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['poste'] = self.request.user.poste_affectation
        return context


@method_decorator(login_required, name='dispatch')
class AgentInventaireDashboardView(TemplateView):
    """Dashboard pour les agents d'inventaire"""
    template_name = 'accounts/agent_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['poste'] = self.request.user.poste_affectation
        return context


@method_decorator(login_required, name='dispatch')
class GeneralDashboardView(TemplateView):
    """Dashboard général pour les autres rôles"""
    template_name = 'accounts/general_dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_role'] = self.request.user.get_habilitation_display()
        return context


# ===================================================================
# API ENDPOINTS
# ===================================================================

class ValidateUsernameAPIView(LoginRequiredMixin, AdminRequiredMixin, View):
    """API pour valider l'unicité d'un nom d'utilisateur en temps réel"""
    
    def get(self, request):
        """Valide si un matricule est disponible"""
        username = request.GET.get('username', '').strip().upper()
        
        if not username:
            return JsonResponse({
                'valid': False,
                'message': 'Matricule requis'
            })
        
        # Vérifier le format
        import re
        if not re.match(r'^[A-Z0-9]{6,20}$', username):
            return JsonResponse({
                'valid': False,
                'message': 'Format invalide (6-20 caractères alphanumériques)'
            })
        
        # Vérifier l'unicité
        exists = UtilisateurSUPPER.objects.filter(username=username).exists()
        
        return JsonResponse({
            'valid': not exists,
            'message': 'Matricule déjà utilisé' if exists else 'Matricule disponible'
        })


class UserSearchAPIView(LoginRequiredMixin, AdminRequiredMixin, View):
    """API pour la recherche d'utilisateurs (autocomplete)"""
    
    def get(self, request):
        """Recherche des utilisateurs selon un terme"""
        query = request.GET.get('q', '').strip()
        
        if len(query) < 2:
            return JsonResponse({'results': []})
        
        # Rechercher dans username et nom_complet
        users = UtilisateurSUPPER.objects.filter(
            Q(username__icontains=query) |
            Q(nom_complet__icontains=query)
        ).filter(is_active=True)[:10]
        
        results = []
        for user in users:
            results.append({
                'id': user.id,
                'username': user.username,
                'nom_complet': user.nom_complet,
                'habilitation': user.get_habilitation_display(),
                'poste': user.poste_affectation.nom if user.poste_affectation else None
            })
        
        return JsonResponse({'results': results})


@login_required
def postes_api(request):
    """API pour récupérer la liste des postes"""
    postes = Poste.objects.filter(is_active=True).values(
        'id', 'nom', 'code', 'type', 'region'
    )
    
    return JsonResponse({
        'success': True,
        'postes': list(postes)
    })


@login_required
def stats_api(request):
    """API pour les statistiques en temps réel"""
    if not _check_admin_permission(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    today = timezone.now().date()
    
    stats = {
        'users_online': UtilisateurSUPPER.objects.filter(
            last_login__gte=timezone.now() - timedelta(minutes=30)
        ).count(),
        'actions_today': JournalAudit.objects.filter(timestamp__date=today).count(),
        'timestamp': timezone.now().isoformat(),
    }
    
    return JsonResponse(stats)


@login_required
@require_http_methods(["GET"])
def check_admin_permission_api(request):
    """API pour vérifier si l'utilisateur a les permissions admin"""
    user = request.user
    
    has_permission = _check_admin_permission(user)
    
    response_data = {
        'has_admin_permission': has_permission,
        'user_habilitation': user.habilitation,
        'is_superuser': user.is_superuser,
        'is_staff': user.is_staff,
        'username': user.username,
        'nom_complet': user.nom_complet,
    }
    
    if has_permission:
        response_data['admin_urls'] = {
            'main': '/admin/',
            'users': '/admin/accounts/utilisateursupper/',
            'postes': '/admin/accounts/poste/',
            'inventaires': '/admin/inventaire/inventairejournalier/',
            'recettes': '/admin/inventaire/recettejournaliere/',
            'journal': '/admin/accounts/journalaudit/',
        }
    
    return JsonResponse(response_data)


# ===================================================================
# VUES D'AIDE ET DOCUMENTATION
# ===================================================================

@login_required
def admin_help_view(request):
    """Vue d'aide pour l'utilisation de l'admin Django"""
    user = request.user
    
    if not _check_admin_permission(user):
        messages.error(request, _("Accès non autorisé."))
        return redirect('accounts:dashboard_redirect')
    
    context = {
        'title': 'Aide - Administration Django',
        'user_permissions': {
            'can_manage_users': True,
            'can_manage_postes': True,
            'can_manage_inventaires': True,
            'can_view_audit': True,
        },
        'admin_urls': {
            'main': '/admin/',
            'users': '/admin/accounts/utilisateursupper/',
            'postes': '/admin/accounts/poste/',
            'inventaires': '/admin/inventaire/inventairejournalier/',
            'recettes': '/admin/inventaire/recettejournaliere/',
            'journal': '/admin/accounts/journalaudit/',
        }
    }
    
    return render(request, 'accounts/admin_help.html', context)


# ===================================================================
# GESTION DES ERREURS DE REDIRECTION
# ===================================================================

@login_required
def redirect_error_handler(request, error_type='permission'):
    """Gestionnaire d'erreurs pour les redirections"""
    user = request.user
    
    if error_type == 'permission':
        messages.error(request, _(
            "Vous n'avez pas les permissions nécessaires pour accéder à cette section. "
            "Contactez un administrateur si vous pensez que c'est une erreur."
        ))
        
        # Journaliser la tentative d'accès non autorisée
        try:
            JournalAudit.objects.create(
                utilisateur=user,
                action="ACCÈS REFUSÉ - Redirection admin Django",
                details=f"Tentative d'accès non autorisée depuis {request.META.get('HTTP_REFERER', 'URL inconnue')}",
                adresse_ip=request.META.get('REMOTE_ADDR'),
                url_acces=request.path,
                methode_http=request.method,
                succes=False
            )
        except Exception as e:
            logger.error(f"Erreur journalisation tentative accès: {str(e)}")
    
    elif error_type == 'not_found':
        messages.error(request, _("La ressource demandée n'a pas été trouvée."))
    
    else:
        messages.error(request, _("Une erreur est survenue lors de la redirection."))
    
    # Rediriger vers le dashboard approprié selon le rôle
    if _check_admin_permission(user):
        return redirect('/admin/')
    else:
        return redirect('accounts:dashboard_redirect')


# ===================================================================
# FONCTIONS POUR LE TEMPLATE (si nécessaire)
# ===================================================================

def get_admin_navigation_context(user):
    """Retourne le contexte de navigation pour les templates admin"""
    
    if not _check_admin_permission(user):
        return {}
    
    return {
        'admin_navigation': {
            'main_admin': {
                'url': '/admin/',
                'title': 'Panel Administrateur',
                'icon': 'fas fa-crown',
                'description': 'Accès principal à l\'administration Django'
            },
            'users_admin': {
                'url': '/admin/accounts/utilisateursupper/',
                'title': 'Gérer Utilisateurs',
                'icon': 'fas fa-users',
                'description': 'Gestion complète des utilisateurs'
            },
            'postes_admin': {
                'url': '/admin/accounts/poste/',
                'title': 'Gérer Postes',
                'icon': 'fas fa-map-marker-alt',
                'description': 'Gestion des postes de péage et pesage'
            },
            'inventaires_admin': {
                'url': '/admin/inventaire/inventairejournalier/',
                'title': 'Gérer Inventaires',
                'icon': 'fas fa-clipboard-list',
                'description': 'Gestion des inventaires journaliers'
            },
            'recettes_admin': {
                'url': '/admin/inventaire/recettejournaliere/',
                'title': 'Gérer Recettes',
                'icon': 'fas fa-euro-sign',
                'description': 'Gestion des recettes journalières'
            },
            'journal_admin': {
                'url': '/admin/accounts/journalaudit/',
                'title': 'Journal d\'Audit',
                'icon': 'fas fa-file-alt',
                'description': 'Consultation du journal d\'audit'
            }
        }
    }


# ===================================================================
# GESTIONNAIRES D'ERREURS PERSONNALISÉS
# ===================================================================

def custom_404(request, exception=None):
    """Page 404 personnalisée"""
    return render(request, 'errors/404.html', {
        'title': 'Page non trouvée',
        'message': 'La page que vous cherchez n\'existe pas.',
    }, status=404)


def custom_500(request):
    """Page 500 personnalisée"""
    return render(request, 'errors/500.html', {
        'title': 'Erreur serveur',
        'message': 'Une erreur interne s\'est produite.',
    }, status=500)


def custom_403(request, exception=None):
    """Page 403 personnalisée"""
    return render(request, 'errors/403.html', {
        'title': 'Accès interdit',
        'message': 'Vous n\'avez pas les permissions nécessaires.',
    }, status=403)