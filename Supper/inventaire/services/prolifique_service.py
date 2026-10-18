# ===================================================================
# Supper/inventaire/services/prolifique_service.py
# SERVICE DE CALCUL : jour et heure les plus prolifiques (inventaires)  - V2
#
# Définitions métier :
#   - un "jour" prolifique  = un jour qui cumule beaucoup de véhicules
#                             (somme de tous les créneaux saisis ce jour-là) ;
#   - une "heure" prolifique = un créneau précis d'un jour précis
#                             (ex. "10h-11h le 14/03/2026") avec beaucoup de véhicules.
#
# Deux modes de restitution :
#   1) PLUSIEURS POSTES (ou tous) -> CLASSEMENT DES POSTES, chacun avec son
#      jour record et son heure record (et la date associée) ;
#   2) UN SEUL POSTE -> CLASSEMENT DES N MEILLEURS JOURS ou N MEILLEURES
#      HEURES (1er, 2e ... Ne) avec le jour associé à chaque heure.
#
# Service NON PERSISTÉ : calcul à la volée sur DetailInventairePeriode
# (aucune table, aucune migration, aucune désynchronisation possible).
# ===================================================================

from collections import defaultdict            # dictionnaires à valeur par défaut
from dataclasses import dataclass, field       # structures de résultat lisibles
from datetime import date                      # type des dates
from typing import Dict, List, Optional        # annotations de type

from django.db.models import Sum               # agrégation SQL

from inventaire.models import DetailInventairePeriode  # détail par créneau horaire


# -------------------------------------------------------------------
# STRUCTURES DE RÉSULTAT
# -------------------------------------------------------------------

@dataclass
class Record:
    """Un jour (creneau=None) ou une heure (date + créneau) avec son nombre de véhicules."""
    date: Optional[date] = None      # jour concerné
    creneau: Optional[str] = None    # ex. "10h-11h" ; None quand il s'agit d'un jour entier
    valeur: int = 0                  # véhicules comptés
    rang: int = 0                    # position dans le classement (1 = meilleur)
    pct: float = 0.0                 # valeur en % du 1er du classement (barre de progression)


@dataclass
class LignePoste:
    """Une ligne du classement des postes."""
    rang: int = 0                                   # position du poste
    poste_id: int = 0
    poste_nom: str = ""
    nb_inventaires: int = 0                         # jours inventoriés sur la période
    total_vehicules: int = 0                        # total de véhicules comptés sur la période
    jour_record: Optional[Record] = None            # meilleur jour du poste
    heure_record: Optional[Record] = None           # meilleure heure (date + créneau) du poste
    valeur: int = 0                                 # valeur utilisée pour le classement
    detail: str = ""                                # précision lisible (ex. "10h-11h, le 14/03/2026")
    pct: float = 0.0                                # valeur en % du 1er du classement (barre)


@dataclass
class Resultat:
    """Résultat complet d'une analyse."""
    date_debut: date
    date_fin: date
    critere: str = "jour"                           # "jour" ou "heure"
    classer_par: str = "record"                     # "record" ou "total"
    poste_unique: bool = False                      # True = un seul poste analysé
    poste_nom: str = ""                             # nom du poste si poste_unique
    nb_postes: int = 0                              # postes ayant au moins un inventaire
    nb_inventaires: int = 0                         # inventaires (poste + jour) pris en compte
    total_vehicules: int = 0                        # total de véhicules sur la période
    classement_postes: List[LignePoste] = field(default_factory=list)  # mode plusieurs postes
    top_jours: List[Record] = field(default_factory=list)              # mode un poste, critère jour
    top_heures: List[Record] = field(default_factory=list)             # mode un poste, critère heure
    repartition_heures: List[Dict] = field(default_factory=list)       # total par créneau (graphique)


# -------------------------------------------------------------------
# FONCTION PRINCIPALE
# -------------------------------------------------------------------

