# ===================================================================
# inventaire/models.py - Modèles pour la gestion des inventaires SUPPER
# ===================================================================

from datetime import timedelta
import decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from accounts.models import UtilisateurSUPPER, Poste
from django.urls import reverse
import calendar
from .models_config import ConfigurationGlobale
import logging

logger = logging.getLogger('supper')

class MoisChoices(models.TextChoices):
    """Choix des mois pour l'inventaire mensuel"""
    JANVIER = '01', _('Janvier')
    FEVRIER = '02', _('Février')
    MARS = '03', _('Mars')
    AVRIL = '04', _('Avril')
    MAI = '05', _('Mai')
    JUIN = '06', _('Juin')
    JUILLET = '07', _('Juillet')
    AOUT = '08', _('Août')
    SEPTEMBRE = '09', _('Septembre')
    OCTOBRE = '10', _('Octobre')
    NOVEMBRE = '11', _('Novembre')
    DECEMBRE = '12', _('Décembre')


# ===================================================================
# CORRECTION DANS inventaire/models.py
# Remplacer la classe InventaireMensuel
# ===================================================================
class MotifInventaire(models.TextChoices):
    """Motifs pour programmer un inventaire"""
    TAUX_DEPERDITION = 'taux_deperdition', _('Taux de déperdition élevé')
    RISQUE_BAISSE = 'risque_baisse', _('Risque de baisse annuel')
    GRAND_STOCK = 'grand_stock', _('Risque de grand stock')
    PRESENCE_ADMINISTRATIVE = 'presence_admin', _('Présence administrative')

class ProgrammationInventaire(models.Model):
    """
    Modèle pour programmer des inventaires mensuels par poste
    Un poste peut avoir plusieurs motifs pour le même mois
    """
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='programmations_inventaire',
        verbose_name=_("Poste")
    )
    
    mois = models.DateField(
        verbose_name=_("Mois de programmation"),
        help_text=_("Premier jour du mois concerné")
    )
    
    motif = models.CharField(
        max_length=20,
        choices=MotifInventaire.choices,
        verbose_name=_("Motif de l'inventaire"),
        default=0
    )
    
    # Données pour le motif taux de déperdition
    taux_deperdition_precedent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux de déperdition précédent (%)"),
        help_text=_("Saisi manuellement ou récupéré du dernier inventaire")
    )
    
    # Données pour le risque de baisse annuel
    risque_baisse_annuel = models.BooleanField(
        default=False,
        verbose_name=_("Risque de baisse annuel"),
        help_text=_("Calculé automatiquement selon les recettes")
    )
    
    recettes_periode_actuelle = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Recettes période actuelle")
    )
    
    recettes_periode_precedente = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Recettes même période année précédente")
    )

    pourcentage_baisse = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Pourcentage de baisse (%)")
    )
    
    # Données pour le risque de grand stock
    stock_restant = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Stock restant de tickets")
    )
    
    date_epuisement_prevu = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date d'épuisement prévue du stock")
    )
    
    risque_grand_stock = models.BooleanField(
        default=False,
        verbose_name=_("Risque de grand stock"),
        help_text=_("Si la date d'épuisement dépasse le 31 décembre")
    )
    
    # Métadonnées
    cree_par = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        related_name='programmations_creees',
        verbose_name=_("Créé par")
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name=_("Programmation active")
    )
    
    class Meta:
        verbose_name = _("Programmation inventaire")
        verbose_name_plural = _("Programmations inventaires")
        # CHANGEMENT : Un poste peut avoir plusieurs motifs pour le même mois
        unique_together = [['poste', 'mois', 'motif']]  # Ajout du motif dans la contrainte
        ordering = ['-mois', 'poste__nom', 'motif']
        indexes = [
            models.Index(fields=['poste', '-mois']),
            models.Index(fields=['motif']),
            models.Index(fields=['actif']),
        ]
    
    
    def __str__(self):
        return f"Programmation {self.poste.nom} - {self.mois.strftime('%B %Y')} - {self.get_motif_display()}"
    
    def calculer_risque_baisse_annuel(self):
        """
        Calcule automatiquement le risque de baisse annuel
        Compare les recettes de la période actuelle avec la même période l'année précédente
        """
        from datetime import date, timedelta
        from django.db.models import Sum
        
        # Période actuelle (du 1er janvier à aujourd'hui)
        annee_actuelle = date.today().year
        debut_annee = date(annee_actuelle, 1, 1)
        fin_periode = date.today()
        
        # Calculer les recettes de la période actuelle
        recettes_actuelles = RecetteJournaliere.objects.filter(
            poste=self.poste,
            date__range=[debut_annee, fin_periode]
        ).aggregate(total=Sum('montant_declare'))['total'] or 0
        
        # Même période l'année précédente
        annee_precedente = annee_actuelle - 1
        debut_annee_prec = date(annee_precedente, 1, 1)
        fin_periode_prec = date(annee_precedente, fin_periode.month, fin_periode.day)
        
        # Calculer les recettes de la période précédente
        recettes_precedentes = RecetteJournaliere.objects.filter(
            poste=self.poste,
            date__range=[debut_annee_prec, fin_periode_prec]
        ).aggregate(total=Sum('montant_declare'))['total'] or 0
        
        # Sauvegarder les valeurs
        self.recettes_periode_actuelle = recettes_actuelles
        self.recettes_periode_precedente = recettes_precedentes
        
        # Calculer le pourcentage de baisse
        if recettes_precedentes > 0 and recettes_actuelles < recettes_precedentes:
            self.pourcentage_baisse = ((recettes_precedentes - recettes_actuelles) / recettes_precedentes) * 100
            self.risque_baisse_annuel = True
        else:
            self.pourcentage_baisse = 0
            self.risque_baisse_annuel = False
        
        return self.risque_baisse_annuel
    
    def calculer_date_epuisement_stock(self):
        """
        Calcule la date d'épuisement prévue du stock en utilisant le forecasting
        """
        from datetime import date, timedelta
        from inventaire.services.forecasting_service import ForecastingService
        
        if not self.stock_restant:
            return None
        
        try:
            # Calculer les prévisions pour les 365 prochains jours
            resultats_prevision = ForecastingService.prevoir_recettes(
                self.poste,
                nb_jours_future=365
            )
            
            if not resultats_prevision['success']:
                # Fallback sur l'ancienne méthode si échec
                return self._calculer_date_epuisement_moyenne_simple()
            
            df_prev = resultats_prevision['predictions']
            
            # Parcourir les prévisions jour par jour
            stock_restant_simule = float(self.stock_restant)
            date_actuelle = date.today()
            
            for index, row in df_prev.iterrows():
                vente_prevue_jour = row['montant_prevu']
                stock_restant_simule -= vente_prevue_jour
                
                if stock_restant_simule <= 0:
                    # Stock épuisé à cette date
                    self.date_epuisement_prevu = row['date'].date()
                    
                    # Vérifier si ça dépasse le 31 décembre
                    fin_annee = date(date_actuelle.year, 12, 31)
                    self.risque_grand_stock = self.date_epuisement_prevu > fin_annee
                    
                    return self.date_epuisement_prevu
            
            # Si on arrive ici, le stock dure plus d'un an
            self.date_epuisement_prevu = date_actuelle + timedelta(days=365)
            self.risque_grand_stock = True
            
            return self.date_epuisement_prevu
            
        except Exception as e:
            import logging
            logger = logging.getLogger('supper')
            logger.error(f"Erreur calcul épuisement stock forecasting: {str(e)}")
            # Fallback sur l'ancienne méthode
            return self._calculer_date_epuisement_moyenne_simple()

    def _calculer_date_epuisement_moyenne_simple(self):
        """Méthode de fallback avec moyenne simple"""
        from datetime import date, timedelta
        from django.db.models import Avg
        
        fin = date.today()
        debut = fin - timedelta(days=30)
        
        moyenne_journaliere = RecetteJournaliere.objects.filter(
            poste=self.poste,
            date__range=[debut, fin]
        ).aggregate(moyenne=Avg('montant_declare'))['moyenne'] or 0
        
        if moyenne_journaliere > 0:
            tickets_par_jour = moyenne_journaliere / 500
            if tickets_par_jour > 0:
                jours_restants = self.stock_restant / tickets_par_jour
                self.date_epuisement_prevu = date.today() + timedelta(days=int(jours_restants))
                
                fin_annee = date(date.today().year, 12, 31)
                self.risque_grand_stock = self.date_epuisement_prevu > fin_annee
                
                return self.date_epuisement_prevu
        
        return None

    @classmethod
    def get_postes_avec_grand_stock(cls):
        """
        Retourne les postes dont la date d'épuisement dépasse le 31 décembre
        en utilisant le forecasting
        """
        from inventaire.models import GestionStock
        from inventaire.services.forecasting_service import ForecastingService
        from datetime import date
        
        postes_grand_stock = []
        date_limite = date(date.today().year, 12, 31)
        
        for poste in Poste.objects.filter(is_active=True):
            try:
                stock = GestionStock.objects.get(poste=poste)
                if stock.valeur_monetaire <= 0:
                    continue
                
                # Utiliser le forecasting pour calculer l'épuisement
                resultats = ForecastingService.prevoir_recettes(
                    poste,
                    nb_jours_future=365
                )
                
                if not resultats['success']:
                    continue
                
                df_prev = resultats['predictions']
                stock_restant_simule = float(stock.valeur_monetaire)
                date_epuisement = None
                vente_moyenne_calculee = 0
                
                # Simuler l'épuisement du stock
                for index, row in df_prev.iterrows():
                    vente_prevue = row['montant_prevu']
                    stock_restant_simule -= vente_prevue
                    
                    if stock_restant_simule <= 0:
                        date_epuisement = row['date'].date()
                        # Calculer la vente moyenne sur la période
                        jours_ecoules = (date_epuisement - date.today()).days
                        if jours_ecoules > 0:
                            vente_moyenne_calculee = float(stock.valeur_monetaire) / jours_ecoules
                        break
                
                # Si le stock n'est pas épuisé en 365 jours
                if date_epuisement is None:
                    date_epuisement = date.today() + timedelta(days=365)
                    vente_moyenne_calculee = df_prev['montant_prevu'].mean()
                
                # Vérifier si dépasse la date limite
                if date_epuisement > date_limite:
                    jours_restants = (date_epuisement - date.today()).days
                    
                    postes_grand_stock.append({
                        'poste': poste,
                        'stock_restant': int(stock.valeur_monetaire),
                        'date_epuisement': date_epuisement,
                        'jours_restants': jours_restants,
                        'vente_moyenne': vente_moyenne_calculee,
                        'depasse_limite': True,
                        'methode_calcul': 'forecasting'
                    })
                    
            except Exception as e:
                import logging
                logger = logging.getLogger('supper')
                logger.error(f"Erreur calcul grand stock pour {poste.nom}: {str(e)}")
                continue
        
        return postes_grand_stock

    
    @classmethod
    def get_postes_avec_risque_baisse(cls):
        """Version améliorée utilisant le service d'évolution"""
        from inventaire.services.evolution_service import EvolutionService
        
        postes_risque = EvolutionService.identifier_postes_en_baisse(
            type_analyse='annuel',
            seuil_baisse=-5
        )
        
        return postes_risque
    
    @classmethod
    def get_postes_avec_grand_stock(cls):
        """
        Retourne les postes dont la date d'épuisement du stock dépasse le 1er décembre
        de l'année en cours
        """
        from inventaire.models import GestionStock
        from datetime import date, timedelta
        from django.db.models import Sum, Count
        
        postes_grand_stock = []

        # Date limite : 31 décembre de l'année en cours
        date_limite = date(date.today().year, 12, 31)
        date_fin = date.today()
        date_debut = date_fin - timedelta(days=30)
        
        # Parcourir tous les postes actifs
        for poste in Poste.objects.filter(is_active=True):
            # Récupérer le stock actuel
            try:
                stock = GestionStock.objects.get(poste=poste)
                if stock.valeur_monetaire <= 0:
                    continue
                    
                # Calculer la vente moyenne journalière
                ventes_mois = RecetteJournaliere.objects.filter(
                    poste=poste,
                    date__range=[date_debut, date_fin]
                ).aggregate(
                    total=Sum('montant_declare'),
                    nombre_jours=Count('id')
                )
                
                if ventes_mois['total'] and ventes_mois['nombre_jours'] > 0:
                    vente_moyenne = ventes_mois['total'] / ventes_mois['nombre_jours']
                    
                    # Calculer les jours restants et la date d'épuisement
                    jours_restants = int(stock.valeur_monetaire / vente_moyenne)
                    date_epuisement = date_fin + timedelta(days=jours_restants)
                    
                    # Si la date d'épuisement dépasse le 1er décembre, l'ajouter à la liste
                    if date_epuisement > date_limite:
                        postes_grand_stock.append({
                            'poste': poste,
                            'stock_restant': int(stock.valeur_monetaire),
                            'date_epuisement': date_epuisement,
                            'jours_restants': jours_restants,
                            'vente_moyenne': float(vente_moyenne),
                            'depasse_limite': True
                        })
                        
            except GestionStock.DoesNotExist:
                continue
        
        return postes_grand_stock
        
    @classmethod
    def get_postes_avec_taux_deperdition(cls):
        """Retourne les postes avec leur dernier taux de déperdition"""
        postes_taux = []
        
        for poste in Poste.objects.filter(is_active=True):
            # Récupérer le dernier taux de déperdition
            derniere_recette = RecetteJournaliere.objects.filter(
                poste=poste,
                taux_deperdition__isnull=False
            ).order_by('-date').first()
            
            if derniere_recette:
                postes_taux.append({
                    'poste': poste,
                    'taux_deperdition': derniere_recette.taux_deperdition,
                    'date_calcul': derniere_recette.date,
                    'alerte': derniere_recette.get_couleur_alerte()
                })
        
        return postes_taux
    
    @classmethod
    def get_postes_taux_automatique(cls):
        """
        Retourne les postes à sélectionner automatiquement selon leur taux de déperdition
        Sélectionne automatiquement si taux < -10%
        """
        postes_auto = []
        
        for poste in Poste.objects.filter(is_active=True):
            derniere_recette = RecetteJournaliere.objects.filter(
                poste=poste,
                taux_deperdition__isnull=False
            ).order_by('-date').first()
            
            if derniere_recette and derniere_recette.taux_deperdition < -10:
                postes_auto.append({
                    'poste': poste,
                    'taux_deperdition': derniere_recette.taux_deperdition,
                    'date_calcul': derniere_recette.date,
                    'selection_auto': True
                })
        
        return postes_auto

    @classmethod
    def get_tous_postes_presence_admin(cls):
        """Retourne TOUS les postes pour la présence administrative"""
        return Poste.objects.filter(is_active=True).order_by('nom')
        
    def save(self, *args, **kwargs):
            """Calculs automatiques avant sauvegarde"""
            # Si c'est un risque de baisse annuel, calculer automatiquement
            if self.motif == MotifInventaire.RISQUE_BAISSE:
                self.calculer_risque_baisse_annuel()
            
            # Si c'est un risque de grand stock, calculer la date d'épuisement
            if self.motif == MotifInventaire.GRAND_STOCK:
                self.calculer_date_epuisement_stock()
            
            # Si c'est pour taux de déperdition et qu'il n'y a pas de taux précédent
            if self.motif == MotifInventaire.TAUX_DEPERDITION and not self.taux_deperdition_precedent:
                # Récupérer le dernier taux de déperdition calculé pour ce poste
                derniere_recette = RecetteJournaliere.objects.filter(
                    poste=self.poste,
                    taux_deperdition__isnull=False
                ).order_by('-date').first()
                
                if derniere_recette:
                    self.taux_deperdition_precedent = derniere_recette.taux_deperdition
            
            super().save(*args, **kwargs)
