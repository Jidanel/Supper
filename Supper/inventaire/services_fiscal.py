# inventaire/services_fiscal.py
# ===================================================================
# SERVICE - SITUATION FISCALE RÉELLE DES AGENCES DE TRANSPORT
#
# Ce module regroupe la logique (sans vue ni gabarit) pour :
#   1. comparer la catégorie ACTUELLE d'une agence (DGE / CIME / CFLP, saisie à la main)
#      avec la structure ESTIMÉE par le calcul du chiffre d'affaires ;
#   2. ajouter ces informations à la liste des agences du calcul du CA ;
#   3. lire un fichier d'import (CSV ou Excel) et en déduire les lignes à appliquer ;
#   4. retrouver l'agence correspondant à un nom écrit à la main.
# ===================================================================

import csv                                                    # lecture/écriture CSV
import io                                                     # lecture d'un fichier en mémoire
import re                                                     # expressions régulières (nettoyage)
import unicodedata                                            # suppression des accents

from inventaire.models_transporteurs import (                 # modèles et fonctions de normalisation
    AgenceTransport, CategorieFiscale, cle_unicite_agence, normaliser_niu, niu_valide,
)
from inventaire.services_ca import RANG_STRUCTURE            # CFLP < CIME < DGE (même échelle que le calcul du CA)

# Statuts de la comparaison « catégorie actuelle » / « structure estimée par le CA »
CONFORME = 'conforme'                                         # l'agence est déjà dans la bonne structure
SOUS_CLASSEE = 'sous'                                         # elle est dans une structure INFÉRIEURE à celle estimée
SUR_CLASSEE = 'sur'                                           # elle est dans une structure SUPÉRIEURE à celle estimée
INCONNU = 'inconnu'                                           # catégorie actuelle non renseignée
NON_COMPARABLE = 'autre'                                      # centre hors DGE/CIME/CFLP (ex. CSIPLI) : pas de comparaison

# Mots de forme juridique ignorés quand le nom exact n'est pas trouvé (SARL, SA, LTD...)
FORMES_JURIDIQUES = {'SARL', 'SA', 'SUARL', 'LTD', 'LIMITED'}


def comparer(structure_estimee, categorie_actuelle):
    """
    Compare la structure estimée (calcul du CA) et la catégorie actuelle (saisie).
    Retourne {'statut': ..., 'libelle': texte court, 'css': classe de couleur Bootstrap}.
    """
    if not categorie_actuelle:                                # rien de saisi
        return {'statut': INCONNU, 'libelle': 'Non renseignée', 'css': 'secondary'}
    if categorie_actuelle not in RANG_STRUCTURE:              # « AUTRE » : on ne peut pas comparer
        return {'statut': NON_COMPARABLE, 'libelle': 'Centre hors DGE/CIME/CFLP', 'css': 'secondary'}
    rang_reel = RANG_STRUCTURE[categorie_actuelle]            # rang de la catégorie actuelle
    rang_estime = RANG_STRUCTURE.get(structure_estimee, 0)    # rang de la structure estimée
    if rang_reel == rang_estime:                              # même structure
        return {'statut': CONFORME, 'libelle': 'Conforme', 'css': 'success'}
    if rang_reel < rang_estime:                               # actuellement trop bas : l'agence devrait être suivie plus haut
        return {'statut': SOUS_CLASSEE, 'libelle': f'Devrait être en {structure_estimee}', 'css': 'danger'}
    return {'statut': SUR_CLASSEE, 'libelle': f'Estimée plus basse ({structure_estimee})', 'css': 'warning'}


def situation_depuis_agence(agence):
    """Dictionnaire simple de la situation fiscale d'une agence (None accepté : agence absente de l'annuaire)."""
    if agence is None:                                        # agence vue sur la route mais absente de l'annuaire
        return {'trouvee': False, 'niu': '', 'sans_niu': False, 'categorie': '', 'centre': '',
                'regime': '', 'a_verifier': False, 'remarque': '', 'renseignee': False}
    return {'trouvee': True, 'pk': agence.pk, 'niu': agence.niu, 'sans_niu': agence.sans_niu,
            'categorie': agence.categorie_actuelle, 'centre': agence.centre_actuel,
            'regime': agence.regime, 'a_verifier': agence.a_verifier, 'remarque': agence.remarque_fiscale,
            'renseignee': agence.situation_fiscale_renseignee}


def ajouter_situation_fiscale(agences_ca):
    """
    Ajoute à chaque dict d'agence du calcul du CA la clé 'fiscal' (situation saisie + comparaison).
    La liaison se fait par la clé d'unicité du nom (VOYAGE = VOYAGES, sans accent...).
    Retourne un récapitulatif {statut: nombre} pour l'affichage.
    """
    annuaire = {a.cle_unicite: a for a in AgenceTransport.objects.all()}   # une seule requête pour toutes les agences
    recap = {CONFORME: 0, SOUS_CLASSEE: 0, SUR_CLASSEE: 0, INCONNU: 0, NON_COMPARABLE: 0}   # compteurs
    for a in agences_ca:                                      # chaque agence du calcul
        situation = situation_depuis_agence(annuaire.get(cle_unicite_agence(a['agence'])))   # fiche de l'annuaire
        situation['comparaison'] = comparer(a.get('structure'), situation['categorie'])      # écart avec l'estimation
        a['fiscal'] = situation                               # on attache le tout à l'agence
        recap[situation['comparaison']['statut']] += 1        # on compte
    return recap


