# ===================================================================
# accounts/views.py - Vues corrigées avec décorateurs appropriés
# CORRECTION : Utilisation des mixins au lieu de décorateurs de fonction
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
from django.http import JsonResponse, HttpResponseRedirect
from django.utils.translation import gettext_lazy as _  # Support bilingue FR/EN
from django.contrib.auth import login, authenticate
from django.core.exceptions import ValidationError
from django.utils import timezone  # Ajout import manquant
from .forms import ProfileEditForm  # Ajouter cet import

# Import des modèles SUPPER
from .models import UtilisateurSUPPER, Poste, JournalAudit, NotificationUtilisateur
from .forms import (
    CustomLoginForm, PasswordChangeForm, UserCreateForm, 
    UserUpdateForm, BulkUserCreateForm, PasswordResetForm
)

# Import des utilitaires communs avec journalisation
from common.utils import log_user_action  # Suppression de admin_required problématique
from common.mixins import AuditMixin, AdminRequiredMixin, BilingualMixin


class CustomLoginView(BilingualMixin, LoginView):
    """
    Vue de connexion personnalisée avec journalisation automatique
    Support bilingue et redirection intelligente selon le rôle utilisateur
    """
    
    template_name = 'accounts/login.html'  # Template de connexion personnalisé
    form_class = CustomLoginForm  # Formulaire personnalisé avec matricule
    redirect_authenticated_user = True  # Rediriger si déjà connecté
    
    def form_valid(self, form):
        """
        Traitement du formulaire de connexion valide
        Effectue la connexion et redirige selon le rôle
        Args:
            form: Formulaire de connexion validé
        Returns:
            HttpResponse: Redirection vers le dashboard approprié
        """
        # Effectuer la connexion standard Django
        response = super().form_valid(form)
        
        # Récupérer l'utilisateur connecté pour redirection personnalisée
        user = self.request.user
        
        # Message de bienvenue personnalisé selon la langue
        messages.success(
            self.request,
            _("Bienvenue %(nom)s ! Connexion réussie.") % {'nom': user.nom_complet}
        )
        
        # Redirection intelligente selon le rôle de l'utilisateur
        if user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info']:
            # Administrateurs → Dashboard admin avec toutes les fonctionnalités
            return redirect('common:dashboard_admin')
        elif user.habilitation in ['chef_peage', 'chef_pesage']:
            # Chefs de poste → Dashboard spécialisé gestion de poste
            return redirect('common:dashboard_chef')
        elif user.habilitation == 'agent_inventaire':
            # Agents inventaire → Interface simplifiée de saisie
            return redirect('common:dashboard_agent')
        else:
            # Autres rôles → Dashboard général avec permissions limitées
            return redirect('common:dashboard_general')
    
    def form_invalid(self, form):
        """
        Traitement du formulaire de connexion invalide
        Journalise les tentatives d'accès échouées pour sécurité
        Args:
            form: Formulaire avec erreurs de validation
        Returns:
            HttpResponse: Page de connexion avec messages d'erreur
        """
        # Récupérer le matricule saisi pour journalisation sécurisée
        username = form.cleaned_data.get('username', 'Inconnu')
        
        # Journaliser la tentative de connexion échouée si utilisateur existe
        try:
            # Chercher l'utilisateur pour journalisation (sans révéler s'il existe)
            user = UtilisateurSUPPER.objects.get(username=username.upper())
            log_user_action(
                user=user,
                action=_("TENTATIVE CONNEXION ÉCHOUÉE"),
                details=_("Mot de passe incorrect depuis %(ip)s") % {
                    'ip': self.request.META.get('REMOTE_ADDR', 'IP inconnue')
                },
                request=self.request
            )
        except UtilisateurSUPPER.DoesNotExist:
            # Ne pas journaliser si l'utilisateur n'existe pas (sécurité)
            pass
        
        # Message d'erreur générique pour éviter l'énumération d'utilisateurs
        messages.error(
            self.request,
            _("Matricule ou mot de passe incorrect. Veuillez réessayer.")
        )
        
        # Retourner le formulaire avec erreurs
        return super().form_invalid(form)


