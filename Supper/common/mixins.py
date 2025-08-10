# ===================================================================
# common/mixins.py - Mixins pour les vues (CORRIGÉ)
# Chaque ligne est commentée pour faciliter la maintenance
# Support bilingue FR/EN intégré
# ===================================================================

from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from common.utils import log_user_action


class AuditMixin:
    """
    Mixin pour ajouter automatiquement la journalisation aux vues
    Utilise le système d'audit SUPPER pour tracer toutes les actions utilisateur
    Compatible avec les vues basées sur les classes Django
    """
    audit_action = None  # Action à journaliser (définie dans chaque vue)
    
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
        # Vérifier si l'action doit être journalisée et si l'utilisateur est connecté
        if self.audit_action and request.user.is_authenticated:
            # Journaliser l'accès à cette vue avec les détails
            log_user_action(
                user=request.user,
                action=self.audit_action,
                details=_("Vue: %(class_name)s") % {'class_name': self.__class__.__name__},
                request=request
            )
        
        # Continuer avec la vue normale
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(UserPassesTestMixin):
    """
    Mixin pour restreindre l'accès aux utilisateurs administrateurs uniquement
    Vérifie les permissions avant d'afficher la vue
    Redirige vers une page appropriée si l'accès est refusé
    """
    
    def test_func(self):
        """
        Test de permissions pour l'accès administrateur
        Returns:
            bool: True si l'utilisateur est connecté ET administrateur
        """
        # Vérifier que l'utilisateur est connecté ET a des droits admin
        return self.request.user.is_authenticated and self.request.user.is_admin
    
    def handle_no_permission(self):
        """
        Gestion du refus d'accès avec journalisation et message d'erreur
        Returns:
            HttpResponse: Redirection vers la page appropriée
        """
        # Si l'utilisateur est connecté mais n'a pas les droits
        if self.request.user.is_authenticated:
            # Afficher un message d'erreur en français (par défaut) ou anglais
            messages.error(
                self.request,
                _("Accès interdit. Permissions administrateur requises.")
            )
            
            # Journaliser la tentative d'accès non autorisée
            log_user_action(
                user=self.request.user,
                action=_("ACCÈS REFUSÉ - Permissions admin requises"),
                details=_("Tentative d'accès à %(class_name)s") % {
                    'class_name': self.__class__.__name__
                },
                request=self.request
            )
            
            # Rediriger vers le dashboard général
            return redirect('common:dashboard_general')
        else:
            # Utilisateur non connecté : rediriger vers la page de connexion
            return redirect('accounts:login')


class ChefPosteRequiredMixin(UserPassesTestMixin):
    """
    Mixin pour restreindre l'accès aux chefs de poste et administrateurs
    Les administrateurs ont également accès pour supervision
    """
    
    def test_func(self):
        """
        Test de permissions pour chef de poste ou administrateur
        Returns:
            bool: True si chef de poste OU administrateur
        """
        # Vérifier la connexion et les rôles appropriés
        return (
            self.request.user.is_authenticated and 
            (self.request.user.is_chef_poste() or self.request.user.is_admin)
        )
    
    def handle_no_permission(self):
        """
        Gestion du refus d'accès pour non-chef de poste
        Returns:
            HttpResponse: Redirection appropriée
        """
        if self.request.user.is_authenticated:
            # Message d'erreur adapté au contexte
            messages.error(
                self.request,
                _("Accès interdit. Permissions chef de poste requises.")
            )
            # Redirection vers le dashboard général
            return redirect('common:dashboard_general')
        else:
            # Redirection vers la connexion
            return redirect('accounts:login')


class InventaireRequiredMixin(UserPassesTestMixin):
    """
    Mixin pour les utilisateurs autorisés à gérer l'inventaire
    Vérifie la permission spécifique peut_gerer_inventaire
    """
    
    def test_func(self):
        """
        Test de permission pour la gestion d'inventaire
        Returns:
            bool: True si autorisé à gérer l'inventaire
        """
        # Vérifier la connexion et la permission spécifique inventaire
        return (
            self.request.user.is_authenticated and 
            self.request.user.peut_gerer_inventaire
        )
    
    def handle_no_permission(self):
        """
        Gestion du refus d'accès pour gestion inventaire
        Returns:
            HttpResponse: Redirection avec message d'erreur
        """
        if self.request.user.is_authenticated:
            # Message spécifique à l'inventaire
            messages.error(
                self.request,
                _("Accès interdit. Permissions de gestion d'inventaire requises.")
            )
            return redirect('common:dashboard_general')
        else:
            return redirect('accounts:login')


