# ===================================================================
# inventaire/models_commandes.py - MODÈLES COMMANDES ET LIVRAISONS
# Application SUPPER - Gestion des commandes de tickets
# ===================================================================
"""
Ce fichier contient les modèles pour le système de commandes de tickets:

- CommandeTickets: Commande globale avec numéro, exercice, période
- DetailCommandePoste: Détails par poste (montant, carnets, code sécurisation, QR)
- LivraisonTickets: Livraisons avec association aux recharges imprimerie nationale

RÈGLES MÉTIER:
- Numéro de commande de 1 à 10 par exercice
- Périodes: mensuelle, trimestrielle, semestrielle, annuelle
- Code sécurisation format: PSRR{année}XXXXXX (alphanumérique)
- QR Code contient: poste, commande, exercice, code sécurisation
- Possibilité d'écraser une commande existante pour un poste
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid
import random
import string
import hashlib
import json


class CommandeTickets(models.Model):
    """
    Modèle principal pour une commande de tickets.
    Une commande peut concerner plusieurs postes (via DetailCommandePoste).
    """

    PERIODE_CHOICES = [
        ('mensuelle', _('Mensuelle')),
        ('trimestrielle', _('Trimestrielle')),
        ('semestrielle', _('Semestrielle')),
        ('annuelle', _('Annuelle')),
    ]

    MOIS_CHOICES = [
        (1, _('Janvier')), (2, _('Février')), (3, _('Mars')),
        (4, _('Avril')), (5, _('Mai')), (6, _('Juin')),
        (7, _('Juillet')), (8, _('Août')), (9, _('Septembre')),
        (10, _('Octobre')), (11, _('Novembre')), (12, _('Décembre')),
    ]

    TRIMESTRE_CHOICES = [
        (1, _('1er Trimestre (Jan-Mar)')),
        (2, _('2ème Trimestre (Avr-Juin)')),
        (3, _('3ème Trimestre (Juil-Sept)')),
        (4, _('4ème Trimestre (Oct-Déc)')),
    ]

    SEMESTRE_CHOICES = [
        (1, _('1er Semestre (Jan-Juin)')),
        (2, _('2ème Semestre (Juil-Déc)')),
    ]

    STATUT_CHOICES = [
        ('brouillon', _('Brouillon')),
        ('validee', _('Validée')),
        ('en_cours', _('En cours de livraison')),
        ('completee', _('Complétée')),
        ('annulee', _('Annulée')),
    ]

    # Identification de la commande
    numero_commande = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        verbose_name=_("Numéro de commande"),
        help_text=_("Numéro de 1 à 10")
    )

    exercice = models.PositiveIntegerField(
        verbose_name=_("Exercice (année)"),
        help_text=_("Année de l'exercice budgétaire")
    )

    # Période
    type_periode = models.CharField(
        max_length=20,
        choices=PERIODE_CHOICES,
        verbose_name=_("Type de période")
    )

    mois = models.PositiveIntegerField(
        choices=MOIS_CHOICES,
        null=True,
        blank=True,
        verbose_name=_("Mois"),
        help_text=_("Requis si période mensuelle")
    )

    trimestre = models.PositiveIntegerField(
        choices=TRIMESTRE_CHOICES,
        null=True,
        blank=True,
        verbose_name=_("Trimestre"),
        help_text=_("Requis si période trimestrielle")
    )

    semestre = models.PositiveIntegerField(
        choices=SEMESTRE_CHOICES,
        null=True,
        blank=True,
        verbose_name=_("Semestre"),
        help_text=_("Requis si période semestrielle")
    )

    # Statut et métadonnées
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_cours',
        verbose_name=_("Statut")
    )

    titre = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("Titre de la commande"),
        help_text=_("Généré automatiquement si vide")
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description/Observations")
    )

    # Totaux calculés
    montant_total = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Montant total (FCFA)")
    )

    nombre_tickets_total = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Nombre total de tickets")
    )

    nombre_carnets_total = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Nombre total de carnets")
    )

    nombre_postes = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Nombre de postes concernés")
    )

    # Traçabilité
    cree_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        related_name='commandes_creees',
        verbose_name=_("Créé par")
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )

    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Date de modification")
    )

    date_validation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Date de validation")
    )

    valide_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='commandes_validees',
        verbose_name=_("Validé par")
    )

    class Meta:
        verbose_name = _("Commande de tickets")
        verbose_name_plural = _("Commandes de tickets")
        ordering = ['-exercice', '-numero_commande', '-date_creation']
        indexes = [
            models.Index(fields=['exercice', 'numero_commande']),
            models.Index(fields=['statut']),
            models.Index(fields=['type_periode']),
        ]

    def __str__(self):
        return f"Commande n°{self.numero_commande} - Exercice {self.exercice}"

    def save(self, *args, **kwargs):
        # Générer le titre automatiquement
        if not self.titre:
            self.titre = self._generer_titre()
        super().save(*args, **kwargs)

    def _generer_titre(self):
        """Génère le titre automatique de la commande."""
        ordinal = self._get_ordinal(self.numero_commande)
        return f"{ordinal} Commande des tickets de l'année {self.exercice}"

    @staticmethod
    def _get_ordinal(n):
        """Retourne l'ordinal en français."""
        if n == 1:
            return "1ère"
        return f"{n}ème"

    def get_periode_display_complet(self):
        """Retourne l'affichage complet de la période."""
        if self.type_periode == 'mensuelle' and self.mois:
            return f"Mois de {self.get_mois_display()}"
        elif self.type_periode == 'trimestrielle' and self.trimestre:
            return self.get_trimestre_display()
        elif self.type_periode == 'semestrielle' and self.semestre:
            return self.get_semestre_display()
        else:
            return f"Année {self.exercice}"

    def recalculer_totaux(self):
        """Recalcule les totaux à partir des détails."""
        from django.db.models import Sum, Count

        aggregats = self.details.aggregate(
            total_montant=Sum('montant_commande'),
            total_tickets=Sum('nombre_tickets'),
            total_carnets=Sum('nombre_carnets'),
            nb_postes=Count('id')
        )

        self.montant_total = aggregats['total_montant'] or Decimal('0')
        self.nombre_tickets_total = aggregats['total_tickets'] or 0
        self.nombre_carnets_total = aggregats['total_carnets'] or 0
        self.nombre_postes = aggregats['nb_postes'] or 0
        self.save(update_fields=[
            'montant_total', 'nombre_tickets_total',
            'nombre_carnets_total', 'nombre_postes'
        ])

    def valider(self, user):
        """Valide la commande."""
        self.statut = 'validee'
        self.date_validation = timezone.now()
        self.valide_par = user
        self.save(update_fields=['statut', 'date_validation', 'valide_par'])

    def get_taux_livraison(self):
        """Calcule le taux de livraison global."""
        if self.nombre_carnets_total == 0:
            return 0

        from django.db.models import Sum
        carnets_livres = self.details.aggregate(
            total=Sum('carnets_livres')
        )['total'] or 0

        return round((carnets_livres / self.nombre_carnets_total) * 100, 2)

    def get_titre_complet(self):
        """
        Retourne le titre complet de la commande avec la période.
        Utilisé dans les templates pour l'affichage dans les listes déroulantes.
        """
        ordinal = self._get_ordinal(self.numero_commande)
        periode = self.get_periode_display_complet()
        return f"{ordinal} Commande {self.exercice} - {periode}"

    @property
    def carnets_total(self):
        """Alias pour nombre_carnets_total (compatibilité templates)."""
        return self.nombre_carnets_total