# ===================================================================
# RETROUVER UNE AGENCE À PARTIR D'UN NOM ÉCRIT À LA MAIN
# ===================================================================

def _cle_sans_forme(nom):
    """Clé de comparaison sans les mots de forme juridique : « MEN TRAVEL SA » = « MEN TRAVEL »."""
    mots = [m for m in cle_unicite_agence(nom).split(' ') if m and m not in FORMES_JURIDIQUES]   # on retire SARL, SA...
    return ' '.join(mots)                                     # on recolle


def construire_index():
    """Prépare deux dictionnaires de recherche : par clé exacte et par clé sans forme juridique."""
    exact, lache = {}, {}                                     # clé -> agence ; clé lâche -> [agences]
    for a in AgenceTransport.objects.all():                   # toutes les agences de l'annuaire
        exact[a.cle_unicite] = a
        lache.setdefault(_cle_sans_forme(a.nom), []).append(a)
    return exact, lache


def trouver_agence(nom, index):
    """
    Retourne (agence, etat) avec etat = 'exacte' | 'approchee' | 'ambigue' | 'absente'.
    On cherche d'abord le nom exact, puis le nom sans forme juridique (s'il désigne une seule agence).
    """
    exact, lache = index                                      # les deux dictionnaires
    agence = exact.get(cle_unicite_agence(nom))               # 1) correspondance exacte
    if agence:
        return agence, 'exacte'
    candidates = lache.get(_cle_sans_forme(nom), [])          # 2) correspondance sans SARL/SA/LTD
    if len(candidates) == 1:
        return candidates[0], 'approchee'
    if len(candidates) > 1:                                   # plusieurs agences possibles : on ne devine pas
        return None, 'ambigue'
    return None, 'absente'


# ===================================================================
# LECTURE D'UN FICHIER D'IMPORT (CSV ou Excel)
# ===================================================================

# Noms d'en-têtes acceptés (sans accent, minuscules) -> champ interne
ENTETES = {
    'agence': 'agence', 'nom': 'agence', 'nom agence': 'agence', 'nom de l agence': 'agence',
    'niu': 'niu', 'nui': 'niu',
    'categorie': 'categorie', 'categorie actuelle': 'categorie', 'structure': 'categorie',
    'centre': 'centre', 'centre actuel': 'centre', 'centre des impots': 'centre',
    'regime': 'regime', 'regime d imposition': 'regime',
    'a verifier': 'a_verifier', 'verifier': 'a_verifier',
    'sans niu': 'sans_niu',
    'remarque': 'remarque', 'remarques': 'remarque', 'observation': 'remarque', 'observations': 'remarque',
}


def _simplifier(texte):
    """Minuscules, sans accent, ponctuation = espace (pour reconnaître les en-têtes)."""
    texte = unicodedata.normalize('NFD', str(texte or ''))    # sépare lettres et accents
    texte = ''.join(c for c in texte if unicodedata.category(c) != 'Mn')   # retire les accents
    return re.sub(r'[^a-z0-9]+', ' ', texte.lower()).strip()  # tout sauf lettres/chiffres -> espace


def _booleen(valeur):
    """Interprète 1/oui/yes/true/x comme vrai, tout le reste comme faux."""
    return _simplifier(valeur) in {'1', 'oui', 'o', 'yes', 'y', 'true', 'vrai', 'x'}


def deduire_categorie(categorie, centre):
    """
    Catégorie normalisée (DGE/CIME/CFLP/AUTRE ou '') à partir de la colonne catégorie, sinon du début du centre.
    Ex. « CIME Bamenda » -> CIME ; « CSIPLI Wouri » -> AUTRE ; « Moyenne entreprise » -> ''.
    """
    for source in (categorie, centre):                        # on essaie d'abord la catégorie, puis le centre
        mots = _simplifier(source).split(' ')                 # premiers mots en minuscules
        premier = mots[0].upper() if mots and mots[0] else ''
        if premier in ('DGE', 'CIME', 'CFLP'):
            return premier
        if premier in ('AUTRE', 'CSIPLI'):
            return CategorieFiscale.AUTRE
    return ''                                                 # rien de reconnu