class PosteAccessMixin:
    """
    Mixin pour vérifier l'accès aux données d'un poste spécifique
    S'assure que l'utilisateur peut consulter/modifier les données du poste demandé
    Ajoute automatiquement le poste au contexte de la requête
    """
    
    def dispatch(self, request, *args, **kwargs):
        """
        Vérification de l'accès au poste avant affichage de la vue
        Args:
            request: Requête HTTP
            *args, **kwargs: Paramètres d'URL (peut contenir poste_id)
        Returns:
            HttpResponse: Vue normale ou redirection si accès refusé
        """
        # Récupérer l'ID du poste depuis les paramètres d'URL ou GET
        poste_id = kwargs.get('poste_id') or request.GET.get('poste_id')
        
        # Si un poste est spécifié, vérifier les permissions
        if poste_id:
            try:
                # Importer ici pour éviter les imports circulaires
                from accounts.models import Poste
                
                # Récupérer le poste depuis la base de données
                poste = Poste.objects.get(id=poste_id)
                
                # Vérifier si l'utilisateur peut accéder à ce poste
                if not request.user.peut_acceder_poste(poste):
                    # Afficher un message d'erreur avec le nom du poste
                    messages.error(
                        request,
                        _("Accès interdit au poste %(poste_nom)s.") % {
                            'poste_nom': poste.nom
                        }
                    )
                    
                    # Journaliser la tentative d'accès non autorisée
                    log_user_action(
                        user=request.user,
                        action=_("ACCÈS REFUSÉ - Poste non autorisé"),
                        details=_("Tentative d'accès au poste %(poste_nom)s") % {
                            'poste_nom': poste.nom
                        },
                        request=request
                    )
                    
                    # Rediriger vers le dashboard général
                    return redirect('common:dashboard_general')
                
                # Ajouter le poste au contexte de la requête pour utilisation dans la vue
                request.current_poste = poste
                
            except Poste.DoesNotExist:
                # Le poste demandé n'existe pas
                messages.error(
                    request, 
                    _("Le poste demandé n'existe pas.")
                )
                return redirect('common:dashboard_general')
        
        # Continuer avec la vue normale si tout est OK
        return super().dispatch(request, *args, **kwargs)


class BilingualMixin:
    """
    Mixin pour supporter le bilinguisme FR/EN dans les vues
    Ajoute automatiquement les informations de langue au contexte
    Facilite la gestion des traductions dans les templates
    """
    
    def get_context_data(self, **kwargs):
        """
        Ajoute les informations de langue au contexte des templates
        Returns:
            dict: Contexte enrichi avec les données multilingues
        """
        # Récupérer le contexte de base de la vue parente
        context = super().get_context_data(**kwargs)
        
        # Ajouter les informations de langue courante
        context.update({
            'current_language': self.request.LANGUAGE_CODE,  # Code langue actuel (fr/en)
            'is_french': self.request.LANGUAGE_CODE == 'fr',  # Helper pour les templates
            'is_english': self.request.LANGUAGE_CODE == 'en',  # Helper pour les templates
            'available_languages': [  # Langues disponibles avec labels
                ('fr', _('Français')),
                ('en', _('English'))
            ]
        })
        
        return context


class PaginationMixin:
    """
    Mixin pour la pagination standardisée dans SUPPER
    Utilise les paramètres de pagination définis dans settings.py
    Ajoute des informations de pagination utiles aux templates
    """
    
    def get_paginate_by(self, queryset):
        """
        Détermine le nombre d'éléments par page selon le type de contenu
        Returns:
            int: Nombre d'éléments par page
        """
        from django.conf import settings
        
        # Récupérer la configuration de pagination
        pagination_config = getattr(settings, 'PAGINATION_CONFIG', {})
        
        # Retourner la pagination selon le type de vue
        model_name = getattr(self, 'model', None)
        if model_name:
            # Utiliser le nom du modèle pour déterminer la pagination
            model_class_name = model_name.__name__.upper()
            
            # Mapping des modèles vers leurs paramètres de pagination
            model_pagination = {
                'JOURNALAUDIT': pagination_config.get('LOGS_PER_PAGE', 50),
                'UTILISATEURSUPPER': pagination_config.get('USERS_PER_PAGE', 25),
                'INVENTAIREJOURNALIER': pagination_config.get('INVENTAIRES_PER_PAGE', 30),
                'RECETTEJOURNALIERE': pagination_config.get('RECETTES_PER_PAGE', 30),
            }
            
            return model_pagination.get(model_class_name, 25)  # 25 par défaut
        
        # Pagination par défaut si pas de modèle spécifique
        return 25
    
    def get_context_data(self, **kwargs):
        """
        Ajoute des informations de pagination utiles au contexte
        Returns:
            dict: Contexte avec métadonnées de pagination
        """
        context = super().get_context_data(**kwargs)
        
        # Ajouter des informations de pagination si applicable
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


