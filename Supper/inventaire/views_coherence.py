# inventaire/views_coherence.py
# Page d'administration « Cohérence des stocks » : compare CSP et compte d'emploi pour tous les postes en un clic,
# et donne le diagnostic détaillé d'un poste. Accès : administrateur, Service Informatique.
from datetime import date  # Mois par défaut
from django.contrib import messages  # Messages utilisateur
from django.contrib.auth.decorators import login_required  # Connexion obligatoire
from django.shortcuts import render, redirect  # Rendu et redirection

from accounts.models import Poste  # Postes
from common.permissions import is_admin_user, log_acces_refuse  # Droits
from inventaire.services.coherence_stock import ecarts_mois, detail_poste  # Calculs


@login_required
def coherence_stock(request):
    """Tableau de tous les postes (écart CSP / séries au début du mois) + détail d'un poste (?poste=ID)."""
    if not is_admin_user(request.user):  # Réservé aux administrateurs
        log_acces_refuse(request.user, "coherence_stock", "Administrateur requis")
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('/')
    mois = request.GET.get('mois') or date.today().strftime('%Y-%m')  # Mois contrôlé (AAAA-MM)
    try:
        debut, lignes = ecarts_mois(mois)  # Tous les postes
    except Exception:
        messages.error(request, "Mois invalide : utilisez le format AAAA-MM (ex. 2026-11).")
        return redirect(request.path)
    detail, poste_sel = None, None
    if request.GET.get('poste'):  # Diagnostic d'un poste
        poste_sel = Poste.objects.filter(pk=request.GET['poste'], type='peage').first()
        if poste_sel:
            detail = detail_poste(poste_sel, debut)
    contexte = {
        'mois': mois, 'debut': debut, 'lignes': lignes, 'poste_sel': poste_sel, 'detail': detail,
        'nb_incoherents': sum(1 for l in lignes if not l['coherent']), 'nb_postes': len(lignes),
        'total_ecart': sum(l['ecart'] for l in lignes),
    }
    return render(request, 'inventaire/coherence_stock.html', contexte)