class InventaireMensuel(models.Model):
    """
    Modèle pour organiser les inventaires par mois
    Permet d'activer/désactiver des jours spécifiques pour la saisie
    """
    
    titre = models.CharField(
        max_length=200,
        verbose_name=_("Titre de l'inventaire"),
        help_text=_("Titre descriptif pour cet inventaire mensuel")
    )
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='inventaires_mensuels',
        verbose_name=_("Poste"),
        #default=1
       #null=True
        null=True,  # ← Gardez null=True temporairement
        blank=True
    )
    programmation = models.OneToOneField(
        ProgrammationInventaire,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventaire_mensuel',
        verbose_name=_("Programmation associée")
    )

    motif = models.CharField(
        max_length=20,
        choices=MotifInventaire.choices,
        verbose_name=_("Motif de l'inventaire"),
        default=MotifInventaire.TAUX_DEPERDITION
    )
     # Données pour le motif
    taux_deperdition_precedent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux de déperdition précédent (%)")
    )
    
    risque_baisse_annuel = models.BooleanField(
        default=False,
        verbose_name=_("Risque de baisse annuel détecté")
    )
    
    date_epuisement_stock = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date prévue d'épuisement du stock")
    )
    
    mois = models.CharField(
        max_length=2,
        choices=MoisChoices.choices,
        verbose_name=_("Mois")
    )
    
    annee = models.IntegerField(
        verbose_name=_("Année"),
        help_text=_("Année de l'inventaire")
    )
    
    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
        help_text=_("Description détaillée de cet inventaire mensuel")
    )
    
    nombre_jours_saisis = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de jours saisis")
    )
    
    # Métadonnées
    cree_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        related_name='inventaires_mensuels_crees',
        verbose_name=_("Créé par")
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )
    actif = models.BooleanField(
        default=True,
        verbose_name=_("Inventaire actif"),
        help_text=_("Indique si cet inventaire mensuel est en cours")
    )
    
    # def get_jours_actifs_display(self):
    #     """Retourne une représentation textuelle des jours actifs"""
    #     if not self.jours_actifs:
    #         return "Aucun jour sélectionné"
        
    #     if isinstance(self.jours_actifs, list):
    #         if len(self.jours_actifs) == 0:
    #             return "Aucun jour sélectionné"
    #         elif len(self.jours_actifs) <= 5:
    #             return f"Jours: {', '.join(map(str, sorted(self.jours_actifs)))}"
    #         else:
    #             return f"{len(self.jours_actifs)} jours sélectionnés"
        
    #     return str(self.jours_actifs)
    
    total_vehicules = models.IntegerField(
        default=0,
        verbose_name=_("Total véhicules du mois")
    )
    
    total_recettes_declarees = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Total recettes déclarées")
    )
    
    total_recettes_potentielles = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Total recettes potentielles")
    )
    
    taux_deperdition_moyen = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux de déperdition moyen (%)")
    )
    
    nombre_jours_impertinents = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de jours impertinents")
    )

    def clean(self):
        """Validation du modèle"""
        from django.core.exceptions import ValidationError
        import json
        
        # Validation et nettoyage des jours_actifs
        if self.jours_actifs is not None:
            if not isinstance(self.jours_actifs, list):
                if isinstance(self.jours_actifs, str):
                    try:
                        self.jours_actifs = json.loads(self.jours_actifs)
                    except (json.JSONDecodeError, ValueError):
                        self.jours_actifs = []
                else:
                    self.jours_actifs = []
            
            # Valider que tous les éléments sont des entiers valides
            jours_valides = []
            for jour in self.jours_actifs:
                try:
                    jour_int = int(jour)
                    if 1 <= jour_int <= 31:
                        jours_valides.append(jour_int)
                except (ValueError, TypeError):
                    continue
            
            self.jours_actifs = sorted(list(set(jours_valides)))  # Supprimer les doublons
    class Meta:
        verbose_name = _("Inventaire mensuel")
        verbose_name_plural = _("Inventaires mensuels")
        unique_together = [['mois', 'poste']]
        ordering = ['-mois', 'poste__nom']
    
    def save(self, *args, **kwargs):
        """Surcharge pour validation automatique"""
        self.clean()
        super().save(*args, **kwargs)
    
    def get_mois_display(self):
        """Retourne le nom du mois en français"""
        if isinstance(self.mois, str):
            mois_num = int(self.mois)
        else:
            mois_num = self.mois
            
        mois_noms = {
            1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
            5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
            9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
        }
        return mois_noms.get(mois_num, f'Mois {mois_num}')

    def get_nombre_postes(self):
        """Retourne le nombre de postes dans le système"""
        from accounts.models import Poste
        return Poste.objects.filter(is_active=True).count()
    
    def get_calendrier_mois(self):
        """Génère le calendrier du mois sous forme de grille"""
        import calendar
        mois_int = int(self.mois)
        cal = calendar.monthcalendar(int(self.annee), mois_int)
        return cal
    
    # def est_jour_actif(self, jour):
    #     """Vérifie si un jour donné est actif pour la saisie"""
    #     if not self.jours_actifs or not isinstance(self.jours_actifs, list):
    #         return False
    #     return jour in self.jours_actifs
    
    # def activer_jour(self, jour):
    #     """Active un jour pour la saisie"""
    #     if not self.jours_actifs:
    #         self.jours_actifs = []
    #     elif not isinstance(self.jours_actifs, list):
    #         self.jours_actifs = []
            
    #     if jour not in self.jours_actifs and 1 <= jour <= 31:
    #         self.jours_actifs.append(jour)
    #         self.jours_actifs = sorted(self.jours_actifs)
    #         self.save()
    
    # def desactiver_jour(self, jour):
    #     """Désactive un jour pour la saisie"""
    #     if self.jours_actifs and isinstance(self.jours_actifs, list) and jour in self.jours_actifs:
    #         self.jours_actifs.remove(jour)
    #         self.save()
    
    # def activer_jours_ouvres(self):
    #     """Active automatiquement tous les jours ouvrés (lundi à vendredi)"""
    #     import calendar
        
    #     mois_int = int(self.mois)
    #     cal = calendar.monthcalendar(int(self.annee), mois_int)
    #     jours_ouvres = []
        
    #     for semaine in cal:
    #         for i, jour in enumerate(semaine):
    #             if jour != 0 and i < 5:  # Lundi à vendredi
    #                 jours_ouvres.append(jour)
        
    #     self.jours_actifs = sorted(jours_ouvres)
    #     self.save()
        
    def generer_configurations_jours(self):
        """Génère automatiquement les ConfigurationJour pour tous les jours actifs"""
        from datetime import date
        
        if not self.jours_actifs or not isinstance(self.jours_actifs, list):
            return []
        
        configurations_creees = []
        
        for jour in self.jours_actifs:
            try:
                mois_int = int(self.mois)
                date_jour = date(int(self.annee), mois_int, jour)
                
                # 🔧 CORRECTION : Import local pour éviter circular import
                from . import models as inv_models
                
                config, created = inv_models.ConfigurationJour.objects.get_or_create(
                    date=date_jour,
                    defaults={
                        'statut': inv_models.StatutJour.OUVERT,
                        'cree_par': self.cree_par,
                        'commentaire': f'Généré automatiquement depuis {self.titre}'
                    }
                )
                
                if created:
                    configurations_creees.append(config)
                    
            except ValueError:
                # Jour invalide (ex: 31 février)
                continue
        
        return configurations_creees
    
    # 🔧 CORRECTION : Une seule classe Meta
    class Meta:
        verbose_name = _("Inventaire mensuel")
        verbose_name_plural = _("Inventaires mensuels")
        unique_together = [['mois', 'annee']]
        ordering = ['-annee', '-mois']
        indexes = [
            models.Index(fields=['mois', 'annee']),
            models.Index(fields=['actif']),
        ]
    
    def __str__(self):
        return f"{self.titre} - {self.get_mois_display()} {self.annee}"
    
    def get_absolute_url(self):
        return reverse('admin:inventaire_inventairemensuel_change', kwargs={'object_id': self.pk})
    
    def consolider_donnees(self):
        """
        Consolide les données du mois à partir des inventaires journaliers
        """
        from datetime import date
        from calendar import monthrange
        from django.db.models import Sum, Avg, Count
        
        # Déterminer le début et la fin du mois
        annee = self.mois.year
        mois = self.mois.month
        debut_mois = date(annee, mois, 1)
        dernier_jour = monthrange(annee, mois)[1]
        fin_mois = date(annee, mois, dernier_jour)
        
        # Récupérer tous les inventaires du mois
        inventaires = InventaireJournalier.objects.filter(
            poste=self.poste,
            date__range=[debut_mois, fin_mois]
        )
        
        # Récupérer toutes les recettes du mois
        recettes = RecetteJournaliere.objects.filter(
            poste=self.poste,
            date__range=[debut_mois, fin_mois]
        )
        
        # Calculer les statistiques
        self.nombre_jours_saisis = inventaires.count()
        self.total_vehicules = inventaires.aggregate(
            total=Sum('total_vehicules')
        )['total'] or 0
        
        self.total_recettes_declarees = recettes.aggregate(
            total=Sum('montant_declare')
        )['total'] or float('0')
        
        self.total_recettes_potentielles = recettes.aggregate(
            total=Sum('recette_potentielle')
        )['total'] or float('0')
        
        # Calculer le taux de déperdition moyen
        if self.total_recettes_potentielles > 0:
            ecart = self.total_recettes_declarees - self.total_recettes_potentielles
            self.taux_deperdition_moyen = (ecart / self.total_recettes_potentielles) * 100
        
        # Compter les jours impertinents
        self.nombre_jours_impertinents = ConfigurationJour.objects.filter(
            date__range=[debut_mois, fin_mois],
            statut=StatutJour.IMPERTINENT
        ).count()
        
        self.save()
        
        return self
    