class ExportMixin:
    """
    Mixin pour ajouter des fonctionnalités d'export aux vues liste
    Permet l'export en CSV/Excel des données affichées
    Respecte les permissions d'accès de l'utilisateur
    """
    
    def get(self, request, *args, **kwargs):
        """
        Gestion des requêtes GET avec support d'export
        Args:
            request: Requête HTTP
        Returns:
            HttpResponse: Vue normale ou fichier d'export
        """
        # Vérifier si un export est demandé
        export_format = request.GET.get('export')
        
        if export_format in ['csv', 'excel']:
            # Effectuer l'export au lieu d'afficher la vue
            return self.export_data(export_format)
        
        # Affichage normal de la vue
        return super().get(request, *args, **kwargs)
    
    def export_data(self, format_type):
        """
        Exporte les données au format demandé
        Args:
            format_type (str): 'csv' ou 'excel'
        Returns:
            HttpResponse: Fichier d'export
        """
        # Récupérer le queryset de la vue
        queryset = self.get_queryset()
        
        # Nom du fichier d'export basé sur la vue
        filename = f"{self.__class__.__name__.lower()}_{format_type}"
        
        # Utiliser la fonction d'export des utilitaires
        from common.utils import exporter_donnees_csv
        
        # Déterminer les champs à exporter selon le modèle
        if hasattr(self, 'export_fields'):
            fields = self.export_fields  # Champs définis dans la vue
        else:
            # Champs par défaut du modèle
            fields = self.model._meta.fields
        
        # Journaliser l'export
        log_user_action(
            user=self.request.user,
            action=_("Export de données"),
            details=_("Export %(format)s de %(count)d éléments") % {
                'format': format_type.upper(),
                'count': queryset.count()
            },
            request=self.request
        )
        
        # Retourner le fichier d'export
        return exporter_donnees_csv(queryset, fields, filename)
    
# ===================================================================
# À AJOUTER À LA FIN DE common/mixins.py
# RoleRequiredMixin - Mixin manquant pour la gestion des permissions
# ===================================================================

