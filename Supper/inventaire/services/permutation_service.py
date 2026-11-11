# inventaire/services/permutation_service.py
# Service métier : permutation de tickets entre une plage à RÉVEILLER (vendue dans SUPPER) et une plage
# à TUER (en stock) d'un même poste. Les couleurs peuvent différer ; la valeur en FCFA doit être identique.
#
# Effet d'une permutation :
#   - plage réveillée (ex. jaune 10-20) : VENDU -> EN STOCK  (la vente est retirée de ces numéros)
#   - plage tuée      (ex. vert 30-40)  : EN STOCK -> VENDU  (la vente est reportée sur ces numéros,
#                                                             même recette et même date)
# Même nombre de tickets (donc même valeur à 500 FCFA/ticket) des deux côtés : le montant de la recette
# et le stock en FCFA ne changent pas, seule l'identité des numéros change. La plage réveillée peut couvrir
# plusieurs ventes (recettes) : la plage tuée est alors découpée dans l'ordre pour suivre chaque recette.

import datetime  # Dates du détail conservé
import re  # Lecture des plages "début-fin"
from django.db import transaction  # Atomicité : tout ou rien
from django.utils import timezone  # Horodatage

from inventaire.models import SerieTicket, DetailVenteTicket, StockEvent  # Modèles de stock
from inventaire.models_permutation import PermutationSeries, StatutPermutation  # Historique

MOTIF_MIN = 5  # Nombre minimal de caractères du motif (justification obligatoire)


class PermutationError(Exception):
    """Erreur métier : la permutation demandée est impossible (message lisible par l'utilisateur)."""


def lire_plage(texte):
    """Lit '10-20', '10 à 20' ou '15' (un seul ticket) et retourne (premier, dernier) ou None."""
    m = re.match(r'^\s*(\d+)\s*(?:[-–—]|à|a|au)?\s*(\d+)?\s*$', texte or '')  # Deux nombres séparés ou un seul
    if not m:
        return None  # Format non reconnu
    premier = int(m.group(1))  # Premier numéro
    dernier = int(m.group(2)) if m.group(2) else premier  # Dernier (égal au premier si un seul ticket)
    return premier, dernier


def peut_permuter(user):
    """Autorisés : administrateur, Service Informatique, Service Émissions et Recouvrement."""
    if not user or not user.is_authenticated:
        return False  # Anonyme refusé
    if user.is_superuser:
        return True  # Superutilisateur toujours autorisé
    return getattr(user, 'habilitation', None) in ('admin_principal', 'serv_info', 'serv_emission')


# ----------------------------------------------------------------------
# Outils sur les séries
# ----------------------------------------------------------------------
def _cloner(serie, premier, dernier):
    """Crée une copie de `serie` limitée à [premier, dernier] (mêmes attributs, même date de réception)."""
    copie = SerieTicket.objects.create(
        poste=serie.poste, couleur=serie.couleur, numero_premier=premier, numero_dernier=dernier,
        nombre_tickets=dernier - premier + 1, valeur_monetaire=(dernier - premier + 1) * 500,
        statut=serie.statut, type_entree=serie.type_entree, date_utilisation=serie.date_utilisation,
        reference_recette=serie.reference_recette, commentaire=serie.commentaire,
        responsable_reception=serie.responsable_reception, historique_source=serie.historique_source,
        poste_destination_transfert=serie.poste_destination_transfert)
    SerieTicket.objects.filter(pk=copie.pk).update(date_reception=serie.date_reception)  # Contourne auto_now_add
    return copie


def _isoler(serie, premier, dernier):
    """Découpe `serie` pour isoler [premier, dernier] dans une ligne à part et retourne cette ligne.
    Les morceaux avant/après gardent le statut et les attributs d'origine."""
    avant = (serie.numero_premier, premier - 1) if premier > serie.numero_premier else None  # Reste avant
    apres = (dernier + 1, serie.numero_dernier) if dernier < serie.numero_dernier else None  # Reste après
    if avant:
        _cloner(serie, *avant)  # Ligne du morceau avant
    if apres:
        _cloner(serie, *apres)  # Ligne du morceau après
    serie.numero_premier, serie.numero_dernier = premier, dernier  # La ligne d'origine devient la plage isolée
    serie.save()  # save() recalcule nombre de tickets et valeur
    return serie