class StatutJour(models.TextChoices):
    """Statut d'un jour pour la saisie d'inventaire"""
    OUVERT = 'ouvert', _('Ouvert pour saisie')
    FERME = 'ferme', _('Fermé - saisie verrouillée')
    IMPERTINENT = 'impertinent', _('Journée impertinente')


class PeriodeHoraire(models.TextChoices):
    """Créneaux horaires pour l'inventaire"""
    H08_09 = '08h-09h', _('08h-09h')
    H09_10 = '09h-10h', _('09h-10h')
    H10_11 = '10h-11h', _('10h-11h')
    H11_12 = '11h-12h', _('11h-12h')
    H12_13 = '12h-13h', _('12h-13h')
    H13_14 = '13h-14h', _('13h-14h')
    H14_15 = '14h-15h', _('14h-15h')
    H15_16 = '15h-16h', _('15h-16h')
    H16_17 = '16h-17h', _('16h-17h')
    H17_18 = '17h-18h', _('17h-18h')

class TypeConfiguration(models.TextChoices):
    """Types de configuration de jour"""
    INVENTAIRE = 'inventaire', _('Configuration Inventaire')
    RECETTE = 'recette', _('Configuration Recette')

class StatutJour(models.TextChoices):
    """Statut d'un jour pour la saisie d'inventaire"""
    # Suppression de OUVERT et FERME, on garde uniquement IMPERTINENT
    IMPERTINENT = 'impertinent', _('Journée impertinente')
    NORMAL = 'normal', _('Journée normale')  # Ajout d'un statut par défaut