class RoleRequiredMixin(UserPassesTestMixin):
    """
    Mixin générique pour vérifier les rôles et permissions spécifiques
    Peut vérifier les habilitations, permissions ou méthodes personnalisées
    Plus flexible que AdminRequiredMixin pour différents types de permissions
    """
    
    # Attributs à définir dans chaque vue utilisant ce mixin
    required_permission = None  # Permission requise (ex: 'peut_gerer_inventaire')
    required_role = None        # Rôle requis (ex: 'admin_principal', 'chef_peage')
    required_habilitation = None # Alias pour required_role (compatibilité)
    allow_superuser = True      # Les superusers passent automatiquement
    
    def test_func(self):
        """
        Test principal de permissions avec logique flexible
        Returns:
            bool: True si l'utilisateur a les permissions requises
        """
        # Vérifier que l'utilisateur est connecté
        if not self.request.user.is_authenticated:
            return False
        
        user = self.request.user
        
        # Les superusers passent automatiquement (sauf si explicitement désactivé)
        if self.allow_superuser and user.is_superuser:
            return True
        
        # Vérifier la permission spécifique
        if self.required_permission:
            return self._check_permission(user, self.required_permission)
        
        # Vérifier le rôle/habilitation
        role_to_check = self.required_role or self.required_habilitation
        if role_to_check:
            return self._check_role(user, role_to_check)
        
        # Si aucun critère défini, accès refusé par sécurité
        return False
    
    def _check_permission(self, user, permission):
        """
        Vérifie une permission spécifique sur l'utilisateur
        Args:
            user: Utilisateur à vérifier
            permission (str): Nom de la permission à vérifier
        Returns:
            bool: True si l'utilisateur a la permission
        """
        # Vérifier si c'est un attribut direct de l'utilisateur
        if hasattr(user, permission):
            return getattr(user, permission, False)
        
        # Vérifier si c'est une méthode de l'utilisateur
        if hasattr(user, permission) and callable(getattr(user, permission)):
            try:
                return getattr(user, permission)()
            except Exception:
                return False
        
        # Vérifications spéciales pour SUPPER
        permission_checks = {
            'peut_gerer_inventaire': lambda u: getattr(u, 'peut_gerer_inventaire', False),
            'peut_gerer_peage': lambda u: getattr(u, 'peut_gerer_peage', False),
            'peut_gerer_pesage': lambda u: getattr(u, 'peut_gerer_pesage', False),
            'peut_gerer_personnel': lambda u: getattr(u, 'peut_gerer_personnel', False),
            'peut_gerer_budget': lambda u: getattr(u, 'peut_gerer_budget', False),
            'peut_gerer_archives': lambda u: getattr(u, 'peut_gerer_archives', False),
            'peut_gerer_stocks_psrr': lambda u: getattr(u, 'peut_gerer_stocks_psrr', False),
            'peut_gerer_stock_info': lambda u: getattr(u, 'peut_gerer_stock_info', False),
            'is_admin': lambda u: u.is_admin() if hasattr(u, 'is_admin') else u.is_superuser,
            'is_chef_poste': lambda u: u.is_chef_poste() if hasattr(u, 'is_chef_poste') else False,
            'is_agent_inventaire': lambda u: getattr(u, 'habilitation', '') == 'agent_inventaire',
        }
        
        # Appliquer la vérification si elle existe
        if permission in permission_checks:
            return permission_checks[permission](user)
        
        # Permission inconnue = accès refusé
        return False
    
    def _check_role(self, user, role):
        """
        Vérifie si l'utilisateur a le rôle/habilitation requis
        Args:
            user: Utilisateur à vérifier
            role (str ou list): Rôle(s) requis
        Returns:
            bool: True si l'utilisateur a le rôle requis
        """
        user_habilitation = getattr(user, 'habilitation', '')
        
        # Si role est une liste, vérifier si l'utilisateur a l'un des rôles
        if isinstance(role, (list, tuple)):
            return user_habilitation in role
        
        # Vérification simple du rôle
        if isinstance(role, str):
            return user_habilitation == role
        
        # Type de rôle non supporté
        return False
    
    def handle_no_permission(self):
        """
        Gestion personnalisée du refus d'accès avec messages contextuels
        Returns:
            HttpResponse: Redirection appropriée avec message d'erreur
        """
        if self.request.user.is_authenticated:
            # Utilisateur connecté mais sans permissions
            
            # Message d'erreur personnalisé selon le type de permission manquante
            if self.required_permission:
                error_message = self._get_permission_error_message(self.required_permission)
            elif self.required_role or self.required_habilitation:
                role = self.required_role or self.required_habilitation
                error_message = self._get_role_error_message(role)
            else:
                error_message = _("Accès interdit. Permissions insuffisantes.")
            
            # Afficher le message d'erreur
            messages.error(self.request, error_message)
            
            # Journaliser la tentative d'accès non autorisée
            log_user_action(
                user=self.request.user,
                action=_("ACCÈS REFUSÉ - Permissions insuffisantes"),
                details=_("Tentative d'accès à %(view)s - Permission: %(perm)s - Rôle: %(role)s") % {
                    'view': self.__class__.__name__,
                    'perm': self.required_permission or 'Non définie',
                    'role': self.required_role or self.required_habilitation or 'Non défini'
                },
                request=self.request
            )
            
            # Redirection intelligente selon le rôle de l'utilisateur
            return self._get_redirect_for_user(self.request.user)
        else:
            # Utilisateur non connecté : rediriger vers la connexion
            return redirect('accounts:login')
    
    def _get_permission_error_message(self, permission):
        """
        Génère un message d'erreur contextualisé selon la permission manquante
        Args:
            permission (str): Permission manquante
        Returns:
            str: Message d'erreur traduit et contextualisé
        """
        permission_messages = {
            'peut_gerer_inventaire': _("Accès interdit. Permission de gestion d'inventaire requise."),
            'peut_gerer_peage': _("Accès interdit. Permission de gestion des péages requise."),
            'peut_gerer_pesage': _("Accès interdit. Permission de gestion des pesages requise."),
            'peut_gerer_personnel': _("Accès interdit. Permission de gestion du personnel requise."),
            'peut_gerer_budget': _("Accès interdit. Permission de gestion budgétaire requise."),
            'peut_gerer_archives': _("Accès interdit. Permission de gestion des archives requise."),
            'peut_gerer_stocks_psrr': _("Accès interdit. Permission de gestion des stocks PSRR requise."),
            'peut_gerer_stock_info': _("Accès interdit. Permission de gestion des stocks informatiques requise."),
            'is_admin': _("Accès interdit. Permissions administrateur requises."),
            'is_chef_poste': _("Accès interdit. Permissions chef de poste requises."),
            'is_agent_inventaire': _("Accès interdit. Permissions agent d'inventaire requises."),
        }
        
        return permission_messages.get(
            permission, 
            _("Accès interdit. Permission %(permission)s requise.") % {'permission': permission}
        )
    
    def _get_role_error_message(self, role):
        """
        Génère un message d'erreur contextualisé selon le rôle manquant
        Args:
            role (str ou list): Rôle(s) manquant(s)
        Returns:
            str: Message d'erreur traduit et contextualisé
        """
        role_messages = {
            'admin_principal': _("Accès interdit. Rôle administrateur principal requis."),
            'coord_psrr': _("Accès interdit. Rôle coordinateur PSRR requis."),
            'serv_info': _("Accès interdit. Rôle service informatique requis."),
            'serv_emission': _("Accès interdit. Rôle service émission requis."),
            'chef_peage': _("Accès interdit. Rôle chef de péage requis."),
            'chef_pesage': _("Accès interdit. Rôle chef de pesage requis."),
            'agent_inventaire': _("Accès interdit. Rôle agent d'inventaire requis."),
        }
        
        if isinstance(role, (list, tuple)):
            roles_str = ', '.join(role)
            return _("Accès interdit. L'un de ces rôles est requis : %(roles)s") % {'roles': roles_str}
        
        return role_messages.get(
            role,
            _("Accès interdit. Rôle %(role)s requis.") % {'role': role}
        )
    
    def _get_redirect_for_user(self, user):
        """
        Détermine la redirection appropriée selon le rôle de l'utilisateur
        Args:
            user: Utilisateur connecté
        Returns:
            HttpResponse: Redirection vers le dashboard approprié
        """
        # Redirection intelligente selon l'habilitation
        if hasattr(user, 'habilitation'):
            if user.habilitation in ['admin_principal', 'coord_psrr', 'serv_info', 'serv_emission']:
                return redirect('/admin/')  # Dashboard admin
            elif user.habilitation in ['chef_peage', 'chef_pesage']:
                return redirect('/admin/')  # Dashboard chef (temporairement admin)
            elif user.habilitation == 'agent_inventaire':
                return redirect('/admin/')  # Dashboard agent (temporairement admin)
        
        # Redirection par défaut vers le dashboard général
        try:
            return redirect('common:dashboard_general')
        except:
            # Fallback si les URLs common ne sont pas configurées
            return redirect('/admin/')


