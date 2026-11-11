# inventaire/models_cloture.py
# Modèles de la clôture mensuelle : affectations datées (titulaires par période)
# et documents mensuels générés (compte d'emploi péage / PV de confrontation pesage).

import secrets  # Génération du jeton aléatoire servant au QR code de vérification
from django.db import models  # Base des modèles Django
from django.utils import timezone  # Horodatage
from django.utils.translation import gettext_lazy as _  # Textes traduisibles FR/EN
from accounts.models import UtilisateurSUPPER, Poste  # Utilisateurs et postes existants


class FonctionTitulaire(models.TextChoices):
    """Fonctions dont on conserve le titulaire par période."""
    CHEF_POSTE_PEAGE = 'chef_poste_peage', _('Chef de poste péage')
    REGISSEUR_PESAGE = 'regisseur_pesage', _('Régisseur de station pesage')
    CHEF_STATION_PESAGE = 'chef_station_pesage', _('Chef de station pesage')


class AffectationPoste(models.Model):
    """Titulaire d'une fonction sur un poste, pour une période donnée (historique)."""

    poste = models.ForeignKey(Poste, on_delete=models.CASCADE, related_name='affectations_titulaires')  # Poste concerné
    fonction = models.CharField(max_length=30, choices=FonctionTitulaire.choices)  # Fonction exercée
    utilisateur = models.ForeignKey(  # Compte SUPPER du titulaire (facultatif)
        UtilisateurSUPPER, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='affectations_titulaires')
    nom_manuel = models.CharField(max_length=150, blank=True)  # Nom saisi à la main si pas de compte
    date_debut = models.DateField()  # Premier jour d'exercice
    date_fin = models.DateField(null=True, blank=True)  # Dernier jour (vide = en cours)
    est_interim = models.BooleanField(default=False)  # Intérim ?
    cree_par = models.ForeignKey(  # Auteur de la saisie
        UtilisateurSUPPER, null=True, on_delete=models.SET_NULL, related_name='+')
    date_creation = models.DateTimeField(auto_now_add=True)  # Horodatage de création

    class Meta:
        ordering = ['-date_debut']  # Plus récent d'abord
        indexes = [models.Index(fields=['poste', 'fonction', 'date_debut'])]  # Recherche par poste/fonction/date

    @property
    def nom_affiche(self):
        """Nom à imprimer : compte SUPPER s'il existe, sinon nom manuel."""
        if self.utilisateur_id:
            return self.utilisateur.nom_complet
        return self.nom_manuel

    @classmethod
    def titulaire_au(cls, poste, fonction, jour):
        """Titulaire à une date donnée (None si aucun enregistré)."""
        return cls.objects.filter(
            models.Q(date_fin__gte=jour) | models.Q(date_fin__isnull=True),
            poste=poste, fonction=fonction, date_debut__lte=jour,
        ).order_by('-date_debut').first()  # Le plus récent si chevauchement

    def __str__(self):
        return f"{self.poste.nom} - {self.get_fonction_display()} - {self.nom_affiche}"


class TypeCloture(models.TextChoices):
    COMPTE_EMPLOI = 'compte_emploi', _("Compte d'emploi (péage)")
    PV_CONFRONTATION = 'pv_confrontation', _('PV de confrontation (pesage)')


class StatutCloture(models.TextChoices):
    GENERE = 'genere', _('Généré')
    SIGNE = 'signe', _('Signé (verrouillé)')
    REMPLACE = 'remplace', _('Remplacé par une version plus récente')


def _nouveau_jeton():
    """Jeton aléatoire non devinable pour l'URL /verifier/<jeton>."""
    return secrets.token_urlsafe(16)


class ClotureMensuelle(models.Model):
    """Document mensuel figé, avec version, signataire et jeton de vérification QR."""

    poste = models.ForeignKey(Poste, on_delete=models.CASCADE, related_name='clotures')  # Poste
    type_document = models.CharField(max_length=20, choices=TypeCloture.choices)  # Compte d'emploi ou PV
    mois = models.CharField(max_length=7)  # Format "YYYY-MM"
    version = models.PositiveIntegerField(default=1)  # Incrémentée à chaque régénération
    statut = models.CharField(max_length=10, choices=StatutCloture.choices, default=StatutCloture.GENERE)
    donnees = models.JSONField(default=dict)  # Champs manuels + chiffres calculés, figés
    jeton = models.CharField(max_length=40, unique=True, default=_nouveau_jeton)  # Jeton du QR code
    signataire_nom = models.CharField(max_length=150, blank=True)  # Nom figé du titulaire
    signataire_fonction = models.CharField(max_length=60, blank=True)  # Fonction figée
    genere_par = models.ForeignKey(UtilisateurSUPPER, null=True, on_delete=models.SET_NULL, related_name='+')
    date_generation = models.DateTimeField(default=timezone.now)  # Horodatage

    class Meta:
        ordering = ['-mois', '-version']
        constraints = [models.UniqueConstraint(
            fields=['poste', 'type_document', 'mois', 'version'], name='uniq_cloture_version')]
        indexes = [models.Index(fields=['poste', 'type_document', 'mois'])]

    def __str__(self):
        return f"{self.get_type_document_display()} {self.poste.nom} {self.mois} v{self.version}"