def _signature(s):
    """Attributs qui doivent être identiques pour fusionner deux lignes voisines."""
    return (s.poste_id, s.couleur_id, s.statut, s.type_entree, s.historique_source_id,
            s.reference_recette_id, s.date_utilisation, s.poste_destination_transfert_id)


def _fusionner_voisins(serie):
    """Fusionne `serie` avec ses voisines contiguës de même nature (évite de fragmenter le stock)."""
    continuer = True  # On répète tant qu'une fusion est possible
    while continuer:
        continuer = False
        base = SerieTicket.objects.filter(poste=serie.poste, couleur=serie.couleur).exclude(pk=serie.pk)
        precedente = base.filter(numero_dernier=serie.numero_premier - 1).first()  # Voisine de gauche
        suivante = base.filter(numero_premier=serie.numero_dernier + 1).first()  # Voisine de droite
        if precedente and _signature(precedente) == _signature(serie):
            serie.numero_premier = precedente.numero_premier  # Étend vers la gauche
            precedente.delete()  # Supprime la ligne absorbée
            serie.save()
            continuer = True
        elif suivante and _signature(suivante) == _signature(serie):
            serie.numero_dernier = suivante.numero_dernier  # Étend vers la droite
            suivante.delete()  # Supprime la ligne absorbée
            serie.save()
            continuer = True
    return serie


def _maj_details_vente(recette, couleur_a, a, couleur_b, b):
    """Dans le détail de vente de la recette, la plage `a` (couleur_a) est remplacée par `b` (couleur_b).
    Retourne True si au moins une ligne de détail a été modifiée."""
    if recette is None:
        return False  # Pas de recette : rien à mettre à jour
    lignes = list(recette.details_ventes_tickets.order_by('ordre'))  # Détail actuel, dans l'ordre de saisie
    nouvelles, insere, modifie = [], False, False  # Nouvelle liste (couleur_id, premier, dernier)
    for l in lignes:
        if l.couleur_id != couleur_a.id or l.numero_dernier < a[0] or l.numero_premier > a[1]:
            nouvelles.append((l.couleur_id, l.numero_premier, l.numero_dernier))  # Ligne non concernée
            continue
        modifie = True  # La ligne chevauche la plage retirée
        if l.numero_premier < a[0]:
            nouvelles.append((l.couleur_id, l.numero_premier, a[0] - 1))  # Partie avant la plage retirée
        if not insere:
            nouvelles.append((couleur_b.id, b[0], b[1]))  # La plage réellement vendue prend la place
            insere = True
        if l.numero_dernier > a[1]:
            nouvelles.append((l.couleur_id, a[1] + 1, l.numero_dernier))  # Partie après la plage retirée
    if not modifie:
        return False  # Aucune ligne ne contenait la plage : détail laissé tel quel
    recette.details_ventes_tickets.all().delete()  # On recrée le détail complet de la recette
    for ordre, (c, p, d) in enumerate(nouvelles, start=1):
        DetailVenteTicket.objects.create(recette=recette, couleur_id=c, numero_premier=p,
                                         numero_dernier=d, ordre=ordre)  # save() calcule nombre et montant
    return True


