# inventaire/services_ca.py
# ===================================================================
# SERVICE DE CALCUL - CHIFFRE D'AFFAIRES ESTIMÉ DES TRANSPORTEURS
#
# Ce fichier contient LA méthode de calcul. Il ne dépend pas des vues : il reçoit des
# données simples (listes, dictionnaires) et renvoie des résultats. Les fonctions de la
# section « ACCÈS BASE DE DONNÉES » en bas de fichier font le lien avec les modèles.
#
# MÉTHODE (résumée - la note complète est affichée à l'écran, page « Méthode de calcul ») :
#   1. On regroupe les passages d'un véhicule (plaque + agence) par SEMAINE (lundi→dimanche).
#   2. Pour chaque semaine, on déduit son TRAJET à partir des postes où il a été vu :
#        - un seul poste  : on prend la liaison la plus chère partant de ce poste ;
#        - plusieurs      : on prend le chemin le moins cher entre les deux postes les plus
#                           éloignés (somme des liaisons voisines, via le maillage).
#   3. Le véhicule garde son trajet de RÉFÉRENCE = le plus long (tarif le plus élevé)
#      des semaines observées dans la période.
#   4. CA de la semaine = tarif du trajet × places × 2 (aller-retour) × nombre de tours
#      (2 par semaine si le trajet traverse plus de 3 régions, sinon 4), × 5/3 pour un bus
#      climatisé.
#   5. CA de la période = CA de la semaine × (nombre de jours de la période ÷ 7).
# ===================================================================

import heapq                                                     # file de priorité de l'algorithme de Dijkstra
import itertools                                                 # combinaisons de régions supplémentaires
import json                                                      # lecture du fichier de maillage
import os                                                        # chemin du fichier de maillage
import re                                                        # nettoyage des noms
import unicodedata                                               # suppression des accents
from collections import Counter, defaultdict                     # comptages / regroupements
from decimal import Decimal, ROUND_HALF_UP                       # arithmétique exacte

# Fichier de données livré avec l'application (88 liaisons, 63 postes)
FICHIER_MAILLAGE = os.path.join(os.path.dirname(__file__), 'data', 'maillage_postes.json')


# ===================================================================
# 1. OUTILS DE NOMS (rapprocher le maillage des postes SUPPER)
# ===================================================================

def cle_nom_poste(nom):
    """Clé de comparaison : minuscules, sans accents ni ponctuation ni espaces."""
    texte = unicodedata.normalize('NFKD', str(nom or ''))           # sépare lettres et accents
    texte = ''.join(c for c in texte if not unicodedata.combining(c))   # retire les accents
    return re.sub(r'[^a-z0-9]', '', texte.lower())                  # ne garde que lettres et chiffres


def variantes_cles(nom):
    """
    Clés possibles d'un nom : complet, sans parenthèse, et contenu de la parenthèse.
    « Okoa-Maria (Mbankomo) » -> {okoamariambankomo, okoamaria, mbankomo}
    """
    cles = {cle_nom_poste(nom)}                                     # nom complet
    sans = re.sub(r'\(.*?\)', '', str(nom or ''))                   # nom sans la parenthèse
    cles.add(cle_nom_poste(sans))
    for dedans in re.findall(r'\((.*?)\)', str(nom or '')):         # contenu de chaque parenthèse
        cles.add(cle_nom_poste(dedans))
    cles.discard('')                                                # jamais de clé vide
    return cles


# ===================================================================
# 2. LE RÉSEAU (graphe des postes) ET LE CALCUL DE TRAJET
# ===================================================================

