# inventaire/views_permutation.py
# Vues de la permutation de séries de tickets : formulaire + simulation + confirmation,
# historique des permutations et annulation.
# Accès : administrateur, Service Informatique, Service Émissions et Recouvrement.

import logging  # Journal technique
from django.contrib import messages  # Messages à l'utilisateur
from django.contrib.auth.decorators import login_required  # Accès authentifié
from django.shortcuts import render, redirect, get_object_or_404  # Raccourcis Django
from django.views.decorators.http import require_POST  # Annulation : POST uniquement

from accounts.models import Poste  # Postes
from common.permissions import get_postes_accessibles  # Postes accessibles à l'utilisateur
from common.utils import log_user_action  # Journalisation des actions
from inventaire.models import SerieTicket, CouleurTicket  # Séries et couleurs
from inventaire.models_permutation import PermutationSeries, StatutPermutation  # Historique
from inventaire.services import permutation_service as ps  # Logique métier

logger = logging.getLogger('supper')


def _refuser(request):
    """Message + redirection quand l'utilisateur n'a pas le droit de permuter."""
    messages.error(request, "Vous n'avez pas la permission de permuter des séries de tickets.")
    return redirect('common:dashboard')


GAP_NOTE = 10  # Un écart (série intermédiaire) jusqu'à 10 numéros entre deux séries vendues est signalé à l'écran


def _series_chargees(poste):
    """Séries en stock du poste : d'abord celles chargées par l'Imprimerie Nationale, puis les autres entrées."""
    lignes = list(SerieTicket.objects.filter(poste=poste, statut='stock').select_related('couleur'))
    lignes.sort(key=lambda s: (0 if s.type_entree == 'imprimerie_nationale' else 1, s.couleur.libelle_affichage,
                               s.numero_premier))  # IN en premier, puis par couleur et numéro
    return lignes


def _statut_intermediaire(poste, couleur, premier, dernier):
    """Libellé du statut des numéros intermédiaires [premier, dernier] : « en stock » si tout est en stock, sinon « non vendus »."""
    lignes = SerieTicket.objects.filter(poste=poste, couleur=couleur, numero_premier__lte=dernier,
                                        numero_dernier__gte=premier)  # Lignes qui couvrent l'écart
    return 'en stock' if lignes.exists() and not lignes.exclude(statut='stock').exists() else 'non vendus'


def _series_vendues(poste):
    """Séries vendues du poste, les plus récentes d'abord.
    Seules les séries strictement contiguës d'une même couleur sont fusionnées (1-5 + 6-8 -> 1-8).
    Si deux séries sont séparées (1-5 et 7-8), elles restent affichées telles quelles et la série
    intermédiaire (6) est signalée avec son statut."""
    blocs = []  # Blocs {couleur, premier, dernier, nb_vendus, date, inter_avant, inter_apres}
    lignes = SerieTicket.objects.filter(poste=poste, statut='vendu').select_related('couleur').order_by(
        'couleur_id', 'numero_premier')
    bloc = None  # Bloc en cours de construction
    for s in lignes:
        if bloc and bloc['couleur'].pk == s.couleur_id and s.numero_premier <= bloc['dernier'] + 1:
            bloc['dernier'] = max(bloc['dernier'], s.numero_dernier)  # Contigu : on fusionne
            bloc['nb_vendus'] += s.nombre_tickets
            if s.date_utilisation and (not bloc['date'] or s.date_utilisation > bloc['date']):
                bloc['date'] = s.date_utilisation  # Date de la vente la plus récente
        else:
            if bloc:
                blocs.append(bloc)  # Bloc terminé
            bloc = {'couleur': s.couleur, 'premier': s.numero_premier, 'dernier': s.numero_dernier,
                    'nb_vendus': s.nombre_tickets, 'date': s.date_utilisation, 'inter_avant': '', 'inter_apres': ''}
    if bloc:
        blocs.append(bloc)
    for x, y in zip(blocs, blocs[1:]):  # Blocs voisins (triés par couleur puis numéro)
        if x['couleur'].pk == y['couleur'].pk and 0 < y['premier'] - x['dernier'] - 1 <= GAP_NOTE:
            p, d = x['dernier'] + 1, y['premier'] - 1  # Série intermédiaire
            txt = f"{p}-{d}" if p != d else str(p)
            statut = _statut_intermediaire(poste, x['couleur'], p, d)
            x['inter_apres'] = f"série intermédiaire {txt} ({statut})"  # Note sous le bloc du bas
            y['inter_avant'] = f"série intermédiaire {txt} ({statut})"  # Note sous le bloc du haut
    blocs.sort(key=lambda x: (x['date'] is not None, x['date']), reverse=True)  # Plus récentes d'abord
    return blocs[:200]