class ConfigurationJour(models.Model):
    """
    Configuration des jours ouverts/fermés pour la saisie d'inventaire ET de recettes
    Permet aux administrateurs de contrôler quels jours sont disponibles pour la saisie
    CORRECTION : Support amélioré pour configurations globales et par poste
    """
    
    
    type_config = models.CharField(
        max_length=15,
        choices=TypeConfiguration.choices,
        default=TypeConfiguration.INVENTAIRE,
        verbose_name=_("Type de configuration")
    )
    
    date = models.DateField(
        unique=True,
        verbose_name=_("Date"),
        help_text=_("Date concernée par cette configuration")
    )
    poste = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='configurations_jours',
        verbose_name=_("Poste"),
        help_text=_("Si spécifié, la configuration ne s'applique qu'à ce poste. Si vide, s'applique à tous les postes.")
    )

    statut = models.CharField(
        max_length=15,
        choices=StatutJour.choices,
        default=StatutJour.NORMAL,  # Changement du défaut
        verbose_name=_("Statut du jour")
    )
    
    # 🔧 CORRECTION : Types de saisie séparés
    permet_saisie_inventaire = models.BooleanField(
        default=True,
        verbose_name=_("Permet saisie inventaire"),
        help_text=_("Autorise la saisie d'inventaires pour cette date")
    )
    
    permet_saisie_recette = models.BooleanField(
        default=True,
        verbose_name=_("Permet saisie recette"),
        help_text=_("Autorise la saisie de recettes pour cette date")
    )
    
    # Métadonnées de gestion
    cree_par = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        related_name='jours_configures',
        verbose_name=_("Configuré par")
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    commentaire = models.TextField(
        blank=True,
        verbose_name=_("Commentaire"),
        help_text=_("Raison du marquage ou notes particulières")
    )
    
    class Meta:
        verbose_name = _("Configuration de jour")
        verbose_name_plural = _("Configurations de jours")
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['statut']),
        ]
    
    def __str__(self):
        return f"{self.date.strftime('%d/%m/%Y')} - {self.get_statut_display()}"
    
    # 🔧 CORRECTION : Méthodes de vérification améliorées
    def get_config_summary(self):
        """Résumé de la configuration pour l'admin"""
        summary_parts = []
        
        # Statut principal
        summary_parts.append(f"Statut: {self.get_statut_display()}")
        
        # Permissions de saisie
        permissions = []
        if getattr(self, 'permet_saisie_inventaire', False):
            permissions.append("Inventaire")
        if getattr(self, 'permet_saisie_recette', False):
            permissions.append("Recette")
        
        if permissions:
            summary_parts.append(f"Autorisé: {', '.join(permissions)}")
        else:
            summary_parts.append("Aucune saisie autorisée")
        
        # Poste ou global
        if self.poste:
            summary_parts.append(f"Poste: {self.poste.code}")
        else:
            summary_parts.append("Configuration globale")
        
        return " | ".join(summary_parts)
    
    def permet_saisie_inventaire_display(self):
        """Affichage pour l'admin - Permission inventaire"""
        return "✓ Oui" if getattr(self, 'permet_saisie_inventaire', False) else "✗ Non"
    permet_saisie_inventaire_display.short_description = 'Inventaire autorisé'
    
    def permet_saisie_recette_display(self):
        """Affichage pour l'admin - Permission recette"""
        return "✓ Oui" if getattr(self, 'permet_saisie_recette', False) else "✗ Non"
    permet_saisie_recette_display.short_description = 'Recette autorisée'

    def est_jour_ouvert_pour_inventaire(cls, date, poste=None):
        """Vérifie si la saisie d'inventaire est autorisée pour un jour donné"""
        try:
            # Chercher configuration spécifique au poste
            if poste:
                config = cls.objects.filter(date=date, poste=poste).first()
                if config:
                    return (config.statut == StatutJour.OUVERT and 
                            getattr(config, 'permet_saisie_inventaire', False))
            
            # Chercher configuration globale
            config_globale = cls.objects.filter(date=date, poste__isnull=True).first()
            if config_globale:
                return (config_globale.statut == StatutJour.OUVERT and 
                        getattr(config_globale, 'permet_saisie_inventaire', False))
            
            # Par défaut : fermé si pas de configuration
            return False
            
        except Exception:
            return False
    
    @classmethod
    def est_jour_ouvert_pour_recette(cls, date, poste=None):
        """Vérifie si la saisie de recette est autorisée pour un jour donné"""
        try:
            # Chercher configuration spécifique au poste
            if poste:
                config = cls.objects.filter(date=date, poste=poste).first()
                if config:
                    return (config.statut == StatutJour.OUVERT and 
                            getattr(config, 'permet_saisie_recette', False))
            
            # Chercher configuration globale
            config_globale = cls.objects.filter(date=date, poste__isnull=True).first()
            if config_globale:
                return (config_globale.statut == StatutJour.OUVERT and 
                        getattr(config_globale, 'permet_saisie_recette', False))
            
            # Par défaut : fermé si pas de configuration
            return False
            
        except Exception:
            return False
    
    # 🔧 CORRECTION : Méthode globale pour les cas génériques
    @classmethod
    def est_jour_ouvert(cls, date, poste=None):
        """Méthode de compatibilité - vérifie pour inventaire"""
        return cls.est_jour_ouvert_pour_inventaire(date, poste)
    
    @classmethod
    def ouvrir_jour_global(cls, date, admin_user, commentaire="", permet_inventaire=True, permet_recette=True):
        """Ouvre un jour pour tous les postes"""
        config, created = cls.objects.get_or_create(
            date=date,
            poste=None,  # Configuration globale
            defaults={
                'statut': StatutJour.OUVERT,
                'permet_saisie_inventaire': permet_inventaire,
                'permet_saisie_recette': permet_recette,
                'cree_par': admin_user,
                'commentaire': commentaire or f'Jour ouvert globalement le {date}'
            }
        )
        
        if not created:
            # Mettre à jour si existe déjà
            config.statut = StatutJour.OUVERT
            config.permet_saisie_inventaire = permet_inventaire
            config.permet_saisie_recette = permet_recette
            if commentaire:
                config.commentaire = commentaire
            config.save()
        
        return config
    
    @classmethod
    def ouvrir_jour_pour_poste(cls, date, poste, admin_user, commentaire="", permet_inventaire=True, permet_recette=True):
        """Ouvre un jour pour un poste spécifique"""
        config, created = cls.objects.get_or_create(
            date=date,
            poste=poste,
            defaults={
                'statut': StatutJour.OUVERT,
                'permet_saisie_inventaire': permet_inventaire,
                'permet_saisie_recette': permet_recette,
                'cree_par': admin_user,
                'commentaire': commentaire or f'Jour ouvert pour {poste.nom} le {date}'
            }
        )
        
        if not created:
            config.statut = StatutJour.OUVERT
            config.permet_saisie_inventaire = permet_inventaire
            config.permet_saisie_recette = permet_recette
            if commentaire:
                config.commentaire = commentaire
            config.save()
        
        return config
    
    @classmethod
    def fermer_jour(cls, date, admin_user, poste=None, commentaire=""):
        """Ferme un jour (global ou pour un poste spécifique)"""
        try:
            if poste:
                config = cls.objects.get(date=date, poste=poste)
            else:
                config = cls.objects.get(date=date, poste__isnull=True)
            
            config.statut = StatutJour.FERME
            config.permet_saisie_inventaire = False
            config.permet_saisie_recette = False
            if commentaire:
                config.commentaire = commentaire
            config.save()
            
            return config
            
        except cls.DoesNotExist:
            # Créer une configuration fermée si elle n'existe pas
            return cls.objects.create(
                date=date,
                poste=poste,
                statut=StatutJour.FERME,
                permet_saisie_inventaire=False,
                permet_saisie_recette=False,
                cree_par=admin_user,
                commentaire=commentaire or f'Jour fermé le {timezone.now()}'
            )
    
    @classmethod
    def est_jour_impertinent(cls, date):
        """Vérifie si un jour est marqué comme impertinent"""
        try:
            config = cls.objects.get(date=date)
            return config.statut == StatutJour.IMPERTINENT
        except cls.DoesNotExist:
            return False
    @classmethod
    def marquer_impertinent(cls, date, admin_user, commentaire=""):
        """Marque un jour comme impertinent"""
        config, created = cls.objects.get_or_create(
            date=date,
            defaults={
                'statut': StatutJour.IMPERTINENT,
                'cree_par': admin_user,
                'commentaire': commentaire
            }
        )
        
        if not created and config.statut != StatutJour.IMPERTINENT:
            config.statut = StatutJour.IMPERTINENT
            config.commentaire = commentaire
            config.save()
        
        return config
    
   
    
    def clean(self):
        """Validation personnalisée du modèle"""
        from django.core.exceptions import ValidationError
        
        # Validation de la date
        if not self.date:
            raise ValidationError("La date est obligatoire.")
        
        # Vérifier l'unicité date/poste
        existing = ConfigurationJour.objects.filter(
            date=self.date, 
            poste=self.poste
        ).exclude(pk=self.pk if self.pk else 0)
        
        if existing.exists():
            if self.poste:
                raise ValidationError(
                    f"Une configuration existe déjà pour le poste {self.poste.nom} "
                    f"à la date du {self.date.strftime('%d/%m/%Y')}."
                )
            else:
                raise ValidationError(
                    f"Une configuration globale existe déjà "
                    f"pour la date du {self.date.strftime('%d/%m/%Y')}."
                )
    
    def save(self, *args, **kwargs):
        """Sauvegarde avec validation"""
        self.full_clean()  # Appelle clean() automatiquement
        super().save(*args, **kwargs)