class DetailCommandePoste(models.Model):
    """
    Détail d'une commande pour un poste spécifique.
    Contient le code de sécurisation et les données QR.
    """

    commande = models.ForeignKey(
        CommandeTickets,
        on_delete=models.CASCADE,
        related_name='details',
        verbose_name=_("Commande")
    )

    poste = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='commandes_details',
        verbose_name=_("Poste de péage")
    )

    # Numéro d'ordre dans la commande
    numero_ordre = models.PositiveIntegerField(
        default=1,
        verbose_name=_("N° d'ordre")
    )

    # Montant basé sur les ventes de la période
    montant_commande = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_("Montant commandé (FCFA)")
    )

    # Calculés automatiquement
    nombre_tickets = models.PositiveIntegerField(
        verbose_name=_("Nombre de tickets"),
        help_text=_("Montant / 500")
    )

    nombre_carnets = models.PositiveIntegerField(
        verbose_name=_("Nombre de carnets"),
        help_text=_("Nombre tickets / 100")
    )

    # Couleur récupérée du dernier chargement du poste
    couleur_tickets = models.ForeignKey(
        'inventaire.CouleurTicket',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Couleur des tickets")
    )

    # Code de sécurisation unique
    code_securisation = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=_("Code de sécurisation"),
        help_text=_("Format: PSRR{année}XXXXXX")
    )

    # Données QR encodées
    qr_data = models.TextField(
        verbose_name=_("Données QR"),
        help_text=_("Données JSON encodées dans le QR code")
    )

    # Hash pour vérification
    hash_verification = models.CharField(
        max_length=64,
        verbose_name=_("Hash de vérification")
    )

    # Suivi des livraisons
    carnets_livres = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Carnets livrés")
    )

    est_complet = models.BooleanField(
        default=False,
        verbose_name=_("Livraison complète")
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )

    class Meta:
        verbose_name = _("Détail commande poste")
        verbose_name_plural = _("Détails commandes postes")
        ordering = ['commande', 'numero_ordre']
        unique_together = [['commande', 'poste']]
        indexes = [
            models.Index(fields=['commande', 'poste']),
            models.Index(fields=['code_securisation']),
        ]

    def __str__(self):
        return f"Commande {self.commande.numero_commande} - {self.poste.nom}"

    def save(self, *args, **kwargs):
        # Calculs automatiques
        if self.montant_commande:
            self.nombre_tickets = int(self.montant_commande / 500)
            self.nombre_carnets = self.nombre_tickets // 100

        # Générer code de sécurisation si absent
        if not self.code_securisation:
            self.code_securisation = self._generer_code_securisation()

        # Générer données QR si absentes
        if not self.qr_data:
            self.qr_data = self._generer_qr_data()

        # Calculer hash de vérification
        self.hash_verification = self._calculer_hash()

        # Vérifier si livraison complète
        self.est_complet = self.carnets_livres >= self.nombre_carnets

        super().save(*args, **kwargs)

    def _generer_code_securisation(self):
        """
        Génère un code de sécurisation unique.
        Format: PSRR{année sur 2 chiffres}{6 caractères alphanumériques}
        Exemple: PSRR26A7B2C9
        """
        annee_courte = str(self.commande.exercice)[-2:]

        # Générer 6 caractères alphanumériques
        caracteres = string.ascii_uppercase + string.digits
        # Exclure les caractères ambigus (0, O, I, 1, L)
        caracteres = caracteres.replace('0', '').replace('O', '')
        caracteres = caracteres.replace('I', '').replace('1', '').replace('L', '')

        code_aleatoire = ''.join(random.choices(caracteres, k=6))
        code = f"PSRR{annee_courte}{code_aleatoire}"

        # Vérifier l'unicité
        while DetailCommandePoste.objects.filter(code_securisation=code).exists():
            code_aleatoire = ''.join(random.choices(caracteres, k=6))
            code = f"PSRR{annee_courte}{code_aleatoire}"

        return code

    def _generer_qr_data(self):
        """
        Génère les données JSON pour le QR code.
        Ces données permettent l'authentification sans connexion.
        """
        data = {
            'type': 'SUPPER_COMMANDE',
            'version': '1.0',
            'code': self.code_securisation,
            'commande': {
                'numero': self.commande.numero_commande,
                'exercice': self.commande.exercice,
                'periode': self.commande.type_periode,
            },
            'poste': {
                'code': self.poste.code,
                'nom': self.poste.nom,
                'region': self.poste.region.nom if self.poste.region else None,
            },
            'details': {
                'montant': str(self.montant_commande),
                'tickets': self.nombre_tickets,
                'carnets': self.nombre_carnets,
            },
            'timestamp': timezone.now().isoformat(),
        }
        return json.dumps(data, ensure_ascii=False)

    def _calculer_hash(self):
        """Calcule un hash SHA-256 pour vérification d'intégrité."""
        data_to_hash = f"{self.code_securisation}{self.commande.exercice}{self.poste.code}{self.montant_commande}"
        return hashlib.sha256(data_to_hash.encode()).hexdigest()

    def get_taux_livraison(self):
        """Calcule le taux de livraison pour ce poste."""
        if self.nombre_carnets == 0:
            return 0
        return round((self.carnets_livres / self.nombre_carnets) * 100, 2)

    def get_statut_livraison(self):
        """Retourne le statut de livraison."""
        if self.carnets_livres == 0:
            return 'non_commence'
        elif self.est_complet:
            return 'complet'
        else:
            return 'en_cours'

    def get_statut_livraison_display(self):
        """Retourne l'affichage du statut de livraison."""
        statuts = {
            'non_commence': _('Non commencé'),
            'en_cours': _('En cours'),
            'complet': _('Complet'),
        }
        return statuts.get(self.get_statut_livraison(), _('Inconnu'))

    def generer_qr_image_base64(self):
        """
        Génère une image QR code en base64 pour affichage dans le template.
        Nécessite la librairie qrcode: pip install qrcode[pil]
        """
        try:
            import qrcode
            from io import BytesIO
            import base64

            # Créer le QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=2,
            )
            qr.add_data(self.qr_data)
            qr.make(fit=True)

            # Générer l'image
            img = qr.make_image(fill_color="black", back_color="white")

            # Convertir en base64
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

            return f"data:image/png;base64,{img_base64}"

        except ImportError:
            # Si qrcode n'est pas installé, retourner None
            return None
        except Exception:
            return None

    @classmethod
    def verifier_qr_code(cls, qr_data_json):
        """
        Vérifie l'authenticité d'un QR code scanné.
        Retourne les informations si valide, None sinon.
        """
        try:
            data = json.loads(qr_data_json)

            if data.get('type') != 'SUPPER_COMMANDE':
                return None

            code = data.get('code')
            if not code:
                return None

            # Rechercher le détail correspondant
            detail = cls.objects.filter(code_securisation=code).first()
            if not detail:
                return {'valid': False, 'error': 'Code non trouvé'}

            # Vérifier le hash
            hash_calcule = detail._calculer_hash()
            if hash_calcule != detail.hash_verification:
                return {'valid': False, 'error': 'Données altérées'}

            return {
                'valid': True,
                'detail': detail,
                'data': data,
            }

        except (json.JSONDecodeError, Exception):
            return None


