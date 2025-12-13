# ===================================================================
# Fichier : common/mixins.py - VERSION MISE À JOUR
# Mixins pour les vues avec habilitations granulaires
# Support bilingue FR/EN intégré, journalisation détaillée
# ===================================================================

from django.contrib.auth.mixins import UserPassesTestMixin, LoginRequiredMixin
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
import logging

logger = logging.getLogger('supper')


# ===================================================================
# IMPORT DES UTILITAIRES - Éviter les imports circulaires
# ===================================================================

def _get_utils():
    """Import différé pour éviter les imports circulaires"""
    from common.utils import (
        log_user_action,
        log_acces_refuse,
        get_user_description,
        get_user_short_description,
        get_user_category,
        get_niveau_acces,
        get_habilitation_normalisee,
        get_habilitation_label,
        is_admin_user,
        is_service_central,
        is_cisop,
        is_chef_poste,
        is_chef_peage,
        is_chef_pesage,
        is_operationnel_pesage,
        is_operationnel_peage,
        HABILITATIONS_ADMIN,
        HABILITATIONS_SERVICES_CENTRAUX,
        HABILITATIONS_CISOP,
        HABILITATIONS_CHEFS,
        HABILITATIONS_CHEFS_PEAGE,
        HABILITATIONS_CHEFS_PESAGE,
        HABILITATIONS_OPERATIONNELS_PESAGE,
        HABILITATIONS_OPERATIONNELS_PEAGE,
    )
    return {
        'log_user_action': log_user_action,
        'log_acces_refuse': log_acces_refuse,
        'get_user_description': get_user_description,
        'get_user_short_description': get_user_short_description,
        'get_user_category': get_user_category,
        'get_niveau_acces': get_niveau_acces,
        'get_habilitation_normalisee': get_habilitation_normalisee,
        'get_habilitation_label': get_habilitation_label,
        'is_admin_user': is_admin_user,
        'is_service_central': is_service_central,
        'is_cisop': is_cisop,
        'is_chef_poste': is_chef_poste,
        'is_chef_peage': is_chef_peage,
        'is_chef_pesage': is_chef_pesage,
        'is_operationnel_pesage': is_operationnel_pesage,
        'is_operationnel_peage': is_operationnel_peage,
        'HABILITATIONS_ADMIN': HABILITATIONS_ADMIN,
        'HABILITATIONS_SERVICES_CENTRAUX': HABILITATIONS_SERVICES_CENTRAUX,
        'HABILITATIONS_CISOP': HABILITATIONS_CISOP,
        'HABILITATIONS_CHEFS': HABILITATIONS_CHEFS,
        'HABILITATIONS_CHEFS_PEAGE': HABILITATIONS_CHEFS_PEAGE,
        'HABILITATIONS_CHEFS_PESAGE': HABILITATIONS_CHEFS_PESAGE,
        'HABILITATIONS_OPERATIONNELS_PESAGE': HABILITATIONS_OPERATIONNELS_PESAGE,
        'HABILITATIONS_OPERATIONNELS_PEAGE': HABILITATIONS_OPERATIONNELS_PEAGE,
    }


# ===================================================================
# MIXIN DE BASE POUR L'AUDIT
# ===================================================================