# ===================================================================
# UTILISATION DANS LES VUES
# ===================================================================

# 🔧 EXEMPLE d'utilisation dans une vue de saisie de recette :

"""
from inventaire.models import ConfigurationJour

def saisie_recette_view(request, poste_id, date):
    poste = get_object_or_404(Poste, id=poste_id)
    date_obj = datetime.strptime(date, '%Y-%m-%d').date()
    
    # Vérifier si le jour est ouvert pour les recettes
    if not ConfigurationJour.est_jour_ouvert_pour_recette(date_obj, poste):
        messages.error(request, f"La saisie de recettes n'est pas autorisée pour le {date_obj} au poste {poste.nom}")
        return redirect('some_redirect_url')
    
    # Continuer avec la logique de saisie...
"""

# 🔧 EXEMPLE d'utilisation pour ouvrir/fermer des jours :

"""
# Ouvrir un jour pour tous les postes (inventaire + recettes)
ConfigurationJour.ouvrir_jour_global(
    date=date.today(),
    admin_user=request.user,
    commentaire="Ouverture exceptionnelle",
    permet_inventaire=True,
    permet_recette=True
)

# Ouvrir seulement pour un poste spécifique
ConfigurationJour.ouvrir_jour_pour_poste(
    date=date.today(),
    poste=mon_poste,
    admin_user=request.user,
    commentaire="Ouverture pour rattrapage"
)

# Fermer un jour
ConfigurationJour.fermer_jour(
    date=date.today(),
    admin_user=request.user,
    commentaire="Jour férié"
)
"""

class InventaireJournalier(models.Model):
    """
    Modèle principal pour l'inventaire journalier d'un poste
    Un enregistrement par jour et par poste
    """
    
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='inventaires',
        verbose_name=_("Poste")
    )
    type_inventaire = models.CharField(
        max_length=20,
        choices=[
            ('normal', 'Inventaire Normal'),
            ('administratif', 'Inventaire Administratif')
        ],
        default='normal',
        verbose_name=_("Type d'inventaire")
    )
    date = models.DateField(
        verbose_name=_("Date de l'inventaire"),
        help_text=_("Date pour laquelle l'inventaire est effectué")
    )
    
    agent_saisie = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        related_name='inventaires_saisis',
        verbose_name=_("Agent de saisie")
    )
    
    
    
    # Totaux calculés automatiquement
    modifiable_par_agent = models.BooleanField(
        default=True,
        verbose_name=_("Modifiable par l'agent"),
        help_text=_("False après première soumission, seul admin peut modifier")
    )
    
    # Ajout d'un champ pour tracer qui a modifié en dernier
    derniere_modification_par = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventaires_modifies',
        verbose_name=_("Dernière modification par")
    )

    total_vehicules = models.IntegerField(
        default=0,
        verbose_name=_("Total véhicules comptés"),
        help_text=_("Somme de tous les véhicules comptés dans les périodes")
    )
    
    nombre_periodes_saisies = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de périodes saisies"),
        help_text=_("Nombre de créneaux horaires avec données")
    )
    
    # Métadonnées
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )
    
    observations = models.TextField(
        blank=True,
        verbose_name=_("Observations"),
        help_text=_("Notes particulières sur cet inventaire")
    )
    
    class Meta:
        verbose_name = _("Inventaire journalier")
        verbose_name_plural = _("Inventaires journaliers")
        unique_together = [['poste', 'date']]
        ordering = ['-date', 'poste__nom']
        indexes = [
            models.Index(fields=['poste', '-date']),
            models.Index(fields=['date']),
            models.Index(fields=['agent_saisie']),
        ]
    
    def __str__(self):
        return f"Inventaire {self.poste.nom} - {self.date.strftime('%d/%m/%Y')}"
    
    def get_absolute_url(self):
        return reverse('inventaire_detail', kwargs={'pk': self.pk})
    
    def peut_etre_modifie_par(self, user):
        """Vérifie si l'inventaire peut être modifié par l'utilisateur"""
        # Les admins peuvent toujours modifier
        if user.is_admin:
            return True
        
        # Si l'inventaire n'a jamais été sauvegardé ou s'il n'a pas de détails
        if not self.pk or not self.details_periodes.exists():
            return True
        
        # Une fois saisi avec des données, seuls les admins peuvent modifier
        return False
    def soumettre(self):
        """Soumet l'inventaire - ne peut plus être modifié par l'agent après"""
        self.modifiable_par_agent = False
        self.save()
    
    # # def verrouiller(self, user=None):
    # #     """Verrouille l'inventaire"""
    # #     if not self.verrouille:
    # #         self.verrouille = True
    # #         self.save()
            
    # #         # Log de l'action
    # #         if user:
    # #             from common.utils import log_user_action
    # #             log_user_action(
    # #                 user, 
    # #                 "Verrouillage inventaire",
    # #                 f"Poste: {self.poste.nom}, Date: {self.date}"
    #             )
    
    def calculer_moyenne_horaire(self):
        """Calcule la moyenne de véhicules par heure"""
        if self.nombre_periodes_saisies > 0:
            return self.total_vehicules / self.nombre_periodes_saisies
        return 0
    
    def estimer_total_24h(self):
        """Estime le total de véhicules sur 24h basé sur la moyenne"""
        moyenne = self.calculer_moyenne_horaire()
        return moyenne * 24
    
    def calculer_recette_potentielle(self):
        """
        Calcule la recette potentielle selon l'algorithme correct
        """
        details = self.details_periodes.all()
        
        if not details.exists():
            return Decimal('0')
        
        # Calcul avec Decimal pour la précision
        somme_vehicules = Decimal(str(sum(detail.nombre_vehicules for detail in details)))
        nombre_periodes = Decimal(str(details.count()))
        
        if nombre_periodes > 0:
            # Moyenne horaire
            moyenne_horaire = somme_vehicules / nombre_periodes
            
            # Estimation 24h
            estimation_24h = moyenne_horaire * Decimal('24')
            
            # Véhicules effectifs (75%)
            vehicules_effectifs = estimation_24h * Decimal('0.75')
            
            # Recette potentielle
            recette_potentielle = vehicules_effectifs * Decimal('500')
            
            # Arrondir à l'entier le plus proche
            return recette_potentielle.quantize(Decimal('1'))
        
        return Decimal('0')
    
    def get_statistiques_detaillees(self):
        """Retourne des statistiques détaillées pour debug"""
        details = self.details_periodes.all()
        
        if not details.exists():
            return {
                'erreur': 'Aucun détail de période trouvé'
            }
        
        somme_vehicules = sum(detail.nombre_vehicules for detail in details)
        nombre_periodes = details.count()
        moyenne_horaire = somme_vehicules / nombre_periodes
        estimation_24h = moyenne_horaire * 24
        vehicules_effectifs = estimation_24h * 0.75
        recette_potentielle = vehicules_effectifs * 500
        
        return {
            'somme_vehicules': somme_vehicules,
            'nombre_periodes': nombre_periodes,
            'moyenne_horaire': round(moyenne_horaire, 2),
            'estimation_24h': round(estimation_24h, 2),
            'vehicules_effectifs_75%': round(vehicules_effectifs, 2),
            'recette_potentielle': round(recette_potentielle, 2)
        }
    
    def recalculer_totaux(self):
        """Recalcule les totaux basés sur les détails de périodes"""
        details = self.details_periodes.all()
        self.total_vehicules = sum(detail.nombre_vehicules for detail in details)
        self.nombre_periodes_saisies = details.count()
        self.save(update_fields=['total_vehicules', 'nombre_periodes_saisies'])
    
    def save(self, *args, **kwargs):
        """Surcharge pour recalculer automatiquement les totaux"""
        # Toujours recalculer la recette potentielle associée si elle existe
        super().save(*args, **kwargs)
        
        # Recalculer les totaux après la sauvegarde si nécessaire
        if hasattr(self, '_recalculer_totaux'):
            self.recalculer_totaux()
        
        # Mettre à jour la recette si elle existe
        try:
            if hasattr(self, 'recette'):
                self.recette.calculer_indicateurs()
                self.recette.save()
        except:
            pass

    
    def link_to_inventaire_mensuel(self):
    # """Lie cet inventaire journalier à un inventaire mensuel s'il existe"""
        from datetime import date
        # Importer le modèle PosteInventaireMensuel localement pour éviter les problèmes de dépendance circulaire
        from .models import PosteInventaireMensuel

        # Chercher l'inventaire mensuel correspondant
        inventaire_mensuel = InventaireMensuel.objects.filter(
            mois=self.date.month,
            annee=self.date.year,
            is_active=True
        ).first()
        
        if inventaire_mensuel:
            # Vérifier si le poste est dans l'inventaire mensuel
            return PosteInventaireMensuel.objects.filter(
                inventaire_mensuel=inventaire_mensuel,
                poste=self.poste
            ).first()
        
        return None