class LivraisonTickets(models.Model):
    """
    Modèle pour suivre les livraisons de tickets.
    Associe les recharges imprimerie nationale aux commandes.
    """

    STATUT_CHOICES = [
        ('en_cours', _('En cours')),
        ('complete', _('Complète')),
        ('annulee', _('Annulée')),
    ]

    # Référence à la commande et au détail
    commande = models.ForeignKey(
        CommandeTickets,
        on_delete=models.CASCADE,
        related_name='livraisons',
        verbose_name=_("Commande")
    )

    detail_commande = models.ForeignKey(
        DetailCommandePoste,
        on_delete=models.CASCADE,
        related_name='livraisons',
        verbose_name=_("Détail commande")
    )

    poste = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='livraisons_tickets',
        verbose_name=_("Poste de péage")
    )

    # Date de livraison
    date_livraison = models.DateField(
        verbose_name=_("Date de livraison")
    )

    # Recharges associées (HistoriqueStock de type imprimerie_nationale)
    historiques_associes = models.ManyToManyField(
        'inventaire.HistoriqueStock',
        related_name='livraisons_associees',
        verbose_name=_("Recharges associées"),
        help_text=_("Recharges imprimerie nationale associées à cette livraison")
    )

    # Totaux de la livraison
    montant_livre = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Montant livré (FCFA)")
    )

    nombre_tickets_livres = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Tickets livrés")
    )

    nombre_carnets_livres = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Carnets livrés")
    )

    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_cours',
        verbose_name=_("Statut")
    )

    observations = models.TextField(
        blank=True,
        verbose_name=_("Observations")
    )

    # Traçabilité
    cree_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        related_name='livraisons_creees',
        verbose_name=_("Créé par")
    )

    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )

    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Date de modification")
    )

    class Meta:
        verbose_name = _("Livraison de tickets")
        verbose_name_plural = _("Livraisons de tickets")
        ordering = ['-date_livraison', '-date_creation']
        indexes = [
            models.Index(fields=['commande', 'poste']),
            models.Index(fields=['date_livraison']),
            models.Index(fields=['statut']),
        ]

    def __str__(self):
        return f"Livraison {self.poste.nom} - {self.date_livraison}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Mettre à jour le détail de commande après sauvegarde
        self._mettre_a_jour_detail_commande()

    def delete(self, *args, **kwargs):
        """
        Supprime la livraison ET recalcule le détail de commande /
        le statut de la commande, exactement comme save() le fait
        à la création. Sans ça, carnets_livres et est_complet restent
        figés sur l'ancienne valeur après suppression.
        """
        detail_commande = self.detail_commande
        commande = self.commande

        result = super().delete(*args, **kwargs)

        # self n'a plus de PK ici, donc on recalcule "à la main"
        # avec les références capturées avant la suppression.
        self._recalculer_detail_et_commande(detail_commande, commande)

        return result

    def _mettre_a_jour_detail_commande(self):
        """Met à jour les carnets livrés dans le détail de commande."""
        self._recalculer_detail_et_commande(self.detail_commande, self.commande)

    def _recalculer_detail_et_commande(self, detail_commande, commande):
        """Recalcule carnets_livres/est_complet sur le détail, puis le
        statut de la commande. Utilisé après save() ET après delete()."""
        from django.db.models import Sum

        total_carnets = LivraisonTickets.objects.filter(
            detail_commande=detail_commande,
            statut__in=['en_cours', 'complete']
        ).aggregate(total=Sum('nombre_carnets_livres'))['total'] or 0

        detail_commande.carnets_livres = total_carnets
        detail_commande.est_complet = (
            total_carnets >= detail_commande.nombre_carnets
        )
        detail_commande.save(update_fields=['carnets_livres', 'est_complet'])

        # Mettre à jour le statut de la commande
        self._verifier_statut_commande(commande)

    def _verifier_statut_commande(self, commande=None):
        """Vérifie et met à jour le statut de la commande."""
        commande = commande or self.commande

        details_total = commande.details.count()
        details_complets = commande.details.filter(est_complet=True).count()

        if details_complets == 0:
            nouveau_statut = 'validee'
        elif details_complets < details_total:
            nouveau_statut = 'en_cours'
        else:
            nouveau_statut = 'completee'

        if commande.statut != nouveau_statut:
            commande.statut = nouveau_statut
            commande.save(update_fields=['statut'])

    def recalculer_totaux(self):
        """Recalcule les totaux à partir des historiques associés."""
        from django.db.models import Sum

        aggregats = self.historiques_associes.aggregate(
            total_montant=Sum('montant'),
            total_tickets=Sum('nombre_tickets')
        )

        self.montant_livre = aggregats['total_montant'] or Decimal('0')
        self.nombre_tickets_livres = aggregats['total_tickets'] or 0
        self.nombre_carnets_livres = self.nombre_tickets_livres // 100

        self.save(update_fields=[
            'montant_livre', 'nombre_tickets_livres', 'nombre_carnets_livres'
        ])