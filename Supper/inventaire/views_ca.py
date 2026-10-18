# inventaire/views_ca.py
# ===================================================================
# VUES - CHIFFRE D'AFFAIRES ESTIMÉ DES TRANSPORTEURS DE PERSONNES
#
#   transporteurs_ca            : CA par agence puis par véhicule (mois / semestre / année)
#   transporteurs_ca_methode    : la NOTE expliquant comment le CA est déterminé
#   transporteurs_ca_parametres : paramètres de la méthode + maillage + liens avec les postes
#                                 (réservé à l'administrateur)
#
# Le calcul est dans inventaire/services_ca.py ; ici on ne fait que préparer les
# données, appliquer les droits et afficher.
# ===================================================================

import calendar                                              # dernier jour d'un mois
import csv                                                   # export CSV
from datetime import date                                    # dates
from collections import Counter                              # nombre de voisins par poste
from decimal import Decimal, InvalidOperation                # lecture de la majoration

from django.contrib import messages                          # messages à l'utilisateur
from django.contrib.auth.decorators import login_required    # exige une connexion
from django.db import transaction                            # enregistrement tout-ou-rien
from django.db.models import Q                               # liaisons d'un poste (A ou B)
from django.shortcuts import get_object_or_404               # 404 si poste inconnu
from django.http import HttpResponse                         # réponse CSV
from django.shortcuts import render, redirect                # raccourcis Django
from django.utils import timezone                            # date du jour
from django.utils.dates import MONTHS                        # noms de mois traduits (FR/EN)
from django.utils.translation import gettext as _            # textes traduisibles
from django.views.decorators.http import require_POST        # impose POST

from accounts.models import Poste                            # postes SUPPER
from common.utils import log_user_action                     # journalisation existante
from inventaire.models_transporteurs import (                # modèles de la fiche transporteurs
    AgenceTransport, DetailVehiculeTransporteur, TypeVehicule,
)
from inventaire.models_ca import (                           # nouveaux modèles du CA
    PosteMaillage, LiaisonMaillage, ParametresCA,
)
from inventaire import services_ca                           # moteur de calcul
from inventaire.views_transporteurs import (                 # outils de droits du module existant
    _est_admin, _refuser,
)

LIBELLES_TYPES = dict(TypeVehicule.choices)                  # code -> libellé du type


def _peut_voir_ca(user):
    """
    Le CA est réservé aux ADMINISTRATEURS ayant accès à l'inventaire :
    administrateur SUPPER ou permission « peut_saisir_inventaire_admin ».
    (Même règle que _est_admin du module transporteurs.)
    """
    return _est_admin(user)


def _entier(texte, defaut, mini, maxi):
    """Lit un entier borné ; retourne 'defaut' si invalide."""
    try:
        valeur = int(texte)
    except (TypeError, ValueError):
        return defaut
    return valeur if mini <= valeur <= maxi else defaut


def _bornes_periode(periode, annee, mois, semestre):
    """Dates de début et de fin de la période choisie (mois, semestre ou année)."""
    if periode == 'annee':
        return date(annee, 1, 1), date(annee, 12, 31)
    if periode == 'semestre':
        return (date(annee, 1, 1), date(annee, 6, 30)) if semestre == 1 else (date(annee, 7, 1), date(annee, 12, 31))
    dernier = calendar.monthrange(annee, mois)[1]                # nombre de jours du mois
    return date(annee, mois, 1), date(annee, mois, dernier)


def _libelle_periode(periode, annee, mois, semestre):
    """Texte lisible de la période (titres, impression, export)."""
    if periode == 'annee':
        return _("Année %(a)s") % {'a': annee}
    if periode == 'semestre':
        return _("Semestre %(s)s %(a)s") % {'s': semestre, 'a': annee}
    return f"{mois:02d}/{annee}"


# ===================================================================
# 1. TABLEAU DU CHIFFRE D'AFFAIRES
# ===================================================================