class Reseau:
    """
    Graphe non orienté : sommets = postes du maillage, arêtes = liaisons avec tarif.
    adj[a][b] = tarif par passager entre a et b (sens simple).
    """

    def __init__(self, liaisons, regions, noms, par_regions=True):
        # liaisons : itérable de (id_a, id_b, tarif) ; regions/noms : {id: texte}
        self.adj = defaultdict(dict)                                # voisins de chaque poste
        for a, b, tarif in liaisons:
            # Si deux tarifs existent pour la même paire, on garde le plus faible (règle du document)
            ancien = self.adj[a].get(b)
            valeur = tarif if ancien is None else min(ancien, tarif)
            self.adj[a][b] = valeur
            self.adj[b][a] = valeur
        self.regions = dict(regions)                                # région de chaque poste
        self.noms = dict(noms)                                      # nom de chaque poste
        self.par_regions = par_regions                              # chemin limité aux régions des 2 postes ?
        self._cache = {}                                            # résultats de Dijkstra déjà calculés
        self._routes = {}                                           # routes (a, b) déjà calculées

    def _dijkstra(self, source, autorises=None):
        """
        Plus courts chemins (en tarif cumulé) depuis 'source'.
        autorises : ensemble de régions utilisables (None = toutes).
        """
        cle = (source, autorises)                                   # autorises est un frozenset (hachable)
        if cle in self._cache:                                      # déjà calculé : on réutilise
            return self._cache[cle]
        dist = {source: 0}                                          # tarif cumulé minimal connu
        prec = {}                                                   # prédécesseur sur le meilleur chemin
        file = [(0, source)]                                        # file de priorité (tarif, poste)
        while file:
            d, u = heapq.heappop(file)                              # poste le moins cher à explorer
            if d > dist.get(u, float('inf')):                       # entrée périmée : on ignore
                continue
            for v, tarif in self.adj.get(u, {}).items():            # chaque voisin de u
                if autorises is not None and self.regions.get(v) not in autorises:
                    continue                                        # poste d'une région non autorisée
                nd = d + tarif                                      # tarif cumulé en passant par u
                if nd < dist.get(v, float('inf')):                  # meilleur chemin trouvé
                    dist[v] = nd
                    prec[v] = u
                    heapq.heappush(file, (nd, v))
        self._cache[cle] = (dist, prec)                             # mémorisation
        return dist, prec

    def chemin(self, a, b, autorises=None):
        """Liste ordonnée des postes de a à b sur le chemin le moins cher (a et b inclus)."""
        _dist, prec = self._dijkstra(a, autorises)
        if b != a and b not in prec:                                # b non joignable depuis a
            return []
        noeuds = [b]
        while noeuds[-1] != a:                                      # on remonte de b vers a
            noeuds.append(prec[noeuds[-1]])
        return list(reversed(noeuds))

    def route(self, a, b):
        """
        Chemin entre deux postes : (tarif, liste des postes) ou None si non reliés.

        Si 'par_regions' est actif, on cherche d'abord un chemin qui n'utilise QUE les régions
        des deux postes. À défaut, on ajoute UNE région (la combinaison la moins chère), puis
        deux, etc. Une région supplémentaire n'est donc impliquée qu'en cas de nécessité.
        """
        cle = (a, b)                                                # le sens n'a pas d'importance pour le tarif
        if cle in self._routes:
            return self._routes[cle]
        if not self.par_regions:                                    # mode « chemin le moins cher partout »
            dist, _prec = self._dijkstra(a)
            res = (dist[b], self.chemin(a, b)) if b in dist else None
        else:
            base = {self.regions.get(a), self.regions.get(b)}       # régions des deux extrémités
            autres = sorted({r for r in self.regions.values() if r} - base)
            res = None
            for k in range(len(autres) + 1):                        # 0, 1, 2... région(s) en plus
                meilleur = None
                for extra in itertools.combinations(autres, k):
                    autorises = frozenset(base | set(extra))
                    dist, _prec = self._dijkstra(a, autorises)
                    if b in dist and (meilleur is None or dist[b] < meilleur[0]):
                        meilleur = (dist[b], self.chemin(a, b, autorises))
                if meilleur:                                        # dès qu'un chemin existe, on s'arrête
                    res = meilleur
                    break
        self._routes[cle] = res                                     # mémorisation
        return res

    def trajet(self, postes):
        """
        Déduit le trajet d'un véhicule vu aux postes 'postes' (ids du maillage).
        Retourne un dict : tarif (sens simple, par passager), chemin (ids), regions, mode.
        mode = 'plusieurs' | 'seul' | 'sans_voisin' | 'non_relie'
        """
        postes = sorted(set(postes))                                # postes distincts, ordre stable
        if not postes:
            return None
        if len(postes) >= 2:                                        # --- cas de plusieurs postes ---
            meilleur = None                                         # (tarif, nb_postes_chemin, chemin)
            for i, a in enumerate(postes):
                for b in postes[i + 1:]:
                    r = self.route(a, b)                            # chemin (limité aux régions si activé)
                    if r:
                        cand = (r[0], len(r[1]), r[1])
                        if meilleur is None or cand[:2] > meilleur[:2]:   # plus cher, puis plus long
                            meilleur = cand
            if meilleur is not None:                                # le plus long trajet entre deux postes vus
                return self._resultat(meilleur[0], meilleur[2], 'plusieurs')
            # Aucun couple relié (postes dans des zones non reliées) : on retombe sur le cas « seul »
        # --- cas d'un seul poste (ou postes non reliés entre eux) ---
        meilleur = None
        for p in postes:
            for v, tarif in self.adj.get(p, {}).items():            # liaisons partant du poste
                if meilleur is None or tarif > meilleur[0]:         # la plus chère = le voisin le plus éloigné
                    meilleur = (tarif, p, v)
        if meilleur is None:                                        # poste sans aucun voisin renseigné
            return self._resultat(0, [postes[0]], 'sans_voisin')
        tarif, p, v = meilleur
        res = self._resultat(tarif, [p, v], 'seul' if len(postes) == 1 else 'non_relie')
        # Postes voisins que le véhicule a pu rejoindre depuis le poste où il a été vu (du moins cher au plus cher)
        res['poste_vu'] = self.noms.get(p, str(p))
        res['voisins'] = sorted(((self.noms.get(x, str(x)), t) for x, t in self.adj.get(p, {}).items()),
                                key=lambda c: (c[1], c[0]))
        return res

    def _resultat(self, tarif, chemin, mode):
        """Assemble le dictionnaire de résultat (noms et régions traversées)."""
        regions = []                                                # régions dans l'ordre de traversée
        for p in chemin:
            r = self.regions.get(p, '')
            if r and r not in regions:
                regions.append(r)
        return {
            'tarif': tarif,                                         # FCFA par passager, sens simple
            'chemin': list(chemin),                                 # ids des postes
            'chemin_noms': [self.noms.get(p, str(p)) for p in chemin],
            'regions': regions,
            'nb_regions': len(regions),
            'mode': mode,
        }