# ===================================================================
# MIXINS SPÉCIALISÉS BASÉS SUR RoleRequiredMixin
# ===================================================================

class InventaireRequiredMixin(RoleRequiredMixin):
    """
    Mixin spécialisé pour les vues de gestion d'inventaire
    Remplace l'ancienne version pour plus de cohérence
    """
    required_permission = 'peut_gerer_inventaire'


class PeageRequiredMixin(RoleRequiredMixin):
    """Mixin pour les vues de gestion des péages"""
    required_permission = 'peut_gerer_peage'


class PesageRequiredMixin(RoleRequiredMixin):
    """Mixin pour les vues de gestion des pesages"""
    required_permission = 'peut_gerer_pesage'


class PersonnelRequiredMixin(RoleRequiredMixin):
    """Mixin pour les vues de gestion du personnel"""
    required_permission = 'peut_gerer_personnel'


class BudgetRequiredMixin(RoleRequiredMixin):
    """Mixin pour les vues de gestion budgétaire"""
    required_permission = 'peut_gerer_budget'


class ArchivesRequiredMixin(RoleRequiredMixin):
    """Mixin pour les vues de gestion des archives"""
    required_permission = 'peut_gerer_archives'


class StocksPSRRRequiredMixin(RoleRequiredMixin):
    """Mixin pour les vues de gestion des stocks PSRR"""
    required_permission = 'peut_gerer_stocks_psrr'


class StockInfoRequiredMixin(RoleRequiredMixin):
    """Mixin pour les vues de gestion des stocks informatiques"""
    required_permission = 'peut_gerer_stock_info'


class ChefPosteOnlyMixin(RoleRequiredMixin):
    """Mixin strict pour les chefs de poste uniquement"""
    required_role = ['chef_peage', 'chef_pesage']
    allow_superuser = False  # Les superusers doivent avoir le rôle approprié


class AgentInventaireOnlyMixin(RoleRequiredMixin):
    """Mixin strict pour les agents d'inventaire uniquement"""
    required_role = 'agent_inventaire'
    allow_superuser = False  # Les superusers doivent avoir le rôle approprié