class AuditMixin:
    """
    Mixin pour ajouter automatiquement la journalisation détaillée aux vues
    Utilise le système d'audit SUPPER avec descriptions contextuelles
    Compatible avec les vues basées sur les classes Django
    
    Attributs:
        audit_action: Action à journaliser (définie dans chaque vue)
        audit_details: Détails supplémentaires (optionnel)
        audit_log_get: Journaliser les requêtes GET (défaut: False)
        audit_log_post: Journaliser les requêtes POST (défaut: True)
    """
    audit_action = None
    audit_details = None
    audit_log_get = False
    audit_log_post = True
    
    def dispatch(self, request, *args, **kwargs):
        """
        Méthode appelée avant chaque vue pour journaliser l'action
        Args:
            request: Requête HTTP Django
            *args: Arguments positionnels de l'URL
            **kwargs: Arguments nommés de l'URL
        Returns:
            Réponse de la vue parente
        """
        # Vérifier si on doit journaliser cette méthode HTTP
        should_log = (
            self.audit_action and 
            request.user.is_authenticated and
            ((request.method == 'GET' and self.audit_log_get) or
             (request.method == 'POST' and self.audit_log_post) or
             request.method in ['PUT', 'DELETE', 'PATCH'])
        )
        
        if should_log:
            utils = _get_utils()
            
            # Construire les détails contextuels
            details = f"Vue: {self.__class__.__name__}"
            if self.audit_details:
                details += f" | {self.audit_details}"
            
            # Ajouter des informations sur les paramètres URL si présents
            if kwargs:
                params = ', '.join([f"{k}={v}" for k, v in kwargs.items()])
                details += f" | Params: {params}"
            
            # Journaliser avec description complète de l'utilisateur
            utils['log_user_action'](
                user=request.user,
                action=f"ACCES_{self.audit_action}",
                details=details,
                request=request,
                vue=self.__class__.__name__,
                methode=request.method
            )
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        """Ajoute les informations utilisateur au contexte"""
        context = super().get_context_data(**kwargs)
        
        if self.request.user.is_authenticated:
            utils = _get_utils()
            context.update({
                'user_description': utils['get_user_description'](self.request.user),
                'user_short_description': utils['get_user_short_description'](self.request.user),
                'user_category': utils['get_user_category'](self.request.user),
                'user_niveau_acces': utils['get_niveau_acces'](self.request.user),
                'user_habilitation_label': utils['get_habilitation_label'](
                    getattr(self.request.user, 'habilitation', '')
                ),
            })
        
        return context


# ===================================================================
# MIXIN POUR PERMISSIONS GRANULAIRES
# ===================================================================

