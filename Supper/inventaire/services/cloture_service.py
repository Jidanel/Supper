# inventaire/services/cloture_service.py
# Fonctions pures de calcul pour la clôture mensuelle (sans accès base de données,
# donc facilement testables).

from decimal import Decimal, ROUND_HALF_UP  # Arithmétique exacte, arrondi commercial

PRIX_TICKET = 500  # Valeur d'un ticket en FCFA


def fusionner_intervalles(intervalles):
    """Fusionne des intervalles [(debut, fin)] contigus ou chevauchants.
    Ex: [(12,16),(17,20)] -> [(12,20)]. Les séries ne sont pas fusionnées en base,
    seulement à l'affichage."""
    tries = sorted((int(d), int(f)) for d, f in intervalles)  # Tri par début
    resultat = []  # Liste fusionnée
    for debut, fin in tries:
        if resultat and debut <= resultat[-1][1] + 1:  # Contigu ou chevauchant
            resultat[-1] = (resultat[-1][0], max(resultat[-1][1], fin))  # Étend le dernier
        else:
            resultat.append((debut, fin))  # Nouvel intervalle
    return resultat


def nombre_tickets(intervalles):
    """Nombre de tickets (bornes incluses) après fusion : fin - debut + 1."""
    return sum(f - d + 1 for d, f in fusionner_intervalles(intervalles))


def valeur_fcfa(intervalles):
    """Valeur en FCFA : nombre de tickets x 500."""
    return nombre_tickets(intervalles) * PRIX_TICKET


def libelle_intervalles(intervalles, langue='fr'):
    """Texte « de N°12 à N°20 et de N°30 à N°35 » (ou version anglaise)."""
    de, a, et = ('de', 'à', 'et') if langue == 'fr' else ('from', 'to', 'and')
    parts = [f"{de} N°{d} {a} N°{f}" for d, f in fusionner_intervalles(intervalles)]
    return f" {et} ".join(parts)


def taux_pct(numerateur, denominateur):
    """Pourcentage arrondi à 2 décimales (jamais tronqué). None si dénominateur nul
    (affiché « N/D »)."""
    if not denominateur:
        return None
    return (Decimal(numerateur) * 100 / Decimal(denominateur)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP)


def formater_pct(valeur):
    """Format français : 87,95 % ou N/D."""
    return 'N/D' if valeur is None else f"{valeur:.2f}".replace('.', ',') + '%'


def calculer_rar(emissions, rar_precedent, recouvre):
    """RAR du mois = émissions + RAR précédent - recouvré."""
    return Decimal(emissions) + Decimal(rar_precedent) - Decimal(recouvre)


# ----------------------------------------------------------------------
# Opérations ensemblistes sur des listes d'intervalles de tickets
# ----------------------------------------------------------------------
def soustraire_intervalles(a, b):
    """Intervalles de `a` privés de ceux de `b`.
    Ex: a=[(1,10)], b=[(4,6)] -> [(1,3),(7,10)]."""
    resultat = []
    retirer = fusionner_intervalles(b)  # Intervalles à retirer, triés et fusionnés
    for debut, fin in fusionner_intervalles(a):
        courant = debut  # Premier numéro encore non traité
        for r_debut, r_fin in retirer:
            if r_fin < courant or r_debut > fin:
                continue  # Pas de chevauchement
            if r_debut > courant:
                resultat.append((courant, r_debut - 1))  # Partie conservée avant le retrait
            courant = max(courant, r_fin + 1)  # On saute la partie retirée
        if courant <= fin:
            resultat.append((courant, fin))  # Reste après les retraits
    return resultat


def analyser_intervalles(texte):
    """Lit un texte libre « 11121973-11148800 » / « de N°… à N°… », un intervalle par ligne ou séparé par ;
    Retourne une liste [(debut, fin)] (lève ValueError si un intervalle est incohérent)."""
    import re
    resultat = []
    for ligne in re.split(r'[\n;]+', texte or ''):
        nombres = re.findall(r'\d+', ligne.replace(' ', ''))  # Chiffres seuls (espaces ignorés)
        if not nombres:
            continue
        if len(nombres) == 1:
            nombres = nombres * 2  # Un seul numéro = ticket unique
        debut, fin = int(nombres[0]), int(nombres[1])
        if fin < debut:
            raise ValueError(f"Intervalle invalide : {ligne.strip()}")
        resultat.append((debut, fin))
    return fusionner_intervalles(resultat)


MOIS_FR = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
           'août', 'septembre', 'octobre', 'novembre', 'décembre']  # Noms de mois


def nom_mois(mois, majuscules=False):
    """'2026-10' -> 'Octobre 2026'."""
    annee, num = mois.split('-')
    texte = f"{MOIS_FR[int(num) - 1].capitalize()} {annee}"
    return texte.upper() if majuscules else texte


def de_mois(mois):
    """'2026-10' -> "D'OCTOBRE 2026" ; '2026-03' -> 'DE MARS 2026' (élision devant voyelle)."""
    texte = nom_mois(mois, majuscules=True)
    return ("D'" if texte[0] in 'AEIOUÂÉÈ' else 'DE ') + texte


def date_longue(d):
    """date(2026,11,2) -> '02 Novembre 2026'."""
    return f"{d.day:02d} {MOIS_FR[d.month - 1].capitalize()} {d.year}"