@login_required
def transporteurs_ca(request):
    """CA estimé par agence, puis détail par véhicule. ?export=csv télécharge le détail."""
    user = request.user
    if not _peut_voir_ca(user):
        return _refuser(request, user, "Chiffre d'affaires transporteurs")

    aujourdhui = timezone.localdate()
    periode = request.GET.get('periode', 'mois')
    if periode not in ('mois', 'semestre', 'annee'):
        periode = 'mois'
    annee = _entier(request.GET.get('annee'), aujourdhui.year, 2020, 2100)
    mois = _entier(request.GET.get('mois'), aujourdhui.month, 1, 12)
    semestre = _entier(request.GET.get('semestre'), 1 if aujourdhui.month <= 6 else 2, 1, 2)
    agence_id = request.GET.get('agence', '')
    debut, fin = _bornes_periode(periode, annee, mois, semestre)

    ctx = {
        'periode': periode, 'annee': annee, 'mois': mois, 'semestre': semestre,
        'agence_id': agence_id, 'agences': AgenceTransport.objects.order_by('nom'),
        'mois_liste': [(i, MONTHS[i]) for i in range(1, 13)],                   # (numéro, nom traduit)
        'annees': range(aujourdhui.year - 3, aujourdhui.year + 1),            # 4 dernières années
        'debut': debut, 'fin': fin, 'libelle_periode': _libelle_periode(periode, annee, mois, semestre),
        'calcule': 'go' in request.GET, 'est_admin': _est_admin(user),
    }
    services_ca.assurer_maillage()                               # précharge le maillage du document si les tables sont vides
    ctx['maillage_vide'] = not PosteMaillage.objects.exists()   # (sécurité) maillage toujours vide ?
    if not ctx['calcule'] or ctx['maillage_vide']:              # formulaire seul (ou maillage absent)
        return render(request, 'inventaire/transporteurs/ca.html', ctx)

    # --- Données : passages de la période, avec le poste converti en poste du maillage ---
    lien = dict(PosteMaillage.objects.exclude(poste=None).values_list('poste_id', 'id'))   # poste SUPPER -> maillage
    qs = DetailVehiculeTransporteur.objects.filter(inventaire__date__range=(debut, fin))
    if agence_id.isdigit():                                      # filtre facultatif sur une agence
        agence = AgenceTransport.objects.filter(id=int(agence_id)).first()
        if agence:
            qs = qs.filter(agence_nom=agence.nom)
            ctx['agence'] = agence
    observations = [
        (pn, pa, ag, ty, jour, lien.get(poste_id))
        for pn, pa, ag, ty, jour, poste_id in qs.values_list(
            'plaque_normalisee', 'plaque', 'agence_nom', 'type_vehicule',
            'inventaire__date', 'inventaire__poste_id')
    ]

    # Postes SUPPER où des véhicules ont été vus mais qui ne sont pas reliés au maillage (ignorés)
    ctx['postes_ignores'] = list(
        qs.exclude(inventaire__poste_id__in=list(lien.keys()))
        .values_list('inventaire__poste__nom', flat=True).distinct().order_by('inventaire__poste__nom'))

    reseau = services_ca.construire_reseau()
    params = services_ca.parametres_en_dict()
    vehicules, agences, infos = services_ca.calculer_ca(observations, reseau, params, debut, fin)
    for v in vehicules:
        v['type_libelle'] = LIBELLES_TYPES.get(v['code_type'], v['code_type'])   # libellé lisible
        v['trajet'] = ' → '.join(v['chemin_noms'])                               # trajet en texte
        v['regions_txt'] = ', '.join(v['regions'])
        # Véhicule vu à un seul poste : liste des postes voisins qu'il a pu rejoindre, avec leur tarif
        v['voisins_txt'] = ', '.join(f"{nom} ({tarif})" for nom, tarif in v['voisins'])

    log_user_action(user, "Chiffre d'affaires transporteurs",
                    f"{ctx['libelle_periode']} | véhicules: {len(vehicules)}", request)

    # --- Export CSV du détail par véhicule ---
    if request.GET.get('export') == 'csv':
        rep = HttpResponse(content_type='text/csv; charset=utf-8')
        rep.write('\ufeff')                                    # BOM unique : Excel lit bien les accents
        rep['Content-Disposition'] = f'attachment; filename="ca_transporteurs_{debut}_{fin}.csv"'
        w = csv.writer(rep, delimiter=';')
        w.writerow([_("Agence"), _("Plaque"), _("Type"), _("Places retenues"), _("Passages"),
                    _("Semaines vues"), _("Trajet de référence"), _("Régions"), _("Tarif sens simple"),
                    _("Aller-retour / semaine"), _("CA semaine (FCFA)"), _("CA période (FCFA)"),
                    _("Postes voisins possibles (vu à un seul poste)")])
        for v in vehicules:
            w.writerow([v['agence'], v['plaque'], v['type_libelle'], v['places'], v['passages'],
                        v['semaines_vues'], v['trajet'], v['regions_txt'], v['tarif'],
                        v['tours'], v['ca_semaine'], v['ca_periode'], v['voisins_txt']])
        return rep

    vehicules_par_agence = {}                                    # détail regroupé par agence
    for v in vehicules:
        vehicules_par_agence.setdefault(v['agence'], []).append(v)
    for a in agences:
        a['detail'] = vehicules_par_agence.get(a['agence'], [])  # véhicules de l'agence
    ctx.update({
        'agences_ca': agences, 'infos': infos, 'params': params,
        'total_ca': sum(a['ca_periode'] for a in agences),
        'total_semaine': sum(a['ca_semaine'] for a in agences),
        'total_vehicules': len(vehicules),
        'retour': request.get_full_path(),
    })
    return render(request, 'inventaire/transporteurs/ca.html', ctx)