class DetailInventairePeriode(models.Model):
    """
    Détails de l'inventaire par période horaire
    Stocke le nombre de véhicules comptés pour chaque créneau
    """
    
    inventaire = models.ForeignKey(
        InventaireJournalier,
        on_delete=models.CASCADE,
        related_name='details_periodes',
        verbose_name=_("Inventaire")
    )
    
    periode = models.CharField(
        max_length=10,
        choices=PeriodeHoraire.choices,
        verbose_name=_("Période horaire")
    )
    
    nombre_vehicules = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(1000)],
        verbose_name=_("Nombre de véhicules"),
        help_text=_("Nombre de véhicules comptés pendant cette période")
    )
    
    # Métadonnées de saisie
    heure_saisie = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Heure de saisie")
    )
    
    modifie_le = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )
    
    observations_periode = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("Observations"),
        help_text=_("Notes sur cette période (incidents, conditions particulières)")
    )
    
    class Meta:
        verbose_name = _("Détail inventaire période")
        verbose_name_plural = _("Détails inventaire par période")
        unique_together = [['inventaire', 'periode']]
        ordering = ['periode']
        indexes = [
            models.Index(fields=['inventaire', 'periode']),
        ]
    
    def __str__(self):
        return f"{self.inventaire} - {self.get_periode_display()}: {self.nombre_vehicules}"
    
    def save(self, *args, **kwargs):
        """Surcharge pour recalculer les totaux de l'inventaire"""
        super().save(*args, **kwargs)
        
        # Recalculer directement sans sauvegarder l'inventaire
        self.inventaire.recalculer_totaux()


class RecetteJournaliere(models.Model):
    """
    Modèle pour la saisie des recettes déclarées par les chefs de poste
    """
    
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='recettes',
        verbose_name=_("Poste")
    )
    
    date = models.DateField(
        verbose_name=_("Date de la recette")
    )
    
    montant_declare = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name=_("Montant déclaré (FCFA)"),
        help_text=_("Recette déclarée par le chef de poste")
    )
    
    chef_poste = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        related_name='recettes_saisies',
        verbose_name=_("Chef de poste")
    )
    
    # Liaison avec l'inventaire pour calculs
    inventaire_associe = models.OneToOneField(
        InventaireJournalier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recette',
        verbose_name=_("Inventaire associé")
    )
    
    # Calculs automatiques
    recette_potentielle = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Recette potentielle (FCFA)"),
        help_text=_("Calculée automatiquement à partir de l'inventaire")
    )
    
    ecart = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Écart (FCFA)"),
        help_text=_("Différence entre recette déclarée et potentielle")
    )
    
    taux_deperdition = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux de déperdition (%)"),
        help_text=_("Taux de déperdition calculé")
    )
    stock_tickets_restant = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Stock de tickets restant"),
        help_text=_("Nombre de tickets restants après cette journée")
    )
    
    # État de la saisie
    # verrouille = models.BooleanField(
    #     default=False,
    #     verbose_name=_("Recette verrouillée")
    # )
    
    # valide = models.BooleanField(
    #     default=False,
    #     verbose_name=_("Recette validée")
    # )
    modifiable_par_chef = models.BooleanField(
        default=True,
        verbose_name=_("Modifiable par le chef"),
        help_text=_("False après première soumission, seul admin peut modifier")
    )
    derniere_modification_par = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recettes_modifiees',
        verbose_name=_("Dernière modification par")
    )
    # Métadonnées
    date_saisie = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de saisie")
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )
    prolongation_accordee = models.BooleanField(
        default=False,
        verbose_name="Prolongation accordée",
        help_text="Indique si une prolongation a été accordée pour ce poste"
    )
    observations = models.TextField(
        blank=True,
        verbose_name=_("Observations"),
        help_text=_("Commentaires sur cette recette")
    )
    
    
    class Meta:
        verbose_name = _("Recette journalière")
        verbose_name_plural = _("Recettes journalières")
        unique_together = [['poste', 'date']]
        ordering = ['-date', 'poste__nom']
        indexes = [
            models.Index(fields=['poste', '-date']),
            models.Index(fields=['date']),
            models.Index(fields=['chef_poste']),
        ]
    
    def __str__(self):
        return f"Recette {self.poste.nom} - {self.date.strftime('%d/%m/%Y')}: {self.montant_declare} FCFA"
    
    def get_absolute_url(self):
        return reverse('recette_detail', kwargs={'pk': self.pk})
    
    def calculer_indicateurs(self):
        """
        Calcule tous les indicateurs basés sur l'inventaire associé
        Version corrigée avec conversion sécurisée des Decimal
        """
        from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
        
        if not self.inventaire_associe:
            self.recette_potentielle = None
            self.ecart = None
            self.taux_deperdition = None
            # try:
            #     self.inventaire_associe = InventaireJournalier.objects.get(
            #         poste=self.poste,
            #         date=self.date
            #     )
            # except InventaireJournalier.DoesNotExist:
            #     self.recette_potentielle = Decimal('0')
            #     self.ecart = Decimal('0')
            #     self.taux_deperdition = Decimal('0')
            return
        
        inventaire = self.inventaire_associe
        details_periodes = inventaire.details_periodes.all()
        
        if not details_periodes.exists():
            self.recette_potentielle = None
            self.ecart = None
            self.taux_deperdition = None
            return
        
        try:
            # Utiliser uniquement Decimal pour tous les calculs
            somme_vehicules = Decimal(str(sum(detail.nombre_vehicules for detail in details_periodes)))
            nombre_periodes = Decimal(str(details_periodes.count()))
            
            if nombre_periodes > 0:
                moyenne_horaire = somme_vehicules / nombre_periodes
                estimation_24h = moyenne_horaire * Decimal('24')
                vehicules_effectifs = estimation_24h * Decimal('0.75')
                self.recette_potentielle = (vehicules_effectifs * Decimal('500')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            else:
                self.recette_potentielle = Decimal('0')
            
            # S'assurer que montant_declare est un Decimal valide
            if self.montant_declare is None:
                self.montant_declare = Decimal('0')
            elif not isinstance(self.montant_declare, Decimal):
                self.montant_declare = Decimal(str(self.montant_declare))
            
            # Calcul de l'écart
            self.ecart = self.montant_declare - self.recette_potentielle
            
            # Calcul du taux de déperdition
            if self.recette_potentielle > 0:
                self.taux_deperdition = (self.ecart / self.recette_potentielle) * Decimal('100')
            else:
                self.taux_deperdition = Decimal('0')
                
        except (TypeError, ValueError, InvalidOperation) as e:
            logger.error(f"Erreur calcul indicateurs: {str(e)}")
            self.recette_potentielle = Decimal('0')
            self.ecart = Decimal('0')
            self.taux_deperdition = Decimal('0')
        
        # Gestion des journées impertinentes
        self._gerer_journee_impertinente()
    
    def _gerer_journee_impertinente(self):
        """Gère les journées impertinentes selon le TD"""
        if self.taux_deperdition is None:
            return
        
        # Si TD > -5% : journée impertinente
        if self.taux_deperdition > Decimal('-5'):
            self._marquer_journee_impertinente()
    
    def _marquer_journee_impertinente(self):
        """Marque la journée comme impertinente"""
        from .models import ConfigurationJour
        
        ConfigurationJour.marquer_impertinent(
            self.date,
            self.chef_poste or self.inventaire_associe.agent_saisie,
            f"TD > -5%: {self.taux_deperdition:.2f}% - "
            f"Recettes déclarées ({self.montant_declare} FCFA) trop proches des potentielles ({self.recette_potentielle} FCFA)"
        )
    def get_couleur_alerte(self):
        """
        Retourne la couleur d'alerte selon le nouveau système:
        - TD > -5% : Impertinent (gris)
        - -5% >= TD >= -29.99% : Bon (vert)  
        - TD < -30% : Mauvais (rouge)
        """
        if self.taux_deperdition is None:
            return 'secondary'
        
        try:
        # Conversion sécurisée en float
            if isinstance(self.taux_deperdition, Decimal):
                td = Decimal(str(self.taux_deperdition))
            else:
                td = Decimal(self.taux_deperdition) if self.taux_deperdition else 0.0
        except (TypeError, ValueError, InvalidOperation):
            return 'secondary'
        
        if td > -5:
            return 'secondary'  # Gris - Impertinent
        elif -5 >= td >= -29.99:
            return 'success'    # Vert - Bon  
        else:  # td < -30
            return 'danger'     # Rouge - Mauvais
    
    def get_classe_css_alerte(self):
        """Retourne la classe CSS Bootstrap pour l'alerte"""
        couleur = self.get_couleur_alerte()
        return f'alert-{couleur}'
    
    def get_statut_deperdition(self):
        """Retourne le statut textuel de la déperdition"""
        if self.taux_deperdition is None:
            return 'Non calculé'
        
        try:
            td = float(self.taux_deperdition)
        except (TypeError, ValueError):
            return 'Non calculé'
        
        if td > -5:
            return 'Impertinent'
        elif -5 >= td >= -29.99:
            return 'Bon'
        else:
            return 'Mauvais'
    
    def get_chef_historique(self):
        """Récupère le chef de poste à la date de la recette"""
        if self.chef_poste:
            return self.chef_poste
        
        # Chercher dans l'historique
        historique = HistoriqueAffectation.get_affectation_a_date(
            self.poste, self.date, 'chef_poste'
        )
        return historique.utilisateur if historique else None
    

    def save(self, *args, **kwargs):
        """Surcharge pour calculer automatiquement les indicateurs avec gestion d'erreurs"""
        try:
            # Calculer les indicateurs avant la sauvegarde
            self.calculer_indicateurs()
        except (TypeError, ValueError, InvalidOperation) as e:
            logger.error(f"Erreur calcul indicateurs pour recette {self.pk}: {str(e)}")
            # Continuer la sauvegarde même si le calcul échoue
            self.taux_deperdition = None
            self.recette_potentielle = None
            self.ecart = None
        # Si pas de chef défini, chercher dans l'historique
        if not self.chef_poste:
            historique = HistoriqueAffectation.get_affectation_a_date(
                self.poste, self.date, 'chef_poste'
            )
            if historique:
                self.chef_poste = historique.utilisateur
        
        super().save(*args, **kwargs)

class ObjectifAnnuel(models.Model):
    """Modèle pour gérer les objectifs annuels par poste"""
    
    poste = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='objectifs_annuels',
        verbose_name=_("Poste")
    )
    
    annee = models.IntegerField(
        verbose_name=_("Année"),
        validators=[
            MinValueValidator(2020),
            MaxValueValidator(2099)
        ]
    )
    
    montant_objectif = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name=_("Montant objectif annuel (FCFA)")
    )
    
    cree_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        related_name='objectifs_crees',
        verbose_name=_("Créé par")
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière modification")
    )
    
    class Meta:
        verbose_name = _("Objectif annuel")
        verbose_name_plural = _("Objectifs annuels")
        unique_together = [['poste', 'annee']]
        ordering = ['-annee', 'poste__nom']
        indexes = [
            models.Index(fields=['poste', '-annee']),
        ]
    
    def __str__(self):
        return f"Objectif {self.poste.nom} - {self.annee}: {self.montant_objectif} FCFA"