class GranularPermissionMixin(UserPassesTestMixin):
    """
    Mixin générique pour vérifier les permissions granulaires SUPPER
    
    Attributs à définir dans chaque vue:
        required_permission: Permission requise (str ou list)
        required_habilitation: Habilitation requise (str ou list)
        required_any_permission: Au moins une de ces permissions
        required_all_permissions: Toutes ces permissions
        allow_superuser: Les superusers passent automatiquement (défaut: True)
        allow_staff: Les staff passent automatiquement (défaut: False)
        redirect_url: URL de redirection en cas de refus (défaut: /common/)
    """
    
    required_permission = None
    required_habilitation = None
    required_any_permission = None
    required_all_permissions = None
    allow_superuser = True
    allow_staff = False
    redirect_url = '/common/'
    
    def test_func(self):
        """Test principal de permissions avec logique flexible"""
        if not self.request.user.is_authenticated:
            return False
        
        user = self.request.user
        utils = _get_utils()
        
        # Superusers passent automatiquement (sauf si explicitement désactivé)
        if self.allow_superuser and user.is_superuser:
            return True
        
        # Staff passent si autorisés
        if self.allow_staff and user.is_staff:
            return True
        
        # Administrateurs passent toujours pour les vues générales
        if utils['is_admin_user'](user):
            return True
        
        # Vérifier les permissions multiples (ANY)
        if self.required_any_permission:
            permissions = self.required_any_permission
            if isinstance(permissions, str):
                permissions = [permissions]
            
            for perm in permissions:
                if self._check_single_permission(user, perm):
                    return True
            return False
        
        # Vérifier les permissions multiples (ALL)
        if self.required_all_permissions:
            permissions = self.required_all_permissions
            if isinstance(permissions, str):
                permissions = [permissions]
            
            for perm in permissions:
                if not self._check_single_permission(user, perm):
                    return False
            return True
        
        # Vérifier la permission simple
        if self.required_permission:
            return self._check_single_permission(user, self.required_permission)
        
        # Vérifier l'habilitation
        if self.required_habilitation:
            return self._check_habilitation(user, self.required_habilitation)
        
        # Si aucun critère défini, accès autorisé par défaut
        return True
    
    def _check_single_permission(self, user, permission):
        """Vérifie une permission spécifique sur l'utilisateur"""
        # Vérifier si c'est un attribut direct
        if hasattr(user, permission):
            value = getattr(user, permission, False)
            # Si c'est une méthode, l'appeler
            if callable(value):
                try:
                    return value()
                except Exception:
                    return False
            return bool(value)
        
        return False
    
    def _check_habilitation(self, user, habilitation):
        """Vérifie si l'utilisateur a l'habilitation requise"""
        utils = _get_utils()
        user_hab = utils['get_habilitation_normalisee'](getattr(user, 'habilitation', ''))
        
        # Si habilitation est une liste
        if isinstance(habilitation, (list, tuple)):
            normalized_habs = [utils['get_habilitation_normalisee'](h) for h in habilitation]
            return user_hab in normalized_habs
        
        # Habilitation simple
        return user_hab == utils['get_habilitation_normalisee'](habilitation)
    
    def handle_no_permission(self):
        """Gestion personnalisée du refus d'accès avec journalisation détaillée"""
        utils = _get_utils()
        
        if self.request.user.is_authenticated:
            # Construire le message d'erreur contextuel
            error_message = self._get_error_message()
            messages.error(self.request, error_message)
            
            # Journaliser l'accès refusé avec détails
            utils['log_acces_refuse'](
                user=self.request.user,
                ressource=f"Vue {self.__class__.__name__}",
                raison=self._get_refusal_reason(),
                request=self.request
            )
            
            # Log système détaillé
            logger.warning(
                f"🚫 ACCÈS REFUSÉ | {utils['get_user_short_description'](self.request.user)} | "
                f"Vue: {self.__class__.__name__} | Raison: {self._get_refusal_reason()}"
            )
            
            # Redirection intelligente selon le rôle
            return self._get_redirect_for_user()
        else:
            return redirect('accounts:login')
    
    def _get_error_message(self):
        """Génère un message d'erreur contextuel"""
        utils = _get_utils()
        
        if self.required_permission:
            perm = self.required_permission
            if isinstance(perm, list):
                perm = ', '.join(perm)
            return _("Accès interdit. Permission requise : %(perm)s") % {'perm': perm}
        
        if self.required_habilitation:
            hab = self.required_habilitation
            if isinstance(hab, list):
                hab = ', '.join([utils['get_habilitation_label'](h) for h in hab])
            else:
                hab = utils['get_habilitation_label'](hab)
            return _("Accès interdit. Rôle requis : %(hab)s") % {'hab': hab}
        
        if self.required_any_permission:
            perms = ', '.join(self.required_any_permission)
            return _("Accès interdit. Une de ces permissions est requise : %(perms)s") % {'perms': perms}
        
        if self.required_all_permissions:
            perms = ', '.join(self.required_all_permissions)
            return _("Accès interdit. Toutes ces permissions sont requises : %(perms)s") % {'perms': perms}
        
        return _("Accès interdit. Permissions insuffisantes.")
    
    def _get_refusal_reason(self):
        """Retourne la raison du refus pour la journalisation"""
        if self.required_permission:
            return f"Permission manquante: {self.required_permission}"
        if self.required_habilitation:
            return f"Habilitation manquante: {self.required_habilitation}"
        if self.required_any_permission:
            return f"Aucune des permissions: {self.required_any_permission}"
        if self.required_all_permissions:
            return f"Toutes les permissions requises: {self.required_all_permissions}"
        return "Aucun critère de permission défini"
    
    def _get_redirect_for_user(self):
        """Détermine la redirection appropriée selon le rôle de l'utilisateur"""
        utils = _get_utils()
        user = self.request.user
        habilitation = utils['get_habilitation_normalisee'](getattr(user, 'habilitation', ''))
        
        # Redirection selon la catégorie
        if habilitation in utils['HABILITATIONS_ADMIN']:
            return redirect('/admin/')
        elif habilitation in utils['HABILITATIONS_SERVICES_CENTRAUX']:
            return redirect(self.redirect_url)
        elif habilitation in utils['HABILITATIONS_CISOP']:
            return redirect(self.redirect_url)
        elif habilitation in utils['HABILITATIONS_CHEFS']:
            return redirect(self.redirect_url)
        else:
            try:
                return redirect('common:dashboard_general')
            except:
                return redirect(self.redirect_url)