def lire_fichier(fichier):
    """
    Lit un fichier .csv (séparateur ; ou ,) ou .xlsx et retourne (lignes, erreur).
    Chaque ligne est un dict {agence, niu, categorie, centre, regime, a_verifier, sans_niu, remarque}.
    """
    nom = (fichier.name or '').lower()                        # extension du fichier
    if nom.endswith('.xlsx'):                                 # --- Excel ---
        try:
            from openpyxl import load_workbook                # lecture Excel
            feuille = load_workbook(fichier, read_only=True, data_only=True).active   # première feuille
            matrice = [list(r) for r in feuille.iter_rows(values_only=True)]          # toutes les lignes
        except Exception as e:                                # fichier illisible
            return [], f"Fichier Excel illisible : {e}"
    elif nom.endswith('.csv'):                                # --- CSV ---
        brut = fichier.read()                                 # octets du fichier
        try:
            texte = brut.decode('utf-8-sig')                  # utf-8 (avec ou sans BOM)
        except UnicodeDecodeError:
            texte = brut.decode('cp1252', errors='replace')   # export Excel Windows
        premiere = texte.splitlines()[0] if texte.splitlines() else ''
        separateur = ';' if premiere.count(';') >= premiere.count(',') else ','   # Excel FR utilise ;
        matrice = list(csv.reader(io.StringIO(texte), delimiter=separateur))      # lignes du CSV
    else:
        return [], "Format non pris en charge : utilisez un fichier .csv ou .xlsx."
    if not matrice:
        return [], "Le fichier est vide."
    entetes = [ENTETES.get(_simplifier(c), '') for c in matrice[0]]   # champ interne de chaque colonne
    if 'agence' not in entetes:
        return [], "Colonne « agence » introuvable dans la première ligne."
    lignes = []                                               # résultat
    for brute in matrice[1:]:                                 # on saute la ligne d'en-têtes
        ligne = {champ: '' for champ in ENTETES.values()}     # toutes les clés présentes
        for i, valeur in enumerate(brute):                    # colonne par colonne
            if i < len(entetes) and entetes[i]:
                ligne[entetes[i]] = str(valeur if valeur is not None else '').strip()
        if not ligne['agence']:                               # ligne sans nom : ignorée
            continue
        ligne['a_verifier'] = _booleen(ligne['a_verifier'])   # texte -> booléen
        ligne['sans_niu'] = _booleen(ligne['sans_niu'])
        ligne['niu'] = normaliser_niu(ligne['niu'])           # NIU propre
        ligne['categorie'] = deduire_categorie(ligne['categorie'], ligne['centre'])   # DGE/CIME/CFLP/AUTRE
        lignes.append(ligne)
    return lignes, ''


def appliquer_ligne(agence, ligne, ecraser, utilisateur, maintenant):
    """
    Applique une ligne d'import à une agence. Par défaut on ne remplit QUE les champs vides ;
    avec ecraser=True les valeurs du fichier remplacent celles déjà saisies.
    Retourne (liste des champs modifiés, liste des conflits ignorés).
    """
    champs = {'niu': ligne['niu'], 'categorie_actuelle': ligne['categorie'], 'centre_actuel': ligne['centre'][:150],
              'regime': ligne['regime'][:60], 'remarque_fiscale': ligne['remarque'][:300]}   # valeur proposée par champ
    modifies, conflits = [], []                               # comptes rendus
    for champ, valeur in champs.items():
        if not valeur:                                        # le fichier ne dit rien : on ne touche pas
            continue
        actuel = getattr(agence, champ)                       # valeur déjà en base
        if actuel == valeur:                                  # identique : rien à faire
            continue
        if actuel and not ecraser:                            # déjà rempli et pas d'écrasement : conflit signalé
            conflits.append(champ)
            continue
        setattr(agence, champ, valeur)                        # on applique
        modifies.append(champ)
    if ligne['sans_niu'] and not agence.niu and not agence.sans_niu:   # « pas de NIU » confirmé par le fichier
        agence.sans_niu = True
        modifies.append('sans_niu')
    if ligne['a_verifier'] and not agence.a_verifier:         # le fichier demande un contrôle
        agence.a_verifier = True
        modifies.append('a_verifier')
    if modifies:                                              # trace de la modification
        agence.fiscal_modifie_par = utilisateur
        agence.fiscal_modifie_le = maintenant
    return modifies, conflits


def avertissement_niu(niu, agence_courante=None):
    """Texte d'avertissement si le NIU est mal formé ou déjà utilisé par une autre agence ; '' sinon."""
    niu = normaliser_niu(niu)                                 # forme propre
    if not niu:
        return ''
    if not niu_valide(niu):                                   # format M/P + 12 chiffres + lettre
        return f"Le NIU « {niu} » n'a pas la forme habituelle (lettre M ou P, 12 chiffres, une lettre)."
    doublons = AgenceTransport.objects.filter(niu=niu)        # même NIU ailleurs ?
    if agence_courante is not None:
        doublons = doublons.exclude(pk=agence_courante.pk)
    autre = doublons.first()
    if autre:
        return f"Le NIU « {niu} » est déjà utilisé par l'agence « {autre.nom} »."
    return ''