# ----------------------------------------------------------------------
# Validation (aperçu) et exécution
# ----------------------------------------------------------------------
def _segments(poste, couleur, statut, premier, dernier, verrou=False):
    """Découpe [premier, dernier] en segments (ligne, p, d) tous au `statut` demandé dans ce poste/couleur.
    Retourne None si la plage n'est pas entièrement couverte (au moins un ticket n'a pas ce statut)."""
    qs = SerieTicket.objects.filter(poste=poste, couleur=couleur, statut=statut,
                                    numero_premier__lte=dernier, numero_dernier__gte=premier)
    if verrou:
        qs = qs.select_for_update()  # Verrou de ligne pendant l'exécution
    courant, segments = premier, []  # `courant` = prochain ticket à couvrir
    for ligne in qs.select_related('reference_recette').order_by('numero_premier'):
        if ligne.numero_premier > courant:
            return None  # Trou : des tickets ne sont pas à ce statut
        p, d = max(courant, ligne.numero_premier), min(dernier, ligne.numero_dernier)  # Partie de la ligne utile
        if d >= p:
            segments.append((ligne, p, d))
            courant = d + 1
        if courant > dernier:
            break  # Plage entièrement couverte
    return segments if courant > dernier else None


def previsualiser(poste, reveil, tue, verrou=False):
    """Vérifie une permutation sans rien modifier.
    reveil = (couleur, premier, dernier) : tickets vendus dans SUPPER à REMETTRE EN STOCK ;
    tue    = (couleur, premier, dernier) : tickets en stock à PASSER EN VENDU.
    Retourne {'erreurs': [...]} ou {'erreurs': [], 'paires': [...], 'nombre', 'montant'}."""
    if not reveil or not tue:
        return {'erreurs': ["Indiquez les deux plages (ex. 10-20 et 30-40)."]}
    (ca, a1, a2), (cb, b1, b2) = reveil, tue  # Dépaquetage des plages
    if a1 > a2 or b1 > b2 or min(a1, b1) < 1:
        return {'erreurs': ["Chaque plage doit aller d'un numéro à un numéro supérieur ou égal (≥ 1)."]}
    na, nb = a2 - a1 + 1, b2 - b1 + 1  # Nombre de tickets de chaque plage
    erreurs = []
    if na != nb:  # Même valeur monétaire exigée (500 FCFA par ticket)
        erreurs.append(f"Les deux plages doivent avoir la même valeur : {na * 500:,} FCFA ({na} tickets) à réveiller "
                       f"contre {nb * 500:,} FCFA ({nb} tickets) à tuer.".replace(',', ' '))
    if ca.pk == cb.pk and not (a2 < b1 or b2 < a1):
        erreurs.append("Les deux plages se chevauchent.")
    seg_a = _segments(poste, ca, 'vendu', a1, a2, verrou)  # Segments vendus à réveiller
    seg_b = _segments(poste, cb, 'stock', b1, b2, verrou)  # Segments en stock à tuer
    if seg_a is None:
        erreurs.append(f"Les tickets {ca} {a1} à {a2} ne sont pas tous « vendus » dans SUPPER pour ce poste.")
    if seg_b is None:
        erreurs.append(f"Les tickets {cb} {b1} à {b2} ne sont pas tous « en stock » dans ce poste.")
    if erreurs:
        return {'erreurs': erreurs}
    paires, i, j = [], 0, 0  # Appariement séquentiel des segments de même longueur
    a_list, b_list = [list(x) for x in seg_a], [list(x) for x in seg_b]  # Copies modifiables [ligne, p, d]
    while i < len(a_list) and j < len(b_list):
        la, pa, da = a_list[i]
        lb, pb, db = b_list[j]
        n = min(da - pa + 1, db - pb + 1)  # Taille du morceau commun
        recette = la.reference_recette  # Recette de la vente déclarée
        date_vente = recette.date if recette else la.date_utilisation
        if date_vente is None:
            return {'erreurs': [f"La vente des tickets {ca} {pa}-{pa + n - 1} n'a ni recette ni date : "
                                f"permutation impossible."]}
        paires.append({'couleur_reveil': ca, 'a': (pa, pa + n - 1), 'couleur_tue': cb, 'b': (pb, pb + n - 1),
                       'recette': recette, 'date': date_vente, 'n': n})
        a_list[i][1] += n  # Avance dans le segment vendu
        b_list[j][1] += n  # Avance dans le segment en stock
        if a_list[i][1] > da:
            i += 1  # Segment vendu épuisé
        if b_list[j][1] > db:
            j += 1  # Segment en stock épuisé
    return {'erreurs': [], 'paires': paires, 'nombre': na, 'montant': na * 500}