# ===================================================================
# MIXINS SPÉCIALISÉS POUR ADMINISTRATION
# ===================================================================

class AdminRequiredMixin(GranularPermissionMixin):
    """
    Mixin pour restreindre l'accès aux utilisateurs administrateurs uniquement
    Vérifie: superuser, staff, ou habilitations admin
    """
    
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        
        user = self.request.user
        utils = _get_utils()
        
        # Superuser ou staff
        if user.is_superuser or user.is_staff:
            return True
        
        # Habilitations admin
        return utils['is_admin_user'](user)
    
    def handle_no_permission(self):
        utils = _get_utils()
        
        if self.request.user.is_authenticated:
            messages.error(
                self.request,
                _("Accès interdit. Permissions administrateur requises.")
            )
            
            utils['log_acces_refuse'](
                self.request.user,
                f"Vue admin {self.__class__.__name__}",
                "Permissions administrateur requises",
                self.request
            )
            
            logger.warning(
                f"🚫 ACCÈS ADMIN REFUSÉ | {utils['get_user_short_description'](self.request.user)} | "
                f"Vue: {self.__class__.__name__}"
            )
            
            return redirect('/common/')
        else:
            return redirect('accounts:login')


class ServiceCentralRequiredMixin(GranularPermissionMixin):
    """
    Mixin pour les services centraux (admin + services centraux)
    """
    
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        
        user = self.request.user
        utils = _get_utils()
        
        if user.is_superuser or user.is_staff:
            return True
        
        return utils['is_service_central'](user)
    
    def handle_no_permission(self):
        utils = _get_utils()
        
        if self.request.user.is_authenticated:
            messages.error(
                self.request,
                _("Accès interdit. Réservé aux services centraux.")
            )
            
            utils['log_acces_refuse'](
                self.request.user,
                f"Vue service central {self.__class__.__name__}",
                "Accès services centraux requis",
                self.request
            )
            
            return redirect('/common/')
        else:
            return redirect('accounts:login')


class CISOPRequiredMixin(GranularPermissionMixin):
    """
    Mixin pour les agents CISOP (+ admin + services centraux)
    """
    
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        
        user = self.request.user
        utils = _get_utils()
        
        if user.is_superuser or user.is_staff:
            return True
        
        if utils['is_service_central'](user):
            return True
        
        return utils['is_cisop'](user)
    
    def handle_no_permission(self):
        utils = _get_utils()
        
        if self.request.user.is_authenticated:
            messages.error(
                self.request,
                _("Accès interdit. Réservé aux agents CISOP.")
            )
            
            utils['log_acces_refuse'](
                self.request.user,
                f"Vue CISOP {self.__class__.__name__}",
                "Accès CISOP requis",
                self.request
            )
            
            return redirect('/common/')
        else:
            return redirect('accounts:login')


# ===================================================================
# MIXINS SPÉCIALISÉS POUR CHEFS DE POSTE
# ===================================================================

class ChefPosteRequiredMixin(GranularPermissionMixin):
    """
    Mixin pour les chefs de poste (péage et pesage)
    Les administrateurs et services centraux ont également accès
    """
    
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        
        user = self.request.user
        utils = _get_utils()
        
        if user.is_superuser or user.is_staff:
            return True
        
        if utils['is_service_central'](user):
            return True
        
        return utils['is_chef_poste'](user)
    
    def handle_no_permission(self):
        utils = _get_utils()
        
        if self.request.user.is_authenticated:
            messages.error(
                self.request,
                _("Accès interdit. Permissions chef de poste requises.")
            )
            
            utils['log_acces_refuse'](
                self.request.user,
                f"Vue chef de poste {self.__class__.__name__}",
                "Permissions chef de poste requises",
                self.request
            )
            
            return redirect('/common/')
        else:
            return redirect('accounts:login')


