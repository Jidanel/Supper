# ===================================================================
# accounts/views_permissions_helpers.py - Fonctions utilitaires pour les vues
# ===================================================================
#
# Ce fichier contient les fonctions helpers à utiliser dans creer_utilisateur
# et modifier_utilisateur pour gérer le contexte des permissions.
# ===================================================================

import json
import logging
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _

# Import depuis permissions_config.py (à placer dans accounts/)
from .permissions_config import (
    TOUTES_PERMISSIONS,
    CATEGORIES_PERMISSIONS,
    LABELS_PERMISSIONS,
    PERMISSIONS_PAR_HABILITATION,
    get_permissions_context_pour_template,
    get_permissions_json_pour_js,
)

logger = logging.getLogger('supper')


# ===================================================================
# FONCTIONS DE DÉTECTION DES MODIFICATIONS DE PERMISSIONS
# ===================================================================

def detecter_modifications_permissions(user, post_data):
    """
    Détecte si des permissions ont été modifiées via les checkboxes du formulaire.
    
    Args:
        user: Instance UtilisateurSUPPER existante
        post_data: request.POST
    
    Returns:
        tuple: (has_custom_perms: bool, perm_changes: list)
    """
    perm_changes = []
    
    for perm in TOUTES_PERMISSIONS:
        # Valeur actuelle de l'utilisateur
        valeur_actuelle = getattr(user, perm, False) if user else False
        
        # Valeur du formulaire (checkbox cochée = présent dans POST)
        valeur_formulaire = perm in post_data
        
        if valeur_actuelle != valeur_formulaire:
            action = "ajoutée" if valeur_formulaire else "retirée"
            perm_changes.append(f"{LABELS_PERMISSIONS.get(perm, perm)} ({action})")
    
    return bool(perm_changes), perm_changes


def appliquer_permissions_formulaire(user, post_data):
    """
    Applique les permissions du formulaire à l'utilisateur.
    Les checkboxes cochées sont dans POST, les non-cochées sont absentes.
    
    Args:
        user: Instance UtilisateurSUPPER à modifier
        post_data: request.POST
    """
    for perm in TOUTES_PERMISSIONS:
        # Checkbox cochée = présent dans POST
        setattr(user, perm, perm in post_data)


def comparer_permissions_avec_defaut(user):
    """
    Compare les permissions actuelles d'un utilisateur avec celles par défaut
    de son habilitation.
    
    Args:
        user: Instance UtilisateurSUPPER
    
    Returns:
        dict: {
            'personnalisees': list des permissions différentes du défaut,
            'ajoutees': list des permissions ajoutées,
            'retirees': list des permissions retirées
        }
    """
    if not user or not user.habilitation:
        return {'personnalisees': [], 'ajoutees': [], 'retirees': []}
    
    perms_defaut = PERMISSIONS_PAR_HABILITATION.get(user.habilitation, [])
    
    ajoutees = []
    retirees = []
    
    for perm in TOUTES_PERMISSIONS:
        valeur_utilisateur = getattr(user, perm, False)
        valeur_defaut = perm in perms_defaut
        
        if valeur_utilisateur and not valeur_defaut:
            ajoutees.append(LABELS_PERMISSIONS.get(perm, perm))
        elif not valeur_utilisateur and valeur_defaut:
            retirees.append(LABELS_PERMISSIONS.get(perm, perm))
    
    return {
        'personnalisees': ajoutees + retirees,
        'ajoutees': ajoutees,
        'retirees': retirees
    }


# ===================================================================
# FONCTIONS DE PRÉPARATION DU CONTEXTE POUR LES TEMPLATES
# ===================================================================

def preparer_contexte_permissions_creation(habilitation=None):
    """
    Prépare le contexte complet pour le template de création d'utilisateur.
    
    Args:
        habilitation: Code de l'habilitation présélectionnée (optionnel)
    
    Returns:
        dict: Contexte à merger avec le contexte principal de la vue
    """
    return {
        # Permissions organisées par catégorie pour l'accordéon
        'permissions_categories': get_permissions_context_pour_template(
            user=None, 
            habilitation=habilitation
        ),
        
        # JSON des permissions par habilitation pour JavaScript
        'permissions_par_habilitation_json': get_permissions_json_pour_js(),
        
        # Liste des toutes les permissions (pour JavaScript)
        'toutes_permissions_json': json.dumps(TOUTES_PERMISSIONS),
        
        # Compteurs
        'total_permissions': len(TOUTES_PERMISSIONS),
        
        # Labels pour JavaScript
        'labels_permissions_json': json.dumps({
            k: str(v) for k, v in LABELS_PERMISSIONS.items()
        }),
        
        # Flag pour afficher la section permissions
        'show_permissions_section': True,
    }


def preparer_contexte_permissions_modification(user):
    """
    Prépare le contexte complet pour le template de modification d'utilisateur.
    
    Args:
        user: Instance UtilisateurSUPPER à modifier
    
    Returns:
        dict: Contexte à merger avec le contexte principal de la vue
    """
    # Compter les permissions actives
    count_actives = sum(1 for perm in TOUTES_PERMISSIONS if getattr(user, perm, False))
    
    # Comparer avec les permissions par défaut
    comparaison = comparer_permissions_avec_defaut(user)
    
    return {
        # Permissions organisées par catégorie pour l'accordéon
        'permissions_categories': get_permissions_context_pour_template(user=user),
        
        # JSON des permissions par habilitation pour JavaScript
        'permissions_par_habilitation_json': get_permissions_json_pour_js(),
        
        # Liste des toutes les permissions (pour JavaScript)
        'toutes_permissions_json': json.dumps(TOUTES_PERMISSIONS),
        
        # Compteurs
        'count_permissions_actives': count_actives,
        'total_permissions': len(TOUTES_PERMISSIONS),
        
        # Personnalisations détectées
        'permissions_personnalisees': comparaison['personnalisees'],
        'has_permissions_personnalisees': bool(comparaison['personnalisees']),
        
        # Labels pour JavaScript
        'labels_permissions_json': json.dumps({
            k: str(v) for k, v in LABELS_PERMISSIONS.items()
        }),
        
        # Flag pour afficher la section permissions
        'show_permissions_section': True,
    }


# ===================================================================
# EXEMPLE DE VUE CREER_UTILISATEUR MISE À JOUR
# ===================================================================

"""
Exemple d'utilisation dans views.py:

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
"""


# ===================================================================
# EXEMPLE DE VUE MODIFIER_UTILISATEUR MISE À JOUR
# ===================================================================

"""
Exemple d'utilisation dans views.py:

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
"""