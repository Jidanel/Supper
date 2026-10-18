# inventaire/views_transporteurs.py
# ===================================================================
# VUES - FICHE D'INVENTAIRE DES TRANSPORTEURS DE PERSONNES
#
# Parcours de saisie (agent d'inventaire ou administrateur) :
#   1. transporteurs_choix_date : choix de la date (et du poste pour un admin)
#   2. transporteurs_saisie     : agences + plaques + types (boutons +/-)
#                                 -> aperçu/confirmation -> enregistrement
# Consultation : transporteurs_liste (par poste/jour) -> transporteurs_detail (l'œil)
# Agences      : transporteurs_agences (liste/ajout), _importer (Excel), _supprimer
# Statistiques : transporteurs_stats (par poste / par agence / par plaque)
#
# Règle de visibilité : l'administrateur voit TOUS les postes ;
# l'agent d'inventaire ne voit QUE son poste d'affectation.
# ===================================================================

from collections import defaultdict                          # regroupements (postes par plaque)
import re                                                    # lecture des noms de champs du formulaire
import logging                                               # logs techniques
from datetime import date, datetime, timedelta               # gestion des dates

from django.contrib import messages                          # messages affichés à l'utilisateur
from django.contrib.auth.decorators import login_required    # exige une connexion
from django.core.paginator import Paginator                  # pagination de la liste
from django.db import transaction, IntegrityError            # atomicité de l'enregistrement
from django.db.models import Count, Max, Min, Q                   # agrégats SQL
from django.shortcuts import render, redirect, get_object_or_404   # raccourcis Django
from django.urls import reverse                              # construit l'adresse de retour par défaut
from django.utils.http import url_has_allowed_host_and_scheme   # vérifie l'adresse de retour
from django.utils import timezone                            # heure serveur
from django.utils.translation import gettext as _            # textes traduisibles (exécution)
from django.views.decorators.http import require_POST        # impose la méthode POST

from accounts.models import Poste                            # modèle Poste existant
from inventaire.models_transporteurs import (                # nos modèles
    AgenceTransport, InventaireTransporteur, DetailVehiculeTransporteur,
    TypeVehicule, normaliser_nom_agence, cle_unicite_agence, normaliser_plaque, afficher_plaque,
    poste_programme_pour_transporteurs,
)
from common.permissions import (                             # permissions granulaires existantes de SUPPER
    has_permission, is_admin_user, user_has_acces_tous_postes,
)
from common.utils import log_user_action                     # journalisation manuelle existante

logger = logging.getLogger('supper')                         # logger du projet

# Types sous forme de liste de (code, libellé) réutilisée partout
TYPES = list(TypeVehicule.choices)
CODES_TYPES = [code for code, _lib in TYPES]


# ===================================================================
# OUTILS DE PERMISSIONS ET DE PORTÉE
# ===================================================================

def _est_admin(user):
    """Admin = administrateur SUPPER ou permission 'peut_saisir_inventaire_admin'."""
    return is_admin_user(user) or has_permission(user, 'peut_saisir_inventaire_admin')


def _peut_saisir(user):
    """Peut saisir = permission de saisie normale ou admin."""
    return has_permission(user, 'peut_saisir_inventaire_normal') or _est_admin(user)


def _peut_consulter(user):
    """Peut consulter = saisie, liste des inventaires ou statistiques."""
    return (_peut_saisir(user)
            or has_permission(user, 'peut_voir_liste_inventaires')
            or has_permission(user, 'peut_voir_stats_deperdition'))


def _voit_tous_postes(user):
    """Vrai si l'utilisateur voit tous les postes (admin ou accès multi-postes)."""
    return _est_admin(user) or user_has_acces_tous_postes(user)


def _postes_visibles(user):
    """
    Postes de péage actifs visibles par l'utilisateur :
    tous pour l'admin, uniquement le poste d'affectation sinon.
    """
    base = Poste.objects.filter(is_active=True, type='peage').order_by('nom')   # tous les postes de péage
    if _voit_tous_postes(user):
        return base                                                             # admin : tout
    if getattr(user, 'poste_affectation_id', None):
        return base.filter(id=user.poste_affectation_id)                        # agent : son poste
    return base.none()                                                          # sans poste : rien


def _refuser(request, user, action, redirection='common:dashboard'):
    """Journalise et signale un refus d'accès."""
    log_user_action(user, f"ACCÈS REFUSÉ - {action}",
                    f"Habilitation: {getattr(user, 'habilitation', 'N/A')} | "
                    f"IP: {request.META.get('REMOTE_ADDR')}", request)
    messages.error(request, _("Vous n'avez pas la permission d'accéder à cette page."))
    return redirect(redirection)


def _nom_utilisateur(u):
    """
    Nom lisible d'un utilisateur, jamais 'None'.
    Sur SUPPER, first_name et last_name sont supprimés du modèle : la méthode
    standard get_full_name() renverrait donc « None None ». On utilise le champ
    nom_complet, puis le matricule (username) en secours, puis un tiret si
    l'utilisateur n'existe plus (clé étrangère remise à NULL).
    """
    if u is None:                                            # utilisateur supprimé (SET_NULL)
        return '—'
    nom = str(getattr(u, 'nom_complet', '') or '').strip()   # nom et prénom(s) de l'agent
    if nom and nom.lower() != 'none':
        return nom
    matricule = str(getattr(u, 'username', '') or '').strip()    # matricule
    return matricule or '—'