class ChefPeageRequiredMixin(GranularPermissionMixin):
    """
    Mixin spécifique pour les chefs de poste péage
    """
    
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        
        user = self.request.user
        utils = _get_utils()
        
        if user.is_superuser or user.is_staff:
            return True
        
        if utils['is_service_central'](user):
            return True
        
        return utils['is_chef_peage'](user)
    
    def handle_no_permission(self):
        utils = _get_utils()
        
        if self.request.user.is_authenticated:
            messages.error(
                self.request,
                _("Accès interdit. Réservé aux chefs de poste péage.")
            )
            
            utils['log_acces_refuse'](
                self.request.user,
                f"Vue chef péage {self.__class__.__name__}",
                "Accès chef de poste péage requis",
                self.request
            )
            
            return redirect('/common/')
        else:
            return redirect('accounts:login')


class ChefPesageRequiredMixin(GranularPermissionMixin):
    """
    Mixin spécifique pour les chefs de station pesage
    """
    
    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        
        user = self.request.user
        utils = _get_utils()
        
        if user.is_superuser or user.is_staff:
            return True
        
        if utils['is_service_central'](user):
            return True
        
        return utils['is_chef_pesage'](user)
    
    def handle_no_permission(self):
        utils = _get_utils()
        
        if self.request.user.is_authenticated:
            messages.error(
                self.request,
                _("Accès interdit. Réservé aux chefs de station pesage.")
            )
            
            utils['log_acces_refuse'](
                self.request.user,
                f"Vue chef pesage {self.__class__.__name__}",
                "Accès chef de station pesage requis",
                self.request
            )
            
            return redirect('/common/')
        else:
            return redirect('accounts:login')


# ===================================================================
# MIXINS SPÉCIALISÉS POUR PERMISSIONS GRANULAIRES PÉAGE
# ===================================================================

class RecettePeagePermissionMixin(GranularPermissionMixin):
    """
    Mixin pour les vues de gestion des recettes péage
    Permissions granulaires: peut_saisir_recette_peage, peut_voir_liste_recettes_peage, etc.
    """
    required_any_permission = [
        'peut_saisir_recette_peage',
        'peut_voir_liste_recettes_peage',
        'peut_importer_recettes_peage',
        'peut_voir_stats_recettes',
    ]


class StockPeagePermissionMixin(GranularPermissionMixin):
    """
    Mixin pour les vues de gestion des stocks péage
    Permissions granulaires: peut_charger_stock_peage, peut_transferer_stock_peage, etc.
    """
    required_any_permission = [
        'peut_charger_stock_peage',
        'peut_transferer_stock_peage',
        'peut_voir_liste_stocks_peage',
        'peut_voir_tracabilite_tickets',
        'peut_gerer_series_tickets',
    ]


class InventairePermissionMixin(GranularPermissionMixin):
    """
    Mixin pour les vues de gestion d'inventaire
    Vérifie les permissions granulaires liées à l'inventaire
    """
    required_any_permission = [
        'peut_saisir_inventaire_normal',
        'peut_programmer_inventaire',
        'peut_voir_stats_deperdition',
        'peut_calculer_recette_potentielle',
        'peut_gerer_inventaire',
    ]


# ===================================================================
# MIXINS SPÉCIALISÉS POUR PERMISSIONS GRANULAIRES PESAGE
# ===================================================================

class PesagePermissionMixin(GranularPermissionMixin):
    """
    Mixin pour les vues de gestion du pesage
    Permissions granulaires: peut_saisir_amende, peut_valider_paiement_amende, etc.
    """
    required_any_permission = [
        'peut_saisir_amende',
        'peut_valider_paiement_amende',
        'peut_confirmer_paiement_autre_station',
        'peut_voir_stats_pesage',
        'peut_generer_rapport_pesage',
    ]