class StatistiquesPeriodiques(models.Model):
    """
    Modèle pour stocker les statistiques calculées par période
    (hebdomadaire, mensuelle, trimestrielle, annuelle)
    """
    
    TYPE_PERIODE_CHOICES = [
        ('hebdomadaire', _('Hebdomadaire')),
        ('mensuelle', _('Mensuelle')),
        ('trimestrielle', _('Trimestrielle')),
        ('annuelle', _('Annuelle')),
    ]
    
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='statistiques',
        verbose_name=_("Poste")
    )
    
    type_periode = models.CharField(
        max_length=15,
        choices=TYPE_PERIODE_CHOICES,
        verbose_name=_("Type de période")
    )
    
    date_debut = models.DateField(
        verbose_name=_("Date de début de période")
    )
    
    date_fin = models.DateField(
        verbose_name=_("Date de fin de période")
    )
    
    # Données consolidées
    nombre_jours_actifs = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de jours avec données")
    )
    
    total_recettes_declarees = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Total recettes déclarées")
    )
    
    total_recettes_potentielles = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Total recettes potentielles")
    )
    
    taux_deperdition_moyen = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux de déperdition moyen (%)")
    )
    
    nombre_jours_impertinents = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de jours impertinents")
    )
    
    # Métadonnées
    date_calcul = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Date du calcul")
    )
    
    class Meta:
        verbose_name = _("Statistiques périodiques")
        verbose_name_plural = _("Statistiques périodiques")
        unique_together = [['poste', 'type_periode', 'date_debut']]
        ordering = ['-date_debut', 'poste__nom']
        indexes = [
            models.Index(fields=['poste', 'type_periode', '-date_debut']),
        ]
    
    def __str__(self):
        return f"Stats {self.get_type_periode_display()} {self.poste.nom} - {self.date_debut}"
    
    @classmethod
    def calculer_statistiques_periode(cls, poste, type_periode, date_debut, date_fin):
        """
        Calcule et sauvegarde les statistiques pour une période donnée
        """
        recettes = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[date_debut, date_fin]
        )
        
        if not recettes.exists():
            return None
        
        # Calculer les totaux
        total_declarees = sum(r.montant_declare for r in recettes)
        total_potentielles = sum(r.recette_potentielle or 0 for r in recettes)
        
        # Calculer le taux moyen
        taux_moyen = None
        if total_potentielles > 0:
            ecart_total = total_declarees - total_potentielles
            taux_moyen = (ecart_total / total_potentielles) * 100
        
        # Compter les jours impertinents
        jours_impertinents = ConfigurationJour.objects.filter(
            date__range=[date_debut, date_fin],
            statut=StatutJour.IMPERTINENT
        ).count()
        
        # Créer ou mettre à jour les statistiques
        stats, created = cls.objects.update_or_create(
            poste=poste,
            type_periode=type_periode,
            date_debut=date_debut,
            defaults={
                'date_fin': date_fin,
                'nombre_jours_actifs': recettes.count(),
                'total_recettes_declarees': total_declarees,
                'total_recettes_potentielles': total_potentielles,
                'taux_deperdition_moyen': taux_moyen,
                'nombre_jours_impertinents': jours_impertinents,
            }
        )
        
        return stats




class HistoriqueAffectation(models.Model):
    """Historique des affectations utilisateur-poste"""
    
    utilisateur = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.CASCADE,
        related_name='historique_affectations'
    )
    
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='historique_affectations'
    )
    
    type_affectation = models.CharField(
        max_length=20,
        choices=[
            ('chef_poste', 'Chef de poste'),
            ('agent_inventaire', 'Agent inventaire'),
        ]
    )
    
    date_debut = models.DateField(
        verbose_name="Date de début d'affectation"
    )
    
    date_fin = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de fin d'affectation"
    )
    
    actif = models.BooleanField(
        default=True,
        verbose_name="Affectation active"
    )
    
    class Meta:
        ordering = ['-date_debut']
        indexes = [
            models.Index(fields=['poste', 'date_debut']),
            models.Index(fields=['utilisateur', 'actif']),
        ]
    
    @classmethod
    def get_affectation_a_date(cls, poste, date, type_affectation):
        """Récupère l'affectation active à une date donnée"""
        return cls.objects.filter(
            models.Q(date_fin__gte=date) | models.Q(date_fin__isnull=True),
            poste=poste,
            type_affectation=type_affectation,
            date_debut__lte=date
        ).first()

class GestionStock(models.Model):
    """Modèle pour la gestion des stocks de tickets par poste"""
    
    poste = models.OneToOneField(
        Poste,
        on_delete=models.CASCADE,
        related_name='stock',
        verbose_name=_("Poste")
    )
    
    valeur_monetaire = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Valeur monétaire (FCFA)")
    )
    
    nombre_tickets = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de tickets"),
        help_text=_("Calculé automatiquement : valeur / 500")
    )
    
    derniere_mise_a_jour = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Dernière mise à jour")
    )
    
    def save(self, *args, **kwargs):
        # Calcul automatique du nombre de tickets
        if self.valeur_monetaire:
            self.nombre_tickets = int(self.valeur_monetaire / 500)
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = _("Gestion du stock")
        verbose_name_plural = _("Gestion des stocks")