def _lignes(donnees, prefixe):
    """Lit les lignes d'un côté du formulaire : listes <prefixe>_couleur et <prefixe>_plage.
    Retourne (lignes_brutes, plages) : lignes_brutes sert à réafficher la saisie, plages = [(couleur, premier, dernier)].
    Les lignes complètement vides sont ignorées ; une ligne incomplète ou illisible lève ValueError."""
    couleurs = donnees.getlist(f'{prefixe}_couleur')  # Couleur de chaque ligne
    textes = donnees.getlist(f'{prefixe}_plage')  # Plage de chaque ligne
    brutes, plages = [], []
    for cid, texte in zip(couleurs, textes):
        texte = (texte or '').strip()
        if not cid and not texte:
            continue  # Ligne vide
        brutes.append({'couleur': cid, 'plage': texte})  # Conservée pour le réaffichage
        couleur = CouleurTicket.objects.filter(pk=cid or 0).first()
        p = ps.lire_plage(texte)
        if not couleur or not p:
            raise ValueError(f"Ligne « {texte or 'vide'} » : choisissez la couleur et une plage valide (ex. 10-20).")
        plages.append((couleur, p[0], p[1]))
    return brutes, plages


@login_required
def permutation_nouvelle(request):
    """Permutation : on choisit le poste (les séries apparaissent), puis les plages à réveiller et à tuer
    (autant de lignes que nécessaire de chaque côté)."""
    user = request.user
    if not ps.peut_permuter(user):
        return _refuser(request)  # Contrôle d'accès côté vue (en plus du menu)
    postes = get_postes_accessibles(user, type_poste='peage').order_by('nom')  # Permutation = tickets de péage
    donnees = request.POST if request.method == 'POST' else request.GET  # Valeurs saisies ou pré-remplies
    poste = postes.filter(pk=donnees.get('poste') or 0).first()  # Poste choisi (ou None)
    contexte = {'postes': postes, 'poste': poste, 'couleurs': CouleurTicket.objects.all().order_by('libelle_affichage'),
                'lignes_reveil': [], 'lignes_tue': [], 'motif': donnees.get('motif', ''), 'title': 'Permutation de séries'}

    if request.method == 'POST' and poste:
        try:
            contexte['lignes_reveil'], reveil = _lignes(donnees, 'reveil')
            contexte['lignes_tue'], tue = _lignes(donnees, 'tue')
        except ValueError as exc:
            messages.error(request, str(exc))
            reveil = tue = None
        if reveil is not None and (not reveil or not tue):
            messages.error(request, "Indiquez au moins une plage à réveiller et une plage à tuer.")
        elif reveil is not None:
            apercu = ps.previsualiser(poste, reveil, tue)  # Validation sans modification
            if apercu['erreurs']:
                for e in apercu['erreurs']:
                    messages.error(request, e)  # Affiche chaque problème (dont l'égalité de valeur)
            elif donnees.get('action') == 'confirmer':  # Exécution réelle
                try:
                    perm = ps.executer(poste, reveil, tue, donnees.get('motif', ''), user)
                except ps.PermutationError as exc:
                    messages.error(request, str(exc))  # Erreur métier (verrou, motif, etc.)
                else:
                    try:  # La journalisation ne doit jamais bloquer l'opération
                        log_user_action(user, "PERMUTATION_SERIES", f"{perm} - {perm.motif}", request)
                    except Exception:
                        logger.exception("Journalisation de la permutation impossible")
                    messages.success(request, f"Permutation effectuée : {perm.nombre_tickets} tickets ({perm.montant} FCFA) "
                                              f"échangés dans {len(perm.details)} opération(s).")
                    return redirect('inventaire:permutation_historique')
            else:  # Simulation : on affiche ce qui va changer
                contexte['apercu'] = apercu
    elif request.method == 'POST':
        messages.error(request, "Choisissez d'abord le poste.")

    if not contexte['lignes_reveil']:
        contexte['lignes_reveil'] = [{'couleur': donnees.get('reveil_couleur', ''), 'plage': donnees.get('reveil_plage', '')}]
    if not contexte['lignes_tue']:
        contexte['lignes_tue'] = [{'couleur': donnees.get('tue_couleur', ''), 'plage': donnees.get('tue_plage', '')}]
    if poste:  # Séries du poste : chargées (IN d'abord) puis vendues (consolidées, récentes d'abord)
        contexte['series_stock'] = _series_chargees(poste)
        contexte['series_vendues'] = _series_vendues(poste)
    return render(request, 'inventaire/permutation_form.html', contexte)