class AmendePermissionMixin(GranularPermissionMixin):
    """
    Mixin spécifique pour la gestion des amendes pesage
    """
    required_any_permission = [
        'peut_saisir_amende',
        'peut_modifier_amende',
        'peut_annuler_amende',
        'peut_valider_paiement_amende',
    ]


# ===================================================================
# MIXINS SPÉCIALISÉS POUR GESTION UTILISATEURS/POSTES
# ===================================================================

class GestionUtilisateursPermissionMixin(GranularPermissionMixin):
    """
    Mixin pour les vues de gestion des utilisateurs
    """
    required_any_permission = [
        'peut_gerer_utilisateurs',
        'peut_creer_utilisateur',
        'peut_modifier_utilisateur',
        'peut_desactiver_utilisateur',
        'peut_reinitialiser_mot_de_passe',
    ]


class GestionPostesPermissionMixin(GranularPermissionMixin):
    """
    Mixin pour les vues de gestion des postes
    """
    required_any_permission = [
        'peut_gerer_postes',
        'peut_ajouter_poste',
        'peut_modifier_poste',
        'peut_creer_poste_masse',
    ]


class AuditPermissionMixin(GranularPermissionMixin):
    """
    Mixin pour les vues du journal d'audit
    """
    required_permission = 'peut_voir_journal_audit'


# ===================================================================
# MIXIN POUR ACCÈS AU POSTE
# ===================================================================

class PosteAccessMixin:
    """
    Mixin pour vérifier l'accès aux données d'un poste spécifique
    S'assure que l'utilisateur peut consulter/modifier les données du poste demandé
    Ajoute automatiquement le poste au contexte de la requête
    """
    
    def dispatch(self, request, *args, **kwargs):
        """Vérification de l'accès au poste avant affichage de la vue"""
        poste_id = kwargs.get('poste_id') or kwargs.get('pk') or request.GET.get('poste_id')
        
        if poste_id:
            try:
                from accounts.models import Poste
                utils = _get_utils()
                
                poste = Poste.objects.get(id=poste_id)
                
                # Vérifier si l'utilisateur peut accéder à ce poste
                if not request.user.peut_acceder_poste(poste):
                    messages.error(
                        request,
                        _("Accès interdit au poste %(poste_nom)s.") % {
                            'poste_nom': poste.nom
                        }
                    )
                    
                    utils['log_acces_refuse'](
                        request.user,
                        f"Poste {poste.nom} ({poste.code})",
                        "Accès au poste non autorisé",
                        request
                    )
                    
                    logger.warning(
                        f"🚫 ACCÈS POSTE REFUSÉ | {utils['get_user_short_description'](request.user)} | "
                        f"Poste: {poste.nom} ({poste.code})"
                    )
                    
                    return redirect('/common/')
                
                # Ajouter le poste au contexte de la requête
                request.current_poste = poste
                
            except Poste.DoesNotExist:
                messages.error(request, _("Le poste demandé n'existe pas."))
                return redirect('/common/')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        """Ajoute le poste au contexte"""
        context = super().get_context_data(**kwargs)
        if hasattr(self.request, 'current_poste'):
            context['current_poste'] = self.request.current_poste
        return context


# ===================================================================
# MIXIN POUR LE BILINGUISME
# ===================================================================

class BilingualMixin:
    """
    Mixin pour supporter le bilinguisme FR/EN dans les vues
    Ajoute automatiquement les informations de langue au contexte
    """
    
    def get_context_data(self, **kwargs):
        """Ajoute les informations de langue au contexte des templates"""
        context = super().get_context_data(**kwargs)
        
        current_lang = getattr(self.request, 'LANGUAGE_CODE', 'fr')
        
        context.update({
            'current_language': current_lang,
            'is_french': current_lang == 'fr',
            'is_english': current_lang == 'en',
            'available_languages': [
                ('fr', _('Français')),
                ('en', _('English'))
            ]
        })
        
        return context


# ===================================================================
# MIXIN POUR LA PAGINATION
# ===================================================================

