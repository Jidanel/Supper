# ===================================================================
# accounts/views.py - VERSION COMPLÈTE avec PERMISSIONS GRANULAIRES
# Intégration des mixins granulaires, gestion profil utilisateur
# Support bilingue FR/EN, journalisation détaillée contextuelle
# ===================================================================

import re
from django.contrib.auth.views import LoginView, PasswordChangeView as DjangoPasswordChangeView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import (
    ListView, DetailView, CreateView, UpdateView, 
    TemplateView, View, DeleteView, FormView
)
from django.shortcuts import redirect, get_object_or_404, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.contrib import messages
from django.urls import reverse_lazy, reverse
from django.db import transaction
from django.db.models import Q, Count, Sum, Avg
from django.http import JsonResponse, HttpResponseRedirect, HttpResponseForbidden
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import login, authenticate, logout, update_session_auth_hash
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from django.contrib.auth.views import LogoutView as DjangoLogoutView
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.conf import settings
from functools import wraps
import logging
import json

import pandas as pd
from .models import UtilisateurSUPPER, Poste, Habilitation
from common.utils import log_user_action, get_user_short_description
from common.decorators import permission_required_granular

logger = logging.getLogger('supper')



# ===================================================================
# IMPORTS DES MODÈLES ET FORMULAIRES SUPPER
# ===================================================================
from .models import (
    UtilisateurSUPPER, Poste, JournalAudit, NotificationUtilisateur,
    Habilitation, TypePoste, Region, Departement
)
from .forms import (
    CustomLoginForm, UserCreateForm, UserUpdateForm, UserEditForm,
    PasswordChangeForm, PasswordResetForm, BulkUserCreateForm,
    ProfileEditForm, HABILITATIONS_PESAGE, HABILITATIONS_PEAGE,
    HABILITATIONS_MULTI_POSTES, clean_habilitation_poste,
    get_postes_pour_habilitation, habilitation_requiert_poste,
    get_type_poste_requis, FILTRAGE_POSTES_JS, PERMISSIONS_CSS
)

# ===================================================================
# IMPORTS DES UTILITAIRES COMMUNS AVEC PERMISSIONS GRANULAIRES
# ===================================================================
from common.utils import *

# ===================================================================
# IMPORTS DES MIXINS AVEC PERMISSIONS GRANULAIRES
# ===================================================================
from common.mixins import *

logger = logging.getLogger('supper')


# ===================================================================
# FONCTIONS UTILITAIRES DE VÉRIFICATION DES PERMISSIONS
# ===================================================================

def check_granular_permission(user, permission_field):
    """
    Vérifie une permission granulaire spécifique sur l'utilisateur.
    
    Args:
        user: Instance UtilisateurSUPPER
        permission_field: Nom du champ de permission (ex: 'peut_gerer_utilisateurs')
    
    Returns:
        bool: True si permission accordée
    """
    if not user.is_authenticated:
        return False
    
    # Superuser a toutes les permissions
    if user.is_superuser:
        return True
    
    # Vérifier la permission spécifique
    return getattr(user, permission_field, False)


def check_admin_permission(user):
    """
    Vérifie les permissions administrateur (version améliorée avec granularité).
    Compatible avec l'ancienne fonction _check_admin_permission.
    
    Args:
        user: Instance UtilisateurSUPPER
    
    Returns:
        bool: True si l'utilisateur a des droits admin
    """
    if not user.is_authenticated:
        return False
    
    # Superuser ou staff
    if user.is_superuser or user.is_staff:
        return True
    
    # Habilitations avec droits admin
    if user.habilitation in HABILITATIONS_ADMIN:
        return True
    
    # Services centraux avec droits étendus
    if user.habilitation in HABILITATIONS_SERVICES_CENTRAUX:
        return True
    
    return False


def check_user_management_permission(user):
    """
    Vérifie si l'utilisateur peut gérer les utilisateurs.
    
    Args:
        user: Instance UtilisateurSUPPER
    
    Returns:
        bool: True si peut gérer les utilisateurs
    """
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    return getattr(user, 'peut_gerer_utilisateurs', False)


def check_poste_management_permission(user):
    """
    Vérifie si l'utilisateur peut gérer les postes.
    
    Args:
        user: Instance UtilisateurSUPPER
    
    Returns:
        bool: True si peut gérer les postes
    """
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    return getattr(user, 'peut_gerer_postes', False)


def check_audit_permission(user):
    """
    Vérifie si l'utilisateur peut consulter le journal d'audit.
    
    Args:
        user: Instance UtilisateurSUPPER
    
    Returns:
        bool: True si peut voir le journal d'audit
    """
    if not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
    
    return getattr(user, 'peut_voir_journal_audit', False)


# Alias pour compatibilité avec l'ancien code
_check_admin_permission = check_admin_permission


def _log_admin_access(request, action):
    """
    Journalise l'accès aux sections admin avec description contextuelle.
    
    Args:
        request: HttpRequest
        action: Description de l'action
    """
    try:
        user_desc = get_user_short_description(request.user)
        
        JournalAudit.objects.create(
            utilisateur=request.user,
            action=f"Accès admin - {action}",
            details=f"{user_desc} a accédé à: {action}",
            adresse_ip=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            url_acces=request.path,
            methode_http=request.method,
            succes=True
        )
        
        logger.info(f"ACCÈS ADMIN - {request.user.username} -> {action}")
        
    except Exception as e:
        logger.error(f"Erreur journalisation admin access: {str(e)}")


# ===================================================================
# DÉCORATEURS DE PERMISSIONS GRANULAIRES POUR VUES FONCTIONNELLES
# ===================================================================