def _lire_date(texte, defaut=None):
    """Convertit 'AAAA-MM-JJ' en date ; retourne 'defaut' si invalide."""
    try:
        return datetime.strptime(texte, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return defaut


# ===================================================================
# LECTURE ET VALIDATION DU FORMULAIRE DE SAISIE (agences + véhicules)
# ===================================================================
# Champs envoyés par la page (créés dynamiquement par le JavaScript) :
#   ag-<i>-agence            : id de l'agence du bloc i
#   ag-<i>-v-<j>-plaque      : plaque du véhicule j du bloc i
#   ag-<i>-v-<j>-type        : type (bouton radio) du véhicule j du bloc i
# Les blocs/lignes supprimés avec le bouton « − » n'existent plus dans la page,
# donc ne sont pas envoyés : les indices peuvent avoir des « trous ».

RE_AGENCE = re.compile(r'^ag-(\d+)-agence$')                 # détecte un champ agence
RE_VEHICULE = re.compile(r'^ag-(\d+)-v-(\d+)-(plaque|type)$')   # détecte un champ véhicule


def lire_blocs(post):
    """
    Transforme request.POST en liste de blocs :
    [{'index': i, 'agence_id': '12', 'vehicules': [{'index': j, 'plaque': '..', 'type': '..'}]}]
    """
    blocs = {}                                               # index de bloc -> bloc
    for cle in post.keys():                                  # parcourt tous les champs reçus
        m = RE_AGENCE.match(cle)
        if m:                                                # champ agence
            i = int(m.group(1))
            blocs.setdefault(i, {'index': i, 'agence_id': '', 'vehicules': {}})
            blocs[i]['agence_id'] = post.get(cle, '').strip()
            continue
        m = RE_VEHICULE.match(cle)
        if m:                                                # champ véhicule
            i, j, champ = int(m.group(1)), int(m.group(2)), m.group(3)
            blocs.setdefault(i, {'index': i, 'agence_id': '', 'vehicules': {}})
            veh = blocs[i]['vehicules'].setdefault(j, {'index': j, 'plaque': '', 'type': ''})
            veh[champ] = post.get(cle, '').strip()
    resultat = []                                            # mise en forme finale, triée
    for i in sorted(blocs):
        bloc = blocs[i]
        bloc['vehicules'] = [bloc['vehicules'][j] for j in sorted(bloc['vehicules'])]
        resultat.append(bloc)
    return resultat


def valider_blocs(blocs):
    """
    Valide les blocs. Retourne (blocs_propres, erreurs, avertissements).
    blocs_propres : [{'agence': AgenceTransport, 'vehicules': [{'plaque','type','type_libelle'}]}]
    """
    erreurs, avertissements, propres = [], [], []            # listes de sortie
    agences = {str(a.id): a for a in AgenceTransport.objects.filter(est_active=True)}   # agences valides
    agences_vues = set()                                     # détecte une agence saisie deux fois
    plaques_vues = {}                                        # détecte une plaque répétée (info)
    libelles = dict(TYPES)                                   # code -> libellé du type
    for n, bloc in enumerate(blocs, start=1):                # n = numéro affiché du bloc
        lignes = [v for v in bloc['vehicules'] if v['plaque'] or v['type']]   # ignore les lignes vides
        if not bloc['agence_id'] and not lignes:
            continue                                         # bloc totalement vide : ignoré
        agence = agences.get(bloc['agence_id'])              # agence choisie
        if not agence:
            erreurs.append(_("Agence n°%(n)s : veuillez choisir une agence valide.") % {'n': n})
            continue
        if agence.id in agences_vues:
            erreurs.append(_("L'agence %(a)s est saisie deux fois : regroupez ses véhicules dans un seul bloc.") % {'a': agence.nom})
            continue
        agences_vues.add(agence.id)
        if not lignes:
            erreurs.append(_("L'agence %(a)s n'a aucun véhicule.") % {'a': agence.nom})
            continue
        vehicules = []
        for k, v in enumerate(lignes, start=1):              # k = numéro de ligne
            plaque = afficher_plaque(v['plaque'])
            if not plaque:
                erreurs.append(_("%(a)s, véhicule %(k)s : la plaque est obligatoire.") % {'a': agence.nom, 'k': k})
                continue
            if len(plaque) > 30:
                erreurs.append(_("%(a)s, véhicule %(k)s : plaque trop longue.") % {'a': agence.nom, 'k': k})
                continue
            if v['type'] not in CODES_TYPES:
                erreurs.append(_("%(a)s, plaque %(p)s : choisissez le nombre de places.") % {'a': agence.nom, 'p': plaque})
                continue
            cle = normaliser_plaque(plaque)
            if cle in plaques_vues:                          # même plaque déjà saisie : possible (aller/retour)
                avertissements.append(_("La plaque %(p)s apparaît plusieurs fois (aller/retour ?).") % {'p': plaque})
            plaques_vues[cle] = True
            vehicules.append({'plaque': plaque, 'type': v['type'], 'type_libelle': libelles[v['type']]})
        if vehicules:
            propres.append({'agence': agence, 'vehicules': vehicules})
    if not propres and not erreurs:
        erreurs.append(_("Ajoutez au moins une agence avec un véhicule."))
    return propres, erreurs, avertissements


def totaux(propres):
    """Totaux par type + total général + récapitulatif par agence (pour la confirmation)."""
    par_type = {code: 0 for code in CODES_TYPES}             # compteurs par type
    recap = []
    for bloc in propres:
        ligne = {code: 0 for code in CODES_TYPES}            # compteurs de l'agence
        for v in bloc['vehicules']:
            par_type[v['type']] += 1
            ligne[v['type']] += 1
        recap.append({'agence': bloc['agence'].nom, 'vehicules': bloc['vehicules'],
                      'total': len(bloc['vehicules']), 'par_type': ligne})
    return {
        'par_type': [(code, lib, par_type[code]) for code, lib in TYPES],   # pour affichage en boucle
        'total': sum(par_type.values()),
        'nb_agences': len(propres),
        'recap': recap,
    }


def blocs_depuis_inventaire(inv):
    """Recharge une fiche existante sous forme de blocs (modification par l'admin)."""
    blocs, index = {}, {}
    for v in inv.vehicules.all().order_by('agence_nom', 'id'):
        if v.agence_nom not in index:                        # nouveau bloc pour cette agence
            agence = v.agence or AgenceTransport.trouver_par_nom(v.agence_nom)   # agence supprimée ? on cherche l'équivalente
            index[v.agence_nom] = len(index)
            blocs[v.agence_nom] = {'index': index[v.agence_nom],
                                   'agence_id': str(agence.id) if agence else '',
                                   'vehicules': []}
        bloc = blocs[v.agence_nom]
        bloc['vehicules'].append({'index': len(bloc['vehicules']), 'plaque': v.plaque, 'type': v.type_vehicule})
    return sorted(blocs.values(), key=lambda b: b['index'])


# ===================================================================
# ÉTAPE 1 : CHOIX DE LA DATE (et du poste pour l'administrateur)
# ===================================================================

@login_required
def transporteurs_choix_date(request):
    """Page « choisir la date » ; l'agent ne choisit pas de poste (le sien est imposé)."""
    user = request.user
    if not _peut_saisir(user):
        return _refuser(request, user, "Choix date transporteurs")
    postes = _postes_visibles(user)                          # admin : tous ; agent : le sien
    if not postes.exists():
        messages.error(request, _("Aucun poste d'affectation configuré."))
        return redirect('common:dashboard')
    aujourd_hui = timezone.localdate()                       # date du jour
    if request.method == 'POST':
        poste = postes.filter(id=request.POST.get('poste') or None).first() if _voit_tous_postes(user) else postes.first()
        jour = _lire_date(request.POST.get('date'))
        if not poste or not jour:
            messages.error(request, _("Choisissez un poste et une date valides."))
        elif jour > aujourd_hui:
            messages.error(request, _("La date ne peut pas être dans le futur."))
        else:
            return redirect('inventaire:transporteurs_saisie', poste_id=poste.id, date_str=jour.isoformat())
    return render(request, 'inventaire/transporteurs/choix_date.html', {
        'postes': postes, 'choix_poste': _voit_tous_postes(user),
        'poste_unique': postes.first(), 'aujourd_hui': aujourd_hui.isoformat(),
    })


# ===================================================================
# ÉTAPE 2 : SAISIE -> CONFIRMATION -> ENREGISTREMENT
# ===================================================================

@login_required
def transporteurs_saisie(request, poste_id, date_str):
    """
    Une seule URL gère trois moments, selon le champ POST 'action' :
      (rien / GET)  : affiche le formulaire (vide, ou prérempli pour l'admin)
      'apercu'      : valide puis affiche la fenêtre de confirmation (tableau)
      'modifier'    : retour de la confirmation vers le formulaire (données conservées)
      'confirmer'   : valide à nouveau et ENREGISTRE (verrouille pour les agents)
    """
    user = request.user
    if not _peut_saisir(user):
        return _refuser(request, user, "Saisie transporteurs")
    poste = get_object_or_404(_postes_visibles(user), id=poste_id)   # 404 si poste non autorisé
    jour = _lire_date(date_str)
    if not jour or jour > timezone.localdate():
        messages.error(request, _("Date invalide."))
        return redirect('inventaire:transporteurs_choix_date')
    est_admin = _est_admin(user)
    # Règle : poste programmé pour l'inventaire => programmé pour les transporteurs
    programme = poste_programme_pour_transporteurs(poste, jour)
    if not programme and not est_admin:
        log_user_action(user, "Saisie transporteurs refusée (poste non programmé)",
                        f"Poste: {poste.nom} | Date: {jour}", request)
        messages.error(request, _("Ce poste n'est pas programmé pour l'inventaire à cette date."))
        return redirect('inventaire:transporteurs_choix_date')
    existante = InventaireTransporteur.objects.filter(poste=poste, date=jour).first()
    if existante and not est_admin:                          # fiche validée : lecture seule pour l'agent
        messages.warning(request, _("Cette fiche est validée. Seul un administrateur peut la modifier."))
        return redirect('inventaire:transporteurs_detail', pk=existante.pk)

    action = request.POST.get('action') if request.method == 'POST' else None
    agences = AgenceTransport.objects.filter(est_active=True).order_by('nom')   # ordre alphabétique

    def afficher_formulaire(blocs, erreurs=()):
        """Rend la page de saisie avec les blocs donnés (au moins un bloc vide)."""
        if not blocs:
            blocs = [{'index': 0, 'agence_id': '', 'vehicules': [{'index': 0, 'plaque': '', 'type': ''}]}]
        for b in blocs:                                      # garantit une ligne véhicule par bloc
            if not b['vehicules']:
                b['vehicules'] = [{'index': 0, 'plaque': '', 'type': ''}]
        return render(request, 'inventaire/transporteurs/saisie.html', {
            'poste': poste, 'date': jour, 'agences': agences, 'blocs': blocs, 'types': TYPES,
            'erreurs': erreurs, 'existante': existante, 'est_admin': est_admin,
            'non_programme': not programme,
            'prochain_bloc': max([b['index'] for b in blocs] + [0]) + 1,   # indice du prochain bloc JS
        })

    if request.method != 'POST':                             # --- GET : formulaire ---
        blocs = blocs_depuis_inventaire(existante) if existante else []
        log_user_action(user, "Accès saisie transporteurs",
                        f"Poste: {poste.nom} | Date: {jour} | Modification: {bool(existante)}", request)
        return afficher_formulaire(blocs)

    blocs = lire_blocs(request.POST)                         # --- POST : on relit tout ---
    if action == 'modifier':                                 # retour depuis la confirmation
        return afficher_formulaire(blocs)
    propres, erreurs, avertissements = valider_blocs(blocs)
    if erreurs:                                              # erreurs : on revient au formulaire
        return afficher_formulaire(blocs, erreurs)

    if action == 'apercu':                                   # --- fenêtre de confirmation ---
        champs = [(k, v) for k, valeurs in request.POST.lists() if k.startswith('ag-') for v in valeurs]
        return render(request, 'inventaire/transporteurs/confirmation.html', {
            'poste': poste, 'date': jour, 'resume': totaux(propres), 'types': TYPES,
            'avertissements': avertissements, 'champs_caches': champs, 'existante': existante,
        })

    if action != 'confirmer':                                # action inconnue
        return afficher_formulaire(blocs)

    # --- ENREGISTREMENT (tout ou rien) ---
    try:
        with transaction.atomic():
            inv, cree = InventaireTransporteur.objects.get_or_create(
                poste=poste, date=jour, defaults={'agent_saisie': user})
            if not cree:                                     # fiche déjà existante
                if not est_admin:                            # un agent ne peut pas l'écraser
                    raise PermissionError("fiche déjà validée")
                inv.vehicules.all().delete()                 # l'admin remplace les anciennes lignes
                inv.derniere_modification_par = user
                inv.date_derniere_modification = timezone.now()
                inv.save(update_fields=['derniere_modification_par', 'date_derniere_modification'])
            lignes = [DetailVehiculeTransporteur(            # bulk_create ne passe pas par save() : on normalise ici
                inventaire=inv, agence=b['agence'], agence_nom=b['agence'].nom,
                plaque=v['plaque'], plaque_normalisee=normaliser_plaque(v['plaque']),
                type_vehicule=v['type'])
                for b in propres for v in b['vehicules']]
            DetailVehiculeTransporteur.objects.bulk_create(lignes)
    except PermissionError:
        messages.error(request, _("Cette fiche vient d'être validée par un autre utilisateur."))
        return redirect('inventaire:transporteurs_liste')
    except IntegrityError:
        messages.error(request, _("Conflit d'enregistrement, veuillez réessayer."))
        return afficher_formulaire(blocs)

    resume = totaux(propres)
    log_user_action(user, "Modification fiche transporteurs" if not cree else "Validation fiche transporteurs",
                    f"Poste: {poste.nom} | Date: {jour} | Agences: {resume['nb_agences']} | "
                    f"Véhicules: {resume['total']}", request)
    messages.success(request, _("Fiche enregistrée : %(a)s agence(s), %(v)s véhicule(s).")
                     % {'a': resume['nb_agences'], 'v': resume['total']})
    return redirect('inventaire:transporteurs_detail', pk=inv.pk)


# ===================================================================
# LISTE PAR POSTE ET PAR JOUR (+ symbole œil)
# ===================================================================

def _annoter_types(qs):
    """Ajoute à un queryset .values() les compteurs de chacun des 4 types."""
    return qs.annotate(
        total=Count('id'),
        coaster=Count('id', filter=Q(type_vehicule='coaster')),
        bus_ordinaire=Count('id', filter=Q(type_vehicule='bus_ordinaire')),
        bus_clim=Count('id', filter=Q(type_vehicule='bus_clim')),
        hiace=Count('id', filter=Q(type_vehicule='hiace')),
    )


@login_required
def transporteurs_liste(request):
    """Liste des fiches : par poste et par jour, nb d'agences, de véhicules et de types."""
    user = request.user
    if not _peut_consulter(user):
        return _refuser(request, user, "Liste transporteurs")
    postes = _postes_visibles(user)
    fin = _lire_date(request.GET.get('date_fin'), timezone.localdate())
    debut = _lire_date(request.GET.get('date_debut'), fin - timedelta(days=30))
    poste_id = request.GET.get('poste') if _voit_tous_postes(user) else None
    fiches = InventaireTransporteur.objects.filter(
        poste__in=postes, date__range=(debut, fin)).select_related('poste', 'agent_saisie')
    if poste_id and poste_id.isdigit():
        fiches = fiches.filter(poste_id=int(poste_id))
    fiches = fiches.annotate(                                # compteurs calculés en une seule requête SQL
        n_vehicules=Count('vehicules'),
        n_agences=Count('vehicules__agence_nom', distinct=True),
        n_coaster=Count('vehicules', filter=Q(vehicules__type_vehicule='coaster')),
        n_bus_ordinaire=Count('vehicules', filter=Q(vehicules__type_vehicule='bus_ordinaire')),
        n_bus_clim=Count('vehicules', filter=Q(vehicules__type_vehicule='bus_clim')),
        n_hiace=Count('vehicules', filter=Q(vehicules__type_vehicule='hiace')),
    ).order_by('-date', 'poste__nom')
    page = Paginator(fiches.select_related('agent_saisie'), 30).get_page(request.GET.get('page'))
    for f in page:                                           # nom lisible de l'agent pour chaque ligne
        f.saisi_par = _nom_utilisateur(f.agent_saisie)
    parametres = request.GET.copy(); parametres.pop('page', None)   # conserve les filtres dans la pagination
    log_user_action(user, "Consultation liste transporteurs", f"Période: {debut} → {fin}", request)
    return render(request, 'inventaire/transporteurs/liste.html', {
        'page': page, 'postes': postes, 'choix_poste': _voit_tous_postes(user),
        'debut': debut.isoformat(), 'fin': fin.isoformat(), 'poste_id': poste_id or '',
        'qs': parametres.urlencode(), 'est_admin': _est_admin(user), 'types': TYPES,
    })


@login_required
def transporteurs_detail(request, pk):
    """Détail d'une fiche (l'œil) : agences, plaques, types, totaux."""
    user = request.user
    if not _peut_consulter(user):
        return _refuser(request, user, "Détail transporteurs")
    fiche = get_object_or_404(InventaireTransporteur.objects.select_related('poste', 'agent_saisie'),
                              pk=pk, poste__in=_postes_visibles(user))   # 404 si hors de sa portée
    fiche.saisi_par = _nom_utilisateur(fiche.agent_saisie)               # jamais 'None'
    fiche.modifie_par = _nom_utilisateur(fiche.derniere_modification_par)
    groupes = fiche.regrouper_par_agence()
    par_type = fiche.totaux_par_type()
    return render(request, 'inventaire/transporteurs/detail.html', {
        'fiche': fiche, 'groupes': groupes,
        'totaux_types': [(code, lib, par_type[code]) for code, lib in TYPES],
        'est_admin': _est_admin(user),
    })


@login_required
@require_POST
def transporteurs_supprimer(request, pk):
    """
    Supprime une fiche (administrateur uniquement, après confirmation).
    Les lignes véhicules sont supprimées en cascade ; la date du poste est donc
    libérée et peut être ressaisie par l'agent ou par un administrateur.
    """
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Suppression fiche transporteurs", 'inventaire:transporteurs_liste')
    if request.POST.get('confirmer') != '1':                 # sécurité côté serveur
        messages.error(request, _("Suppression non confirmée."))
        return redirect('inventaire:transporteurs_liste')
    fiche = get_object_or_404(InventaireTransporteur.objects.select_related('poste', 'agent_saisie'),
                              pk=pk, poste__in=_postes_visibles(user))
    resume = (f"Poste: {fiche.poste.nom} | Date: {fiche.date} | Agences: {fiche.nombre_agences} | "
              f"Véhicules: {fiche.total_vehicules} | Saisi par: {_nom_utilisateur(fiche.agent_saisie)}")
    with transaction.atomic():                               # tout ou rien
        fiche.delete()
    log_user_action(user, "Suppression fiche transporteurs", resume, request)
    messages.success(request, _("Fiche du %(d)s supprimée pour %(p)s : la date peut être ressaisie.")
                     % {'d': fiche.date.strftime('%d/%m/%Y'), 'p': fiche.poste.nom})
    return redirect('inventaire:transporteurs_liste')


# ===================================================================
# GESTION DES AGENCES : liste/ajout, import Excel, suppression
# ===================================================================

@login_required
def transporteurs_agences(request):
    """Liste alphabétique des agences + ajout d'une agence (POST)."""
    user = request.user
    if not _peut_saisir(user):
        return _refuser(request, user, "Agences transport")
    if request.method == 'POST':                             # ajout d'une agence
        agence, cree = AgenceTransport.creer_si_absente(request.POST.get('nom'), user)
        if agence is None:
            messages.error(request, _("Le nom de l'agence est vide."))
        elif cree:
            log_user_action(user, "Ajout agence transport", f"Agence: {agence.nom}", request)
            messages.success(request, _("Agence « %(n)s » ajoutée.") % {'n': agence.nom})
        else:
            messages.info(request, _("L'agence « %(n)s » existe déjà.") % {'n': agence.nom})
        return redirect('inventaire:transporteurs_agences')
    q = request.GET.get('q', '').strip()
    agences = AgenceTransport.objects.annotate(n_vehicules=Count('vehicules')).order_by('nom')
    if q:
        agences = agences.filter(nom__icontains=normaliser_nom_agence(q))
    return render(request, 'inventaire/transporteurs/agences.html', {
        'agences': agences, 'q': q, 'est_admin': _est_admin(user),
    })


@login_required
@require_POST
def transporteurs_agences_importer(request):
    """Import Excel (.xlsx) : 1re colonne = noms ; doublons ignorés ; réservé à l'administrateur."""
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Import agences", 'inventaire:transporteurs_agences')
    fichier = request.FILES.get('fichier')
    if not fichier or not fichier.name.lower().endswith('.xlsx'):
        messages.error(request, _("Veuillez choisir un fichier Excel .xlsx."))
        return redirect('inventaire:transporteurs_agences')
    try:
        from openpyxl import load_workbook                   # lecture Excel
        classeur = load_workbook(fichier, read_only=True, data_only=True)
        feuille = classeur.active                            # première feuille active
        noms = [row[0] for row in feuille.iter_rows(values_only=True) if row and row[0] is not None]
    except Exception as e:                                   # fichier illisible
        logger.error(f"Import agences : {e}")
        messages.error(request, _("Fichier illisible : %(e)s") % {'e': e})
        return redirect('inventaire:transporteurs_agences')
    if noms and normaliser_nom_agence(noms[0]) in {'NOM', 'AGENCE', 'AGENCES', 'NOM AGENCE', 'NOM DE L AGENCE', "NOM DE L'AGENCE"}:
        noms = noms[1:]                                      # saute la ligne d'en-tête
    ajoutees, ignorees = [], []
    for nom in sorted({normaliser_nom_agence(n) for n in noms if normaliser_nom_agence(n)}):   # alphabétique, sans doublon exact
        _agence, cree = AgenceTransport.creer_si_absente(nom, user)    # saute si équivalente existante
        (ajoutees if cree else ignorees).append(nom)
    log_user_action(user, "Import agences transport",
                    f"Fichier: {fichier.name} | Ajoutées: {len(ajoutees)} | Ignorées: {len(ignorees)}", request)
    messages.success(request, _("Import terminé : %(a)s ajoutée(s), %(i)s ignorée(s) (déjà existantes).")
                     % {'a': len(ajoutees), 'i': len(ignorees)})
    return redirect('inventaire:transporteurs_agences')


def _lignes_agence(agence):
    """
    Toutes les lignes véhicules rattachées à une agence : celles liées par clé
    étrangère ET celles qui ne portent que son nom (cas d'une agence supprimée
    puis recréée sous le même nom).
    """
    return DetailVehiculeTransporteur.objects.filter(Q(agence=agence) | Q(agence_nom=agence.nom))


@login_required
@require_POST
def transporteurs_agences_modifier(request, pk):
    """
    Renomme une agence (administrateur uniquement).
    - Si le nouveau nom correspond à une autre agence existante (même clé :
      LEADER = leader = LEADERS), les deux sont FUSIONNÉES : tous les véhicules de
      l'agence modifiée passent à l'agence existante, qui garde son nom, puis
      l'agence modifiée est supprimée. Une page de confirmation est affichée avant.
    - Sinon, l'agence est simplement renommée, et l'historique suit le nouveau nom.
    """
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Modification agence", 'inventaire:transporteurs_agences')
    agence = get_object_or_404(AgenceTransport, pk=pk)
    nouveau = normaliser_nom_agence(request.POST.get('nom'))
    if not nouveau:
        messages.error(request, _("Le nom de l'agence est vide."))
        return redirect('inventaire:transporteurs_agences')
    if len(nouveau) > 150:
        messages.error(request, _("Nom trop long (150 caractères maximum)."))
        return redirect('inventaire:transporteurs_agences')
    cible = AgenceTransport.objects.filter(cle_unicite=cle_unicite_agence(nouveau)).exclude(pk=agence.pk).first()
    ancien = agence.nom

    if cible is None:                                        # --- simple renommage ---
        if nouveau == ancien:
            messages.info(request, _("Le nom n'a pas changé."))
            return redirect('inventaire:transporteurs_agences')
        with transaction.atomic():
            _lignes_agence(agence).update(agence=agence, agence_nom=nouveau)   # l'historique suit le nouveau nom
            agence.nom = nouveau
            agence.save()                                    # recalcule aussi la clé d'unicité
        log_user_action(user, "Renommage agence transport", f"{ancien} → {nouveau}", request)
        messages.success(request, _("Agence renommée : « %(a)s » → « %(n)s ».") % {'a': ancien, 'n': nouveau})
        return redirect('inventaire:transporteurs_agences')

    # --- fusion : il faut une confirmation explicite ---
    n_source = _lignes_agence(agence).count()
    n_cible = _lignes_agence(cible).count()
    if request.POST.get('fusion') != '1':                    # 1er passage : page de confirmation
        return render(request, 'inventaire/transporteurs/agence_fusion.html', {
            'agence': agence, 'cible': cible, 'nom': nouveau,
            'n_source': n_source, 'n_cible': n_cible, 'n_total': n_source + n_cible,
        })
    with transaction.atomic():                               # 2e passage : fusion tout ou rien
        _lignes_agence(agence).update(agence=cible, agence_nom=cible.nom)   # véhicules -> agence cible
        agence.delete()                                      # l'agence mal orthographiée disparaît
    log_user_action(user, "Fusion agences transport",
                    f"{ancien} → {cible.nom} | Véhicules déplacés: {n_source} | Total après fusion: {n_source + n_cible}", request)
    messages.success(request, _("« %(a)s » fusionnée dans « %(c)s » : %(n)s véhicule(s) déplacé(s), %(t)s au total.")
                     % {'a': ancien, 'c': cible.nom, 'n': n_source, 't': n_source + n_cible})
    return redirect('inventaire:transporteurs_agences')


@login_required
@require_POST
def transporteurs_agences_supprimer(request):
    """Supprime une ou plusieurs agences (après la fenêtre de confirmation) ; admin seulement."""
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Suppression agences", 'inventaire:transporteurs_agences')
    if request.POST.get('confirmer') != '1':                 # sécurité côté serveur
        messages.error(request, _("Suppression non confirmée."))
        return redirect('inventaire:transporteurs_agences')
    ids = [int(i) for i in request.POST.getlist('ids') if i.isdigit()]
    agences = list(AgenceTransport.objects.filter(id__in=ids))
    noms = [a.nom for a in agences]
    AgenceTransport.objects.filter(id__in=ids).delete()      # l'historique garde agence_nom (SET_NULL)
    log_user_action(user, "Suppression agences transport",
                    f"{len(noms)} agence(s): {', '.join(noms)[:500]}", request)
    messages.success(request, _("%(n)s agence(s) supprimée(s).") % {'n': len(noms)})
    return redirect('inventaire:transporteurs_agences')


# ===================================================================
# STATISTIQUES : par poste / par agence / par plaque
# ===================================================================

@login_required
@require_POST
def transporteurs_plaque_modifier(request):
    """
    Corrige une plaque mal saisie (administrateur uniquement), pour UNE agence.
    Toutes les lignes de cette plaque (« LT 123 ») chez cette agence, quelles que
    soient les dates et les postes, prennent la nouvelle plaque (« LT 123 EB »).
    Si la nouvelle plaque existe déjà chez la même agence, les passages sont
    FUSIONNÉS : un seul véhicule, les passages et les postes des deux s'additionnent.
    Une page de confirmation (avec les chiffres) précède toute modification.
    """
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Modification plaque", 'inventaire:transporteurs_stats')
    ancienne = normaliser_plaque(request.POST.get('ancienne'))          # plaque actuelle (forme de recherche)
    agence_nom = normaliser_nom_agence(request.POST.get('agence'))       # l'agence concernée
    nouvelle = afficher_plaque(request.POST.get('plaque'))               # nouvelle plaque (affichage)
    nouvelle_norm = normaliser_plaque(nouvelle)                          # nouvelle plaque (recherche)
    retour = request.POST.get('retour') or ''                            # page de statistiques d'où l'on vient
    if not url_has_allowed_host_and_scheme(retour, allowed_hosts={request.get_host()}) or not retour.startswith('/'):
        retour = reverse('inventaire:transporteurs_stats')               # adresse de retour douteuse : on l'ignore
    if len(nouvelle_norm) < 3 or len(nouvelle) > 30:
        messages.error(request, _("Plaque invalide (3 caractères minimum, 30 maximum)."))
        return redirect(retour)
    portee = DetailVehiculeTransporteur.objects.filter(inventaire__poste__in=_postes_visibles(user), agence_nom=agence_nom)
    ids = list(portee.filter(plaque_normalisee=ancienne).values_list('id', flat=True))   # lignes à corriger
    if not ids:
        messages.error(request, _("Aucun passage trouvé pour cette plaque et cette agence."))
        return redirect(retour)
    n_postes = portee.filter(id__in=ids).values('inventaire__poste').distinct().count()
    existantes = portee.filter(plaque_normalisee=nouvelle_norm).exclude(id__in=ids)   # lignes de la vraie plaque
    ids_exist = list(existantes.values_list('id', flat=True))
    type_cible = None                                                    # type retenu après fusion = le plus fréquent de la vraie plaque
    if ids_exist:
        top = existantes.values('type_vehicule').annotate(n=Count('id')).order_by('-n').first()
        type_cible = top['type_vehicule']
    if request.POST.get('confirmer') != '1':                             # 1er passage : page de confirmation
        postes_total = portee.filter(id__in=ids + ids_exist).values('inventaire__poste').distinct().count()
        return render(request, 'inventaire/transporteurs/plaque_fusion.html', {
            'ancienne': portee.filter(id__in=ids).first().plaque, 'ancienne_norm': ancienne,
            'nouvelle': nouvelle, 'agence': agence_nom, 'retour': retour,
            'n_lignes': len(ids), 'n_postes': n_postes, 'n_exist': len(ids_exist),
            'fusion': bool(ids_exist), 'postes_total': postes_total, 'passages_total': len(ids) + len(ids_exist),
        })
    with transaction.atomic():                                           # 2e passage : application tout ou rien
        if ids_exist:                                                    # même écriture d'affichage pour toute la plaque
            DetailVehiculeTransporteur.objects.filter(id__in=ids_exist).update(plaque=nouvelle)
        changements = {'plaque': nouvelle, 'plaque_normalisee': nouvelle_norm}
        if type_cible:
            changements['type_vehicule'] = type_cible                    # un seul type pour le véhicule fusionné
        DetailVehiculeTransporteur.objects.filter(id__in=ids).update(**changements)
    log_user_action(user, "Fusion plaque transporteur" if ids_exist else "Correction plaque transporteur",
                    f"Agence: {agence_nom} | {ancienne} → {nouvelle} | Passages modifiés: {len(ids)} | "
                    f"Passages déjà présents: {len(ids_exist)}", request)
    messages.success(request, _("Plaque corrigée : %(n)s passage(s) déplacé(s) vers « %(p)s ».") % {'n': len(ids), 'p': nouvelle})
    return redirect(retour)


# ===================================================================
# RAPPROCHEMENT DES PLAQUES D'UNE AGENCE (administrateur)
# ===================================================================

def _plaques_par_agence(postes, agence_nom=None):
    """
    Une ligne par plaque (forme normalisée) ET par agence : nombre de passages, postes
    où elle est passée (avec le nombre de passages par poste), type dominant, premier
    et dernier passage. Retourne {nom d'agence: [plaques]}. Quelques requêtes SQL au
    total, quel que soit le nombre d'agences. 'agence_nom' limite à une seule agence.
    """
    lignes = DetailVehiculeTransporteur.objects.filter(inventaire__poste__in=postes)
    if agence_nom:
        lignes = lignes.filter(agence_nom=agence_nom)
    libelles = dict(TYPES)
    postes_par = defaultdict(list)                                       # (agence, plaque) -> [(poste, nb passages)]
    for r in lignes.values('agence_nom', 'plaque_normalisee', 'inventaire__poste__nom').annotate(n=Count('id')).order_by('inventaire__poste__nom'):
        postes_par[(r['agence_nom'], r['plaque_normalisee'])].append((r['inventaire__poste__nom'], r['n']))
    type_dom = {}                                                        # (agence, plaque) -> (type le plus fréquent, effectif)
    for r in lignes.values('agence_nom', 'plaque_normalisee', 'type_vehicule').annotate(n=Count('id')):
        cle = (r['agence_nom'], r['plaque_normalisee'])
        if cle not in type_dom or r['n'] > type_dom[cle][1]:
            type_dom[cle] = (r['type_vehicule'], r['n'])
    resultat = defaultdict(list)
    for r in lignes.values('agence_nom', 'plaque_normalisee').annotate(
            passages=Count('id'), plaque=Max('plaque'), premier=Min('inventaire__date'),
            dernier=Max('inventaire__date')).order_by('agence_nom', 'plaque_normalisee'):
        cle = (r['agence_nom'], r['plaque_normalisee'])
        resultat[r['agence_nom']].append({
            'norm': r['plaque_normalisee'], 'plaque': r['plaque'], 'passages': r['passages'],
            'postes': postes_par[cle], 'n_postes': len(postes_par[cle]),
            'type': type_dom[cle][0], 'type_libelle': str(libelles.get(type_dom[cle][0], '')),
            'premier': r['premier'], 'dernier': r['dernier']})
    return resultat


def _plaques_agence(agence, postes):
    """Plaques d'une seule agence (voir _plaques_par_agence)."""
    return _plaques_par_agence(postes, agence.nom).get(agence.nom, [])


def _suggestions(plaques):
    """
    Propose des groupes « plaque complète + plaques incomplètes qui la composent ».
    Une plaque B est candidate pour A si B (4 caractères minimum) est contenue dans
    A et plus courte : LT123 est candidate pour LT123ER. On part des plaques les plus
    longues ; chaque plaque n'est proposée que dans un seul groupe, et celles qui
    pourraient aller dans plusieurs groupes sont signalées (champ 'autres').
    """
    ordre = sorted(plaques, key=lambda p: (-len(p['norm']), -p['passages'], p['norm']))
    prises, groupes = set(), []
    for cible in ordre:
        if cible['norm'] in prises:
            continue
        cands = [q for q in ordre if q['norm'] != cible['norm'] and q['norm'] not in prises
                 and 4 <= len(q['norm']) < len(cible['norm']) and q['norm'] in cible['norm']]
        if not cands:
            continue
        prises.add(cible['norm'])
        prises.update(q['norm'] for q in cands)
        groupe = {'cible': cible, 'candidats': []}
        for q in cands:
            autres = [a['plaque'] for a in ordre if a['norm'] not in (cible['norm'], q['norm']) and q['norm'] in a['norm']]
            groupe['candidats'].append(dict(q, autres=autres))           # copie + plaques concurrentes
        groupes.append(groupe)
    return groupes


@login_required
def transporteurs_rapprochement(request):
    """
    Page de rapprochement : toutes les plaques d'une agence avec suggestions de fusion
    et cases à cocher, ou (agence=toutes) le tableau des similitudes de TOUTES les agences.
    """
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Rapprochement plaques", 'inventaire:transporteurs_stats')
    agences = AgenceTransport.objects.annotate(n=Count('vehicules')).filter(n__gt=0).order_by('nom')
    choix = request.GET.get('agence') or ''
    ctx = {'agences': agences, 'agence': None, 'toutes_actif': choix == 'toutes', 'retour': request.get_full_path()}
    if choix == 'toutes':                                                # --- toutes les agences ---
        par_agence = _plaques_par_agence(_postes_visibles(user))         # 3 requêtes pour toutes les agences
        resume = []
        for a in agences:
            plaques = par_agence.get(a.nom, [])
            groupes = _suggestions(plaques)
            resume.append({'agence': a, 'nb_plaques': len(plaques), 'passages': sum(p['passages'] for p in plaques),
                           'groupes': groupes, 'nb_candidates': sum(len(g['candidats']) for g in groupes)})
        ctx.update({'resume': resume,
                    'total_groupes': sum(len(r['groupes']) for r in resume),
                    'agences_concernees': sum(1 for r in resume if r['groupes'])})
        log_user_action(user, "Rapprochement plaques (toutes agences)",
                        f"Agences: {len(resume)} | Rapprochements: {ctx['total_groupes']}", request)
    else:                                                                # --- une agence ---
        agence = agences.filter(id=choix or None).first() if choix.isdigit() else None
        ctx['agence'] = agence
        if agence:
            plaques = _plaques_agence(agence, _postes_visibles(user))
            ctx.update({'plaques': plaques, 'groupes': _suggestions(plaques),
                        'n_passages': sum(p['passages'] for p in plaques)})
            log_user_action(user, "Rapprochement plaques", f"Agence: {agence.nom} | Plaques: {len(plaques)}", request)
    return render(request, 'inventaire/transporteurs/rapprochement.html', ctx)


@login_required
@require_POST
def transporteurs_rapprochement_fusionner(request):
    """
    Fusionne plusieurs plaques d'une agence dans une plaque cible (administrateur).
    Étape 1 : page de confirmation avec les chiffres. Étape 2 (confirmer=1) : application.
    Les passages des plaques sources prennent la plaque et le type dominant de la cible.
    """
    user = request.user
    if not _est_admin(user):
        return _refuser(request, user, "Fusion plaques", 'inventaire:transporteurs_stats')
    retour = request.POST.get('retour') or ''
    if not url_has_allowed_host_and_scheme(retour, allowed_hosts={request.get_host()}) or not retour.startswith('/'):
        retour = reverse('inventaire:transporteurs_rapprochement')
    agence = AgenceTransport.objects.filter(id=request.POST.get('agence') or None).first()
    cible = normaliser_plaque(request.POST.get('cible'))
    sources = sorted({normaliser_plaque(x) for x in request.POST.getlist('sources')} - {cible, ''})
    if not agence or not cible or not sources:
        messages.error(request, _("Choisissez une plaque cible et au moins une plaque à fusionner."))
        return redirect(retour)
    infos = {p['norm']: p for p in _plaques_agence(agence, _postes_visibles(user))}
    if cible not in infos or any(x not in infos for x in sources):
        messages.error(request, _("Plaque introuvable pour cette agence."))
        return redirect(retour)
    postes_total = {n for x in sources + [cible] for n, _c in infos[x]['postes']}     # postes distincts après fusion
    passages_total = sum(infos[x]['passages'] for x in sources + [cible])
    if request.POST.get('confirmer') != '1':                              # 1er passage : confirmation
        return render(request, 'inventaire/transporteurs/rapprochement_confirmation.html', {
            'agence': agence, 'cible': infos[cible], 'sources': [infos[x] for x in sources],
            'passages_total': passages_total, 'postes_total': len(postes_total), 'retour': retour,
            'sources_norm': sources,
        })
    with transaction.atomic():                                            # 2e passage : tout ou rien
        DetailVehiculeTransporteur.objects.filter(
            agence_nom=agence.nom, plaque_normalisee__in=sources, inventaire__poste__in=_postes_visibles(user)
        ).update(plaque=infos[cible]['plaque'], plaque_normalisee=cible, type_vehicule=infos[cible]['type'])
    log_user_action(user, "Fusion plaques (rapprochement)",
                    f"Agence: {agence.nom} | {', '.join(sources)} → {cible} | Passages: {passages_total} | "
                    f"Postes distincts: {len(postes_total)}", request)
    messages.success(request, _("%(n)s plaque(s) fusionnée(s) dans « %(c)s » : %(p)s passage(s), %(q)s poste(s).")
                     % {'n': len(sources), 'c': infos[cible]['plaque'], 'p': passages_total, 'q': len(postes_total)})
    return redirect(retour)


def _ajouter_libelles(lignes):
    """Ajoute 'type_libelle' (texte lisible) à chaque ligne issue d'un .values()."""
    libelles = dict(TYPES)
    for ligne in lignes:
        ligne['type_libelle'] = str(libelles.get(ligne['type_vehicule'], ligne['type_vehicule']))


@login_required
def transporteurs_stats(request):
    """
    mode=poste  : agences, véhicules et types passés à un poste sur une période
    mode=agence : postes où une agence (ou toutes) est passée + véhicules utilisés
    mode=plaque : tous les passages d'une plaque (postes traversés) sur une période
    """
    user = request.user
    if not _peut_consulter(user):
        return _refuser(request, user, "Statistiques transporteurs")
    postes = _postes_visibles(user)
    mode = request.GET.get('mode', 'poste')
    if mode not in ('poste', 'agence', 'plaque'):
        mode = 'poste'
    fin = _lire_date(request.GET.get('date_fin'), timezone.localdate())
    debut = _lire_date(request.GET.get('date_debut'), fin.replace(day=1))
    ctx = {'mode': mode, 'debut': debut.isoformat(), 'fin': fin.isoformat(), 'postes': postes,
           'choix_poste': _voit_tous_postes(user), 'agences': AgenceTransport.objects.order_by('nom'),
           'types': TYPES, 'calcule': 'go' in request.GET,
           'poste_id': request.GET.get('poste', ''), 'agence_id': request.GET.get('agence', ''),
           'plaque_q': request.GET.get('plaque', '').strip(),
           'est_admin': _est_admin(user), 'retour': request.get_full_path()}
    if not ctx['calcule']:                                   # première visite : formulaire seul
        return render(request, 'inventaire/transporteurs/stats.html', ctx)
    if debut > fin:
        messages.error(request, _("La date de début doit précéder la date de fin."))
        return render(request, 'inventaire/transporteurs/stats.html', ctx)

    base = DetailVehiculeTransporteur.objects.filter(        # lignes dans la période ET la portée de l'utilisateur
        inventaire__date__range=(debut, fin), inventaire__poste__in=postes)
    log_user_action(user, "Statistiques transporteurs", f"Mode: {mode} | {debut} → {fin}", request)

    if mode == 'poste':
        poste = postes.filter(id=ctx['poste_id'] or None).first() if _voit_tous_postes(user) else postes.first()
        if not poste:
            messages.error(request, _("Choisissez un poste."))
            return render(request, 'inventaire/transporteurs/stats.html', ctx)
        qs = base.filter(inventaire__poste=poste)
        ctx['poste'] = poste
        ctx['par_agence'] = list(_annoter_types(qs.values('agence_nom')
                                 .annotate(jours=Count('inventaire__date', distinct=True))).order_by('-total', 'agence_nom'))
        ctx['par_type'] = [(lib, qs.filter(type_vehicule=code).count()) for code, lib in TYPES]
        ctx['vehicules'] = list(qs.values('plaque_normalisee', 'agence_nom', 'type_vehicule')
                                .annotate(passages=Count('id'), plaque=Max('plaque'), dernier=Max('inventaire__date'))
                                .order_by('-passages', 'agence_nom', 'plaque_normalisee'))
        ctx['total'] = qs.count()
        _ajouter_libelles(ctx['vehicules'])                  # libellé lisible du type

    elif mode == 'agence':
        qs = base
        if ctx['agence_id'].isdigit():                       # une agence précise
            agence = AgenceTransport.objects.filter(id=int(ctx['agence_id'])).first()
            if agence:
                qs = qs.filter(agence_nom=agence.nom)
                ctx['agence'] = agence
        if _voit_tous_postes(user) and ctx['poste_id'].isdigit():
            qs = qs.filter(inventaire__poste_id=int(ctx['poste_id']))   # filtre poste facultatif
        ctx['par_poste'] = list(_annoter_types(qs.values('inventaire__poste__nom')
                                .annotate(jours=Count('inventaire__date', distinct=True),
                                          n_agences=Count('agence_nom', distinct=True))).order_by('-total', 'inventaire__poste__nom'))
        if 'agence' not in ctx:                              # toutes agences : classement des agences
            ctx['par_agence'] = list(_annoter_types(qs.values('agence_nom')
                                     .annotate(n_postes=Count('inventaire__poste', distinct=True))).order_by('-total', 'agence_nom'))
        ctx['vehicules'] = list(qs.values('plaque_normalisee', 'agence_nom', 'type_vehicule')
                                .annotate(passages=Count('id'), plaque=Max('plaque'),
                                          n_postes=Count('inventaire__poste', distinct=True))
                                .order_by('-passages', 'agence_nom')[:1000])   # plafond d'affichage
        ctx['total'] = qs.count()
        _ajouter_libelles(ctx['vehicules'])

    else:  # mode == 'plaque'
        cle = normaliser_plaque(ctx['plaque_q'])
        if len(cle) < 3:
            messages.error(request, _("Saisissez au moins 3 caractères de la plaque."))
            return render(request, 'inventaire/transporteurs/stats.html', ctx)
        qs = base.filter(plaque_normalisee__icontains=cle)   # recherche partielle
        ctx['passages'] = list(qs.select_related('inventaire__poste')
                               .order_by('inventaire__date', 'inventaire__poste__nom')[:2000])
        ctx['par_poste'] = list(qs.values('inventaire__poste__nom')
                                .annotate(passages=Count('id'), dernier=Max('inventaire__date'))
                                .order_by('-passages', 'inventaire__poste__nom'))
        ctx['plaques_trouvees'] = list(qs.values_list('plaque', flat=True).distinct().order_by('plaque')[:50])
        ctx['total'] = qs.count()
    return render(request, 'inventaire/transporteurs/stats.html', ctx)
