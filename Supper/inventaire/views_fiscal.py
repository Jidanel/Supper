# inventaire/views_fiscal.py
# ===================================================================
# VUES - SITUATION FISCALE RÉELLE DES AGENCES DE TRANSPORT
#
#   transporteurs_fiscal           : liste des agences + saisie manuelle (NIU, catégorie, centre...)
#   transporteurs_fiscal_modifier  : enregistre la ligne d'UNE agence (POST)
#   transporteurs_fiscal_importer  : import d'un fichier CSV/Excel (liste du cahier)
#   transporteurs_fiscal_exporter  : export CSV de la situation actuelle (modifiable puis réimportable)
#
# Réservé aux administrateurs (même règle que le chiffre d'affaires).
# ===================================================================

import csv                                                    # export CSV
import logging                                                # journal technique

from django.contrib import messages                          # messages affichés à l'utilisateur
from django.contrib.auth.decorators import login_required    # exige une connexion
from django.core.paginator import Paginator                  # pagination de la liste
from django.db import transaction                            # enregistrement tout-ou-rien
from django.db.models import Count, Q                        # agrégats et filtres SQL
from django.http import HttpResponse                         # réponse CSV
from django.shortcuts import get_object_or_404, redirect, render   # raccourcis Django
from django.urls import reverse                              # adresse de retour par défaut
from django.utils import timezone                            # horodatage
from django.utils.http import url_has_allowed_host_and_scheme   # contrôle de l'adresse de retour
from django.utils.translation import gettext as _            # textes traduisibles
from django.views.decorators.http import require_POST        # impose POST

from common.utils import log_user_action                     # journalisation existante
from inventaire import services_fiscal                       # logique de comparaison / import
from inventaire.models_transporteurs import (                # modèle et fonctions de normalisation
    AgenceTransport, CategorieFiscale, normaliser_niu, normaliser_nom_agence,
)
from inventaire.views_transporteurs import _est_admin, _refuser   # droits du module transporteurs

logger = logging.getLogger('supper')                         # logger du projet
CODES_CATEGORIES = [code for code, _lib in CategorieFiscale.choices]   # valeurs autorisées


def _retour_sur(request, defaut):
    """Adresse de retour sûre (même site, chemin local) ; sinon l'adresse par défaut."""
    retour = request.POST.get('retour') or request.GET.get('retour') or ''
    if retour.startswith('/') and url_has_allowed_host_and_scheme(retour, allowed_hosts={request.get_host()}):
        return retour
    return defaut


@login_required
def transporteurs_fiscal(request):
    """Liste des agences avec leur situation fiscale réelle, filtres et saisie ligne par ligne."""
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Situation fiscale des agences")
    q = request.GET.get('q', '').strip()                      # recherche par nom ou NIU
    filtre = request.GET.get('filtre', '')                    # filtre rapide
    agences = AgenceTransport.objects.annotate(n_vehicules=Count('vehicules')).order_by('nom')
    if q:                                                     # nom ou NIU contient le texte
        agences = agences.filter(Q(nom__icontains=normaliser_nom_agence(q)) | Q(niu__icontains=normaliser_niu(q)))
    if filtre == 'non_renseignees':                           # rien de saisi
        agences = agences.filter(niu='', categorie_actuelle='', centre_actuel='', sans_niu=False)
    elif filtre == 'a_verifier':
        agences = agences.filter(a_verifier=True)
    elif filtre == 'sans_niu':
        agences = agences.filter(sans_niu=True)
    elif filtre in CODES_CATEGORIES:                          # DGE / CIME / CFLP / AUTRE
        agences = agences.filter(categorie_actuelle=filtre)
    page = Paginator(agences, 50).get_page(request.GET.get('page'))   # 50 agences par page
    parametres = request.GET.copy()                           # conserve les filtres dans la pagination
    parametres.pop('page', None)
    tout = AgenceTransport.objects                            # compteurs de l'en-tête
    compteurs = {
        'total': tout.count(),
        'renseignees': tout.exclude(niu='', categorie_actuelle='', centre_actuel='', sans_niu=False).count(),
        'a_verifier': tout.filter(a_verifier=True).count(),
        'sans_niu': tout.filter(sans_niu=True).count(),
    }
    return render(request, 'inventaire/transporteurs/fiscal.html', {
        'page': page, 'q': q, 'filtre': filtre, 'qs': parametres.urlencode(),
        'categories': CategorieFiscale.choices, 'compteurs': compteurs,
        'retour': request.get_full_path(), 'est_admin': True,
    })