def permission_required_granular(permission_field, redirect_url=None):
    """
    Décorateur pour exiger une permission granulaire sur une vue fonctionnelle.
    
    Args:
        permission_field: Nom du champ de permission
        redirect_url: URL de redirection si permission refusée
    
    Usage:
        @permission_required_granular('peut_gerer_utilisateurs')
        def ma_vue(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not check_granular_permission(request.user, permission_field):
                log_acces_refuse(
                    request.user,
                    f"Permission '{permission_field}' requise",
                    request
                )
                messages.error(
                    request,
                    _("Vous n'avez pas la permission requise pour cette action.")
                )
                if redirect_url:
                    return redirect(redirect_url)
                return redirect('common:dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def habilitation_required_view(*habilitations):
    """
    Décorateur pour exiger une habilitation spécifique sur une vue fonctionnelle.
    
    Args:
        habilitations: Liste des habilitations acceptées
    
    Usage:
        @habilitation_required_view('admin_principal', 'coord_psrr')
        def ma_vue(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.habilitation not in habilitations:
                if not request.user.is_superuser:
                    log_acces_refuse(
                        request.user,
                        f"Habilitation requise: {', '.join(habilitations)}",
                        request
                    )
                    messages.error(
                        request,
                        _("Votre habilitation ne permet pas d'accéder à cette fonction.")
                    )
                    return redirect('common:dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ===================================================================
# VUES D'AUTHENTIFICATION
# ===================================================================

class CustomLoginView(BilingualMixin, LoginView):
    """
    Vue de connexion personnalisée avec journalisation automatique.
    Utilise CustomLoginForm pour messages d'erreur détaillés.
    """
    
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True
    form_class = CustomLoginForm
    
    def get_form_kwargs(self):
        """Ajouter la requête au formulaire pour l'authentification"""
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request
        return kwargs
    
    def form_valid(self, form):
        """
        Traitement du formulaire de connexion valide.
        Journalise la connexion avec description contextuelle.
        """
        response = super().form_valid(form)
        user = self.request.user
        
        # Description contextuelle de l'utilisateur
        user_desc = get_user_description(user)
        
        # Message de bienvenue personnalisé selon le rôle
        messages.success(
            self.request,
            f"✓ Bienvenue {user.nom_complet} ! Connexion réussie."
        )
        
        # Journaliser la connexion avec contexte
        log_user_action(
            user=user,
            action="Connexion réussie",
            details=f"{user_desc} s'est connecté depuis {self.request.META.get('REMOTE_ADDR', 'IP inconnue')}",
            request=self.request
        )
        
        # Redirection vers le dashboard commun
        return redirect('common:dashboard')
    
    def form_invalid(self, form):
        """
        Traitement du formulaire de connexion invalide.
        Les messages d'erreur spécifiques sont gérés dans CustomLoginForm.
        """
        # Journaliser les tentatives échouées
        username = form.data.get('username', '').upper()
        if username:
            try:
                user = UtilisateurSUPPER.objects.get(username=username)
                log_user_action(
                    user=user,
                    action="TENTATIVE CONNEXION ÉCHOUÉE",
                    details=f"Tentative échouée depuis {self.request.META.get('REMOTE_ADDR', 'IP inconnue')}",
                    request=self.request
                )
            except UtilisateurSUPPER.DoesNotExist:
                logger.warning(
                    f"Tentative connexion matricule inexistant: {username} "
                    f"depuis IP: {self.request.META.get('REMOTE_ADDR')}"
                )
        
        return super().form_invalid(form)
    
    def get_context_data(self, **kwargs):
        """Ajouter des données au contexte du template"""
        context = super().get_context_data(**kwargs)
        context.update({
            'title': _('Connexion SUPPER'),
            'app_name': 'SUPPER',
            'subtitle': _('Suivi des Péages et Pesages Routiers'),
        })
        return context


class CustomLogoutView(View):
    """Vue personnalisée pour la déconnexion avec journalisation"""
    
    def get(self, request):
        return self.logout_user(request)
    
    def post(self, request):
        return self.logout_user(request)
    
    def logout_user(self, request):
        if request.user.is_authenticated:
            user_desc = get_user_short_description(request.user)
            
            log_user_action(
                request.user,
                "Déconnexion volontaire",
                f"{user_desc} s'est déconnecté",
                request
            )
            
            messages.success(request, _("Vous avez été déconnecté avec succès."))
            logout(request)
        
        return redirect('accounts:login')


# ===================================================================
# GESTION DU PROFIL UTILISATEUR
# ===================================================================

class ProfileView(LoginRequiredMixin, BilingualMixin, AuditMixin, TemplateView):
    """
    Vue du profil utilisateur personnel.
    Accessible à tous les utilisateurs connectés.
    """
    
    template_name = 'accounts/profile.html'
    audit_action = _("Consultation profil personnel")
    audit_log_get = False  # Ne pas journaliser les simples consultations
    
    def get_context_data(self, **kwargs):
        """Préparer les données du profil utilisateur"""
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        # Description contextuelle de l'utilisateur
        user_desc = get_user_description(user)
        user_category = get_user_category(user)
        niveau_acces = get_niveau_acces(user)
        
        # Permissions organisées par catégorie
        permissions_by_category = self._get_permissions_by_category(user)
        
        # Actions récentes de l'utilisateur
        recent_actions = JournalAudit.objects.filter(
            utilisateur=user
        ).order_by('-timestamp')[:10]
        
        # Statistiques personnelles
        stats_user = self._get_user_stats(user)
        
        # Notifications non lues
        notifications_non_lues = NotificationUtilisateur.objects.filter(
            destinataire=user,
            lu=False
        ).count()
        
        context.update({
            'user': user,
            'user_description': user_desc,
            'user_category': user_category,
            'niveau_acces': niveau_acces,
            'permissions_by_category': permissions_by_category,
            'poste_affectation': user.poste_affectation,
            'recent_actions': recent_actions,
            'stats_user': stats_user,
            'notifications_non_lues': notifications_non_lues,
            'account_info': {
                'created_date': user.date_creation,
                'last_modified': user.date_modification,
                'last_login': user.last_login,
                'account_age_days': (timezone.now() - user.date_creation).days,
            },
            'title': _('Mon Profil'),
        })
        
        return context
    
    def _get_permissions_by_category(self, user):
        """Organise les permissions par catégorie pour l'affichage"""
        categories = {
            'Accès Global': [],
            'Inventaires': [],
            'Recettes Péage': [],
            'Quittances Péage': [],
            'Pesage': [],
            'Stock Péage': [],
            'Gestion': [],
            'Rapports': [],
        }
        
        # Mapping des permissions vers catégories
        permission_mapping = {
            # Accès Global
            'acces_tous_postes': ('Accès Global', 'Accès à tous les postes'),
            'peut_saisir_peage': ('Accès Global', 'Saisie données péage'),
            'peut_saisir_pesage': ('Accès Global', 'Saisie données pesage'),
            'voir_recettes_potentielles': ('Accès Global', 'Voir recettes potentielles'),
            'voir_taux_deperdition': ('Accès Global', 'Voir taux de déperdition'),
            # Inventaires
            'peut_saisir_inventaire_normal': ('Inventaires', 'Saisie inventaire normal'),
            'peut_saisir_inventaire_admin': ('Inventaires', 'Saisie inventaire administratif'),
            'peut_programmer_inventaire': ('Inventaires', 'Programmer inventaires'),
            'peut_voir_stats_deperdition': ('Inventaires', 'Statistiques déperdition'),
            # Recettes Péage
            'peut_saisir_recette_peage': ('Recettes Péage', 'Saisie recettes'),
            'peut_voir_liste_recettes_peage': ('Recettes Péage', 'Consulter recettes'),
            'peut_importer_recettes_peage': ('Recettes Péage', 'Importer recettes'),
            # Quittances
            'peut_saisir_quittance_peage': ('Quittances Péage', 'Saisie quittances'),
            'peut_comptabiliser_quittances_peage': ('Quittances Péage', 'Comptabiliser'),
            # Pesage
            'peut_saisir_amende': ('Pesage', 'Saisie amendes'),
            'peut_valider_paiement_amende': ('Pesage', 'Valider paiements'),
            'peut_voir_stats_pesage': ('Pesage', 'Statistiques pesage'),
            # Stock
            'peut_charger_stock_peage': ('Stock Péage', 'Charger stock'),
            'peut_transferer_stock_peage': ('Stock Péage', 'Transférer stock'),
            'peut_voir_tracabilite_tickets': ('Stock Péage', 'Traçabilité tickets'),
            # Gestion
            'peut_gerer_postes': ('Gestion', 'Gérer postes'),
            'peut_gerer_utilisateurs': ('Gestion', 'Gérer utilisateurs'),
            'peut_voir_journal_audit': ('Gestion', 'Journal d\'audit'),
            # Rapports
            'peut_voir_rapports_defaillants_peage': ('Rapports', 'Rapports défaillants péage'),
            'peut_voir_rapports_defaillants_pesage': ('Rapports', 'Rapports défaillants pesage'),
            'peut_voir_classement_peage_rendement': ('Rapports', 'Classement rendement'),
        }
        
        for field_name, (category, label) in permission_mapping.items():
            if hasattr(user, field_name) and getattr(user, field_name):
                categories[category].append(label)
        
        # Retirer les catégories vides
        return {k: v for k, v in categories.items() if v}
    
    def _get_user_stats(self, user):
        """Calcule les statistiques de l'utilisateur"""
        today = timezone.now().date()
        month_start = today.replace(day=1)
        
        return {
            'nb_connexions': JournalAudit.objects.filter(
                utilisateur=user,
                action__icontains='connexion'
            ).count(),
            'derniere_connexion': user.last_login,
            'nb_actions_mois': JournalAudit.objects.filter(
                utilisateur=user,
                timestamp__gte=month_start
            ).count(),
            'nb_actions_today': JournalAudit.objects.filter(
                utilisateur=user,
                timestamp__date=today
            ).count(),
        }


class EditProfileView(LoginRequiredMixin, BilingualMixin, AuditMixin, UpdateView):
    """
    Vue pour permettre à un utilisateur de modifier son propre profil.
    Champs modifiables limités (nom, téléphone, email, photo).
    """
    
    model = UtilisateurSUPPER
    form_class = ProfileEditForm
    template_name = 'accounts/profile_edit.html'
    success_url = reverse_lazy('accounts:profile')
    audit_action = _("Modification profil personnel")
    
    def get_object(self, queryset=None):
        """Retourne l'utilisateur connecté"""
        return self.request.user
    
    def form_valid(self, form):
        """Traitement après validation du formulaire"""
        # Détecter les changements
        changes = []
        if form.has_changed():
            for field in form.changed_data:
                old_value = getattr(self.request.user, field, None)
                new_value = form.cleaned_data.get(field)
                changes.append(f"{field}: {old_value} → {new_value}")
        
        response = super().form_valid(form)
        
        # Message de succès
        messages.success(
            self.request, 
            _("Votre profil a été mis à jour avec succès.")
        )
        
        # Journalisation détaillée
        user_desc = get_user_short_description(self.request.user)
        log_user_action(
            self.request.user,
            "Modification profil personnel",
            f"{user_desc} a modifié son profil. Changements: {', '.join(changes)}" if changes else f"{user_desc} a consulté son profil sans modifications",
            self.request
        )
        
        return response
    
    def get_context_data(self, **kwargs):
        """Ajouter des données au contexte"""
        context = super().get_context_data(**kwargs)
        context.update({
            'title': _("Modifier mon profil"),
            'user_description': get_user_description(self.request.user),
        })
        return context


class ChangePasswordView(LoginRequiredMixin, BilingualMixin, AuditMixin, FormView):
    """
    Vue pour permettre aux utilisateurs de changer leur mot de passe.
    Validation simplifiée (4 caractères minimum) selon les specs SUPPER.
    """
    
    template_name = 'accounts/password_change.html'
    form_class = PasswordChangeForm
    success_url = reverse_lazy('accounts:profile')
    audit_action = _("Changement de mot de passe")
    
    def get_form_kwargs(self):
        """Passer l'utilisateur au formulaire"""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        """Traitement du changement de mot de passe réussi"""
        user = self.request.user
        
        # Changer le mot de passe
        user.set_password(form.cleaned_data['nouveau_mot_de_passe'])
        user.save()
        
        # Maintenir la session active après le changement
        update_session_auth_hash(self.request, user)
        
        # Message de succès
        messages.success(
            self.request, 
            _("Votre mot de passe a été modifié avec succès.")
        )
        
        # Journalisation
        user_desc = get_user_short_description(user)
        log_user_action(
            user,
            "Changement mot de passe",
            f"{user_desc} a changé son mot de passe",
            self.request
        )
        
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        """Ajouter des données au contexte"""
        context = super().get_context_data(**kwargs)
        context.update({
            'title': _("Changer mon mot de passe"),
            'user_description': get_user_description(self.request.user),
        })
        return context


# ===================================================================
# GESTION DES UTILISATEURS (AVEC PERMISSIONS GRANULAIRES)
# ===================================================================

class UserListView(GestionUtilisateursPermissionMixin, BilingualMixin, 
                   PaginationMixin, AuditMixin, ListView):
    """
    Liste des utilisateurs avec filtres et pagination.
    Requiert la permission 'peut_gerer_utilisateurs'.
    """
    
    model = UtilisateurSUPPER
    template_name = 'accounts/liste_utilisateurs.html'
    context_object_name = 'users'
    paginate_by = 25
    audit_action = _("Consultation liste utilisateurs")
    audit_log_get = False
    
    def get_queryset(self):
        """Filtrer selon les paramètres GET"""
        queryset = super().get_queryset().select_related('poste_affectation')
        
        # Filtres
        search = self.request.GET.get('search', '')
        habilitation_filter = self.request.GET.get('habilitation', '')
        actif_filter = self.request.GET.get('actif', '')
        poste_filter = self.request.GET.get('poste', '')
        
        if search:
            queryset = queryset.filter(
                Q(nom_complet__icontains=search) |
                Q(username__icontains=search) |
                Q(telephone__icontains=search) |
                Q(email__icontains=search)
            )
        
        if habilitation_filter:
            queryset = queryset.filter(habilitation=habilitation_filter)
        
        if actif_filter:
            queryset = queryset.filter(is_active=actif_filter == 'true')
        
        if poste_filter:
            queryset = queryset.filter(poste_affectation_id=poste_filter)
        
        return queryset.order_by('-date_creation')
    
    def get_context_data(self, **kwargs):
        """Enrichir le contexte avec statistiques et filtres"""
        context = super().get_context_data(**kwargs)
        
        # Statistiques
        context['stats'] = {
            'total': UtilisateurSUPPER.objects.count(),
            'actifs': UtilisateurSUPPER.objects.filter(is_active=True).count(),
            'admins': UtilisateurSUPPER.objects.filter(
                habilitation__in=HABILITATIONS_ADMIN
            ).count(),
            'agents_peage': UtilisateurSUPPER.objects.filter(
                habilitation__in=HABILITATIONS_CHEFS_PEAGE + HABILITATIONS_OPERATIONNELS_PEAGE
            ).count(),
            'agents_pesage': UtilisateurSUPPER.objects.filter(
                habilitation__in=HABILITATIONS_CHEFS_PESAGE + HABILITATIONS_OPERATIONNELS_PESAGE
            ).count(),
        }
        
        # Valeurs des filtres actuels
        context['search'] = self.request.GET.get('search', '')
        context['habilitation_filter'] = self.request.GET.get('habilitation', '')
        context['actif_filter'] = self.request.GET.get('actif', '')
        context['poste_filter'] = self.request.GET.get('poste', '')
        
        # Listes pour les filtres
        context['habilitations'] = Habilitation.choices
        context['postes'] = Poste.objects.filter(is_active=True).order_by('nom')
        
        context['title'] = _('Gestion des Utilisateurs')
        
        return context


@login_required
@permission_required_granular('peut_gerer_utilisateurs')
def liste_utilisateurs(request):
    """
    Vue fonctionnelle pour lister tous les utilisateurs.
    Alternative à UserListView pour plus de flexibilité.
    """
    # Filtres
    search = request.GET.get('search', '')
    habilitation_filter = request.GET.get('habilitation', '')
    actif_filter = request.GET.get('actif', '')
    poste_filter = request.GET.get('poste', '')
    
    # Construction de la requête
    users = UtilisateurSUPPER.objects.select_related('poste_affectation').all()
    
    if search:
        users = users.filter(
            Q(nom_complet__icontains=search) |
            Q(username__icontains=search) |
            Q(telephone__icontains=search) |
            Q(email__icontains=search)
        )
    
    if habilitation_filter:
        users = users.filter(habilitation=habilitation_filter)
    
    if actif_filter:
        users = users.filter(is_active=actif_filter == 'true')
    
    if poste_filter:
        users = users.filter(poste_affectation_id=poste_filter)
    
    users = users.order_by('-date_creation')
    
    # Pagination
    paginator = Paginator(users, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistiques - CORRIGÉES
    stats = {
        'total': UtilisateurSUPPER.objects.count(),
        'actifs': UtilisateurSUPPER.objects.filter(is_active=True).count(),
        'admins': UtilisateurSUPPER.objects.filter(
            habilitation__in=['admin_principal', 'coord_psrr', 'serv_info']
        ).count(),
        # AJOUT: Agents affectés à des postes de péage
        'agents_peage': UtilisateurSUPPER.objects.filter(
            poste_affectation__type='peage',
            is_active=True
        ).count(),
        # AJOUT: Agents affectés à des postes de pesage
        'agents_pesage': UtilisateurSUPPER.objects.filter(
            poste_affectation__type='pesage',
            is_active=True
        ).count(),
        # Agents inventaire
        'agents': UtilisateurSUPPER.objects.filter(
            habilitation='agent_inventaire'
        ).count(),
    }
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'search': search,
        'habilitation_filter': habilitation_filter,
        'actif_filter': actif_filter,
        'poste_filter': poste_filter,
        'habilitations': Habilitation.choices,
        'postes': Poste.objects.filter(is_active=True).order_by('nom'),
        'title': _('Gestion des Utilisateurs'),
        'user_description': get_user_short_description(request.user),
    }
    
    return render(request, 'accounts/liste_utilisateurs.html', context)

TOUTES_PERMISSIONS_FORMULAIRE = {
    'acces_global': {
        'label': 'Accès Global',
        'permissions': [
            ('acces_tous_postes', 'Accès à tous les postes'),
            ('peut_saisir_peage', 'Peut saisir données péage'),
            ('peut_saisir_pesage', 'Peut saisir données pesage'),
            ('voir_recettes_potentielles', 'Voir recettes potentielles'),
            ('voir_taux_deperdition', 'Voir taux de déperdition'),
            ('voir_statistiques_globales', 'Voir statistiques globales'),
            ('peut_saisir_pour_autres_postes', 'Saisir pour autres postes'),
        ]
    },
    'inventaires': {
        'label': 'Inventaires',
        'permissions': [
            ('peut_saisir_inventaire_normal', 'Saisie inventaire normal'),
            ('peut_saisir_inventaire_admin', 'Saisie inventaire administratif'),
            ('peut_programmer_inventaire', 'Programmer inventaires'),
            ('peut_voir_programmation_active', 'Voir programmation active'),
            ('peut_desactiver_programmation', 'Désactiver programmation'),
            ('peut_voir_programmation_desactivee', 'Voir programmation désactivée'),
            ('peut_voir_liste_inventaires', 'Voir liste inventaires'),
            ('peut_voir_liste_inventaires_admin', 'Voir liste inventaires admin'),
            ('peut_voir_jours_impertinents', 'Voir jours impertinents'),
            ('peut_voir_stats_deperdition', 'Voir stats déperdition'),
        ]
    },
    'recettes_peage': {
        'label': 'Recettes Péage',
        'permissions': [
            ('peut_saisir_recette_peage', 'Saisie recettes péage'),
            ('peut_voir_liste_recettes_peage', 'Voir liste recettes péage'),
            ('peut_voir_stats_recettes_peage', 'Voir stats recettes péage'),
            ('peut_importer_recettes_peage', 'Importer recettes péage'),
            ('peut_voir_evolution_peage', 'Voir évolution péage'),
            ('peut_voir_objectifs_peage', 'Voir objectifs péage'),
        ]
    },
    'quittances_peage': {
        'label': 'Quittances Péage',
        'permissions': [
            ('peut_saisir_quittance_peage', 'Saisie quittances péage'),
            ('peut_voir_liste_quittances_peage', 'Voir liste quittances péage'),
            ('peut_comptabiliser_quittances_peage', 'Comptabiliser quittances péage'),
        ]
    },
    'pesage': {
        'label': 'Pesage',
        'permissions': [
            ('peut_voir_historique_vehicule_pesage', 'Voir historique véhicules'),
            ('peut_saisir_amende', 'Saisie amendes'),
            ('peut_saisir_pesee_jour', 'Saisie pesées du jour'),
            ('peut_voir_objectifs_pesage', 'Voir objectifs pesage'),
            ('peut_valider_paiement_amende', 'Valider paiements amendes'),
            ('peut_lister_amendes', 'Lister amendes'),
            ('peut_saisir_quittance_pesage', 'Saisie quittances pesage'),
            ('peut_comptabiliser_quittances_pesage', 'Comptabiliser quittances pesage'),
            ('peut_voir_liste_quittancements_pesage', 'Voir liste quittancements'),
            ('peut_voir_historique_pesees', 'Voir historique pesées'),
            ('peut_voir_recettes_pesage', 'Voir recettes pesage'),
            ('peut_voir_stats_pesage', 'Voir stats pesage'),
        ]
    },
    'stock_peage': {
        'label': 'Stock Péage',
        'permissions': [
            ('peut_charger_stock_peage', 'Charger stock péage'),
            ('peut_voir_liste_stocks_peage', 'Voir liste stocks péage'),
            ('peut_voir_stock_date_peage', 'Voir stock à date'),
            ('peut_transferer_stock_peage', 'Transférer stock péage'),
            ('peut_voir_tracabilite_tickets', 'Voir traçabilité tickets'),
            ('peut_voir_bordereaux_peage', 'Voir bordereaux péage'),
            ('peut_voir_mon_stock_peage', 'Voir mon stock péage'),
            ('peut_voir_historique_stock_peage', 'Voir historique stock'),
            ('peut_simuler_commandes_peage', 'Simuler commandes péage'),
        ]
    },
    'gestion': {
        'label': 'Gestion',
        'permissions': [
            ('peut_gerer_postes', 'Gérer postes'),
            ('peut_ajouter_poste', 'Ajouter poste'),
            ('peut_creer_poste_masse', 'Créer postes en masse'),
            ('peut_gerer_utilisateurs', 'Gérer utilisateurs'),
            ('peut_creer_utilisateur', 'Créer utilisateur'),
            ('peut_voir_journal_audit', 'Voir journal audit'),
        ]
    },
    'rapports': {
        'label': 'Rapports',
        'permissions': [
            ('peut_voir_rapports_defaillants_peage', 'Rapports défaillants péage'),
            ('peut_voir_rapports_defaillants_pesage', 'Rapports défaillants pesage'),
            ('peut_voir_rapport_inventaires', 'Rapport inventaires'),
            ('peut_voir_classement_peage_rendement', 'Classement péage rendement'),
            ('peut_voir_classement_station_pesage', 'Classement stations pesage'),
            ('peut_voir_classement_peage_deperdition', 'Classement péage déperdition'),
            ('peut_voir_classement_agents_inventaire', 'Classement agents inventaire'),
        ]
    },
    'autres': {
        'label': 'Autres',
        'permissions': [
            ('peut_parametrage_global', 'Paramétrage global'),
            ('peut_voir_compte_emploi', 'Voir compte emploi'),
            ('peut_voir_pv_confrontation', 'Voir PV confrontation'),
            ('peut_authentifier_document', 'Authentifier document'),
            ('peut_voir_tous_postes', 'Voir tous les postes'),
        ]
    },
    'modules_legacy': {
        'label': 'Modules (Legacy)',
        'permissions': [
            ('peut_gerer_peage', 'Gérer péage'),
            ('peut_gerer_pesage', 'Gérer pesage'),
            ('peut_gerer_personnel', 'Gérer personnel'),
            ('peut_gerer_budget', 'Gérer budget'),
            ('peut_gerer_inventaire', 'Gérer inventaire'),
            ('peut_gerer_archives', 'Gérer archives'),
            ('peut_gerer_stocks_psrr', 'Gérer stocks PSRR'),
            ('peut_gerer_stock_info', 'Gérer stock info'),
        ]
    },
}

# Liste plate de toutes les permissions (pour itération)
LISTE_PERMISSIONS_FLAT = []
for category, data in TOUTES_PERMISSIONS_FORMULAIRE.items():
    for perm_code, perm_label in data['permissions']:
        LISTE_PERMISSIONS_FLAT.append(perm_code)


def _appliquer_permissions_formulaire(user, post_data):
    """
    Applique les permissions cochées/décochées dans le formulaire.
    
    Args:
        user: Instance UtilisateurSUPPER (non sauvegardée)
        post_data: request.POST contenant les checkboxes
    
    Note:
        Les checkboxes non cochées n'apparaissent PAS dans POST.
        On doit donc vérifier la présence de chaque permission dans POST.
    """
    for perm_code in LISTE_PERMISSIONS_FLAT:
        # Si la checkbox est cochée, elle sera dans POST
        # Si elle n'est pas cochée, elle n'y sera pas
        value = perm_code in post_data
        if hasattr(user, perm_code):
            setattr(user, perm_code, value)
    
    logger.debug(f"Permissions appliquées pour {user.username} depuis formulaire")


def _detecter_modifications_permissions(user, post_data):
    """
    Détecte si des permissions ont été modifiées par rapport à l'état actuel.
    
    Args:
        user: Instance UtilisateurSUPPER (état actuel en base)
        post_data: request.POST contenant les checkboxes
    
    Returns:
        tuple: (bool, list) - (modifié, liste des changements)
    """
    changes = []
    
    for perm_code in LISTE_PERMISSIONS_FLAT:
        current_value = getattr(user, perm_code, False)
        form_value = perm_code in post_data
        
        if current_value != form_value:
            changes.append({
                'permission': perm_code,
                'old': current_value,
                'new': form_value
            })
    
    return len(changes) > 0, changes


def _get_permissions_context(user=None):
    """
    Prépare le contexte des permissions pour le template.
    
    Args:
        user: Instance UtilisateurSUPPER (optionnel, pour pré-remplir les valeurs)
    
    Returns:
        dict: Permissions organisées par catégorie avec valeurs actuelles
    """
    context = {}
    
    for category_key, category_data in TOUTES_PERMISSIONS_FORMULAIRE.items():
        context[category_key] = {
            'label': category_data['label'],
            'permissions': []
        }
        
        for perm_code, perm_label in category_data['permissions']:
            perm_info = {
                'code': perm_code,
                'label': perm_label,
                'value': getattr(user, perm_code, False) if user else False
            }
            context[category_key]['permissions'].append(perm_info)
    
    return context


# ===================================================================
# VUE creer_utilisateur CORRIGÉE
# ===================================================================

from .views_permissions_helpers import (
    preparer_contexte_permissions_creation,
    preparer_contexte_permissions_modification,
    detecter_modifications_permissions,
    appliquer_permissions_formulaire,
)

@login_required
@permission_required_granular('peut_gerer_utilisateurs')
def creer_utilisateur(request):
    from .models import UtilisateurSUPPER, Poste, Habilitation
    from .forms import UserCreateForm
    from common.utils import log_user_action
    
    if request.method == 'POST':
        form = UserCreateForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Créer l'utilisateur
                    user = form.save(commit=False)
                    user.save()  # Déclenche attribuer_permissions_automatiques()
                    
                    # Vérifier et appliquer les personnalisations
                    has_custom_perms, perm_changes = detecter_modifications_permissions(user, request.POST)
                    
                    if has_custom_perms:
                        appliquer_permissions_formulaire(user, request.POST)
                        user.save(skip_auto_permissions=True)
                    
                    # Journalisation...
                    
                    messages.success(request, f"Utilisateur {user.nom_complet} créé.")
                    return redirect('accounts:detail_utilisateur', user_id=user.id)
                    
            except Exception as e:
                messages.error(request, f"Erreur: {str(e)}")
    else:
        form = UserCreateForm()
    
    # Préparer le contexte
    context = {
        'form': form,
        'postes_peage': Poste.objects.filter(is_active=True, type='peage').order_by('nom'),
        'postes_pesage': Poste.objects.filter(is_active=True, type='pesage').order_by('nom'),
        'habilitations': Habilitation.choices,
        'title': 'Créer un Utilisateur',
    }
    
    # Ajouter le contexte des permissions
    context.update(preparer_contexte_permissions_creation())
    
    return render(request, 'accounts/creer_utilisateur.html', context)

@login_required
@permission_required_granular('peut_gerer_utilisateurs')
def modifier_utilisateur(request, user_id):
    from .models import UtilisateurSUPPER, Poste, Habilitation
    from .forms import UserUpdateForm
    from common.utils import log_user_action
    
    user_to_edit = get_object_or_404(UtilisateurSUPPER, id=user_id)
    old_habilitation = user_to_edit.habilitation
    
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, request.FILES, instance=user_to_edit)
        
        if form.is_valid():
            user_updated = form.save(commit=False)
            
            # Détecter si l'habilitation a changé
            habilitation_changed = old_habilitation != user_updated.habilitation
            
            if habilitation_changed:
                # Recalculer les permissions de base
                user_updated.attribuer_permissions_automatiques()
                # Puis appliquer les personnalisations du formulaire
                appliquer_permissions_formulaire(user_updated, request.POST)
                user_updated.save(skip_auto_permissions=True)
            else:
                # Appliquer directement les permissions du formulaire
                appliquer_permissions_formulaire(user_updated, request.POST)
                user_updated.save(skip_auto_permissions=True)
            
            messages.success(request, f"Utilisateur {user_updated.nom_complet} modifié.")
            return redirect('accounts:detail_utilisateur', user_id=user_updated.id)
    else:
        form = UserUpdateForm(instance=user_to_edit)
    
    # Préparer le contexte
    context = {
        'form': form,
        'user_edit': user_to_edit,
        'postes_peage': Poste.objects.filter(is_active=True, type='peage').order_by('nom'),
        'postes_pesage': Poste.objects.filter(is_active=True, type='pesage').order_by('nom'),
        'habilitations': Habilitation.choices,
        'title': f'Modifier - {user_to_edit.nom_complet}',
    }
    
    # Ajouter le contexte des permissions
    context.update(preparer_contexte_permissions_modification(user_to_edit))
    
    return render(request, 'accounts/modifier_utilisateur.html', context)

# ===================================================================
# VUE detail_utilisateur CORRIGÉE
# ===================================================================

@login_required
def detail_utilisateur(request, user_id):
    """
    Vue pour afficher les détails d'un utilisateur avec toutes ses permissions.
    Accessible par l'utilisateur lui-même ou par les gestionnaires.
    """
    from .models import UtilisateurSUPPER, JournalAudit
    from common.utils import (
        get_user_description, get_user_short_description, log_acces_refuse
    )
    from django.utils import timezone
    
    user_detail = get_object_or_404(UtilisateurSUPPER, id=user_id)
    
    # Vérification des permissions
    can_view = (
        request.user == user_detail or  # L'utilisateur consulte son propre profil
        check_user_management_permission(request.user)  # Gestionnaire d'utilisateurs
    )
    
    if not can_view:
        log_acces_refuse(
            request.user,
            f"Tentative consultation profil de {user_detail.username}",
            request
        )
        messages.error(request, _("Accès non autorisé."))
        return redirect('common:dashboard')
    
    # Description contextuelle
    user_desc = get_user_description(user_detail)
    
    # Activités récentes
    activites_recentes = JournalAudit.objects.filter(
        utilisateur=user_detail
    ).order_by('-timestamp')[:15]
    
    # Statistiques utilisateur
    today = timezone.now().date()
    month_start = today.replace(day=1)
    
    stats_user = {
        'nb_connexions': JournalAudit.objects.filter(
            utilisateur=user_detail,
            action__icontains='connexion'
        ).count(),
        'derniere_connexion': user_detail.last_login,
        'nb_actions_mois': JournalAudit.objects.filter(
            utilisateur=user_detail,
            timestamp__gte=month_start
        ).count(),
        'nb_actions_today': JournalAudit.objects.filter(
            utilisateur=user_detail,
            timestamp__date=today
        ).count(),
    }
    
    # Permissions organisées par catégorie avec valeurs actuelles
    permissions_context = _get_permissions_context(user=user_detail)
    
    # Compter les permissions actives
    total_permissions = 0
    permissions_actives = 0
    for category_key, category_data in permissions_context.items():
        for perm in category_data['permissions']:
            total_permissions += 1
            if perm['value']:
                permissions_actives += 1
    
    context = {
        'user_detail': user_detail,
        'user_description': user_desc,
        'activites_recentes': activites_recentes,
        'stats_user': stats_user,
        # Permissions organisées
        'permissions_categories': permissions_context,
        'total_permissions': total_permissions,
        'permissions_actives': permissions_actives,
        # Droits de l'utilisateur consultant
        'can_edit': check_user_management_permission(request.user),
        'title': f'Profil - {user_detail.nom_complet}',
    }
    
    return render(request, 'accounts/detail_utilisateur.html', context)

class PasswordResetView(GestionUtilisateursPermissionMixin, BilingualMixin, 
                        AuditMixin, View):
    """
    Vue pour la réinitialisation de mot de passe par un administrateur.
    Requiert la permission 'peut_gerer_utilisateurs'.
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
            
            # Journalisation détaillée
            user_desc = get_user_short_description(request.user)
            target_desc = get_user_short_description(user_to_reset)
            
            log_user_action(
                user=request.user,
                action="Réinitialisation mot de passe administrateur",
                details=f"{user_desc} a réinitialisé le mot de passe de {target_desc}",
                request=request
            )
            
            messages.success(
                request,
                _("Mot de passe de %(nom)s réinitialisé avec succès.") % {
                    'nom': user_to_reset.nom_complet
                }
            )
            
            return redirect('accounts:user_list')
        
        context = {
            'user_to_reset': user_to_reset,
            'form': form,
            'title': _('Réinitialiser le mot de passe de %(nom)s') % {
                'nom': user_to_reset.nom_complet
            }
        }
        
        return render(request, self.template_name, context)




# ===================================================================
# DICTIONNAIRE DES PERMISSIONS PAR HABILITATION
# Correspond aux méthodes _configurer_xxx du modèle UtilisateurSUPPER
# ===================================================================

PERMISSIONS_PAR_HABILITATION = {
    # ADMINISTRATEUR PRINCIPAL - Accès total système
    'admin_principal': [
        # Inventaires (10)
        'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin', 'peut_programmer_inventaire',
        'peut_voir_programmation_active', 'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
        'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin', 'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        # Recettes Péage (6)
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_importer_recettes_peage', 'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage (3)
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Pesage (12)
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
        'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Stock Péage (9)
        'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage', 'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage', 'peut_simuler_commandes_peage',
        # Gestion (6)
        'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
        'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit',
        # Rapports (7)
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        # Autres (5)
        'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
        'peut_authentifier_document', 'peut_voir_tous_postes',
    ],

    # COORDONNATEUR PSRR - Accès complet système
    'coord_psrr': [
        # Inventaires
        'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin', 'peut_programmer_inventaire',
        'peut_voir_programmation_active', 'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
        'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin', 'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        # Recettes Péage
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_importer_recettes_peage', 'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
        'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Stock Péage
        'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage', 'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage', 'peut_simuler_commandes_peage',
        # Gestion
        'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
        'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit',
        # Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        # Autres
        'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
        'peut_authentifier_document', 'peut_voir_tous_postes',
    ],

    # SERVICE INFORMATIQUE - Accès complet système + maintenance
    'serv_info': [
        # Inventaires
        'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin', 'peut_programmer_inventaire',
        'peut_voir_programmation_active', 'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
        'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin', 'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        # Recettes Péage
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_importer_recettes_peage', 'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
        'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Stock Péage
        'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage', 'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage', 'peut_simuler_commandes_peage',
        # Gestion
        'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
        'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit',
        # Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        # Autres
        'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
        'peut_authentifier_document', 'peut_voir_tous_postes',
    ],

    # SERVICE ÉMISSIONS ET RECOUVREMENT - Gestion financière
    'serv_emission': [
        # Inventaires
        'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin', 'peut_programmer_inventaire',
        'peut_voir_programmation_active', 'peut_voir_programmation_desactivee',
        'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin', 'peut_voir_jours_impertinents',
        'peut_voir_stats_deperdition',
        # Recettes Péage
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Pesage
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Stock Péage
        'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_transferer_stock_peage', 'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage', 'peut_simuler_commandes_peage',
        # Rapports
        'peut_voir_classement_peage_rendement', 'peut_voir_classement_station_pesage',
        'peut_voir_classement_peage_deperdition', 'peut_voir_classement_agents_inventaire',
        # Autres
        'peut_voir_compte_emploi', 'peut_voir_pv_confrontation', 'peut_authentifier_document',
        'peut_voir_tous_postes',
    ],

    # SERVICE DES AFFAIRES GÉNÉRALES - Gestion RH et administrative
    'chef_ag': [
        # Gestion
        'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
        'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit',
        # Autres
        'peut_parametrage_global', 'peut_voir_tous_postes',
    ],

    # SERVICE CONTRÔLE ET VALIDATION - Audit et validation
    'serv_controle': [
        # Inventaires
        'peut_voir_liste_inventaires', 'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
        # Recettes Péage
        'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage
        'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Pesage
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Stock Péage
        'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage', 'peut_voir_historique_stock_peage',
        # Gestion
        'peut_voir_journal_audit',
        # Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        # Autres
        'peut_parametrage_global', 'peut_voir_compte_emploi', 'peut_voir_pv_confrontation',
        'peut_authentifier_document', 'peut_voir_tous_postes',
    ],

    # SERVICE ORDRE/SECRÉTARIAT - Archivage et documentation
    'serv_ordre': [
        # Inventaires
        'peut_voir_stats_deperdition',
        # Recettes Péage
        'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage
        'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Pesage
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_comptabiliser_quittances_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Stock Péage
        'peut_voir_liste_stocks_peage', 'peut_voir_tracabilite_tickets',
        'peut_voir_bordereaux_peage', 'peut_voir_historique_stock_peage',
        # Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
        # Autres
        'peut_voir_compte_emploi', 'peut_voir_pv_confrontation', 'peut_authentifier_document',
        'peut_voir_tous_postes',
    ],

    # ═══════════════════════════════════════════════════════════════
    # CISOP - Cellules d'Inspection et Suivi des Opérations
    # ═══════════════════════════════════════════════════════════════

    # CISOP PÉAGE - Inspection des postes de péage
    'cisop_peage': [
        # Inventaires
        'peut_voir_liste_inventaires', 'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
        # Recettes Péage
        'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage
        'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Stock Péage
        'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage', 'peut_voir_historique_stock_peage',
        # Rapports
        'peut_voir_rapports_defaillants_peage', 'peut_voir_rapport_inventaires',
        'peut_voir_classement_peage_rendement', 'peut_voir_classement_peage_deperdition',
        'peut_voir_classement_agents_inventaire',
        # Autres
        'peut_voir_compte_emploi', 'peut_voir_pv_confrontation', 'peut_authentifier_document',
        'peut_voir_tous_postes',
    ],

    # CISOP PESAGE - Inspection des stations de pesage
    'cisop_pesage': [
        # Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_voir_liste_quittancements_pesage', 'peut_voir_historique_pesees',
        'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Rapports
        'peut_voir_rapports_defaillants_pesage', 'peut_voir_classement_station_pesage',
        # Autres
        'peut_voir_pv_confrontation', 'peut_authentifier_document', 'peut_voir_tous_postes',
    ],

    # ═══════════════════════════════════════════════════════════════
    # POSTES DE PÉAGE - Accès limité au poste d'affectation
    # ═══════════════════════════════════════════════════════════════

    # CHEF DE POSTE PÉAGE - Gestion complète du poste de péage
    'chef_peage': [
        # Inventaires
        'peut_voir_liste_inventaires', 'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
        'peut_voir_liste_inventaires_admin',
        # Recettes Péage
        'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage', 'peut_voir_stats_recettes_peage',
        'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
        # Quittances Péage
        'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage', 'peut_comptabiliser_quittances_peage',
        # Stock Péage
        'peut_voir_liste_stocks_peage', 'peut_voir_stock_date_peage',
        'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
        'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage',
        # Rapports
        'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
        'peut_voir_classement_peage_deperdition', 'peut_voir_classement_agents_inventaire',
        # Autres
        'peut_voir_compte_emploi', 'peut_authentifier_document',
    ],

    # AGENT INVENTAIRE - Saisie des inventaires uniquement
    'agent_inventaire': [
        # Inventaires - Saisie uniquement
        'peut_saisir_inventaire_normal','peut_voir_liste_inventaires', 'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
        'peut_voir_classement_agents_inventaire',
    ],

    # ═══════════════════════════════════════════════════════════════
    # STATIONS DE PESAGE - Accès limité à la station d'affectation
    # ═══════════════════════════════════════════════════════════════

    # CHEF DE STATION PESAGE - Supervision de la station de pesage
    'chef_station_pesage': [
        # Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende',
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Rapports
        'peut_voir_classement_station_pesage',
        # Autres
        'peut_voir_pv_confrontation', 'peut_authentifier_document',
    ],

    # RÉGISSEUR DE STATION PESAGE - Gestion financière de la station
    'regisseur_pesage': [
        # Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_valider_paiement_amende', 'peut_lister_amendes',
        'peut_saisir_quittance_pesage', 'peut_voir_liste_quittancements_pesage',
        'peut_voir_historique_pesees', 'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
        # Rapports
        'peut_voir_classement_station_pesage',
    ],

    # CHEF D'ÉQUIPE STATION PESAGE - Opérations quotidiennes de pesage
    'chef_equipe_pesage': [
        # Pesage
        'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende', 'peut_saisir_pesee_jour',
        'peut_voir_objectifs_pesage', 'peut_lister_amendes',
        'peut_voir_historique_pesees', 'peut_voir_stats_pesage',
    ],

    # ═══════════════════════════════════════════════════════════════
    # EXTERNES
    # ═══════════════════════════════════════════════════════════════

    # IMPRIMERIE NATIONALE - Consultation historique uniquement
    'imprimerie': [
        # Stock Péage - Historique uniquement
        'peut_voir_historique_stock_peage',
    ],

    
}

# Ajouter les alias pour la rétrocompatibilité
PERMISSIONS_PAR_HABILITATION['chef_pesage'] = PERMISSIONS_PAR_HABILITATION['chef_station_pesage']
PERMISSIONS_PAR_HABILITATION['chef_ordre'] = PERMISSIONS_PAR_HABILITATION['serv_ordre']
PERMISSIONS_PAR_HABILITATION['chef_controle'] = PERMISSIONS_PAR_HABILITATION['serv_controle']


# ===================================================================
# CATÉGORIES DE PERMISSIONS POUR L'AFFICHAGE
# ===================================================================

CATEGORIES_PERMISSIONS = {
    'globales': {
        'label': _('Permissions Globales'),
        'icon': 'fas fa-globe',
        'permissions': [
            ('acces_tous_postes', _('Accès à tous les postes')),
            ('peut_saisir_peage', _('Peut saisir données péage')),
            ('peut_saisir_pesage', _('Peut saisir données pesage')),
            ('voir_recettes_potentielles', _('Voir recettes potentielles')),
            ('voir_taux_deperdition', _('Voir taux de déperdition')),
            ('voir_statistiques_globales', _('Voir statistiques globales')),
            ('peut_saisir_pour_autres_postes', _('Saisir pour autres postes')),
        ]
    },
    'inventaires': {
        'label': _('Inventaires'),
        'icon': 'fas fa-clipboard-list',
        'permissions': [
            ('peut_saisir_inventaire_normal', _('Saisir inventaire normal')),
            ('peut_saisir_inventaire_admin', _('Saisir inventaire admin')),
            ('peut_programmer_inventaire', _('Programmer inventaire')),
            ('peut_voir_programmation_active', _('Voir programmation active')),
            ('peut_desactiver_programmation', _('Désactiver programmation')),
            ('peut_voir_programmation_desactivee', _('Voir prog. désactivées')),
            ('peut_voir_liste_inventaires', _('Voir liste inventaires')),
            ('peut_voir_liste_inventaires_admin', _('Voir liste inv. admin')),
            ('peut_voir_jours_impertinents', _('Voir jours impertinents')),
            ('peut_voir_stats_deperdition', _('Voir stats déperdition')),
        ]
    },
    'recettes_peage': {
        'label': _('Recettes Péage'),
        'icon': 'fas fa-money-bill-wave',
        'permissions': [
            ('peut_saisir_recette_peage', _('Saisir recette péage')),
            ('peut_voir_liste_recettes_peage', _('Voir liste recettes')),
            ('peut_voir_stats_recettes_peage', _('Voir stats recettes')),
            ('peut_importer_recettes_peage', _('Importer recettes')),
            ('peut_voir_evolution_peage', _('Voir évolution péage')),
            ('peut_voir_objectifs_peage', _('Voir objectifs péage')),
        ]
    },
    'quittances_peage': {
        'label': _('Quittances Péage'),
        'icon': 'fas fa-receipt',
        'permissions': [
            ('peut_saisir_quittance_peage', _('Saisir quittance péage')),
            ('peut_voir_liste_quittances_peage', _('Voir liste quittances')),
            ('peut_comptabiliser_quittances_peage', _('Comptabiliser quittances')),
        ]
    },
    'pesage': {
        'label': _('Pesage'),
        'icon': 'fas fa-weight',
        'permissions': [
            ('peut_voir_historique_vehicule_pesage', _('Historique véhicule')),
            ('peut_saisir_amende', _('Saisir amende')),
            ('peut_saisir_pesee_jour', _('Saisir pesée jour')),
            ('peut_voir_objectifs_pesage', _('Voir objectifs pesage')),
            ('peut_valider_paiement_amende', _('Valider paiement amende')),
            ('peut_lister_amendes', _('Lister amendes')),
            ('peut_saisir_quittance_pesage', _('Saisir quittance pesage')),
            ('peut_comptabiliser_quittances_pesage', _('Comptabiliser quitt. pesage')),
            ('peut_voir_liste_quittancements_pesage', _('Voir quittancements')),
            ('peut_voir_historique_pesees', _('Historique pesées')),
            ('peut_voir_recettes_pesage', _('Voir recettes pesage')),
            ('peut_voir_stats_pesage', _('Voir stats pesage')),
        ]
    },
    'stock_peage': {
        'label': _('Stock Péage'),
        'icon': 'fas fa-boxes',
        'permissions': [
            ('peut_charger_stock_peage', _('Charger stock péage')),
            ('peut_voir_liste_stocks_peage', _('Voir liste stocks')),
            ('peut_voir_stock_date_peage', _('Voir stock par date')),
            ('peut_transferer_stock_peage', _('Transférer stock')),
            ('peut_voir_tracabilite_tickets', _('Traçabilité tickets')),
            ('peut_voir_bordereaux_peage', _('Voir bordereaux')),
            ('peut_voir_mon_stock_peage', _('Voir mon stock')),
            ('peut_voir_historique_stock_peage', _('Historique stock')),
            ('peut_simuler_commandes_peage', _('Simuler commandes')),
        ]
    },
    'gestion': {
        'label': _('Gestion'),
        'icon': 'fas fa-cogs',
        'permissions': [
            ('peut_gerer_postes', _('Gérer postes')),
            ('peut_ajouter_poste', _('Ajouter poste')),
            ('peut_creer_poste_masse', _('Créer postes en masse')),
            ('peut_gerer_utilisateurs', _('Gérer utilisateurs')),
            ('peut_creer_utilisateur', _('Créer utilisateur')),
            ('peut_voir_journal_audit', _('Voir journal audit')),
        ]
    },
    'rapports': {
        'label': _('Rapports'),
        'icon': 'fas fa-chart-bar',
        'permissions': [
            ('peut_voir_rapports_defaillants_peage', _('Rapports défaillants péage')),
            ('peut_voir_rapports_defaillants_pesage', _('Rapports défaillants pesage')),
            ('peut_voir_rapport_inventaires', _('Rapport inventaires')),
            ('peut_voir_classement_peage_rendement', _('Classement rendement')),
            ('peut_voir_classement_station_pesage', _('Classement stations')),
            ('peut_voir_classement_peage_deperdition', _('Classement déperdition')),
            ('peut_voir_classement_agents_inventaire', _('Classement agents')),
        ]
    },
    'autres': {
        'label': _('Autres'),
        'icon': 'fas fa-ellipsis-h',
        'permissions': [
            ('peut_parametrage_global', _('Paramétrage global')),
            ('peut_voir_compte_emploi', _('Voir compte emploi')),
            ('peut_voir_pv_confrontation', _('Voir PV confrontation')),
            ('peut_authentifier_document', _('Authentifier document')),
            ('peut_voir_tous_postes', _('Voir tous postes')),
        ]
    },
    'modules_legacy': {
        'label': _('Modules (Ancien)'),
        'icon': 'fas fa-archive',
        'permissions': [
            ('peut_gerer_peage', _('Gérer le péage')),
            ('peut_gerer_pesage', _('Gérer le pesage')),
            ('peut_gerer_personnel', _('Gérer le personnel')),
            ('peut_gerer_budget', _('Gérer le budget')),
            ('peut_gerer_inventaire', _('Gérer l\'inventaire')),
            ('peut_gerer_archives', _('Gérer les archives')),
            ('peut_gerer_stocks_psrr', _('Gérer les stocks PSRR')),
            ('peut_gerer_stock_info', _('Gérer le stock info')),
        ]
    },
}


def get_all_permissions_list():
    """Retourne la liste de toutes les permissions"""
    all_perms = []
    for cat_data in CATEGORIES_PERMISSIONS.values():
        for perm_name, _ in cat_data['permissions']:
            all_perms.append(perm_name)
    return all_perms


def preparer_contexte_permissions(habilitation=None):
    """
    Prépare le contexte pour l'affichage des permissions dans le template.
    """
    permissions_default = PERMISSIONS_PAR_HABILITATION.get(habilitation, []) if habilitation else []
    
    categories = {}
    total_permissions = 0
    
    for cat_id, cat_data in CATEGORIES_PERMISSIONS.items():
        perms_list = []
        count_actives = 0
        
        for perm_name, perm_label in cat_data['permissions']:
            is_checked = perm_name in permissions_default
            if is_checked:
                count_actives += 1
            
            perms_list.append({
                'name': perm_name,
                'label': str(perm_label),
                'checked': is_checked,
            })
        
        categories[cat_id] = {
            'label': str(cat_data['label']),
            'icon': cat_data['icon'],
            'permissions': perms_list,
            'count_total': len(perms_list),
            'count_actives': count_actives,
        }
        total_permissions += len(perms_list)
    
    return {
        'permissions_categories': categories,
        'total_permissions': total_permissions,
        'permissions_par_habilitation_json': json.dumps(PERMISSIONS_PAR_HABILITATION),
        'toutes_permissions_json': json.dumps(get_all_permissions_list()),
    }


# ===================================================================
# VUES PRINCIPALES
# ===================================================================

@login_required
@permission_required_granular('peut_gerer_utilisateurs')
def bulk_create_step1_upload(request):
    """
    Étape 1: Upload du fichier Excel
    Format attendu: A1=Matricule, B1=Noms et Prénoms, C1=Numéro Téléphone
    """
    if request.method == 'POST':
        if 'excel_file' not in request.FILES:
            messages.error(request, _("Veuillez sélectionner un fichier Excel."))
            return redirect('accounts:bulk_create_step1')
        
        excel_file = request.FILES['excel_file']
        
        # Vérifier l'extension
        if not excel_file.name.endswith(('.xlsx', '.xls')):
            messages.error(request, _("Le fichier doit être au format Excel (.xlsx ou .xls)."))
            return redirect('accounts:bulk_create_step1')
        
        try:
            # Lire le fichier Excel avec pandas
            df = pd.read_excel(excel_file, dtype=str)
            
            # Vérifier les colonnes requises (A, B, C)
            if len(df.columns) < 3:
                messages.error(request, _("Le fichier doit contenir au moins 3 colonnes: Matricule, Noms et Prénoms, Numéro Téléphone."))
                return redirect('accounts:bulk_create_step1')
            
            # Renommer les colonnes pour la cohérence
            df.columns = ['matricule', 'nom_complet', 'telephone'] + list(df.columns[3:])
            
            # Nettoyer les données
            utilisateurs_data = []
            erreurs = []
            matricules_vus = set()
            
            for index, row in df.iterrows():
                ligne_num = index + 2  # +2 car Excel commence à 1 et il y a l'en-tête
                
                matricule = str(row['matricule']).strip().upper() if pd.notna(row['matricule']) else ''
                nom_complet = str(row['nom_complet']).strip() if pd.notna(row['nom_complet']) else ''
                telephone = str(row['telephone']).strip() if pd.notna(row['telephone']) else ''
                
                # Ignorer les lignes vides
                if not matricule and not nom_complet:
                    continue
                
                # Validations
                if not matricule:
                    erreurs.append(f"Ligne {ligne_num}: Matricule manquant")
                    continue
                
                if not nom_complet:
                    erreurs.append(f"Ligne {ligne_num}: Nom complet manquant")
                    continue
                
                if not telephone:
                    erreurs.append(f"Ligne {ligne_num}: Numéro de téléphone manquant")
                    continue
                
                # Vérifier doublon dans le fichier
                if matricule in matricules_vus:
                    erreurs.append(f"Ligne {ligne_num}: Matricule '{matricule}' en double dans le fichier")
                    continue
                
                # Vérifier si le matricule existe déjà en base
                if UtilisateurSUPPER.objects.filter(username=matricule).exists():
                    erreurs.append(f"Ligne {ligne_num}: Matricule '{matricule}' existe déjà dans le système")
                    continue
                
                # Valider le téléphone (format camerounais)
                telephone_clean = re.sub(r'\s+', '', telephone)  # Supprimer les espaces
                if not re.match(r'^(\+?237)?[0-9]{8,9}$', telephone_clean):
                    erreurs.append(f"Ligne {ligne_num}: Téléphone '{telephone}' invalide (format: +237XXXXXXXXX)")
                    continue
                
                matricules_vus.add(matricule)
                utilisateurs_data.append({
                    'matricule': matricule,
                    'nom_complet': nom_complet,
                    'telephone': telephone_clean,
                })
            
            if not utilisateurs_data:
                messages.error(request, _("Aucun utilisateur valide trouvé dans le fichier."))
                if erreurs:
                    for err in erreurs[:10]:  # Limiter à 10 erreurs
                        messages.warning(request, err)
                return redirect('accounts:bulk_create_step1')
            
            # Stocker les données en session pour l'étape 2
            request.session['bulk_users_data'] = utilisateurs_data
            request.session['bulk_users_errors'] = erreurs
            
            messages.success(request, _("%(count)d utilisateurs trouvés dans le fichier.") % {'count': len(utilisateurs_data)})
            
            if erreurs:
                messages.warning(request, _("%(count)d lignes ignorées (voir détails).") % {'count': len(erreurs)})
            
            return redirect('accounts:bulk_create_step2')
            
        except Exception as e:
            logger.error(f"Erreur lecture Excel: {str(e)}")
            messages.error(request, _("Erreur lors de la lecture du fichier: %(error)s") % {'error': str(e)})
            return redirect('accounts:bulk_create_step1')
    
    # GET: Afficher le formulaire d'upload
    context = {
        'title': _('Import en masse - Étape 1: Upload du fichier'),
    }
    return render(request, 'accounts/user_bulk_create_step1.html', context)


@login_required
@permission_required_granular('peut_gerer_utilisateurs')
def bulk_create_step2_configure(request):
    """
    Étape 2: Configuration de l'habilitation et des permissions
    """
    # Vérifier que les données existent en session
    utilisateurs_data = request.session.get('bulk_users_data', [])
    erreurs = request.session.get('bulk_users_errors', [])
    
    if not utilisateurs_data:
        messages.error(request, _("Aucune donnée utilisateur en session. Veuillez recommencer l'import."))
        return redirect('accounts:bulk_create_step1')
    
    if request.method == 'POST':
        habilitation = request.POST.get('habilitation', 'agent_inventaire')
        
        # Récupérer les permissions cochées
        permissions_cochees = []
        for perm_name in get_all_permissions_list():
            if request.POST.get(perm_name) == 'on':
                permissions_cochees.append(perm_name)
        
        try:
            with transaction.atomic():
                users_created = []
                
                for user_data in utilisateurs_data:
                    # Créer l'utilisateur avec mot de passe par défaut 0000
                    user = UtilisateurSUPPER.objects.create_user(
                        username=user_data['matricule'],
                        nom_complet=user_data['nom_complet'],
                        telephone=user_data['telephone'],
                        password='0000',
                        habilitation=habilitation,
                        poste_affectation=None,  # Pas de poste par défaut
                        cree_par=request.user,
                        is_active=True,
                    )
                    
                    # Appliquer les permissions personnalisées
                    # D'abord réinitialiser toutes les permissions
                    user._reinitialiser_toutes_permissions()
                    
                    # Puis activer uniquement les permissions cochées
                    for perm_name in permissions_cochees:
                        if hasattr(user, perm_name):
                            setattr(user, perm_name, True)
                    
                    # Marquer comme personnalisé si différent des permissions par défaut
                    permissions_defaut = set(PERMISSIONS_PAR_HABILITATION.get(habilitation, []))
                    permissions_choisies = set(permissions_cochees)
                    
                    if permissions_choisies != permissions_defaut:
                        user.permissions_personnalisees = True
                        user.personnalise_par = request.user
                        from django.utils import timezone
                        user.date_personnalisation = timezone.now()
                    
                    user.save()
                    users_created.append(user)
                
                # Journalisation
                log_user_action(
                    request.user,
                    "CRÉATION UTILISATEURS EN MASSE",
                    f"{get_user_short_description(request.user)} a créé {len(users_created)} utilisateurs "
                    f"avec habilitation '{habilitation}' via import Excel",
                    request
                )
                
                # Nettoyer la session
                del request.session['bulk_users_data']
                if 'bulk_users_errors' in request.session:
                    del request.session['bulk_users_errors']
                
                messages.success(
                    request,
                    _("%(count)d utilisateurs créés avec succès. Mot de passe par défaut: 0000") % {
                        'count': len(users_created)
                    }
                )
                
                return redirect('accounts:user_list')
                
        except Exception as e:
            logger.error(f"Erreur création en masse: {str(e)}")
            messages.error(request, _("Erreur lors de la création: %(error)s") % {'error': str(e)})
    
    # GET: Afficher le formulaire de configuration
    context = {
        'title': _('Import en masse - Étape 2: Configuration'),
        'utilisateurs': utilisateurs_data,
        'erreurs': erreurs,
        'habilitations': Habilitation.choices,
        'postes_peage': Poste.objects.filter(is_active=True, type='peage').order_by('nom'),
        'postes_pesage': Poste.objects.filter(is_active=True, type='pesage').order_by('nom'),
    }
    
    # Ajouter le contexte des permissions (par défaut pour agent_inventaire)
    context.update(preparer_contexte_permissions('agent_inventaire'))
    
    return render(request, 'accounts/user_bulk_create_step2.html', context)


@login_required
@permission_required_granular('peut_gerer_utilisateurs')
def bulk_create_cancel(request):
    """Annuler l'import en masse et nettoyer la session"""
    if 'bulk_users_data' in request.session:
        del request.session['bulk_users_data']
    if 'bulk_users_errors' in request.session:
        del request.session['bulk_users_errors']
    
    messages.info(request, _("Import annulé."))
    return redirect('accounts:user_list')


@login_required
@require_GET
def api_permissions_for_habilitation(request):
    """
    API JSON pour récupérer les permissions par défaut d'une habilitation
    """
    habilitation = request.GET.get('habilitation', '')
    
    if habilitation in PERMISSIONS_PAR_HABILITATION:
        return JsonResponse({
            'success': True,
            'habilitation': habilitation,
            'permissions': PERMISSIONS_PAR_HABILITATION[habilitation]
        })
    else:
        return JsonResponse({
            'success': False,
            'error': f"Habilitation '{habilitation}' non reconnue"
        }, status=400)

# ===================================================================
# GESTION DES POSTES (AVEC PERMISSIONS GRANULAIRES)
# ===================================================================

@login_required
@permission_required_granular('peut_gerer_postes')
def liste_postes(request):
    """Liste des postes avec filtres et pagination."""
    # Filtres
    search = request.GET.get('search', '')
    type_filter = request.GET.get('type', '')
    region_filter = request.GET.get('region', '')
    actif_filter = request.GET.get('actif', '')
    
    # Construction de la requête
    postes = Poste.objects.select_related('region', 'departement').all()
    
    if search:
        postes = postes.filter(
            Q(nom__icontains=search) |
            Q(code__icontains=search)
        )
    
    if type_filter:
        postes = postes.filter(type=type_filter)
    
    if region_filter:
        postes = postes.filter(region_id=region_filter)
    
    if actif_filter:
        postes = postes.filter(is_active=actif_filter == 'true')
    
    postes = postes.order_by('nom')
    
    # Pagination
    paginator = Paginator(postes, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistiques
    stats = {
        'total': Poste.objects.count(),
        'actifs': Poste.objects.filter(is_active=True).count(),
        'peages': Poste.objects.filter(type='peage').count(),
        'pesages': Poste.objects.filter(type='pesage').count(),
    }
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'search': search,
        'type_filter': type_filter,
        'region_filter': region_filter,
        'actif_filter': actif_filter,
        'regions': Region.objects.all().order_by('nom'),
        'types': TypePoste.choices,
        'title': _('Gestion des Postes'),
    }
    
    return render(request, 'accounts/liste_postes.html', context)


@login_required
@permission_required_granular('peut_gerer_postes')
def detail_poste(request, poste_id):
    """Détails d'un poste avec statistiques."""
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Agents affectés au poste
    agents_affectes = UtilisateurSUPPER.objects.filter(
        poste_affectation=poste,
        is_active=True
    ).select_related('poste_affectation')
    
    # Statistiques du poste
    from datetime import date
    today = date.today()
    month_start = today.replace(day=1)
    
    stats_poste = {
        'nb_agents': agents_affectes.count(),
        'agents_par_role': agents_affectes.values('habilitation').annotate(
            count=Count('id')
        ),
    }
    
    # Essayer d'obtenir les statistiques d'inventaires si le module existe
    try:
        from inventaire.models import InventaireJournalier, RecetteJournaliere
        stats_poste['nb_inventaires_mois'] = InventaireJournalier.objects.filter(
            poste=poste,
            date__gte=month_start
        ).count()
        stats_poste['nb_recettes_mois'] = RecetteJournaliere.objects.filter(
            poste=poste,
            date__gte=month_start
        ).count()
    except ImportError:
        stats_poste['nb_inventaires_mois'] = 0
        stats_poste['nb_recettes_mois'] = 0
    
    context = {
        'poste': poste,
        'stats_poste': stats_poste,
        'agents_affectes': agents_affectes,
        'title': f'Poste - {poste.nom}',
    }
    
    return render(request, 'accounts/detail_poste.html', context)


@login_required
@permission_required_granular('peut_gerer_postes')
def creer_poste(request):
    """Créer un nouveau poste."""
    # Charger régions avec départements
    regions = Region.objects.prefetch_related('departements').all().order_by('nom')
    
    # Créer dictionnaire pour JavaScript
    departements_par_region = {}
    for region in regions:
        departements_par_region[region.id] = [
            {'id': d.id, 'nom': d.nom} 
            for d in region.departements.all().order_by('nom')
        ]
    
    if request.method == 'POST':
        code = request.POST.get('code', '').upper().strip()
        nom = request.POST.get('nom', '').strip()
        type_poste = request.POST.get('type', '')
        is_active = request.POST.get('is_active') == 'on'
        nouveau = request.POST.get('nouveau') == 'on'
        region_id = request.POST.get('region')
        departement_id = request.POST.get('departement')
        axe_routier = request.POST.get('axe_routier', '').strip()
        latitude = request.POST.get('latitude') or None
        longitude = request.POST.get('longitude') or None
        description = request.POST.get('description', '').strip()
        
        # Validation
        errors = []
        
        if not code:
            errors.append(_("Le code du poste est obligatoire."))
        elif Poste.objects.filter(code=code).exists():
            errors.append(_(f"Le code '{code}' existe déjà."))
            
        if not nom:
            errors.append(_("Le nom du poste est obligatoire."))
            
        if not type_poste:
            errors.append(_("Le type de poste est obligatoire."))
            
        if not region_id:
            errors.append(_("La région est obligatoire."))
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                region = Region.objects.get(id=region_id)
                departement = None
                if departement_id:
                    departement = Departement.objects.get(id=departement_id)
                
                lat = float(latitude) if latitude else None
                lng = float(longitude) if longitude else None
                
                poste = Poste.objects.create(
                    code=code,
                    nom=nom,
                    type=type_poste,
                    is_active=is_active,
                    nouveau=nouveau,
                    region=region,
                    departement=departement,
                    axe_routier=axe_routier,
                    latitude=lat,
                    longitude=lng,
                    description=description
                )
                
                user_desc = get_user_short_description(request.user)
                log_user_action(
                    request.user,
                    "Création poste",
                    f"{user_desc} a créé le poste: {poste.code} - {poste.nom} ({poste.get_type_display()})",
                    request
                )
                
                messages.success(request, f"Poste {poste.nom} créé avec succès.")
                return redirect('accounts:detail_poste', poste_id=poste.id)
                
            except (Region.DoesNotExist, Departement.DoesNotExist) as e:
                messages.error(request, _("Région ou département invalide."))
            except Exception as e:
                logger.error(f"Erreur création poste: {str(e)}")
                messages.error(request, f"Erreur lors de la création: {str(e)}")
    
    context = {
        'regions': regions,
        'departements_par_region': json.dumps(departements_par_region),
        'types': TypePoste.choices,
        'title': _('Créer un Poste'),
    }
    
    return render(request, 'accounts/creer_poste.html', context)


@login_required
@permission_required_granular('peut_gerer_postes')
def modifier_poste(request, poste_id):
    """Modifier un poste existant."""
    poste = get_object_or_404(Poste, id=poste_id)
    
    regions = Region.objects.prefetch_related('departements').all().order_by('nom')
    
    departements_par_region = {}
    for region in regions:
        departements_par_region[region.id] = [
            {'id': d.id, 'nom': d.nom} 
            for d in region.departements.all().order_by('nom')
        ]
    
    region_actuelle = poste.region.id if poste.region else None
    departement_actuel = poste.departement.id if poste.departement else None
    
    if request.method == 'POST':
        code = request.POST.get('code', '').upper().strip()
        nom = request.POST.get('nom', '').strip()
        type_poste = request.POST.get('type', '')
        is_active = request.POST.get('is_active') == 'on'
        nouveau = request.POST.get('nouveau') == 'on'
        region_id = request.POST.get('region')
        departement_id = request.POST.get('departement')
        axe_routier = request.POST.get('axe_routier', '').strip()
        latitude = request.POST.get('latitude') or None
        longitude = request.POST.get('longitude') or None
        description = request.POST.get('description', '').strip()
        
        # Validation
        errors = []
        
        if not code:
            errors.append(_("Le code du poste est obligatoire."))
        elif Poste.objects.filter(code=code).exclude(id=poste.id).exists():
            errors.append(_(f"Le code '{code}' existe déjà pour un autre poste."))
            
        if not nom:
            errors.append(_("Le nom du poste est obligatoire."))
            
        if not type_poste:
            errors.append(_("Le type de poste est obligatoire."))
            
        if not region_id:
            errors.append(_("La région est obligatoire."))
        
        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            try:
                region = Region.objects.get(id=region_id)
                departement = None
                if departement_id:
                    departement = Departement.objects.get(id=departement_id)
                
                lat = float(latitude) if latitude else None
                lng = float(longitude) if longitude else None
                
                # Détecter les changements
                changes = []
                if poste.code != code:
                    changes.append(f"Code: {poste.code} → {code}")
                if poste.nom != nom:
                    changes.append(f"Nom: {poste.nom} → {nom}")
                if poste.type != type_poste:
                    changes.append(f"Type: {poste.type} → {type_poste}")
                if poste.is_active != is_active:
                    changes.append(f"Actif: {poste.is_active} → {is_active}")
                
                poste.code = code
                poste.nom = nom
                poste.type = type_poste
                poste.is_active = is_active
                poste.nouveau = nouveau
                poste.region = region
                poste.departement = departement
                poste.axe_routier = axe_routier
                poste.latitude = lat
                poste.longitude = lng
                poste.description = description
                poste.save()
                
                user_desc = get_user_short_description(request.user)
                details = f"{user_desc} a modifié le poste: {poste.code} - {poste.nom}"
                if changes:
                    details += f" | Changements: {', '.join(changes)}"
                
                log_user_action(request.user, "Modification poste", details, request)
                
                messages.success(request, f"Poste {poste.nom} modifié avec succès.")
                return redirect('accounts:detail_poste', poste_id=poste.id)
                
            except (Region.DoesNotExist, Departement.DoesNotExist):
                messages.error(request, _("Région ou département invalide."))
            except Exception as e:
                logger.error(f"Erreur modification poste: {str(e)}")
                messages.error(request, f"Erreur lors de la modification: {str(e)}")
    
    context = {
        'poste': poste,
        'regions': regions,
        'departements_par_region': json.dumps(departements_par_region),
        'departement_actuel': departement_actuel,
        'region_actuelle': region_actuelle,
        'types': TypePoste.choices,
        'title': f'Modifier - {poste.nom}',
    }
    
    return render(request, 'accounts/modifier_poste.html', context)


# ===================================================================
# JOURNAL D'AUDIT (AVEC PERMISSIONS GRANULAIRES)
# ===================================================================

@login_required
@permission_required_granular('peut_voir_journal_audit')
def journal_audit(request):
    """Liste complète du journal d'audit avec filtres avancés."""
    # Filtres
    search = request.GET.get('search', '')
    action_filter = request.GET.get('action', '')
    user_filter = request.GET.get('user', '')
    succes_filter = request.GET.get('succes', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    
    # Construction requête
    logs = JournalAudit.objects.select_related('utilisateur').all()
    
    if search:
        logs = logs.filter(
            Q(action__icontains=search) |
            Q(details__icontains=search) |
            Q(utilisateur__username__icontains=search) |
            Q(utilisateur__nom_complet__icontains=search)
        )
    
    if action_filter:
        logs = logs.filter(action__icontains=action_filter)
    
    if user_filter:
        logs = logs.filter(utilisateur__username=user_filter)
    
    if succes_filter:
        logs = logs.filter(succes=succes_filter == 'true')
    
    if date_debut:
        try:
            logs = logs.filter(timestamp__gte=datetime.strptime(date_debut, '%Y-%m-%d'))
        except ValueError:
            pass
    
    if date_fin:
        try:
            logs = logs.filter(timestamp__lte=datetime.strptime(date_fin, '%Y-%m-%d'))
        except ValueError:
            pass
    
    logs = logs.order_by('-timestamp')
    
    # Pagination
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistiques
    today = timezone.now().date()
    stats = {
        'total': JournalAudit.objects.count(),
        'today': JournalAudit.objects.filter(timestamp__date=today).count(),
        'success': JournalAudit.objects.filter(succes=True).count(),
        'errors': JournalAudit.objects.filter(succes=False).count(),
    }
    
    # Actions uniques pour filtre
    actions_uniques = JournalAudit.objects.values_list(
        'action', flat=True
    ).distinct()[:30]
    
    # Utilisateurs actifs récemment
    users_actifs = UtilisateurSUPPER.objects.filter(
        actions_journal__timestamp__gte=timezone.now() - timedelta(days=7)
    ).distinct()[:20]
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'search': search,
        'action_filter': action_filter,
        'user_filter': user_filter,
        'succes_filter': succes_filter,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'actions_uniques': actions_uniques,
        'users_actifs': users_actifs,
        'title': _('Journal d\'Audit'),
    }
    
    return render(request, 'accounts/journal_audit.html', context)


# ===================================================================
# API ENDPOINTS AVEC PERMISSIONS GRANULAIRES
# ===================================================================

@login_required
@require_GET
def api_postes_par_type(request):
    """
    API pour récupérer les postes filtrés par type.
    
    Paramètres GET:
        - type: 'peage', 'pesage' ou 'all'
    
    Returns:
        JSON avec liste des postes
    """
    type_param = request.GET.get('type', 'all')
    
    queryset = Poste.objects.filter(is_active=True)
    
    if type_param == 'peage':
        queryset = queryset.filter(type='peage')
    elif type_param == 'pesage':
        queryset = queryset.filter(type='pesage')
    
    queryset = queryset.select_related('region').order_by('nom')
    
    postes = [{
        'id': p.id,
        'code': p.code,
        'nom': p.nom,
        'type': p.type,
        'type_display': p.get_type_display(),
        'region': p.region.nom if p.region else '',
    } for p in queryset]
    
    return JsonResponse({
        'postes': postes,
        'count': len(postes)
    })


@login_required
@require_GET
def api_habilitation_info(request):
    """
    API pour récupérer les infos sur une habilitation.
    
    Paramètres GET:
        - habilitation: code de l'habilitation
    
    Returns:
        JSON avec infos sur le type de poste requis
    """
    habilitation = request.GET.get('habilitation', '')
    
    if habilitation in HABILITATIONS_PESAGE:
        return JsonResponse({
            'type_requis': 'pesage',
            'poste_obligatoire': True,
            'message': _("Ce rôle doit être affecté à une station de pesage.")
        })
    
    elif habilitation in HABILITATIONS_PEAGE:
        return JsonResponse({
            'type_requis': 'peage',
            'poste_obligatoire': True,
            'message': _("Ce rôle doit être affecté à un poste de péage.")
        })
    
    elif habilitation in HABILITATIONS_MULTI_POSTES:
        return JsonResponse({
            'type_requis': 'all',
            'poste_obligatoire': False,
            'message': _("Ce rôle a accès à tous les postes (affectation optionnelle).")
        })
    
    else:
        return JsonResponse({
            'type_requis': 'all',
            'poste_obligatoire': False,
            'message': _("Sélectionnez un poste si nécessaire.")
        })


@login_required
@require_GET
def api_departements(request):
    """API pour récupérer les départements d'une région."""
    region_id = request.GET.get('region')
    
    if not region_id:
        return JsonResponse({'departements': []})
    
    try:
        departements = Departement.objects.filter(
            region_id=region_id
        ).values('id', 'nom').order_by('nom')
        return JsonResponse({'departements': list(departements)})
    except Exception as e:
        logger.error(f"Erreur API départements: {str(e)}")
        return JsonResponse({'departements': [], 'error': str(e)})


@login_required
@permission_required_granular('peut_gerer_utilisateurs')
@require_GET
def stats_utilisateurs_pesage(request):
    """Statistiques des utilisateurs affectés aux stations de pesage."""
    # Utilisateurs pesage par station
    stats_par_station = UtilisateurSUPPER.objects.filter(
        habilitation__in=HABILITATIONS_OPERATIONNELS_PESAGE + HABILITATIONS_CHEFS_PESAGE,
        poste_affectation__isnull=False,
        is_active=True
    ).values(
        'poste_affectation__id',
        'poste_affectation__nom',
        'poste_affectation__code'
    ).annotate(
        count=Count('id')
    ).order_by('poste_affectation__nom')
    
    # Stations sans personnel
    stations_avec_personnel = [s['poste_affectation__id'] for s in stats_par_station]
    stations_sans_personnel = Poste.objects.filter(
        type='pesage',
        is_active=True
    ).exclude(id__in=stations_avec_personnel)
    
    # Comptage par rôle
    stats_par_role = UtilisateurSUPPER.objects.filter(
        habilitation__in=HABILITATIONS_OPERATIONNELS_PESAGE + HABILITATIONS_CHEFS_PESAGE,
        is_active=True
    ).values('habilitation').annotate(
        count=Count('id')
    )
    
    return JsonResponse({
        'par_station': list(stats_par_station),
        'par_role': list(stats_par_role),
        'stations_sans_personnel': list(stations_sans_personnel.values('id', 'nom', 'code')),
        'total_utilisateurs_pesage': sum(s['count'] for s in stats_par_station),
        'total_stations_pesage': Poste.objects.filter(type='pesage', is_active=True).count(),
    })


class ValidateUsernameAPIView(LoginRequiredMixin, View):
    """API pour valider l'unicité d'un nom d'utilisateur en temps réel."""
    
    def get(self, request):
        username = request.GET.get('username', '').strip().upper()
        
        if not username:
            return JsonResponse({
                'valid': False,
                'message': _('Matricule requis')
            })
        
        import re
        if not re.match(r'^[A-Z0-9]{6,20}$', username):
            return JsonResponse({
                'valid': False,
                'message': _('Format invalide (6-20 caractères alphanumériques)')
            })
        
        exists = UtilisateurSUPPER.objects.filter(username=username).exists()
        
        return JsonResponse({
            'valid': not exists,
            'message': _('Matricule déjà utilisé') if exists else _('Matricule disponible')
        })


class UserSearchAPIView(LoginRequiredMixin, View):
    """API pour la recherche d'utilisateurs (autocomplete)."""
    
    def get(self, request):
        query = request.GET.get('q', '').strip()
        
        if len(query) < 2:
            return JsonResponse({'results': []})
        
        users = UtilisateurSUPPER.objects.filter(
            Q(username__icontains=query) |
            Q(nom_complet__icontains=query)
        ).filter(is_active=True).select_related('poste_affectation')[:10]
        
        results = [{
            'id': user.id,
            'username': user.username,
            'nom_complet': user.nom_complet,
            'habilitation': user.get_habilitation_display(),
            'poste': user.poste_affectation.nom if user.poste_affectation else None
        } for user in users]
        
        return JsonResponse({'results': results})


@login_required
def postes_api(request):
    """API pour récupérer la liste des postes."""
    postes = Poste.objects.filter(is_active=True).select_related('region').values(
        'id', 'nom', 'code', 'type', 'region__nom'
    )
    
    return JsonResponse({
        'success': True,
        'postes': list(postes)
    })


@login_required
@permission_required_granular('peut_voir_journal_audit')
def stats_api(request):
    """API pour les statistiques en temps réel."""
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
    """API pour vérifier les permissions de l'utilisateur."""
    user = request.user
    
    has_admin = check_admin_permission(user)
    has_user_mgmt = check_user_management_permission(user)
    has_poste_mgmt = check_poste_management_permission(user)
    has_audit = check_audit_permission(user)
    
    response_data = {
        'has_admin_permission': has_admin,
        'has_user_management': has_user_mgmt,
        'has_poste_management': has_poste_mgmt,
        'has_audit_permission': has_audit,
        'user_habilitation': user.habilitation,
        'user_habilitation_display': user.get_habilitation_display(),
        'is_superuser': user.is_superuser,
        'is_staff': user.is_staff,
        'username': user.username,
        'nom_complet': user.nom_complet,
        'user_category': get_user_category(user),
        'niveau_acces': get_niveau_acces(user),
    }
    
    # URLs accessibles selon les permissions
    accessible_urls = {'dashboard': '/common/'}
    
    if has_user_mgmt:
        accessible_urls['users'] = '/accounts/utilisateurs/'
    if has_poste_mgmt:
        accessible_urls['postes'] = '/accounts/postes/'
    if has_audit:
        accessible_urls['journal'] = '/accounts/journal-audit/'
    
    response_data['accessible_urls'] = accessible_urls
    
    return JsonResponse(response_data)


# ===================================================================
# REDIRECTION INTELLIGENTE SELON RÔLE
# ===================================================================

@login_required
def dashboard_redirect(request):
    """Redirection intelligente vers le bon dashboard selon le rôle."""
    user = request.user
    user_desc = get_user_short_description(user)
    
    messages.info(
        request, 
        f"Bonjour {user.nom_complet} ! Vous êtes redirigé vers votre espace de travail."
    )
    
    # Redirection vers le dashboard commun
    return redirect('common:dashboard')


# ===================================================================
# DASHBOARDS SPÉCIALISÉS
# ===================================================================

@method_decorator(login_required, name='dispatch')
class AdminDashboardView(AdminRequiredMixin, BilingualMixin, AuditMixin, TemplateView):
    """Dashboard pour les administrateurs."""
    
    template_name = 'accounts/admin_dashboard.html'
    audit_action = _("Accès dashboard admin")
    audit_log_get = False
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stats'] = self._get_admin_stats()
        context['recent_actions'] = JournalAudit.objects.select_related(
            'utilisateur'
        ).order_by('-timestamp')[:15]
        context['title'] = _('Dashboard Administrateur')
        return context
    
    def _get_admin_stats(self):
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        return {
            'users_total': UtilisateurSUPPER.objects.count(),
            'users_active': UtilisateurSUPPER.objects.filter(is_active=True).count(),
            'users_this_week': UtilisateurSUPPER.objects.filter(
                date_creation__gte=week_ago
            ).count(),
            'postes_total': Poste.objects.count(),
            'postes_active': Poste.objects.filter(is_active=True).count(),
            'postes_peage': Poste.objects.filter(type='peage', is_active=True).count(),
            'postes_pesage': Poste.objects.filter(type='pesage', is_active=True).count(),
            'actions_today': JournalAudit.objects.filter(timestamp__date=today).count(),
            'actions_week': JournalAudit.objects.filter(timestamp__gte=week_ago).count(),
            'actions_month': JournalAudit.objects.filter(timestamp__gte=month_ago).count(),
        }


@method_decorator(login_required, name='dispatch')
class ChefPosteDashboardView(ChefPosteRequiredMixin, BilingualMixin, 
                              AuditMixin, TemplateView):
    """Dashboard pour les chefs de poste."""
    
    template_name = 'accounts/chef_dashboard.html'
    audit_action = _("Accès dashboard chef de poste")
    audit_log_get = False
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        poste = user.poste_affectation
        
        context['poste'] = poste
        context['user_description'] = get_user_description(user)
        
        if poste:
            # Agents du poste
            context['agents_poste'] = UtilisateurSUPPER.objects.filter(
                poste_affectation=poste,
                is_active=True
            ).exclude(id=user.id)
        
        context['title'] = _('Dashboard Chef de Poste')
        return context


@method_decorator(login_required, name='dispatch')
class AgentInventaireDashboardView(LoginRequiredMixin, BilingualMixin, 
                                    AuditMixin, TemplateView):
    """Dashboard pour les agents d'inventaire."""
    
    template_name = 'accounts/agent_dashboard.html'
    audit_action = _("Accès dashboard agent")
    audit_log_get = False
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context['poste'] = user.poste_affectation
        context['user_description'] = get_user_description(user)
        context['title'] = _('Dashboard Agent')
        return context


@method_decorator(login_required, name='dispatch')
class GeneralDashboardView(LoginRequiredMixin, BilingualMixin, 
                           AuditMixin, TemplateView):
    """Dashboard général pour les autres rôles."""
    
    template_name = 'accounts/general_dashboard.html'
    audit_action = _("Accès dashboard général")
    audit_log_get = False
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        
        context['user_role'] = user.get_habilitation_display()
        context['user_description'] = get_user_description(user)
        context['user_category'] = get_user_category(user)
        context['title'] = _('Dashboard')
        return context


# ===================================================================
# VUES D'AIDE ET DOCUMENTATION
# ===================================================================

@login_required
def admin_help_view(request):
    """Vue d'aide pour l'utilisation du système."""
    user = request.user
    
    # Construire la liste des fonctionnalités accessibles selon les permissions
    accessible_features = []
    
    if check_user_management_permission(user):
        accessible_features.append({
            'name': _('Gestion des utilisateurs'),
            'url': reverse('accounts:liste_utilisateurs'),
            'icon': 'fas fa-users',
            'description': _('Créer, modifier et gérer les utilisateurs')
        })
    
    if check_poste_management_permission(user):
        accessible_features.append({
            'name': _('Gestion des postes'),
            'url': reverse('accounts:liste_postes'),
            'icon': 'fas fa-map-marker-alt',
            'description': _('Gérer les postes de péage et pesage')
        })
    
    if check_audit_permission(user):
        accessible_features.append({
            'name': _('Journal d\'audit'),
            'url': reverse('accounts:journal_audit'),
            'icon': 'fas fa-file-alt',
            'description': _('Consulter l\'historique des actions')
        })
    
    context = {
        'title': _('Aide - Système SUPPER'),
        'user_description': get_user_description(user),
        'accessible_features': accessible_features,
    }
    
    return render(request, 'accounts/admin_help.html', context)


# ===================================================================
# REDIRECTIONS VERS ADMIN DJANGO (COMPATIBILITÉ)
# ===================================================================

@login_required
def redirect_to_add_user_admin(request):
    """Redirection vers l'ajout d'utilisateur dans l'admin Django."""
    if not check_user_management_permission(request.user):
        messages.error(request, _("Accès non autorisé."))
        return redirect('common:dashboard')
    
    _log_admin_access(request, "Ajout utilisateur (admin Django)")
    return redirect('/admin/accounts/utilisateursupper/add/')


@login_required
def redirect_to_edit_user_admin(request, user_id):
    """Redirection vers l'édition d'un utilisateur dans l'admin Django."""
    if not check_user_management_permission(request.user):
        messages.error(request, _("Accès non autorisé."))
        return redirect('common:dashboard')
    
    try:
        target_user = UtilisateurSUPPER.objects.get(id=user_id)
        _log_admin_access(request, f"Édition utilisateur {target_user.username}")
        return redirect(f'/admin/accounts/utilisateursupper/{user_id}/change/')
    except UtilisateurSUPPER.DoesNotExist:
        messages.error(request, _("Utilisateur non trouvé."))
        return redirect('accounts:liste_utilisateurs')


# ===================================================================
# GESTION DES ERREURS
# ===================================================================

@login_required
def redirect_error_handler(request, error_type='permission'):
    """Gestionnaire d'erreurs pour les redirections."""
    user = request.user
    
    if error_type == 'permission':
        messages.error(request, _(
            "Vous n'avez pas les permissions nécessaires pour accéder à cette section. "
            "Contactez un administrateur si vous pensez que c'est une erreur."
        ))
        
        log_acces_refuse(
            user,
            f"Redirection erreur depuis {request.META.get('HTTP_REFERER', 'URL inconnue')}",
            request
        )
    
    elif error_type == 'not_found':
        messages.error(request, _("La ressource demandée n'a pas été trouvée."))
    
    else:
        messages.error(request, _("Une erreur est survenue lors de la redirection."))
    
    return redirect('common:dashboard')


def custom_404(request, exception=None):
    """Page 404 personnalisée."""
    return render(request, 'errors/404.html', {
        'title': _('Page non trouvée'),
        'message': _('La page que vous cherchez n\'existe pas.'),
    }, status=404)


def custom_500(request):
    """Page 500 personnalisée."""
    return render(request, 'errors/500.html', {
        'title': _('Erreur serveur'),
        'message': _('Une erreur interne s\'est produite.'),
    }, status=500)


def custom_403(request, exception=None):
    """Page 403 personnalisée."""
    return render(request, 'errors/403.html', {
        'title': _('Accès interdit'),
        'message': _('Vous n\'avez pas les permissions nécessaires.'),
    }, status=403)


# ===================================================================
# FONCTIONS UTILITAIRES POUR LES TEMPLATES
# ===================================================================

def get_admin_navigation_context(user):
    """Retourne le contexte de navigation pour les templates."""
    if not user.is_authenticated:
        return {}
    
    navigation = {'admin_navigation': {}}
    
    if check_user_management_permission(user):
        navigation['admin_navigation']['users'] = {
            'url': reverse('accounts:liste_utilisateurs'),
            'title': _('Gérer Utilisateurs'),
            'icon': 'fas fa-users',
        }
    
    if check_poste_management_permission(user):
        navigation['admin_navigation']['postes'] = {
            'url': reverse('accounts:liste_postes'),
            'title': _('Gérer Postes'),
            'icon': 'fas fa-map-marker-alt',
        }
    
    if check_audit_permission(user):
        navigation['admin_navigation']['journal'] = {
            'url': reverse('accounts:journal_audit'),
            'title': _('Journal d\'Audit'),
            'icon': 'fas fa-file-alt',
        }
    
    return navigation


# ===================================================================
# VUES DE CLASSE HÉRITÉES (COMPATIBILITÉ AVEC ANCIEN CODE)
# ===================================================================

class UserDetailView(GestionUtilisateursPermissionMixin, BilingualMixin, 
                     AuditMixin, DetailView):
    """Affichage détaillé d'un utilisateur (vue basée sur classe)."""
    
    model = UtilisateurSUPPER
    template_name = 'accounts/detail_utilisateur.html'
    context_object_name = 'user_detail'
    audit_action = _("Consultation détail utilisateur")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_detail = self.object
        
        context['user_description'] = get_user_description(user_detail)
        context['activites_recentes'] = JournalAudit.objects.filter(
            utilisateur=user_detail
        ).order_by('-timestamp')[:10]
        context['permissions_list'] = user_detail.get_permissions_list() if hasattr(
            user_detail, 'get_permissions_list'
        ) else []
        context['can_edit'] = check_user_management_permission(self.request.user)
        
        return context


class UserUpdateView(GestionUtilisateursPermissionMixin, BilingualMixin, 
                     UpdateWithAuditMixin, UpdateView):
    """Modification des informations d'un utilisateur (vue basée sur classe)."""
    
    model = UtilisateurSUPPER
    form_class = UserUpdateForm
    template_name = 'accounts/modifier_utilisateur.html'
    audit_action = _("Modification utilisateur")
    
    def get_success_url(self):
        return reverse_lazy('accounts:detail_utilisateur', kwargs={'user_id': self.object.pk})
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user_edit'] = self.object
        context['postes_peage'] = Poste.objects.filter(is_active=True, type='peage')
        context['postes_pesage'] = Poste.objects.filter(is_active=True, type='pesage')
        context['habilitations'] = Habilitation.choices
        context['filtrage_postes_js'] = FILTRAGE_POSTES_JS
        return context
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            _("Informations de %(nom)s mises à jour avec succès.") % {
                'nom': self.object.nom_complet
            }
        )
        return response



