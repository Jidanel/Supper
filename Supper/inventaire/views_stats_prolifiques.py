# ===================================================================
# Supper/inventaire/views_stats_prolifiques.py   - V2
# VUE : statistiques "jour et heure les plus prolifiques"
# (fichier NOUVEAU : views_stats.py existant n'est pas modifié)
# ===================================================================

import logging                                       # journal technique
from datetime import date, datetime                  # gestion des dates

from django.contrib import messages                  # messages à l'utilisateur
from django.contrib.auth.decorators import login_required  # accès authentifié
from django.shortcuts import redirect, render        # redirection + rendu template

from accounts.models import Poste                    # modèle des postes
from common.permissions import (                     # contrôle d'accès SUPPER
    get_postes_peage_accessibles,                    # postes visibles par l'utilisateur
    has_permission,                                  # permission granulaire
    log_acces_refuse,                                # journalisation d'un refus
)
from common.utils import log_user_action             # journalisation manuelle
from inventaire.services.prolifique_service import calculer_stats_prolifiques

logger = logging.getLogger("supper")                 # logger du projet

TYPES_INVENTAIRE = [                                 # choix du filtre de type d'inventaire
    ("normal", "Inventaires normaux"),
    ("administratif", "Inventaires administratifs"),
    ("tous", "Normaux + administratifs"),
]
CRITERES = [("jour", "Jour le plus prolifique"), ("heure", "Heure la plus prolifique")]
CLASSER_PAR = [("record", "Jour / heure record"), ("total", "Total de la période")]
TOP_N_MAX = 100                                      # plafond du classement d'un poste
TOP_N_DEFAUT = 30                                    # valeur par défaut (1er au 30e)


def _parse_date(valeur, defaut):
    """Convertit 'AAAA-MM-JJ' en date ; retourne `defaut` si vide ou invalide."""
    try:
        return datetime.strptime(valeur, "%Y-%m-%d").date()  # format du champ <input type="date">
    except (TypeError, ValueError):
        return defaut                                # valeur absente ou mal formée


def _choix(valeur, autorises, defaut):
    """Retourne `valeur` si elle fait partie des choix autorisés, sinon `defaut`."""
    return valeur if valeur in dict(autorises) else defaut


@login_required
def statistiques_prolifiques(request):
    """
    Jour et heure les plus prolifiques (le plus de véhicules).

    - Plusieurs postes / tous  -> classement des postes sur la période.
    - Un seul poste            -> classement 1er..Ne des jours ou des heures
                                  (chaque heure avec le jour associé).

    PERMISSIONS : peut_voir_stats_deperdition OU peut_voir_liste_inventaires
    ACCÈS POSTES : acces_tous_postes -> tous ; sinon poste d'affectation uniquement
    """
    user = request.user                              # utilisateur connecté

    # ---------- Contrôle des permissions (niveau vue) ----------
    if not (has_permission(user, "peut_voir_stats_deperdition")
            or has_permission(user, "peut_voir_liste_inventaires")):
        log_user_action(
            user=user,
            action="ACCES_REFUSE",
            description="Tentative d'accès aux statistiques jour/heure prolifiques",
            details="Permissions peut_voir_stats_deperdition / peut_voir_liste_inventaires manquantes",
            niveau="WARNING",
        )
        log_acces_refuse(user, "statistiques_prolifiques", "Permission statistiques inventaire manquante")
        messages.error(request, "Vous n'avez pas la permission de voir ces statistiques.")
        return redirect("common:dashboard")

    # ---------- Postes accessibles (péage actifs) ----------
    ids_accessibles = [p.id for p in get_postes_peage_accessibles(user)]  # fonctionne queryset ou liste
    postes_accessibles = Poste.objects.filter(id__in=ids_accessibles, is_active=True).order_by("nom")

    # ---------- Paramètres du formulaire ----------
    aujourdhui = date.today()                        # date du jour
    date_debut = _parse_date(request.GET.get("date_debut"), aujourdhui.replace(day=1))  # début de mois par défaut
    date_fin = _parse_date(request.GET.get("date_fin"), aujourdhui)                      # aujourd'hui par défaut
    if date_debut > date_fin:                        # bornes inversées : on les remet dans l'ordre
        date_debut, date_fin = date_fin, date_debut

    type_inventaire = _choix(request.GET.get("type_inventaire"), TYPES_INVENTAIRE, "normal")
    critere = _choix(request.GET.get("critere"), CRITERES, "jour")
    classer_par = _choix(request.GET.get("classer_par"), CLASSER_PAR, "record")

    try:                                             # taille du classement (borné 1..TOP_N_MAX)
        top_n = max(1, min(int(request.GET.get("top_n", TOP_N_DEFAUT)), TOP_N_MAX))
    except (TypeError, ValueError):
        top_n = TOP_N_DEFAUT

    ids_demandes = [int(i) for i in request.GET.getlist("postes") if i.isdigit()]  # postes cochés
    postes_selectionnes = (
        postes_accessibles.filter(id__in=ids_demandes) if ids_demandes else postes_accessibles
    )                                                # aucun poste coché = tous les postes accessibles

    # ---------- Calcul (uniquement quand le formulaire est soumis) ----------
    resultat = None
    if request.GET.get("calculer"):
        resultat = calculer_stats_prolifiques(
            postes_selectionnes.values_list("id", flat=True),
            date_debut, date_fin, type_inventaire, critere, classer_par, top_n,
        )
        try:                                         # le log ne doit jamais bloquer l'affichage
            log_user_action(
                user=user,
                action="STATS_INVENTAIRE_PROLIFIQUE",
                description="Consultation des statistiques jour/heure prolifiques",
                details=(
                    f"{user.nom_complet} - {postes_selectionnes.count()} poste(s) - "
                    f"du {date_debut:%d/%m/%Y} au {date_fin:%d/%m/%Y} - "
                    f"critère: {critere} - type: {type_inventaire}"
                ),
                niveau="INFO",
            )
        except Exception as exc:                     # erreur de journalisation : on trace et on continue
            logger.warning("[STATS_PROLIFIQUE] Échec journalisation: %s", exc)

    contexte = {
        "postes": postes_accessibles,                # liste du sélecteur
        "postes_selectionnes_ids": ids_demandes,     # pour recocher après soumission
        "date_debut": date_debut,
        "date_fin": date_fin,
        "type_inventaire": type_inventaire,
        "types_inventaire": TYPES_INVENTAIRE,
        "critere": critere,
        "criteres": CRITERES,
        "classer_par": classer_par,
        "classer_par_choix": CLASSER_PAR,
        "top_n": top_n,
        "top_n_max": TOP_N_MAX,
        "resultat": resultat,                        # None tant que non calculé
        # Données du graphique (injectées via json_script dans le template)
        "graph_labels": [r["creneau"] for r in resultat.repartition_heures] if resultat else [],
        "graph_totaux": [r["total"] for r in resultat.repartition_heures] if resultat else [],
    }
    return render(request, "inventaire/statistiques_prolifiques.html", contexte)