@login_required
@require_POST
def transporteurs_fiscal_modifier(request, pk):
    """Enregistre la situation fiscale d'une agence (saisie manuelle, administrateur)."""
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Modification situation fiscale", 'inventaire:transporteurs_fiscal')
    agence = get_object_or_404(AgenceTransport, pk=pk)
    retour = _retour_sur(request, reverse('inventaire:transporteurs_fiscal'))
    niu = normaliser_niu(request.POST.get('niu'))             # NIU propre
    categorie = request.POST.get('categorie_actuelle', '').strip().upper()
    if categorie not in CODES_CATEGORIES + ['']:              # valeur inconnue : refus
        messages.error(request, _("Catégorie inconnue."))
        return redirect(retour)
    if len(niu) > 30:
        messages.error(request, _("NIU trop long (30 caractères maximum)."))
        return redirect(retour)
    avertissement = services_fiscal.avertissement_niu(niu, agence)   # NIU mal formé ou doublon
    avant = (agence.niu, agence.categorie_actuelle, agence.centre_actuel, agence.regime, agence.sans_niu, agence.a_verifier)
    agence.niu = niu
    agence.categorie_actuelle = categorie
    agence.centre_actuel = request.POST.get('centre_actuel', '').strip()[:150]
    agence.regime = request.POST.get('regime', '').strip()[:60]
    agence.sans_niu = request.POST.get('sans_niu') == '1' and not niu     # « sans NIU » n'a de sens que sans NIU
    agence.a_verifier = request.POST.get('a_verifier') == '1'
    agence.remarque_fiscale = request.POST.get('remarque_fiscale', '').strip()[:300]
    agence.fiscal_modifie_par = user                          # trace de la modification
    agence.fiscal_modifie_le = timezone.now()
    agence.save()                                             # save() normalise aussi le NIU
    apres = (agence.niu, agence.categorie_actuelle, agence.centre_actuel, agence.regime, agence.sans_niu, agence.a_verifier)
    log_user_action(user, "Modification situation fiscale agence",
                    f"Agence: {agence.nom} | NIU: {agence.niu or '-'} | Catégorie: {agence.categorie_actuelle or '-'} | "
                    f"Centre: {agence.centre_actuel or '-'} | Avant: {avant} | Après: {apres}", request)
    messages.success(request, _("Situation fiscale de « %(a)s » enregistrée.") % {'a': agence.nom})
    if avertissement:                                         # on enregistre quand même, mais on prévient
        messages.warning(request, avertissement)
    return redirect(retour)