def _trouver(poste, couleur, statut, p, d):
    """Ligne de série (verrouillée) qui contient entièrement [p, d] avec ce statut."""
    return SerieTicket.objects.select_for_update().filter(
        poste=poste, couleur=couleur, statut=statut, numero_premier__lte=p, numero_dernier__gte=d).first()


def _appliquer_paires(poste, paires):
    """Applique les échanges (à appeler dans une transaction). Retourne True si le détail de vente a été mis à jour."""
    details_maj, touchees = False, []  # Suivi des lignes à fusionner à la fin
    for pr in paires:
        ca, cb, a, b = pr['couleur_reveil'], pr['couleur_tue'], pr['a'], pr['b']
        ligne_a = _trouver(poste, ca, 'vendu', *a)  # Ligne vendue contenant le morceau à réveiller
        ligne_b = _trouver(poste, cb, 'stock', *b)  # Ligne en stock contenant le morceau à tuer
        if ligne_a is None or ligne_b is None:
            raise PermutationError("Le stock a changé pendant l'opération : réessayez.")
        ra = _isoler(ligne_a, *a)  # Morceau réveillé isolé
        ra.statut, ra.date_utilisation, ra.reference_recette = 'stock', None, None  # Vendu -> en stock
        ra.save()
        rb = _isoler(_trouver(poste, cb, 'stock', *b), *b)  # Morceau tué isolé (re-lu après le premier découpage)
        rb.statut, rb.date_utilisation, rb.reference_recette = 'vendu', pr['date'], pr['recette']  # Stock -> vendu
        rb.save()
        if _maj_details_vente(pr['recette'], ca, a, cb, b):
            details_maj = True  # Détail de vente de la recette mis à jour
        touchees += [(ca, a), (cb, b)]
    for couleur, (p, d) in touchees:  # Évite la fragmentation du stock et des ventes
        ligne = SerieTicket.objects.filter(poste=poste, couleur=couleur, numero_premier__lte=p,
                                           numero_dernier__gte=d).first()
        if ligne:
            _fusionner_voisins(ligne)
    return details_maj


def _evenement_stock(poste, user, perm, libelle):
    """Trace la permutation dans l'historique des mouvements de stock (variation nulle)."""
    StockEvent.objects.create(
        poste=poste, event_type='PERMUTATION', event_datetime=timezone.now(), montant_variation=0,
        nombre_tickets_variation=0, stock_resultant=0, tickets_resultants=0,  # Recalculés par StockEvent.save()
        effectue_par=user, reference_id=str(perm.pk), reference_type='PermutationSeries',
        metadata={'permutation_id': perm.pk, 'nombre_tickets': perm.nombre_tickets, 'valeur': perm.montant,
                  'reveil': {'couleur': str(perm.couleur_reveil), 'plage': [perm.reveil_premier, perm.reveil_dernier]},
                  'tue': {'couleur': str(perm.couleur_tue), 'plage': [perm.tue_premier, perm.tue_dernier]}},
        commentaire=libelle)


def _paires_json(paires):
    """Sérialise les paires pour les conserver dans l'historique (JSON)."""
    return [{'couleur_reveil': p['couleur_reveil'].pk, 'a': list(p['a']), 'couleur_tue': p['couleur_tue'].pk,
             'b': list(p['b']), 'recette_id': p['recette'].pk if p['recette'] else None,
             'date': p['date'].isoformat(), 'n': p['n']} for p in paires]