# ===================================================================
# 2. NOTE MÉTHODOLOGIQUE
# ===================================================================

@login_required
def transporteurs_ca_methode(request):
    """Page « Comment le chiffre d'affaires est déterminé », avec les paramètres en vigueur."""
    user = request.user
    if not _peut_voir_ca(user):
        return _refuser(request, user, "Note CA transporteurs")
    return render(request, 'inventaire/transporteurs/ca_methode.html', {
        'p': ParametresCA.charger(), 'est_admin': _est_admin(user),
    })


# ===================================================================
# 3. PARAMÈTRES, MAILLAGE ET LIENS AVEC LES POSTES (administrateur)
# ===================================================================

@login_required
def transporteurs_ca_parametres(request):
    """Affiche les paramètres, les liaisons du maillage et le lien poste du maillage ↔ poste SUPPER."""
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Paramètres CA transporteurs")
    services_ca.assurer_maillage()                               # précharge le maillage du document au premier accès
    liaisons = LiaisonMaillage.objects.select_related('poste_a', 'poste_b').order_by('poste_a__nom', 'poste_b__nom')
    return render(request, 'inventaire/transporteurs/ca_parametres.html', {
        'p': ParametresCA.charger(),
        'postes_maillage': PosteMaillage.objects.select_related('poste').order_by('region', 'nom'),
        'postes_supper': Poste.objects.filter(is_active=True, type='peage').order_by('nom'),
        'liaisons': liaisons,
        'nb_non_relies': PosteMaillage.objects.filter(poste=None).count(),
        # Postes de péage SUPPER qu'aucun poste du maillage ne représente
        'supper_sans_maillage': Poste.objects.filter(is_active=True, type='peage', maillages=None).order_by('nom'),
        # Postes du maillage sans aucune liaison (ex. Santa) : sans objet pour le calcul
        'sans_voisin': PosteMaillage.objects.filter(liaisons_a=None, liaisons_b=None),
    })


@login_required
@require_POST
def transporteurs_ca_parametres_enregistrer(request):
    """Enregistre les paramètres de calcul (administrateur)."""
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Modifier paramètres CA")
    p = ParametresCA.charger()
    try:
        p.tours_longs = _entier(request.POST.get('tours_longs'), p.tours_longs, 1, 14)
        p.tours_courts = _entier(request.POST.get('tours_courts'), p.tours_courts, 1, 14)
        p.seuil_regions = _entier(request.POST.get('seuil_regions'), p.seuil_regions, 1, 10)
        p.routage_regions = request.POST.get('routage_regions') == 'on'   # case à cocher
        p.places_coaster = _entier(request.POST.get('places_coaster'), p.places_coaster, 1, 200)
        p.places_bus_ordinaire = _entier(request.POST.get('places_bus_ordinaire'), p.places_bus_ordinaire, 1, 200)
        p.places_bus_clim = _entier(request.POST.get('places_bus_clim'), p.places_bus_clim, 1, 200)
        p.places_hiace = _entier(request.POST.get('places_hiace'), p.places_hiace, 1, 200)
        majoration = Decimal(request.POST.get('majoration_clim', '').replace(',', '.'))
        if not Decimal('0') <= majoration <= Decimal('5'):
            raise InvalidOperation
        p.majoration_clim = majoration.quantize(Decimal('0.0001'))
    except InvalidOperation:
        messages.error(request, _("Majoration invalide : saisissez un nombre entre 0 et 5 (ex. 0,6667)."))
        return redirect('inventaire:transporteurs_ca_parametres')
    p.save()
    log_user_action(user, "Paramètres CA transporteurs modifiés", f"tours {p.tours_longs}/{p.tours_courts}, "
                    f"seuil {p.seuil_regions}, clim +{p.majoration_clim}", request)
    messages.success(request, _("Paramètres enregistrés."))
    return redirect('inventaire:transporteurs_ca_parametres')