def calculer_stats_prolifiques(postes_ids, date_debut: date, date_fin: date,
                               type_inventaire: str = "normal",
                               critere: str = "jour",
                               classer_par: str = "record",
                               top_n: int = 30) -> Resultat:
    """
    Args:
        postes_ids      : identifiants des postes analysés (1 ou plusieurs).
        date_debut/fin  : période analysée, bornes incluses.
        type_inventaire : "normal", "administratif" ou "tous"
                          (normaux et administratifs restent séparés par défaut).
        critere         : "jour" ou "heure" (ce qui est mis en avant / classé).
        classer_par     : "record" (classement sur le jour/l'heure record du poste)
                          ou "total" (classement sur le total de la période).
                          N'a d'effet que pour le classement de plusieurs postes.
        top_n           : taille du classement quand un seul poste est analysé.
    """
    ids = list(postes_ids)                                   # fige les identifiants (queryset -> liste)

    # Filtre de base : postes + période (FK `inventaire` -> InventaireJournalier)
    filtres = {
        "inventaire__poste_id__in": ids,
        "inventaire__date__range": (date_debut, date_fin),
    }
    if type_inventaire in ("normal", "administratif"):       # "tous" = aucun filtre de type
        filtres["inventaire__type_inventaire"] = type_inventaire

    # Une seule requête SQL : véhicules par (poste, jour, créneau)
    lignes = (
        DetailInventairePeriode.objects
        .filter(**filtres)
        .values("inventaire__poste_id", "inventaire__poste__nom",
                "inventaire__date", "periode")
        .annotate(total=Sum("nombre_vehicules"))
    )

    # --- Accumulateurs ---
    p_nom: Dict[int, str] = {}                               # poste -> nom
    p_total = defaultdict(int)                               # poste -> total véhicules
    p_jours = defaultdict(lambda: defaultdict(int))          # poste -> date -> total du jour
    p_best_heure: Dict[int, Record] = {}                     # poste -> meilleure heure
    g_creneau = defaultdict(int)                             # créneau -> total (graphique)
    heures_poste_unique: List[Record] = []                   # toutes les heures (si un seul poste)

    poste_unique = len(ids) == 1                             # un seul poste demandé ?

    for l in lignes:                                         # une ligne = (poste, jour, créneau)
        pid = l["inventaire__poste_id"]                      # poste
        jour = l["inventaire__date"]                         # date
        creneau = l["periode"]                               # "08h-09h" ...
        n = l["total"] or 0                                  # véhicules (0 si NULL)

        p_nom[pid] = l["inventaire__poste__nom"]             # mémorise le nom
        p_total[pid] += n                                    # cumul période du poste
        p_jours[pid][jour] += n                              # cumul du jour du poste
        g_creneau[creneau] += n                              # cumul par créneau (tous postes)

        # Meilleure heure du poste : valeur max ; à égalité, la plus ancienne (date puis créneau)
        best = p_best_heure.get(pid)
        if (best is None or n > best.valeur
                or (n == best.valeur and (jour, creneau) < (best.date, best.creneau))):
            p_best_heure[pid] = Record(date=jour, creneau=creneau, valeur=n)

        if poste_unique:                                     # on garde chaque heure pour le top N
            heures_poste_unique.append(Record(date=jour, creneau=creneau, valeur=n))

    # --- Résultat global ---
    res = Resultat(
        date_debut=date_debut, date_fin=date_fin,
        critere=critere, classer_par=classer_par, poste_unique=poste_unique,
        nb_postes=len(p_nom),
        nb_inventaires=sum(len(j) for j in p_jours.values()),
        total_vehicules=sum(p_total.values()),
    )
    res.repartition_heures = [                               # total par créneau, ordre horaire
        {"creneau": c, "total": g_creneau[c]} for c in sorted(g_creneau)
    ]

    # ===============================================================
    # MODE UN SEUL POSTE : classement 1er ... Ne
    # ===============================================================
    if poste_unique and p_nom:
        pid = next(iter(p_nom))                              # l'unique poste
        res.poste_nom = p_nom[pid]

        # Meilleurs jours (total du jour), tri : valeur décroissante puis date croissante
        jours_tries = sorted(p_jours[pid].items(), key=lambda x: (-x[1], x[0]))[:top_n]
        res.top_jours = [
            Record(date=d, valeur=v, rang=i) for i, (d, v) in enumerate(jours_tries, start=1)
        ]

        # Meilleures heures (créneau d'un jour), tri : valeur décroissante, date, créneau
        heures_triees = sorted(heures_poste_unique,
                               key=lambda r: (-r.valeur, r.date, r.creneau))[:top_n]
        for i, r in enumerate(heures_triees, start=1):       # numérote le classement
            r.rang = i
        res.top_heures = heures_triees

        # Pourcentage par rapport au 1er (pour les barres de progression)
        for liste in (res.top_jours, res.top_heures):
            max_v = liste[0].valeur if liste else 0          # le 1er a la plus grande valeur
            for r in liste:
                r.pct = round(r.valeur * 100 / max_v, 1) if max_v else 0.0
        return res                                           # fin du mode un poste

    # ===============================================================
    # MODE PLUSIEURS POSTES : classement des postes
    # ===============================================================
    lignes_postes: List[LignePoste] = []
    for pid, nom in p_nom.items():
        jours = p_jours[pid]                                 # {date: total du jour}
        meilleur_jour = min(jours.items(), key=lambda x: (-x[1], x[0]))  # jour record (égalité : plus ancien)
        lignes_postes.append(LignePoste(
            poste_id=pid, poste_nom=nom,
            nb_inventaires=len(jours),
            total_vehicules=p_total[pid],
            jour_record=Record(date=meilleur_jour[0], valeur=meilleur_jour[1]),
            heure_record=p_best_heure[pid],
        ))

    def cle_tri(lp: LignePoste):
        """Clé de classement : total période, ou record du critère choisi (décroissant)."""
        if classer_par == "total":
            valeur = lp.total_vehicules                      # classement sur le total de la période
        elif critere == "heure":
            valeur = lp.heure_record.valeur                  # classement sur l'heure record
        else:
            valeur = lp.jour_record.valeur                   # classement sur le jour record
        return (-valeur, lp.poste_nom)                       # égalité : ordre alphabétique

    lignes_postes.sort(key=cle_tri)                          # applique le classement
    for i, lp in enumerate(lignes_postes, start=1):          # numérote 1, 2, 3 ...
        lp.rang = i
        # Valeur et précision affichées selon le critère de classement
        if classer_par == "total":
            lp.valeur = lp.total_vehicules
            lp.detail = f"sur {lp.nb_inventaires} inventaire(s)"
        elif critere == "heure":
            lp.valeur = lp.heure_record.valeur
            lp.detail = f"{lp.heure_record.creneau}, le {lp.heure_record.date:%d/%m/%Y}"
        else:
            lp.valeur = lp.jour_record.valeur
            lp.detail = f"le {lp.jour_record.date:%d/%m/%Y}"

    max_v = lignes_postes[0].valeur if lignes_postes else 0  # valeur du 1er
    for lp in lignes_postes:                                 # % pour les barres de progression
        lp.pct = round(lp.valeur * 100 / max_v, 1) if max_v else 0.0
    res.classement_postes = lignes_postes
    return res