@transaction.atomic
def executer(poste, reveil, tue, motif, user):
    """Exécute une permutation et l'enregistre (historique + mouvement de stock). Retourne la PermutationSeries."""
    if len((motif or '').strip()) < MOTIF_MIN:
        raise PermutationError("Le motif de la permutation est obligatoire.")
    prev = previsualiser(poste, reveil, tue, verrou=True)  # Re-validation sous verrou
    if prev['erreurs']:
        raise PermutationError(' '.join(prev['erreurs']))
    details_maj = _appliquer_paires(poste, prev['paires'])  # Échange des statuts
    premiere = prev['paires'][0]  # Recette et date de référence de l'historique
    perm = PermutationSeries.objects.create(
        poste=poste, couleur_reveil=reveil[0], reveil_premier=reveil[1], reveil_dernier=reveil[2],
        couleur_tue=tue[0], tue_premier=tue[1], tue_dernier=tue[2], nombre_tickets=prev['nombre'],
        recette=premiere['recette'], date_vente=premiere['date'], details=_paires_json(prev['paires']),
        motif=motif.strip(), effectue_par=user)  # Historique de la permutation
    _evenement_stock(poste, user, perm,
                     f"Permutation : réveil {reveil[0]} {reveil[1]}-{reveil[2]} / tue {tue[0]} {tue[1]}-{tue[2]}"
                     f" : {motif.strip()}")
    perm.details_maj = details_maj  # Information pour le message à l'écran (non stockée)
    return perm


@transaction.atomic
def annuler(perm, user, motif):
    """Inverse une permutation : les tickets tués redeviennent en stock, les réveillés redeviennent vendus."""
    from inventaire.models import CouleurTicket, RecetteJournaliere  # Rechargement des objets du détail
    perm = PermutationSeries.objects.select_for_update().get(pk=perm.pk)  # Verrou sur la permutation
    if perm.statut != StatutPermutation.EFFECTUEE:
        raise PermutationError("Cette permutation est déjà annulée.")
    if len((motif or '').strip()) < MOTIF_MIN:
        raise PermutationError("Le motif de l'annulation est obligatoire.")
    inverses = []  # Paires inversées : ce qui avait été tué est réveillé, et inversement
    for d in perm.details:
        recette = RecetteJournaliere.objects.filter(pk=d['recette_id']).first() if d['recette_id'] else None
        inverses.append({'couleur_reveil': CouleurTicket.objects.get(pk=d['couleur_tue']), 'a': tuple(d['b']),
                         'couleur_tue': CouleurTicket.objects.get(pk=d['couleur_reveil']), 'b': tuple(d['a']),
                         'recette': recette, 'date': datetime.date.fromisoformat(d['date']), 'n': d['n']})
    for pr in inverses:  # Vérification avant toute modification
        seg_a = _segments(perm.poste, pr['couleur_reveil'], 'vendu', *pr['a'], verrou=True)
        seg_b = _segments(perm.poste, pr['couleur_tue'], 'stock', *pr['b'], verrou=True)
        rid = pr['recette'].pk if pr['recette'] else None
        if seg_a is None or seg_b is None or any(l.reference_recette_id != rid for l, _p, _d in seg_a):
            raise PermutationError("Annulation impossible : ces tickets ont été modifiés depuis la permutation.")
    _appliquer_paires(perm.poste, inverses)  # Échange inverse
    perm.statut, perm.annulee_par = StatutPermutation.ANNULEE, user  # Marque l'annulation
    perm.date_annulation, perm.motif_annulation = timezone.now(), motif.strip()
    perm.save()
    _evenement_stock(perm.poste, user, perm, f"ANNULATION de la permutation #{perm.pk} : {motif.strip()}")
    return perm


def historique_ticket(couleur, numero):
    """Permutations qui concernent un numéro de ticket donné (pour l'historique d'un ticket)."""
    from django.db.models import Q  # Filtre OU
    return PermutationSeries.objects.filter(
        Q(couleur_reveil=couleur, reveil_premier__lte=numero, reveil_dernier__gte=numero) |
        Q(couleur_tue=couleur, tue_premier__lte=numero, tue_dernier__gte=numero)).select_related('poste', 'effectue_par')
