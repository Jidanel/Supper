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


@login_required
def regularisation_historique(request):
    """Formulaire de régularisation de l'historique avec date d'effet libre (admin). Préremplissable depuis la page
    de cohérence : ?poste=ID&sens=CREDIT|DEBIT&tickets=N&mois=AAAA-MM."""
    from datetime import date as _date  # Dates
    from common.utils import log_user_action  # Journalisation
    from inventaire.services.regularisation_service import regulariser, RegularisationError  # Logique métier
    from inventaire.services.coherence_stock import ecart_poste  # Écart avant/après
    if not is_admin_user(request.user):
        log_acces_refuse(request.user, "regularisation_historique", "Administrateur requis")
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('/')
    postes = Poste.objects.filter(type='peage', is_active=True).order_by('nom')
    source = request.POST if request.method == 'POST' else request.GET  # Valeurs du formulaire ou du prérempli
    mois = source.get('mois') or _date.today().strftime('%Y-%m')
    poste_sel = postes.filter(pk=source.get('poste')).first() if source.get('poste') else None
    if request.method == 'POST' and poste_sel:
        try:
            jour = _date.fromisoformat(source.get('date_effet') or '')
            hist = regulariser(poste_sel, source.get('sens'), int(source.get('tickets') or 0), jour,
                               source.get('motif'), request.user)
            debut = jour.replace(day=1)  # Début du mois de la correction
            csp, series, ecart = ecart_poste(poste_sel, debut)
            log_user_action(request.user, "RÉGULARISATION HISTORIQUE",
                            f"{poste_sel.nom} | {hist.type_mouvement} {hist.nombre_tickets} tickets | effet {jour:%d/%m/%Y} | {source.get('motif')}", request)
            messages.success(request, f"✅ Régularisation enregistrée pour {poste_sel.nom} ({hist.type_mouvement} de {hist.nombre_tickets} tickets, "
                                      f"effet {jour:%d/%m/%Y}). Écart restant au {debut:%d/%m/%Y} : {ecart:+,.0f} FCFA.")
            return redirect(f"/inventaire/stocks/coherence/?mois={mois}&poste={poste_sel.pk}#detail")
        except RegularisationError as exc:
            messages.error(request, f"❌ {exc}")
        except ValueError:
            messages.error(request, "❌ Date d'effet ou nombre de tickets invalide.")
    return render(request, 'inventaire/regularisation_historique.html', {
        'postes': postes, 'poste_sel': poste_sel, 'mois': mois, 'sens': source.get('sens') or 'DEBIT',
        'tickets': source.get('tickets') or '', 'motif': source.get('motif') or '',
        'date_effet': source.get('date_effet') or f"{mois}-01",
    })