class PaginationMixin:
    """
    Mixin pour la pagination standardisée dans SUPPER
    Utilise les paramètres de pagination définis dans settings.py
    """
    
    def get_paginate_by(self, queryset):
        """Détermine le nombre d'éléments par page selon le type de contenu"""
        from django.conf import settings
        
        pagination_config = getattr(settings, 'PAGINATION_CONFIG', {})
        
        model_name = getattr(self, 'model', None)
        if model_name:
            model_class_name = model_name.__name__.upper()
            
            model_pagination = {
                'JOURNALAUDIT': pagination_config.get('LOGS_PER_PAGE', 50),
                'UTILISATEURSUPPER': pagination_config.get('USERS_PER_PAGE', 25),
                'INVENTAIREJOURNALIER': pagination_config.get('INVENTAIRES_PER_PAGE', 30),
                'RECETTEJOURNALIERE': pagination_config.get('RECETTES_PER_PAGE', 30),
                'POSTE': pagination_config.get('POSTES_PER_PAGE', 25),
                'AMENDE': pagination_config.get('AMENDES_PER_PAGE', 30),
                'STOCKTICKETS': pagination_config.get('STOCKS_PER_PAGE', 25),
            }
            
            return model_pagination.get(model_class_name, 25)
        
        return 25
    
    def get_context_data(self, **kwargs):
        """Ajoute des informations de pagination utiles au contexte"""
        context = super().get_context_data(**kwargs)
        
        if 'page_obj' in context:
            page_obj = context['page_obj']
            context.update({
                'pagination_info': {
                    'current_page': page_obj.number,
                    'total_pages': page_obj.paginator.num_pages,
                    'total_items': page_obj.paginator.count,
                    'items_per_page': page_obj.paginator.per_page,
                    'start_index': page_obj.start_index(),
                    'end_index': page_obj.end_index(),
                }
            })
        
        return context


# ===================================================================
# MIXIN POUR L'EXPORT
# ===================================================================

class ExportMixin:
    """
    Mixin pour ajouter des fonctionnalités d'export aux vues liste
    Permet l'export en CSV/Excel des données affichées
    """
    export_fields = None
    export_filename = None
    
    def get(self, request, *args, **kwargs):
        """Gestion des requêtes GET avec support d'export"""
        export_format = request.GET.get('export')
        
        if export_format in ['csv', 'excel', 'pdf']:
            return self.export_data(export_format)
        
        return super().get(request, *args, **kwargs)
    
    def export_data(self, format_type):
        """Exporte les données au format demandé"""
        utils = _get_utils()
        
        queryset = self.get_queryset()
        filename = self.export_filename or f"{self.__class__.__name__.lower()}"
        
        # Journaliser l'export
        utils['log_user_action'](
            user=self.request.user,
            action="EXPORT_DONNEES",
            details=f"Export {format_type.upper()} de {queryset.count()} éléments",
            request=self.request,
            format=format_type.upper(),
            nb_elements=queryset.count(),
            vue=self.__class__.__name__
        )
        
        logger.info(
            f"📤 EXPORT | {utils['get_user_short_description'](self.request.user)} | "
            f"Format: {format_type.upper()} | {queryset.count()} éléments"
        )
        
        from common.utils import exporter_donnees_csv
        
        if hasattr(self, 'export_fields') and self.export_fields:
            fields = self.export_fields
        else:
            fields = self.model._meta.fields
        
        return exporter_donnees_csv(queryset, fields, filename)


# ===================================================================
# MIXIN POUR CRÉATION AVEC AUDIT
# ===================================================================

class CreateWithAuditMixin:
    """
    Mixin pour les vues de création avec journalisation automatique
    """
    
    def form_valid(self, form):
        """Journalise la création après validation du formulaire"""
        response = super().form_valid(form)
        
        utils = _get_utils()
        
        # Journaliser la création
        obj = self.object
        model_name = obj.__class__.__name__
        
        utils['log_user_action'](
            user=self.request.user,
            action=f"CREATION_{model_name.upper()}",
            details=f"Création de {model_name}: {str(obj)}",
            request=self.request,
            objet_cree=str(obj),
            model=model_name
        )
        
        logger.info(
            f"✅ CRÉATION | {utils['get_user_short_description'](self.request.user)} | "
            f"{model_name}: {str(obj)}"
        )
        
        return response


