# inventaire/views_declaration_historiques.py
# ===================================================================
# MODULE "DÉCLARATION DES HISTORIQUES" - VUE UNIQUE
# Écran unique : poste + mois -> Quittance/Reçu + Historique ACCT/Extrait
# Réutilise : Quittancement, QuittancementPesage,
#             HistoriqueQuittance, HistoriquesPesage (aucune rupture CSP)
# ===================================================================

from django.contrib import messages  # Messages utilisateur
from django.contrib.auth.decorators import login_required  # Couche 1 : connecté
from django.core.exceptions import ValidationError  # Erreurs des clean() de modèles
from django.db import transaction  # Atomicité des écritures
from django.shortcuts import redirect, render  # Rendu et redirection
from django.urls import reverse  # URL par nom
from django.utils.translation import gettext as _  # Traduction FR/EN

from inventaire.models import Quittancement, HistoriqueQuittance  # Péage
from inventaire.models_pesage import QuittancementPesage  # Pesage : quittances
from inventaire.models_historique_pesage import HistoriquesPesage  # Pesage : historiques
from inventaire.forms_declaration_historiques import (  # Formulaires du module
    SelectionPosteMoisForm, QuittanceRecuForm, HistoriqueAcctForm,
    LABEL_QUITTANCE, LABEL_HISTORIQUE_ACCT,
)
from common.permissions import (  # noqa: E402
    has_permission, is_admin_user,
    get_postes_peage_accessibles, get_postes_pesage_accessibles,
)
from common.utils import log_user_action  # Journalisation (signature : user, action, details, request)


def _journaliser(user, action, details, request):
    """Journalise sans jamais faire échouer la vue (try/except dédié)."""
    try:
        log_user_action(user, action, details, request)
    except Exception:  # Un échec de journal ne doit pas bloquer l'utilisateur
        pass


def _peut_declarer(user, est_peage):
    """Permission de saisie selon le type de poste (admin = toujours autorisé)."""
    if is_admin_user(user):  # Administrateurs : accès complet
        return True
    nom = 'peut_saisir_quittance_peage' if est_peage else 'peut_saisir_quittance_pesage'
    return has_permission(user, nom)  # Permission spécifique


def _est_poste_peage(user, poste):
    """True si le poste est un poste de péage accessible, False si pesage, None si refusé."""
    if get_postes_peage_accessibles(user).filter(pk=poste.pk).exists():
        return True  # Péage accessible
    if get_postes_pesage_accessibles(user).filter(pk=poste.pk).exists():
        return False  # Pesage accessible
    return None  # Poste non accessible : accès refusé (couche 2 de sécurité)


def _charger_donnees(poste, mois, est_peage):
    """Retourne (liste_quittances, historique_existant) pour le poste/mois."""
    if est_peage:  # Péage
        quittances = Quittancement.objects.filter(poste=poste, mois=mois).order_by('date_quittancement')
        historique = HistoriqueQuittance.objects.filter(poste=poste, mois=mois).first()
    else:  # Pesage (mois stocké en entier dans l'historique)
        quittances = QuittancementPesage.objects.filter(station=poste, mois=mois).order_by('date_quittancement')
        historique = HistoriquesPesage.objects.filter(
            station=poste, mois=int(mois[5:7]), annee=int(mois[:4])).first()
    return quittances, historique


def _enregistrer_quittance(user, poste, mois, est_peage, d, fichier):
    """Crée la quittance/le reçu. Les clean() des modèles font les contrôles de chevauchement."""
    commun = dict(  # Champs communs péage/pesage
        numero_quittance=d['numero_quittance'], exercice=int(mois[:4]), mois=mois,
        type_declaration=d['type_declaration'], date_quittancement=d['date_quittancement'],
        observations=d.get('observations', ''), saisi_par=user,
    )
    if d['type_declaration'] == 'journaliere':  # Journalière : une date de recette
        commun['date_recette'] = d['date_recette']
    else:  # Décade : période
        commun['date_debut_decade'] = d['date_debut_decade']
        commun['date_fin_decade'] = d['date_fin_decade']
    if est_peage:  # Modèle péage : champ "montant" et "poste"
        obj = Quittancement(poste=poste, montant=d['montant'], **commun)
    else:  # Modèle pesage : "montant_quittance" et "station"
        obj = QuittancementPesage(station=poste, montant_quittance=d['montant'], **commun)
    if fichier:  # Image facultative
        obj.image_quittance = fichier
    from django.core.exceptions import ValidationError
    from inventaire.services.messages_detail import quittance_existante
    message = quittance_existante(d['numero_quittance'])  # Doublon : détail complet (poste, date, heure, auteur)
    if message:
        raise ValidationError(message)
    obj.save()  # save() appelle full_clean() côté péage
    return obj