class HistoriqueStock(models.Model):
    """Historique des mouvements de stock"""
    
    TYPE_MOUVEMENT = [
        ('CREDIT', 'Crédit/Approvisionnement'),
        ('DEBIT', 'Débit/Vente')
    ]

    TYPE_STOCK = [
        ('regularisation', 'Régularisation'),
        ('imprimerie_nationale', 'Imprimerie Nationale'),
        ('reapprovisionnement', 'Réapprovisionnement Inter-Postes') 
    ]
    
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='historique_stocks',
        verbose_name=_("Poste")
    )
    
    type_mouvement = models.CharField(
        max_length=10,
        choices=TYPE_MOUVEMENT,
        verbose_name=_("Type de mouvement")
    )
    
    poste_origine = models.ForeignKey(
        Poste,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transferts_sortants',
        verbose_name=_("Poste d'origine (transfert)")
    )
    
    poste_destination = models.ForeignKey(
        Poste,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transferts_entrants',
        verbose_name=_("Poste de destination (transfert)")
    )
    
    numero_bordereau = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Numéro de bordereau"),
        help_text=_("Généré automatiquement pour les transferts")
    )
    
    montant = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Montant (FCFA)")
    )
    
    nombre_tickets = models.IntegerField(
        verbose_name=_("Nombre de tickets")
    )
    
    stock_avant = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_("Stock avant (FCFA)")
    )
    
    stock_apres = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_("Stock après (FCFA)")
    )
    
    effectue_par = models.ForeignKey(
        UtilisateurSUPPER,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("Effectué par")
    )
    
    date_mouvement = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date du mouvement")
    )
    
    reference_recette = models.ForeignKey(
        'RecetteJournaliere',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Recette associée")
    )
    
    commentaire = models.TextField(
        blank=True,
        verbose_name=_("Commentaire")
    )

    type_stock = models.CharField(
        max_length=30,
        choices=TYPE_STOCK,
        null=True,  
        blank=True,
        verbose_name=_("Type de stock"),
        help_text=_("Type d'approvisionnement")
    )
    
    class Meta:
        verbose_name = _("Historique stock")
        verbose_name_plural = _("Historiques stocks")
        ordering = ['-date_mouvement']


class TypeDeclaration(models.TextChoices):
    """Types de déclaration pour quittancement"""
    JOUR = 'jour', _('Par Jour')
    DECADE = 'decade', _('Par Décade')


class Quittancement(models.Model):
    """
    Modèle pour gérer les quittancements des recettes
    RÈGLES MÉTIER :
    - Un seul quittancement par jour si type_declaration = JOUR
    - Pas de chevauchement de périodes si type_declaration = DECADE
    - Non modifiable après création
    """
    
    # Identification
    numero_quittance = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Numéro de quittance"),
        help_text=_("Numéro unique de la quittance")
    )
    
    poste = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='quittancements',
        verbose_name=_("Poste")
    )
    
    # Période
    exercice = models.IntegerField(
        verbose_name=_("Exercice (Année)"),
        validators=[MinValueValidator(2020), MaxValueValidator(2099)]
    )
    
    type_declaration = models.CharField(
        max_length=10,
        choices=TypeDeclaration.choices,
        default=TypeDeclaration.JOUR,
        verbose_name=_("Type de déclaration")
    )
    
    # Dates selon le type
    date_quittancement = models.DateField(
        verbose_name=_("Date de quittancement"),
        help_text=_("Date du jour du quittancement")
    )
    
    # Pour JOUR
    date_recette = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date de la recette"),
        help_text=_("Si type = JOUR")
    )
    
    # Pour DECADE
    date_debut_decade = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date début décade"),
        help_text=_("Si type = DECADE")
    )
    
    date_fin_decade = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date fin décade"),
        help_text=_("Si type = DECADE")
    )
    
    # Données financières
    montant = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        verbose_name=_("Montant quittancé (FCFA)")
    )
    
    # Document
    image_quittance = models.ImageField(
        upload_to='quittances/%Y/%m/',
        verbose_name=_("Image de la quittance"),
        help_text=_("Scan ou photo de la quittance")
    )
    
    # Métadonnées
    saisi_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        related_name='quittancements_saisis',
        verbose_name=_("Saisi par")
    )
    
    date_saisie = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de saisie")
    )
    
    # Verrouillage (non modifiable)
    verrouille = models.BooleanField(
        default=True,
        verbose_name=_("Verrouillé"),
        help_text=_("Les quittancements sont verrouillés dès leur création")
    )
    
    class Meta:
        verbose_name = _("Quittancement")
        verbose_name_plural = _("Quittancements")
        ordering = ['-date_quittancement', 'poste__nom']
        indexes = [
            models.Index(fields=['poste', 'exercice']),
            models.Index(fields=['numero_quittance']),
            models.Index(fields=['date_quittancement']),
        ]
        # Contraintes métier
        constraints = [
            # Un seul quittancement par jour pour un poste si type = JOUR
            models.UniqueConstraint(
                fields=['poste', 'date_quittancement', 'date_recette'],
                condition=models.Q(type_declaration='jour'),
                name='unique_quittancement_jour'
            )
        ]
    
    def __str__(self):
        return f"Quittance {self.numero_quittance} - {self.poste.nom}"
    
    def clean(self):
        """Validation métier stricte"""
        from django.core.exceptions import ValidationError
        
        # Date future interdite
        if self.date_quittancement > timezone.now().date():
            raise ValidationError("Les quittancements ne peuvent pas être sur des dates futures.")
        
        # Validation selon type
        if self.type_declaration == TypeDeclaration.JOUR:
            if not self.date_recette:
                raise ValidationError("Date de recette obligatoire pour type JOUR.")
            if self.date_recette > timezone.now().date():
                raise ValidationError("La date de recette ne peut pas être future.")
                
        elif self.type_declaration == TypeDeclaration.DECADE:
            if not self.date_debut_decade or not self.date_fin_decade:
                raise ValidationError("Dates début et fin obligatoires pour type DECADE.")
            
            if self.date_debut_decade > self.date_fin_decade:
                raise ValidationError("Date début ne peut être après date fin.")
            
            # Vérifier les chevauchements de décades
            chevauchements = Quittancement.objects.filter(
                poste=self.poste,
                type_declaration=TypeDeclaration.DECADE,
                date_debut_decade__lte=self.date_fin_decade,
                date_fin_decade__gte=self.date_debut_decade
            ).exclude(pk=self.pk if self.pk else None)
            
            if chevauchements.exists():
                raise ValidationError(
                    f"Cette période chevauche des quittancements existants : "
                    f"{', '.join([q.numero_quittance for q in chevauchements])}"
                )
    
    def save(self, *args, **kwargs):
        """Sauvegarde avec validation et verrouillage automatique"""
        self.full_clean()
        self.verrouille = True  # Toujours verrouillé
        super().save(*args, **kwargs)
    
    def get_periode_display(self):
        """Affichage de la période"""
        if self.type_declaration == TypeDeclaration.JOUR:
            return f"Jour : {self.date_recette.strftime('%d/%m/%Y')}"
        else:
            return f"Décade : {self.date_debut_decade.strftime('%d/%m/%Y')} au {self.date_fin_decade.strftime('%d/%m/%Y')}"


class JustificationEcart(models.Model):
    """
    Modèle pour justifier les écarts de comptabilisation
    """
    
    poste = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='justifications_ecart',
        verbose_name=_("Poste")
    )
    
    # Période de justification
    date_debut = models.DateField(
        verbose_name=_("Date début période")
    )
    
    date_fin = models.DateField(
        verbose_name=_("Date fin période")
    )
    
    # Montants calculés
    montant_quittance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_("Montant total quittancé")
    )
    
    montant_declare = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_("Montant total déclaré")
    )
    
    ecart = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name=_("Écart"),
        help_text=_("Quittancé - Déclaré")
    )
    
    # Justification
    justification = models.TextField(
        verbose_name=_("Justification de l'écart"),
        help_text=_("Explication détaillée de l'écart constaté")
    )
    
    # Métadonnées
    justifie_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        related_name='justifications_effectuees',
        verbose_name=_("Justifié par")
    )
    
    date_justification = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de justification")
    )
    
    class Meta:
        verbose_name = _("Justification d'écart")
        verbose_name_plural = _("Justifications d'écarts")
        ordering = ['-date_justification']
        unique_together = [['poste', 'date_debut', 'date_fin']]
    
    def __str__(self):
        return f"Justification {self.poste.nom} - {self.date_debut} au {self.date_fin}"