@login_required
@require_POST
def transporteurs_ca_maillage_charger(request):
    """(Re)charge le maillage depuis le fichier livré et relie automatiquement les postes."""
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Charger maillage")
    nb_postes, nb_liaisons, relies = services_ca.charger_maillage_depuis_fichier()
    log_user_action(user, "Maillage chargé", f"{nb_postes} postes, {nb_liaisons} liaisons, {relies} reliés", request)
    messages.success(request, _("Tarifs du document rétablis : %(p)s postes, %(l)s liaisons, %(r)s nouveaux rapprochements automatiques.")
                     % {'p': nb_postes, 'l': nb_liaisons, 'r': relies})
    return redirect('inventaire:transporteurs_ca_parametres')


@login_required
@require_POST
def transporteurs_ca_maillage_relier(request):
    """Enregistre les liens poste du maillage ↔ poste SUPPER choisis dans le tableau."""
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Relier maillage")
    choix = {}                                                   # {id maillage: id poste SUPPER}
    for pm in PosteMaillage.objects.all():
        valeur = request.POST.get(f'lien_{pm.id}', '')
        choix[pm.id] = int(valeur) if valeur.isdigit() else None
    utilises = [v for v in choix.values() if v]
    if len(utilises) != len(set(utilises)):                      # un même poste choisi deux fois
        messages.error(request, _("Un poste SUPPER ne peut être relié qu'à un seul poste du maillage."))
        return redirect('inventaire:transporteurs_ca_parametres')
    valides = set(Poste.objects.filter(id__in=utilises).values_list('id', flat=True))
    for pm in PosteMaillage.objects.all():
        nouveau = choix[pm.id] if choix[pm.id] in valides else None
        if pm.poste_id != nouveau:                               # on n'écrit que ce qui change
            pm.poste_id = nouveau
            pm.save(update_fields=['poste'])
    log_user_action(user, "Liens maillage modifiés", f"{len(valides)} postes reliés", request)
    messages.success(request, _("Liens enregistrés."))
    return redirect('inventaire:transporteurs_ca_parametres')


# ===================================================================
# 4. ÉCRAN DES LIAISONS : postes voisins de chaque poste + tarifs (administrateur)
#    Le système construit le maillage à partir de ces liaisons (non orientées :
#    saisir A→B crée aussi B→A).
# ===================================================================

def _lire_tarif(texte):
    """Tarif entier en FCFA (espaces tolérés) entre 1 et 1 000 000 ; None si invalide."""
    try:
        valeur = int(str(texte or '').replace(' ', '').replace('\u202f', '').replace('\xa0', ''))
    except ValueError:
        return None
    return valeur if 1 <= valeur <= 1_000_000 else None


@login_required
def transporteurs_maillage(request):
    """Liste des postes du maillage (par région), nombre de voisins, et diagnostic des zones coupées."""
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Écran du maillage")
    services_ca.assurer_maillage()                               # précharge le maillage du document si vide
    postes = list(PosteMaillage.objects.select_related('poste').order_by('region', 'nom'))
    nb_voisins = Counter()                                       # nombre de voisins de chaque poste
    for a, b in LiaisonMaillage.objects.values_list('poste_a_id', 'poste_b_id'):
        nb_voisins[a] += 1
        nb_voisins[b] += 1
    for p in postes:
        p.nb_voisins = nb_voisins.get(p.id, 0)
    reseau = services_ca.construire_reseau()
    return render(request, 'inventaire/transporteurs/maillage.html', {
        'postes': postes,
        'zones_coupees': services_ca.zones_coupees(reseau),
        'sans_voisin': [p for p in postes if p.nb_voisins == 0],
        'nb_liaisons': LiaisonMaillage.objects.count(),
    })