class PasswordChangeView(LoginRequiredMixin, BilingualMixin, AuditMixin, DjangoPasswordChangeView):
    """
    Vue pour permettre aux utilisateurs de changer leur mot de passe
    Validation simplifiée (4 caractères minimum) selon les specs
    """
    
    template_name = 'accounts/password_change.html'  # Template personnalisé
    form_class = PasswordChangeForm  # Formulaire avec validation simplifiée
    success_url = reverse_lazy('accounts:profile')  # Redirection après succès
    audit_action = _("Changement de mot de passe")  # Action pour journalisation
    
    def form_valid(self, form):
        """
        Traitement du changement de mot de passe réussi
        Args:
            form: Formulaire validé avec nouveau mot de passe
        Returns:
            HttpResponse: Redirection avec message de succès
        """
        # Effectuer le changement de mot de passe
        response = super().form_valid(form)
        
        # Message de confirmation bilingue
        messages.success(
            self.request, 
            _("Votre mot de passe a été modifié avec succès.")
        )
        
        return response


class PasswordResetView(LoginRequiredMixin, AdminRequiredMixin, BilingualMixin, AuditMixin, View):
    """
    Vue pour la réinitialisation de mot de passe par un administrateur
    Permet aux admins de réinitialiser les mots de passe des utilisateurs
    """
    
    template_name = 'accounts/password_reset.html'
    audit_action = _("Réinitialisation mot de passe")
    
    def get(self, request, pk):
        """
        Affichage du formulaire de réinitialisation
        Args:
            request: Requête HTTP
            pk: ID de l'utilisateur à réinitialiser
        Returns:
            HttpResponse: Formulaire de réinitialisation
        """
        # Récupérer l'utilisateur à modifier ou retourner 404
        user_to_reset = get_object_or_404(UtilisateurSUPPER, pk=pk)
        
        # Préparer le contexte pour le template
        context = {
            'user_to_reset': user_to_reset,
            'form': PasswordResetForm(),
            'title': _('Réinitialiser le mot de passe de %(nom)s') % {
                'nom': user_to_reset.nom_complet
            }
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request, pk):
        """
        Traitement de la réinitialisation de mot de passe
        Args:
            request: Requête HTTP avec données du formulaire
            pk: ID de l'utilisateur à réinitialiser
        Returns:
            HttpResponse: Redirection ou formulaire avec erreurs
        """
        # Récupérer l'utilisateur à modifier
        user_to_reset = get_object_or_404(UtilisateurSUPPER, pk=pk)
        form = PasswordResetForm(request.POST)
        
        if form.is_valid():
            # Récupérer le nouveau mot de passe du formulaire
            new_password = form.cleaned_data['nouveau_mot_de_passe']
            
            # Effectuer la réinitialisation
            user_to_reset.set_password(new_password)
            user_to_reset.save()
            
            # Message de succès bilingue
            messages.success(
                request,
                _("Mot de passe de %(nom)s réinitialisé avec succès.") % {
                    'nom': user_to_reset.nom_complet
                }
            )
            
            # Journalisation de l'action administrative
            log_user_action(
                user=request.user,
                action=_("Réinitialisation mot de passe administrateur"),
                details=_("Mot de passe réinitialisé pour %(username)s (%(nom)s)") % {
                    'username': user_to_reset.username,
                    'nom': user_to_reset.nom_complet
                },
                request=request
            )
            
            # Redirection vers la liste des utilisateurs
            return redirect('accounts:user_list')
        
        # Formulaire invalide : réafficher avec erreurs
        context = {
            'user_to_reset': user_to_reset,
            'form': form,
        }
        
        return render(request, self.template_name, context)