# ===================================================================
# 3. ESTIMATION D'UN VÉHICULE PUIS D'UNE PÉRIODE
# ===================================================================

def arrondi(valeur):
    """Arrondi commercial à l'unité (FCFA)."""
    return int(Decimal(valeur).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def nombre_tours(nb_regions, params):
    """Aller-retour par semaine : trajet long (> seuil de régions) -> peu de tours, sinon plus."""
    return params['tours_longs'] if nb_regions > params['seuil_regions'] else params['tours_courts']


def calculer_ca(observations, reseau, params, debut, fin):
    """
    Calcule le chiffre d'affaires estimé de chaque véhicule sur la période [debut, fin].

    observations : itérable de tuples
        (plaque_normalisee, plaque_affichee, agence, code_type, date, id_poste_maillage ou None)
    params : dict {tours_longs, tours_courts, seuil_regions, majoration_clim, places{code: n}}
    Retourne (vehicules, agences, infos) - listes de dicts triées du plus fort CA au plus faible.
    """
    jours = (fin - debut).days + 1                                  # longueur de la période
    semaines_periode = Decimal(jours) / Decimal(7)                  # facteur d'extrapolation
    majoration = Decimal(str(params['majoration_clim']))            # ex. 0.6667

    # --- Regroupement : véhicule -> semaine -> postes vus ---
    postes_semaine = defaultdict(lambda: defaultdict(set))          # {clé véhicule: {semaine: {postes}}}
    types_vus = defaultdict(Counter)                                # type le plus fréquent par véhicule
    affichage = {}                                                  # plaque lisible par véhicule
    passages = Counter()                                            # nombre de passages par véhicule
    ignores = 0                                                     # passages à un poste hors maillage
    for plaque_n, plaque_a, agence, code_type, jour, id_maillage in observations:
        cle = (plaque_n, agence)                                    # un véhicule = plaque + agence
        passages[cle] += 1
        types_vus[cle][code_type] += 1
        affichage.setdefault(cle, plaque_a)
        if id_maillage is None:                                     # poste non relié au maillage
            ignores += 1
            continue
        annee, semaine, _jr = jour.isocalendar()                    # semaine ISO (lundi→dimanche)
        postes_semaine[cle][(annee, semaine)].add(id_maillage)

    vehicules = []
    for cle, par_semaine in postes_semaine.items():
        # Trajet de chaque semaine observée, puis trajet de référence = le plus coûteux
        trajets = [reseau.trajet(p) for p in par_semaine.values()]
        trajets = [t for t in trajets if t]
        if not trajets:
            continue
        ref = max(trajets, key=lambda t: (t['tarif'], len(t['chemin'])))
        code_type = types_vus[cle].most_common(1)[0][0]             # type le plus fréquent
        places = params['places'].get(code_type, 0)                 # borne inférieure des places
        tours = nombre_tours(ref['nb_regions'], params)             # 2 ou 4 selon la longueur
        base = Decimal(ref['tarif']) * places * 2 * tours           # tarif × places × aller-retour × tours
        if code_type == 'bus_clim':                                 # bus climatisé : + 2/3 du tarif
            base = base * (Decimal(1) + majoration)
        ca_semaine = arrondi(base)
        vehicules.append({
            'plaque': affichage[cle], 'plaque_normalisee': cle[0], 'agence': cle[1],
            'code_type': code_type, 'places': places,
            'passages': passages[cle], 'semaines_vues': len(par_semaine),
            'tarif': ref['tarif'], 'chemin_noms': ref['chemin_noms'],
            'regions': ref['regions'], 'nb_regions': ref['nb_regions'],
            'mode': ref['mode'], 'tours': tours,
            'poste_vu': ref.get('poste_vu', ''), 'voisins': ref.get('voisins', []),
            'clim': code_type == 'bus_clim',
            'ca_semaine': ca_semaine,
            'ca_periode': arrondi(base * semaines_periode),         # extrapolation à la période
        })
    vehicules.sort(key=lambda v: (-v['ca_periode'], v['agence'], v['plaque']))

    # --- Totaux par agence ---
    agences = {}
    for v in vehicules:
        a = agences.setdefault(v['agence'], {'agence': v['agence'], 'vehicules': 0,
                                             'ca_semaine': 0, 'ca_periode': 0, 'passages': 0})
        a['vehicules'] += 1
        a['ca_semaine'] += v['ca_semaine']
        a['ca_periode'] += v['ca_periode']
        a['passages'] += v['passages']
    liste_agences = sorted(agences.values(), key=lambda a: (-a['ca_periode'], a['agence']))

    infos = {'jours': jours, 'semaines': float(round(semaines_periode, 2)),
             'passages_ignores': ignores,
             'sans_trajet': len([c for c in passages if c not in postes_semaine])}
    return vehicules, liste_agences, infos


# ===================================================================
# 4. ACCÈS BASE DE DONNÉES (import local pour garder le haut du fichier sans Django)
# ===================================================================

def charger_maillage_depuis_fichier():
    """
    Crée / met à jour PosteMaillage et LiaisonMaillage à partir du fichier JSON,
    puis relie automatiquement chaque poste du maillage à un poste SUPPER de même nom.
    Opération répétable sans doublon. Retourne (postes, liaisons, reliés).
    """
    from django.db import transaction                               # import local : évite Django à l'import du module
    from inventaire.models_ca import PosteMaillage, LiaisonMaillage
    with open(FICHIER_MAILLAGE, encoding='utf-8') as f:             # lecture du fichier livré
        data = json.load(f)
    with transaction.atomic():                                      # tout ou rien
        par_nom = {}
        for p in data['postes']:                                    # postes (créés ou mis à jour)
            obj, _c = PosteMaillage.objects.update_or_create(
                nom=p['nom'], defaults={'region': p['region']})
            par_nom[p['nom']] = obj
        for l in data['liaisons']:                                  # liaisons (créées ou tarif mis à jour)
            a, b = par_nom[l['a']], par_nom[l['b']]
            if a.id > b.id:
                a, b = b, a                                         # même rangement que LiaisonMaillage.save
            LiaisonMaillage.objects.update_or_create(
                poste_a=a, poste_b=b, defaults={'tarif': l['tarif']})
        relies = relier_postes_automatiquement()                    # rapprochement par les noms
    return len(data['postes']), len(data['liaisons']), relies


def relier_postes_automatiquement():
    """
    Relie les postes du maillage non encore reliés à un poste de péage SUPPER de même nom
    (comparaison sans accent/ponctuation, avec ou sans partie entre parenthèses).
    Un rapprochement ambigu (plusieurs postes possibles) est laissé à l'administrateur.
    """
    from accounts.models import Poste
    from inventaire.models_ca import PosteMaillage
    index = defaultdict(set)                                        # clé -> ids de postes SUPPER
    for poste in Poste.objects.filter(type='peage'):
        for cle in variantes_cles(poste.nom):
            index[cle].add(poste.id)
    deja = set(PosteMaillage.objects.exclude(poste=None).values_list('poste_id', flat=True))
    nb = 0
    for pm in PosteMaillage.objects.filter(poste=None):
        candidats = set()
        for cle in variantes_cles(pm.nom):
            candidats |= index.get(cle, set())
        candidats -= deja                                           # un poste SUPPER ne sert qu'une fois
        if len(candidats) == 1:                                     # correspondance certaine
            pm.poste_id = candidats.pop()
            pm.save(update_fields=['poste'])
            deja.add(pm.poste_id)
            nb += 1
    return nb


def zones_coupees(reseau):
    """
    Diagnostic : pour chaque région, les groupes de postes SANS liaison entre eux à l'intérieur
    de la région (ex. Centre en deux morceaux). Retourne [(région, [[noms du groupe 1], [groupe 2]])]
    pour les seules régions comptant plusieurs groupes, plus la liste des postes sans voisin.
    """
    par_region = defaultdict(list)                                  # région -> postes
    for pid, region in reseau.regions.items():
        par_region[region].append(pid)
    resultat = []
    for region, ids in sorted(par_region.items()):
        restants, groupes = set(ids), []
        while restants:                                             # parcours en profondeur dans la région
            pile, groupe = [restants.pop()], set()
            while pile:
                x = pile.pop()
                if x in groupe:
                    continue
                groupe.add(x)
                restants.discard(x)
                pile.extend(v for v in reseau.adj.get(x, {}) if reseau.regions.get(v) == region)
            groupes.append(sorted(reseau.noms[i] for i in groupe))
        if len(groupes) > 1:                                        # région en plusieurs morceaux
            resultat.append((region, sorted(groupes, key=lambda g: (-len(g), g))))
    return resultat


def construire_reseau():
    """Construit le Reseau en mémoire depuis la base."""
    from inventaire.models_ca import PosteMaillage, LiaisonMaillage, ParametresCA
    postes = list(PosteMaillage.objects.all())
    liaisons = LiaisonMaillage.objects.values_list('poste_a_id', 'poste_b_id', 'tarif')
    return Reseau(liaisons, {p.id: p.region for p in postes}, {p.id: p.nom for p in postes},
                  par_regions=ParametresCA.charger().routage_regions)


def assurer_maillage():
    """
    Précharge le maillage du document la PREMIÈRE fois (tables vides). Ensuite on n'y touche
    plus : les modifications faites sur l'écran des liaisons ne sont jamais écrasées.
    """
    from inventaire.models_ca import PosteMaillage
    if not PosteMaillage.objects.exists():
        charger_maillage_depuis_fichier()


def parametres_en_dict():
    """Paramètres enregistrés sous forme de dict simple pour calculer_ca."""
    from inventaire.models_ca import ParametresCA
    p = ParametresCA.charger()
    return {'tours_longs': p.tours_longs, 'tours_courts': p.tours_courts,
            'seuil_regions': p.seuil_regions, 'majoration_clim': p.majoration_clim,
            'places': p.places_par_type()}