# ===================================================================
# 1. API POUR VOIR LES DÉTAILS D'UN LOG
# ===================================================================

@login_required
@require_GET
def api_log_details(request, log_id):
    """
    API pour récupérer les détails complets d'une entrée du journal d'audit.
    
    URL: /accounts/api/log-details/<log_id>/
    
    Retourne un JSON avec tous les détails du log.
    """
    # Vérifier la permission
    if not check_granular_permission(request.user, 'peut_voir_journal_audit'):
        return JsonResponse({
            'success': False,
            'error': 'Permission insuffisante'
        }, status=403)
    
    try:
        log = get_object_or_404(JournalAudit, id=log_id)
        
        # Parser les détails JSON si c'est du JSON
        details_parsed = log.details
        details_structured = None
        
        try:
            if log.details and log.details.startswith('{'):
                details_structured = json.loads(log.details)
        except (json.JSONDecodeError, TypeError):
            pass
        
        # Construire la réponse
        response_data = {
            'success': True,
            'log': {
                'id': log.id,
                'timestamp': log.timestamp.strftime('%d/%m/%Y à %H:%M:%S'),
                'timestamp_iso': log.timestamp.isoformat(),
                
                # Informations utilisateur
                'utilisateur': {
                    'id': log.utilisateur.id,
                    'username': log.utilisateur.username,
                    'nom_complet': log.utilisateur.nom_complet,
                    'habilitation': log.utilisateur.get_habilitation_display(),
                    'habilitation_code': log.utilisateur.habilitation,
                    'poste': log.utilisateur.poste_affectation.nom if log.utilisateur.poste_affectation else None,
                    'description': get_user_description(log.utilisateur),
                },
                
                # Action et détails
                'action': log.action,
                'details': details_parsed,
                'details_structured': details_structured,
                
                # Informations techniques
                'adresse_ip': log.adresse_ip,
                'user_agent': log.user_agent,
                'user_agent_short': _parse_user_agent(log.user_agent) if log.user_agent else None,
                'session_key': log.session_key[:20] + '...' if log.session_key and len(log.session_key) > 20 else log.session_key,
                'url_acces': log.url_acces,
                'methode_http': log.methode_http,
                
                # Statut
                'succes': log.succes,
                'statut_reponse': log.statut_reponse,
                'statut_label': _get_status_label(log.statut_reponse),
                
                # Durée
                'duree_execution': str(log.duree_execution) if log.duree_execution else None,
                'duree_ms': int(log.duree_execution.total_seconds() * 1000) if log.duree_execution else None,
            }
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _parse_user_agent(user_agent):
    """Parse le user agent pour extraire les infos principales"""
    if not user_agent:
        return None
    
    browser = "Navigateur inconnu"
    os_info = "OS inconnu"
    
    # Détection navigateur
    if 'Chrome' in user_agent and 'Edg' not in user_agent:
        browser = "Chrome"
    elif 'Firefox' in user_agent:
        browser = "Firefox"
    elif 'Safari' in user_agent and 'Chrome' not in user_agent:
        browser = "Safari"
    elif 'Edg' in user_agent:
        browser = "Edge"
    elif 'MSIE' in user_agent or 'Trident' in user_agent:
        browser = "Internet Explorer"
    
    # Détection OS
    if 'Windows' in user_agent:
        os_info = "Windows"
    elif 'Mac OS' in user_agent:
        os_info = "macOS"
    elif 'Linux' in user_agent:
        os_info = "Linux"
    elif 'Android' in user_agent:
        os_info = "Android"
    elif 'iPhone' in user_agent or 'iPad' in user_agent:
        os_info = "iOS"
    
    return f"{browser} sur {os_info}"


def _get_status_label(status_code):
    """Retourne un label pour le code de statut HTTP"""
    if status_code is None:
        return "Non défini"
    
    labels = {
        200: "OK - Succès",
        201: "Créé",
        302: "Redirection",
        400: "Requête invalide",
        401: "Non authentifié",
        403: "Accès interdit",
        404: "Non trouvé",
        500: "Erreur serveur",
    }
    
    return labels.get(status_code, f"Code {status_code}")



def audit_view(action_name, get_context=None, skip_middleware=True):
    """
    Décorateur pour journaliser automatiquement une vue avec contexte détaillé.
    
    Usage:
    ------
    @audit_view(
        "SAISIE_RECETTE",
        get_context=lambda request, response, **kwargs: {
            'montant': request.POST.get('montant'),
            'poste_id': kwargs.get('poste_id')
        }
    )
    def saisir_recette(request, poste_id):
        ...
    
    Paramètres:
    -----------
    - action_name: Nom de l'action à journaliser
    - get_context: Fonction optionnelle pour extraire le contexte métier
    - skip_middleware: Si True, évite la double journalisation
    """
    from functools import wraps
    
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Marquer pour éviter la journalisation automatique du middleware
            if skip_middleware:
                request._skip_audit_middleware = True
            
            try:
                # Exécuter la vue
                response = view_func(request, *args, **kwargs)
                
                # Extraire le contexte si une fonction est fournie
                context = {}
                if get_context and callable(get_context):
                    try:
                        context = get_context(request, response, *args, **kwargs) or {}
                    except Exception:
                        pass
                
                # Journaliser l'action avec le contexte
                log_user_action(
                    user=request.user,
                    action=action_name,
                    details=f"Action {action_name} exécutée avec succès",
                    request=request,
                    **context
                )
                
                return response
                
            except Exception as e:
                # Journaliser l'erreur
                log_erreur_action(
                    request.user,
                    action_name,
                    str(e),
                    request
                )
                raise
        
        return wrapper
    return decorator

@login_required
@require_GET
def api_permissions_defaut(request):
    """
    API pour récupérer les permissions par défaut d'une habilitation.
    
    Paramètres GET:
        - habilitation: code de l'habilitation
    
    Returns:
        JSON avec les permissions par défaut
    """
    from .models import UtilisateurSUPPER, Habilitation
    
    habilitation = request.GET.get('habilitation', '')
    
    if not habilitation:
        return JsonResponse({
            'success': False,
            'error': 'Habilitation requise'
        })
    
    try:
        # Créer un utilisateur temporaire pour obtenir les permissions par défaut
        temp_user = UtilisateurSUPPER(habilitation=habilitation)
        
        # Réinitialiser et attribuer les permissions
        if hasattr(temp_user, '_reinitialiser_toutes_permissions'):
            temp_user._reinitialiser_toutes_permissions()
        if hasattr(temp_user, 'attribuer_permissions_automatiques'):
            temp_user.attribuer_permissions_automatiques()
        
        # Extraire toutes les permissions
        permissions = {}
        for perm_code in LISTE_PERMISSIONS_FLAT:
            permissions[perm_code] = getattr(temp_user, perm_code, False)
        
        # Obtenir le label de l'habilitation
        habilitation_label = dict(Habilitation.choices).get(habilitation, habilitation)
        
        return JsonResponse({
            'success': True,
            'habilitation': habilitation,
            'habilitation_label': habilitation_label,
            'permissions': permissions,
        })
        
    except Exception as e:
        logger.error(f"Erreur API permissions défaut: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
