# inventaire/services/date_effet.py
# DATE D'EFFET des corrections de stock (gel, dégel, suppression...).
# Convention : une correction « effective le jour D » est datée D à 00:00:00.
#   - elle fait partie du STOCK DE DÉBUT du jour D (donc du début du mois si D = 1er du mois) ;
#   - elle n'a AUCUN effet sur la fin du jour D-1 (la clôture du mois précédent reste intacte).
# La date réelle de saisie est conservée à part (HistoriqueStock.date_saisie).

import datetime  # Dates et heures

from django.utils import timezone  # Fuseau horaire


class DateEffetError(Exception):
    """Date d'effet refusée (message lisible par l'utilisateur)."""


def datetime_effet(jour):
    """Date d'effet (date) -> instant comptable : ce jour à 00:00:00 (fuseau du projet)."""
    return timezone.make_aware(datetime.datetime(jour.year, jour.month, jour.day, 0, 0, 0))


def debut_du_mois(jour):
    """Premier jour du mois de `jour`."""
    return jour.replace(day=1)


def verifier_date_effet(poste, jour):
    """Refuse une date d'effet future ou située dans un mois dont le compte d'emploi/PV est déjà SIGNÉ.
    (Un document signé ne doit jamais changer après coup.)"""
    if jour > timezone.localdate():
        raise DateEffetError("La date d'effet ne peut pas être dans le futur.")
    from inventaire.models_cloture import ClotureMensuelle, StatutCloture  # Import tardif (évite les cycles)
    mois_a_verifier = f"{jour.year}-{jour.month:02d}"  # Mois où la correction prend effet
    if ClotureMensuelle.objects.filter(poste=poste, mois=mois_a_verifier, statut=StatutCloture.SIGNE).exists():
        raise DateEffetError(
            f"Le mois {mois_a_verifier} est déjà signé pour {poste.nom} : choisissez une date d'effet dans un mois non signé.")
