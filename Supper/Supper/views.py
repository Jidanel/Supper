# ===================================================================
# Supper/views.py - Vue d'accueil avec redirection intelligente
# Support bilingue FR/EN et commentaires détaillés
# ===================================================================

from django.shortcuts import redirect
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin


class HomeView(View):
    """
    Vue d'accueil pour l'URL racine (127.0.0.1:8000/)
    Redirige intelligemment selon l'état de connexion de l'utilisateur
    """
    
    def get(self, request):
        """
        Gestion de l'accès à la page d'accueil
        Args:
            request: Requête HTTP de l'utilisateur
        Returns:
            HttpResponse: Redirection vers login ou dashboard approprié
        """
        # Vérifier si l'utilisateur est déjà connecté
        if request.user.is_authenticated:
            # Utilisateur connecté : rediriger vers son dashboard selon son rôle
            user = request.user
            
            # Redirection intelligente selon le rôle de l'utilisateur
            if user.is_admin():
                # Administrateurs → Dashboard admin complet
                return redirect('common:dashboard_admin')
            elif user.is_chef_poste():
                # Chefs de poste → Dashboard spécialisé
                return redirect('common:dashboard_chef')
            elif user.habilitation == 'agent_inventaire':
                # Agents inventaire → Interface simplifiée
                return redirect('common:dashboard_agent')
            else:
                # Autres rôles → Dashboard général
                return redirect('common:dashboard_general')
        else:
            # Utilisateur non connecté : rediriger vers la page de connexion
            # Ceci fait de /accounts/login/ l'URL par défaut pour 127.0.0.1:8000
            return redirect('accounts:login')