class UserListView(LoginRequiredMixin, AdminRequiredMixin, BilingualMixin, AuditMixin, ListView):
    """
    Liste des utilisateurs du système - accès administrateur uniquement
    Utilise AdminRequiredMixin au lieu du décorateur @admin_required
    """
    
    model = UtilisateurSUPPER
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'
    paginate_by = 25  # 25 utilisateurs par page
    audit_action = _("Consultation liste utilisateurs")
    
    def get_queryset(self):
        """
        Récupérer la liste des utilisateurs avec optimisations et filtres
        Returns:
            QuerySet: Liste optimisée des utilisateurs
        """
        # Requête de base avec jointure pour éviter les requêtes N+1
        queryset = UtilisateurSUPPER.objects.select_related('poste_affectation').order_by('nom_complet')
        
        # Filtrage par terme de recherche si fourni
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            # Recherche dans matricule, nom, téléphone
            queryset = queryset.filter(
                Q(username__icontains=search_query) |
                Q(nom_complet__icontains=search_query) |
                Q(telephone__icontains=search_query)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        """
        Ajouter des statistiques au contexte
        Returns:
            dict: Contexte enrichi pour le template
        """
        context = super().get_context_data(**kwargs)
        
        # Statistiques générales pour le dashboard
        context.update({
            'total_users': UtilisateurSUPPER.objects.count(),
            'active_users': UtilisateurSUPPER.objects.filter(is_active=True).count(),
        })
        
        return context


class UserCreateView(LoginRequiredMixin, AdminRequiredMixin, BilingualMixin, AuditMixin, CreateView):
    """
    Création d'un nouvel utilisateur - accès administrateur uniquement
    Utilise AdminRequiredMixin au lieu du décorateur @admin_required
    """
    
    model = UtilisateurSUPPER
    form_class = UserCreateForm
    template_name = 'accounts/user_create.html'
    success_url = reverse_lazy('accounts:user_list')
    audit_action = _("Création utilisateur")
    
    def form_valid(self, form):
        """
        Traitement de la création d'utilisateur réussie
        Args:
            form: Formulaire validé avec données utilisateur
        Returns:
            HttpResponse: Redirection vers liste avec message de succès
        """
        # Associer l'administrateur créateur avant sauvegarde
        form.instance.cree_par = self.request.user
        
        # Effectuer la création via le formulaire
        response = super().form_valid(form)
        
        # Message de succès bilingue avec détails
        messages.success(
            self.request,
            _("Utilisateur %(username)s (%(nom)s) créé avec succès.") % {
                'username': form.instance.username,
                'nom': form.instance.nom_complet
            }
        )
        
        return response


class UserBulkCreateView(LoginRequiredMixin, AdminRequiredMixin, BilingualMixin, AuditMixin, TemplateView):
    """
    Création en masse d'utilisateurs avec paramètres communs
    Utilise AdminRequiredMixin au lieu du décorateur @admin_required
    """
    
    template_name = 'accounts/user_bulk_create.html'
    audit_action = _("Création utilisateurs en masse")
    
    def get_context_data(self, **kwargs):
        """
        Préparer le contexte pour le formulaire de création en masse
        Returns:
            dict: Contexte avec formulaire et données de référence
        """
        context = super().get_context_data(**kwargs)
        
        context.update({
            'form': BulkUserCreateForm(),
            'title': _('Création en masse d\'utilisateurs'),
            'postes': Poste.objects.filter(actif=True).order_by('region', 'nom'),
        })
        
        return context
    
    def post(self, request, *args, **kwargs):
        """
        Traitement de la création en masse
        Args:
            request: Requête HTTP avec données du formulaire
        Returns:
            HttpResponse: Redirection ou formulaire avec erreurs
        """
        form = BulkUserCreateForm(request.POST)
        
        if form.is_valid():
            try:
                # Utiliser une transaction pour créer tous les utilisateurs
                with transaction.atomic():
                    # Créer les utilisateurs via la méthode du formulaire
                    users_created = form.create_users(created_by=request.user)
                    
                    # Message de succès avec nombre d'utilisateurs créés
                    messages.success(
                        request,
                        _("%(count)d utilisateurs créés avec succès.") % {
                            'count': len(users_created)
                        }
                    )
                    
                    # Redirection vers la liste des utilisateurs
                    return redirect('accounts:user_list')
                    
            except Exception as e:
                # Erreur système : message générique pour sécurité
                messages.error(request, _("Erreur système lors de la création."))
        
        # Formulaire invalide ou erreur : réafficher avec messages
        return self.render_to_response({'form': form})


class UserDetailView(LoginRequiredMixin, AdminRequiredMixin, BilingualMixin, DetailView):
    """
    Affichage détaillé d'un utilisateur avec historique d'actions
    Utilise AdminRequiredMixin au lieu du décorateur @admin_required
    """
    
    model = UtilisateurSUPPER
    template_name = 'accounts/user_detail.html'
    context_object_name = 'user_detail'
    
    def get_context_data(self, **kwargs):
        """
        Enrichir le contexte avec informations détaillées
        Returns:
            dict: Contexte complet pour affichage détaillé
        """
        context = super().get_context_data(**kwargs)
        user_detail = self.object
        
        # Historique des actions de cet utilisateur (10 dernières)
        recent_actions = JournalAudit.objects.filter(
            utilisateur=user_detail
        ).order_by('-timestamp')[:10]
        
        context.update({
            'recent_actions': recent_actions,
            'permissions_list': user_detail.get_permissions_list(),
        })
        
        return context


class UserUpdateView(LoginRequiredMixin, AdminRequiredMixin, BilingualMixin, UpdateView):
    """
    Modification des informations d'un utilisateur
    Utilise AdminRequiredMixin au lieu du décorateur @admin_required
    """
    
    model = UtilisateurSUPPER
    form_class = UserUpdateForm
    template_name = 'accounts/user_edit.html'
    
    def get_success_url(self):
        """Redirection vers le détail de l'utilisateur modifié"""
        return reverse_lazy('accounts:user_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        """
        Traitement de la modification réussie
        Args:
            form: Formulaire validé avec nouvelles données
        Returns:
            HttpResponse: Redirection avec message de succès
        """
        response = super().form_valid(form)
        
        # Message de succès
        messages.success(
            self.request,
            _("Informations de %(nom)s mises à jour avec succès.") % {
                'nom': self.object.nom_complet
            }
        )
        
        return response


class ProfileView(LoginRequiredMixin, BilingualMixin, AuditMixin, TemplateView):
    """
    Vue du profil utilisateur personnel
    Accessible à tous les utilisateurs connectés pour consulter leurs informations
    """
    
    template_name = 'accounts/profile.html'
    audit_action = _("Consultation profil personnel")
    
    def get_context_data(self, **kwargs):
        """
        Préparer les données du profil utilisateur
        Returns:
            dict: Contexte avec informations personnelles
        """
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context.update({
            'user': user,
            'permissions': user.get_permissions_list(),
            'poste_affectation': user.poste_affectation,
            
            # Dernières actions de l'utilisateur
            'recent_actions': JournalAudit.objects.filter(
                utilisateur=user
            ).order_by('-timestamp')[:5],
            
            # Informations sur le compte
            'account_info': {
                'created_date': user.date_creation,
                'last_modified': user.date_modification,
                'account_age_days': (timezone.now() - user.date_creation).days,
            }
        })
        
        return context
# ===================================================================
# À AJOUTER À LA FIN DE accounts/views.py
# Vues API pour les fonctionnalités AJAX
# ===================================================================

from django.http import JsonResponse
from django.views import View
import json


class ValidateUsernameAPIView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    API pour valider l'unicité d'un nom d'utilisateur en temps réel
    Utilisée pour la validation AJAX des formulaires
    """
    
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
    """
    API pour la recherche d'utilisateurs (autocomplete)
    Utilisée pour les champs de sélection avec suggestions
    """
    
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
class ProfileEditView(LoginRequiredMixin, UpdateView):
    """
    Vue pour permettre à un utilisateur de modifier son profil
    Seuls certains champs sont modifiables par l'utilisateur lui-même
    """
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
        
        # Journaliser la modification
        from .models import JournalAudit
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
# accounts/views.py - AJOUT SIMPLE au fichier existant
# ===================================================================
# 📝 AJOUTER ces lignes À LA FIN de votre fichier accounts/views.py existant

# Ajout des imports manquants au début du fichier
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.generic import TemplateView
from django.utils.decorators import method_decorator
from django.db.models import Count, Q
from django.utils import timezone
from datetime import datetime, timedelta
from django.conf import settings

from .models import UtilisateurSUPPER, Poste, JournalAudit, NotificationUtilisateur
from .forms import ProfileEditForm, CustomLoginForm, PasswordChangeForm


# ===================================================================
# REDIRECTION INTELLIGENTE SELON RÔLE
# ===================================================================

@login_required
def dashboard_redirect(request):
    """Redirection intelligente vers le bon dashboard selon le rôle"""
    user = request.user
    
    if user.is_admin():
        return redirect('/accounts/admin/')
    elif user.is_chef_poste():
        return redirect('accounts:chef_dashboard')
    elif user.habilitation == 'agent_inventaire':
        return redirect('accounts:agent_dashboard')
    else:
        return redirect('accounts:general_dashboard')


# ===================================================================
# DASHBOARDS SPÉCIALISÉS
# ===================================================================

@method_decorator(login_required, name='dispatch')
class AdminDashboardView(TemplateView):
    """Dashboard pour les administrateurs"""
    template_name = 'admin/dashboard.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_admin():
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
            'postes_active': Poste.objects.filter(actif=True).count(),
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

@login_required
def postes_api(request):
    """API pour récupérer la liste des postes"""
    postes = Poste.objects.filter(actif=True).values(
        'id', 'nom', 'code', 'type_poste', 'region'
    )
    
    return JsonResponse({
        'success': True,
        'postes': list(postes)
    })


@login_required
def stats_api(request):
    """API pour les statistiques en temps réel"""
    if not request.user.is_admin():
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