@login_required
@require_POST
def transporteurs_fiscal_importer(request):
    """
    Import d'un fichier CSV/Excel (colonnes : agence, niu, categorie, centre, regime, a_verifier, sans_niu, remarque).
    Par défaut on ne remplit que les champs vides ; la case « écraser » remplace aussi les valeurs saisies.
    La case « créer » ajoute les agences absentes de l'annuaire.
    """
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Import situation fiscale", 'inventaire:transporteurs_fiscal')
    fichier = request.FILES.get('fichier')
    if not fichier:
        messages.error(request, _("Choisissez un fichier .csv ou .xlsx."))
        return redirect('inventaire:transporteurs_fiscal')
    lignes, erreur = services_fiscal.lire_fichier(fichier)    # lecture et nettoyage
    if erreur:
        messages.error(request, erreur)
        return redirect('inventaire:transporteurs_fiscal')
    ecraser = request.POST.get('ecraser') == '1'
    creer = request.POST.get('creer') == '1'
    maintenant = timezone.now()
    index = services_fiscal.construire_index()                # recherche des agences par nom
    compte = {'maj': 0, 'inchangees': 0, 'creees': 0}
    absentes, ambigues, conflits, doublons, avertissements = [], [], [], [], []
    deja_traitees = set()                                     # une agence ne doit être ciblée qu'une fois par fichier
    with transaction.atomic():                                # tout ou rien
        for ligne in lignes:
            agence, etat = services_fiscal.trouver_agence(ligne['agence'], index)
            if etat == 'ambigue':
                ambigues.append(ligne['agence'])
                continue
            if etat == 'absente':
                if not creer:
                    absentes.append(ligne['agence'])
                    continue
                agence, _cree = AgenceTransport.creer_si_absente(ligne['agence'], user)   # ajoute l'agence à l'annuaire
                if agence is None:
                    continue
                compte['creees'] += 1
                index[0][agence.cle_unicite] = agence         # visible pour les lignes suivantes
            if agence.pk in deja_traitees:                    # deuxième ligne pour la même agence
                doublons.append(ligne['agence'])
                continue
            deja_traitees.add(agence.pk)
            modifies, en_conflit = services_fiscal.appliquer_ligne(agence, ligne, ecraser, user, maintenant)
            if en_conflit:
                conflits.append(f"{agence.nom} ({', '.join(en_conflit)})")
            if modifies:
                agence.save()                                 # save() normalise le NIU
                compte['maj'] += 1
                texte = services_fiscal.avertissement_niu(agence.niu, agence)
                if texte:
                    avertissements.append(f"{agence.nom} : {texte}")
            else:
                compte['inchangees'] += 1
    log_user_action(user, "Import situation fiscale agences",
                    f"Fichier: {fichier.name} | Lignes: {len(lignes)} | Mises à jour: {compte['maj']} | "
                    f"Créées: {compte['creees']} | Non trouvées: {len(absentes)} | Écraser: {ecraser}", request)
    messages.success(request, _("Import terminé : %(m)s agence(s) mise(s) à jour, %(i)s inchangée(s), %(c)s créée(s).")
                     % {'m': compte['maj'], 'i': compte['inchangees'], 'c': compte['creees']})
    if absentes:                                              # listes tronquées pour rester lisibles
        messages.warning(request, _("Agences introuvables dans l'annuaire (%(n)s) : %(l)s") % {'n': len(absentes), 'l': ' ; '.join(absentes[:25])})
    if ambigues:
        messages.warning(request, _("Nom ambigu, plusieurs agences possibles (%(n)s) : %(l)s") % {'n': len(ambigues), 'l': ' ; '.join(ambigues[:25])})
    if doublons:
        messages.warning(request, _("Plusieurs lignes pour la même agence, seule la première est appliquée : %(l)s") % {'l': ' ; '.join(doublons[:25])})
    if conflits:
        messages.info(request, _("Valeurs déjà saisies conservées (cochez « écraser » pour les remplacer) : %(l)s") % {'l': ' ; '.join(conflits[:25])})
    for texte in avertissements[:15]:
        messages.warning(request, texte)
    return redirect('inventaire:transporteurs_fiscal')


@login_required
def transporteurs_fiscal_exporter(request):
    """Export CSV de la situation fiscale actuelle de toutes les agences (réimportable après correction)."""
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Export situation fiscale", 'inventaire:transporteurs_fiscal')
    rep = HttpResponse(content_type='text/csv; charset=utf-8')
    rep.write('﻿')                                       # BOM unique : Excel lit bien les accents
    rep['Content-Disposition'] = 'attachment; filename="agences_situation_fiscale.csv"'
    w = csv.writer(rep, delimiter=';')
    w.writerow(['agence', 'niu', 'categorie', 'centre', 'regime', 'a_verifier', 'sans_niu', 'remarque'])
    for a in AgenceTransport.objects.order_by('nom'):
        w.writerow([a.nom, a.niu, a.categorie_actuelle, a.centre_actuel, a.regime,
                    1 if a.a_verifier else 0, 1 if a.sans_niu else 0, a.remarque_fiscale])
    log_user_action(user, "Export situation fiscale agences", "CSV", request)
    return rep