# ===================================================================
# MIXIN POUR MODIFICATION AVEC AUDIT
# ===================================================================

class UpdateWithAuditMixin:
    """
    Mixin pour les vues de modification avec journalisation des changements
    """
    
    def get_object(self, queryset=None):
        """Capture l'état avant modification"""
        obj = super().get_object(queryset)
        
        # Stocker l'état avant modification
        self._original_values = {}
        for field in obj._meta.fields:
            self._original_values[field.name] = getattr(obj, field.name)
        
        return obj
    
    def form_valid(self, form):
        """Journalise les modifications après validation"""
        response = super().form_valid(form)
        
        utils = _get_utils()
        obj = self.object
        model_name = obj.__class__.__name__
        
        # Détecter les changements
        changes = []
        for field_name, old_value in self._original_values.items():
            new_value = getattr(obj, field_name)
            if old_value != new_value:
                changes.append(f"{field_name}: {old_value} → {new_value}")
        
        if changes:
            utils['log_user_action'](
                user=self.request.user,
                action=f"MODIFICATION_{model_name.upper()}",
                details=f"Modification de {model_name}: {str(obj)} | Changements: {', '.join(changes[:5])}",
                request=self.request,
                objet_modifie=str(obj),
                model=model_name,
                nb_changements=len(changes)
            )
            
            logger.info(
                f"📝 MODIFICATION | {utils['get_user_short_description'](self.request.user)} | "
                f"{model_name}: {str(obj)} | {len(changes)} changement(s)"
            )
        
        return response


# ===================================================================
# MIXIN POUR SUPPRESSION AVEC AUDIT
# ===================================================================

class DeleteWithAuditMixin:
    """
    Mixin pour les vues de suppression avec journalisation
    """
    
    def delete(self, request, *args, **kwargs):
        """Journalise avant la suppression"""
        utils = _get_utils()
        
        obj = self.get_object()
        model_name = obj.__class__.__name__
        obj_str = str(obj)
        
        # Journaliser avant suppression
        utils['log_user_action'](
            user=request.user,
            action=f"SUPPRESSION_{model_name.upper()}",
            details=f"Suppression de {model_name}: {obj_str}",
            request=request,
            objet_supprime=obj_str,
            model=model_name
        )
        
        logger.info(
            f"🗑️ SUPPRESSION | {utils['get_user_short_description'](request.user)} | "
            f"{model_name}: {obj_str}"
        )
        
        return super().delete(request, *args, **kwargs)


# ===================================================================
# MIXIN COMBINÉ POUR VUES CRUD COMPLÈTES
# ===================================================================

class FullAuditMixin(AuditMixin, BilingualMixin, PaginationMixin):
    """
    Mixin combinant toutes les fonctionnalités d'audit, bilinguisme et pagination
    À utiliser pour les vues CRUD standard
    """
    pass


class FullPermissionMixin(GranularPermissionMixin, AuditMixin, BilingualMixin):
    """
    Mixin combinant permissions granulaires, audit et bilinguisme
    """
    pass


# ===================================================================
# ALIAS POUR RÉTROCOMPATIBILITÉ
# ===================================================================

# Anciens noms de mixins pour compatibilité avec le code existant
RoleRequiredMixin = GranularPermissionMixin
InventaireRequiredMixin = InventairePermissionMixin
PeageRequiredMixin = RecettePeagePermissionMixin
PesageRequiredMixin = PesagePermissionMixin
PersonnelRequiredMixin = GestionUtilisateursPermissionMixin
BudgetRequiredMixin = GranularPermissionMixin
ArchivesRequiredMixin = GranularPermissionMixin
StocksPSRRRequiredMixin = StockPeagePermissionMixin
StockInfoRequiredMixin = GranularPermissionMixin
ChefPosteOnlyMixin = ChefPosteRequiredMixin
AgentInventaireOnlyMixin = InventairePermissionMixin