def _liaisons_du_poste(poste):
    """Liaisons d'un poste sous forme de lignes {liaison, voisin, tarif}, triées par nom de voisin."""
    lignes = []
    for l in LiaisonMaillage.objects.filter(Q(poste_a=poste) | Q(poste_b=poste)).select_related('poste_a', 'poste_b'):
        voisin = l.poste_b if l.poste_a_id == poste.id else l.poste_a   # l'autre extrémité
        lignes.append({'liaison': l, 'voisin': voisin, 'tarif': l.tarif})
    return sorted(lignes, key=lambda x: x['voisin'].nom)


@login_required
def transporteurs_maillage_poste(request, pk):
    """Voisins d'un poste : modifier les tarifs, retirer des voisins, en ajouter plusieurs d'un coup."""
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Écran du maillage")
    poste = get_object_or_404(PosteMaillage, pk=pk)
    lignes = _liaisons_du_poste(poste)
    deja = {x['voisin'].id for x in lignes} | {poste.id}         # postes déjà voisins (ou le poste lui-même)
    return render(request, 'inventaire/transporteurs/maillage_poste.html', {
        'poste': poste, 'lignes': lignes,
        'candidats': PosteMaillage.objects.exclude(id__in=deja).order_by('region', 'nom'),
    })


@login_required
@require_POST
def transporteurs_maillage_poste_enregistrer(request, pk):
    """
    Applique en une fois : tarifs modifiés, voisins retirés (cases cochées) et nouveaux voisins.
    Tout est vérifié avant d'écrire : s'il y a une erreur, rien n'est modifié.
    """
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Écran du maillage")
    poste = get_object_or_404(PosteMaillage, pk=pk)
    retour = redirect('inventaire:transporteurs_maillage_poste', pk=poste.id)
    erreurs, modifs, suppr, ajouts = [], [], [], []

    for x in _liaisons_du_poste(poste):                          # voisins existants
        l = x['liaison']
        if request.POST.get(f'suppr_{l.id}'):                    # case « retirer » cochée
            suppr.append(l)
            continue
        if f'tarif_{l.id}' not in request.POST:                  # champ absent : tarif inchangé
            continue
        tarif = _lire_tarif(request.POST.get(f'tarif_{l.id}'))
        if tarif is None:
            erreurs.append(_("Tarif invalide pour %(n)s.") % {'n': x['voisin'].nom})
        elif tarif != l.tarif:
            modifs.append((l, tarif))

    ids = request.POST.getlist('nouveau_poste')                  # nouveaux voisins (lignes ajoutées)
    tarifs = request.POST.getlist('nouveau_tarif')
    vus = set()
    for id_v, t in zip(ids, tarifs):
        if not id_v and not t.strip():                           # ligne vide : ignorée
            continue
        voisin = PosteMaillage.objects.filter(id=int(id_v)).first() if id_v.isdigit() else None
        tarif = _lire_tarif(t)
        if voisin is None or voisin.id == poste.id or tarif is None:
            erreurs.append(_("Ligne d'ajout incomplète ou invalide."))
        elif voisin.id in vus:
            erreurs.append(_("%(n)s est choisi deux fois.") % {'n': voisin.nom})
        else:
            vus.add(voisin.id)
            ajouts.append((voisin, tarif))
    if erreurs:
        for e in erreurs:
            messages.error(request, e)
        return retour

    with transaction.atomic():                                   # tout ou rien
        for l in suppr:
            l.delete()
        for l, tarif in modifs:
            l.tarif = tarif
            l.save(update_fields=['tarif'])
        for voisin, tarif in ajouts:
            a, b = (poste, voisin) if poste.id < voisin.id else (voisin, poste)   # paire rangée A < B
            LiaisonMaillage.objects.update_or_create(poste_a=a, poste_b=b, defaults={'tarif': tarif})
    log_user_action(request.user, "Maillage modifié",
                    f"{poste.nom} | +{len(ajouts)} ~{len(modifs)} -{len(suppr)}", request)
    messages.success(request, _("Voisins de %(p)s enregistrés : %(a)s ajouté(s), %(m)s modifié(s), %(s)s retiré(s).")
                     % {'p': poste.nom, 'a': len(ajouts), 'm': len(modifs), 's': len(suppr)})
    return retour
