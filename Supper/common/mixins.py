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
        return self.request.user.is_authenticated and self.request.user.is_admin()
    
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
            (self.request.user.is_chef_poste() or self.request.user.is_admin())
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