def _enregistrer_historique(user, poste, mois, est_peage, d, fichier):
    """Crée ou met à jour l'historique du mois (unique par poste/mois)."""
    annee, num_mois = int(mois[:4]), int(mois[5:7])  # Découpage AAAA-MM
    if est_peage:  # Péage
        obj = HistoriqueQuittance.objects.filter(poste=poste, mois=mois).first() or \
            HistoriqueQuittance(poste=poste, mois=mois, annee=annee, saisi_par=user)
        if fichier:
            obj.image_historique = fichier
    else:  # Pesage
        obj = HistoriquesPesage.objects.filter(station=poste, mois=num_mois, annee=annee).first() or \
            HistoriquesPesage(station=poste, mois=num_mois, annee=annee, cree_par=user)
        if fichier:
            obj.image_page1 = fichier
    obj.montant_reel = d['montant_reel']  # Montant de l'extrait de compte (alimente le CSP)
    # Colonne montant_global conservée en base (pas de rupture de schéma) :
    # on la remplit avec le montant de l'extrait de compte pour respecter la contrainte montant_reel <= montant_global
    obj.montant_global = d['montant_reel']
    obj.observations = d.get('observations', '')  # Observations
    obj.save()  # Création ou mise à jour
    return obj


@login_required  # Couche 1 : authentification obligatoire
def declaration_historiques(request):
    """Écran unique de déclaration (Quittance/Reçu + Historique ACCT/Extrait)."""
    user = request.user  # Utilisateur courant

    # Postes que l'utilisateur peut voir (péage + pesage)
    postes_qs = (get_postes_peage_accessibles(user) | get_postes_pesage_accessibles(user)).distinct()

    # ---------- Étape 1 : sélection poste + mois (GET) ----------
    selection = SelectionPosteMoisForm(request.GET or None, postes_qs=postes_qs)
    contexte = {
        'selection_form': selection, 'poste': None, 'mois': None,
        'label_quittance': LABEL_QUITTANCE, 'label_historique': LABEL_HISTORIQUE_ACCT,
        'title': _("Déclaration des historiques"),
    }
    if not (request.GET and selection.is_valid()):  # Pas encore de sélection valide
        return render(request, 'inventaire/declaration_historiques.html', contexte)

    poste = selection.cleaned_data['poste']  # Poste choisi
    mois = selection.cleaned_data['mois']  # Mois choisi (AAAA-MM)
    est_peage = _est_poste_peage(user, poste)  # Type de poste + contrôle d'accès
    if est_peage is None:  # Couche 2 : accès au poste refusé
        _journaliser(user, "ACCES_REFUSE", f"Déclaration historiques : poste {poste} interdit", request)
        messages.error(request, _("Vous n'avez pas accès à ce poste."))
        return redirect('common:dashboard')
    if not _peut_declarer(user, est_peage):  # Permission de saisie manquante
        _journaliser(user, "ACCES_REFUSE", "Déclaration historiques : permission manquante", request)
        messages.error(request, _("Vous n'avez pas la permission de déclarer."))
        return redirect('common:dashboard')

    url_retour = f"{reverse('inventaire:declaration_historiques')}?poste={poste.pk}&mois={mois}"
    form_q, form_h = QuittanceRecuForm(prefix='q'), HistoriqueAcctForm(prefix='h')  # Formulaires vides

    # ---------- Étape 2 : enregistrement (POST) ----------
    if request.method == 'POST':
        action = request.POST.get('action')  # 'quittance' ou 'historique'
        try:
            if action == 'quittance':  # Bloc quittance / reçu
                form_q = QuittanceRecuForm(request.POST, request.FILES, prefix='q')
                if form_q.is_valid():
                    with transaction.atomic():  # Écriture atomique
                        obj = _enregistrer_quittance(user, poste, mois, est_peage,
                                                     form_q.cleaned_data, form_q.cleaned_data.get('image_quittance'))
                    _journaliser(user, "DECLARATION_QUITTANCE",
                                 f"{obj.numero_quittance} - {poste} - {mois}", request)  # Hors atomic
                    messages.success(request, _("Quittance ou reçu de versement enregistré(e)."))
                    return redirect(url_retour)
            elif action == 'historique':  # Bloc historique ACCT / extrait de compte
                form_h = HistoriqueAcctForm(request.POST, request.FILES, prefix='h')
                if form_h.is_valid():
                    with transaction.atomic():  # Écriture atomique
                        _enregistrer_historique(user, poste, mois, est_peage,
                                                form_h.cleaned_data, form_h.cleaned_data.get('image_historique'))
                    _journaliser(user, "DECLARATION_HISTORIQUE", f"{poste} - {mois}", request)  # Hors atomic
                    messages.success(request, _("Historique ou extrait de compte enregistré."))
                    return redirect(url_retour)
        except ValidationError as exc:  # Erreur de règle métier du modèle (chevauchement...)
            messages.error(request, " ".join(exc.messages))

    quittances, historique = _charger_donnees(poste, mois, est_peage)  # Données existantes
    contexte.update({
        'poste': poste, 'mois': mois, 'est_peage': est_peage,
        'quittances': quittances, 'historique': historique,
        'form_q': form_q, 'form_h': form_h, 'is_admin': is_admin_user(user),
    })
    return render(request, 'inventaire/declaration_historiques.html', contexte)