@login_required
def permutation_historique(request):
    """Liste des permutations (filtres : poste, statut, numéro de ticket)."""
    user = request.user
    if not ps.peut_permuter(user):
        return _refuser(request)
    qs = PermutationSeries.objects.select_related('poste', 'couleur_reveil', 'couleur_tue', 'recette',
                                                  'effectue_par', 'annulee_par')
    poste_id = request.GET.get('poste') or ''  # Filtre poste
    statut = request.GET.get('statut') or ''  # Filtre statut
    ticket = (request.GET.get('ticket') or '').strip()  # Filtre : numéro de ticket concerné
    if poste_id.isdigit():
        qs = qs.filter(poste_id=poste_id)
    if statut in StatutPermutation.values:
        qs = qs.filter(statut=statut)
    permutations = list(qs[:2000])  # Liste filtrable en Python (les plages multiples sont dans le détail)
    if ticket.isdigit():  # Filtre « n° de ticket concerné » : toutes couleurs, côtés réveillé et tué
        n = int(ticket)
        permutations = [p for p in permutations if any(x <= n <= y for _c, x, y in p.plages_reveil + p.plages_tue)]
    permutations = permutations[:300]
    return render(request, 'inventaire/permutation_historique.html', {
        'permutations': permutations, 'postes': get_postes_accessibles(user, type_poste='peage').order_by('nom'),
        'poste_id': poste_id, 'statut': statut, 'ticket': ticket, 'title': 'Historique des permutations'})


@login_required
@require_POST
def permutation_annuler(request, pk):
    """Annule une permutation (échange inverse) avec motif obligatoire."""
    if not ps.peut_permuter(request.user):
        return _refuser(request)
    perm = get_object_or_404(PermutationSeries, pk=pk)  # Permutation à annuler
    try:
        ps.annuler(perm, request.user, request.POST.get('motif_annulation', ''))
    except ps.PermutationError as exc:
        messages.error(request, str(exc))  # Impossible : séries modifiées depuis, motif manquant...
    else:
        try:
            log_user_action(request.user, "ANNULATION_PERMUTATION_SERIES",
                            f"Permutation #{perm.pk} annulée : {request.POST.get('motif_annulation', '')}", request)
        except Exception:
            logger.exception("Journalisation de l'annulation impossible")
        messages.success(request, f"Permutation #{perm.pk} annulée : les numéros sont revenus à leur état précédent.")
    return redirect('inventaire:permutation_historique')
