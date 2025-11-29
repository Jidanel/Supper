# ===================================================================
# inventaire/models.py - Modèles pour la gestion des inventaires SUPPER
# ===================================================================

from datetime import datetime, time, timedelta
import decimal
import re
from django.db import models
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from accounts.models import UtilisateurSUPPER, Poste
from django.urls import reverse
import calendar
from .models_config import ConfigurationGlobale
from django.utils import timezone
from django.core.cache import cache

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
        max_digits=10,
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
            
            if derniere_recette and derniere_recette.taux_deperdition < -30:
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
        max_digits=10,
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
        max_digits=10,
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
        max_digits=10,
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
        max_digits=10,
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
    series_tickets_associees = models.ManyToManyField(
        'SerieTicket',
        blank=True,
        related_name='historiques',
        verbose_name=_("Séries de tickets associées"),
        help_text=_("Séries de tickets concernées par ce mouvement")
    )
    numero_premier_ticket = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Premier numéro de ticket"),
        help_text=_("Premier numéro de la série (pour approvisionnement)")
    )
    
    numero_dernier_ticket = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Dernier numéro de ticket"),
        help_text=_("Dernier numéro de la série (pour approvisionnement)")
    )
    
    couleur_principale = models.ForeignKey(
        'CouleurTicket',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='historiques_couleur',
        verbose_name=_("Couleur principale"),
        help_text=_("Couleur des tickets (pour approvisionnement)")
    )
    
    # Ajout d'un JSONField pour stocker des détails supplémentaires structurés
    details_approvisionnement = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Détails de l'approvisionnement"),
        help_text=_("Détails structurés de l'approvisionnement (séries multiples, etc.)")
    )

    
    class Meta:
        verbose_name = _("Historique stock")
        verbose_name_plural = _("Historiques stocks")
        ordering = ['-date_mouvement']

    def get_details_approvisionnement_formattes(self):
        """
        Retourne les détails d'approvisionnement de manière structurée
        Utilise d'abord les champs dédiés, puis le JSONField, puis parse le commentaire
        """
        details = {
            'series': [],
            'type': self.get_type_stock_display() if self.type_stock else 'Non défini',
            'montant_total': self.montant,
            'nombre_tickets_total': self.nombre_tickets
        }
        
        # Priorité 1: Utiliser les champs dédiés s'ils existent
        if self.numero_premier_ticket and self.numero_dernier_ticket and self.couleur_principale:
            details['series'].append({
                'couleur': self.couleur_principale,
                'numero_premier': self.numero_premier_ticket,
                'numero_dernier': self.numero_dernier_ticket,
                'nombre_tickets': self.numero_dernier_ticket - self.numero_premier_ticket + 1,
                'valeur': Decimal((self.numero_dernier_ticket - self.numero_premier_ticket + 1) * 500)
            })
        
        # Priorité 2: Utiliser le JSONField s'il contient des données
        elif self.details_approvisionnement and 'series' in self.details_approvisionnement:
            for serie_data in self.details_approvisionnement['series']:
                # Récupérer la couleur depuis la base de données si on a juste l'ID ou le nom
                couleur = None
                if 'couleur_id' in serie_data:
                    couleur = CouleurTicket.objects.filter(id=serie_data['couleur_id']).first()
                elif 'couleur_nom' in serie_data:
                    couleur = CouleurTicket.objects.filter(
                        Q(libelle_affichage__icontains=serie_data['couleur_nom']) |
                        Q(code_normalise__icontains=serie_data['couleur_nom'].lower())
                    ).first()
                
                if couleur and 'numero_premier' in serie_data and 'numero_dernier' in serie_data:
                    nb_tickets = serie_data['numero_dernier'] - serie_data['numero_premier'] + 1
                    details['series'].append({
                        'couleur': couleur,
                        'numero_premier': serie_data['numero_premier'],
                        'numero_dernier': serie_data['numero_dernier'],
                        'nombre_tickets': nb_tickets,
                        'valeur': Decimal(nb_tickets * 500)
                    })
        
        # Priorité 3: Parser le commentaire comme fallback
        elif self.commentaire and '#' in self.commentaire:
            import re
            pattern = r"Série\s+(\w+)\s+#(\d+)-(\d+)"
            matches = re.finditer(pattern, self.commentaire)
            
            for match in matches:
                couleur_nom = match.group(1)
                num_premier = int(match.group(2))
                num_dernier = int(match.group(3))
                
                couleur = CouleurTicket.objects.filter(
                    Q(libelle_affichage__icontains=couleur_nom) |
                    Q(code_normalise__icontains=couleur_nom.lower())
                ).first()
                
                if couleur:
                    nb_tickets = num_dernier - num_premier + 1
                    details['series'].append({
                        'couleur': couleur,
                        'numero_premier': num_premier,
                        'numero_dernier': num_dernier,
                        'nombre_tickets': nb_tickets,
                        'valeur': Decimal(nb_tickets * 500)
                    })
        
        return details
    def associer_series_tickets(self, series_list):
        """
        Méthode utilitaire pour associer des séries de tickets
        à un historique de stock
        
        Args:
            series_list: Liste ou QuerySet de SerieTicket
        """
        self.series_tickets_associees.set(series_list)
    
    def get_series_par_couleur(self):
        """
        Retourne les séries associées groupées par couleur
        
        Returns:
            dict: {couleur: [series]}
        """
        series_par_couleur = {}
        
        for serie in self.series_tickets_associees.all().select_related('couleur'):
            couleur_code = serie.couleur.code_normalise
            
            if couleur_code not in series_par_couleur:
                series_par_couleur[couleur_code] = {
                    'couleur': serie.couleur,
                    'series': [],
                    'total_tickets': 0,
                    'valeur_totale': Decimal('0')
                }
            
            series_par_couleur[couleur_code]['series'].append(serie)
            series_par_couleur[couleur_code]['total_tickets'] += serie.nombre_tickets
            series_par_couleur[couleur_code]['valeur_totale'] += serie.valeur_monetaire
        
        return series_par_couleur


class TypeDeclaration(models.TextChoices):
    """Types de déclaration pour quittancement"""
    JOURNALIERE = 'journaliere', _('Journalière (Par Jour)')
    DECADE = 'decade', _('Par Décade')



class Quittancement(models.Model):
    """
    Modèle pour gérer les quittancements des recettes
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
    
    # NOUVEAU CHAMP
    mois = models.CharField(
        max_length=7,
        verbose_name=_("Mois concerné"),
        help_text=_("Format: YYYY-MM"),
        blank=True
    )
    
    type_declaration = models.CharField(
        max_length=15,
        choices=TypeDeclaration.choices,
        default=TypeDeclaration.JOURNALIERE,
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
        blank=True,
        null=True,
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
    
    observations = models.TextField(
        blank=True,
        verbose_name=_("Observations"),
        help_text=_("Observations optionnelles")
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
            models.Index(fields=['poste', 'mois']),
            models.Index(fields=['numero_quittance']),
            models.Index(fields=['date_quittancement']),
        ]
    
    def __str__(self):
        return f"Quittance {self.numero_quittance} - {self.poste.nom}"
    
    def clean(self):
        """
        Validation métier stricte CORRIGÉE
        - Empêche le chevauchement des décades
        - Vérifie l'unicité des quittancements journaliers
        - Contrôle les dates futures
        """
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        
        today = timezone.now().date()
        errors = {}
        
        # 1. Vérifier la date de quittancement
        if self.date_quittancement and self.date_quittancement > today:
            errors['date_quittancement'] = "La date de quittancement ne peut pas être dans le futur."
        
        # 2. Validation selon le type de déclaration
        if self.type_declaration == 'journaliere':
            # === VALIDATION JOURNALIÈRE ===
            if not self.date_recette:
                errors['date_recette'] = "Date de recette obligatoire pour type journalière."
            
            elif self.date_recette > today:
                errors['date_recette'] = "La date de recette ne peut pas être dans le futur."
            
            # Vérifier l'unicité pour ce jour et ce poste
            elif self.date_recette and self.poste:
                existing = Quittancement.objects.filter(
                    poste=self.poste,
                    type_declaration='journaliere',
                    date_recette=self.date_recette
                ).exclude(pk=self.pk if self.pk else None)
                
                if existing.exists():
                    errors['date_recette'] = (
                        f"Un quittancement existe déjà pour le {self.date_recette.strftime('%d/%m/%Y')} "
                        f"sur ce poste (N°{existing.first().numero_quittance})."
                    )
            
            # Nettoyer les champs de décade
            self.date_debut_decade = None
            self.date_fin_decade = None
            
        elif self.type_declaration == 'decade':
            # === VALIDATION DÉCADE AMÉLIORÉE ===
            if not self.date_debut_decade:
                errors['date_debut_decade'] = "Date de début de décade obligatoire."
            
            if not self.date_fin_decade:
                errors['date_fin_decade'] = "Date de fin de décade obligatoire."
            
            # Vérifier les dates futures
            if self.date_debut_decade and self.date_debut_decade > today:
                errors['date_debut_decade'] = "La date de début ne peut pas être dans le futur."
            
            if self.date_fin_decade and self.date_fin_decade > today:
                errors['date_fin_decade'] = "La date de fin ne peut pas être dans le futur."
            
            # Vérifier la cohérence des dates
            if self.date_debut_decade and self.date_fin_decade:
                if self.date_debut_decade > self.date_fin_decade:
                    errors['date_fin_decade'] = "La date de fin doit être après la date de début."
                
                # Vérifier que la décade ne dépasse pas 31 jours
                delta = (self.date_fin_decade - self.date_debut_decade).days
                if delta > 30:
                    errors['date_fin_decade'] = "Une décade ne peut pas dépasser 31 jours."
                
                # === VÉRIFICATION CHEVAUCHEMENT STRICT ===
                if self.poste:
                    # 1. Vérifier les chevauchements avec d'autres décades
                    chevauchements_decade = Quittancement.objects.filter(
                        poste=self.poste,
                        type_declaration='decade'
                    ).exclude(pk=self.pk if self.pk else None)
                    
                    for q in chevauchements_decade:
                        # Une décade chevauche si au moins un jour est en commun
                        if (self.date_debut_decade <= q.date_fin_decade and 
                            self.date_fin_decade >= q.date_debut_decade):
                            
                            # Détailler les jours en conflit
                            debut_conflit = max(self.date_debut_decade, q.date_debut_decade)
                            fin_conflit = min(self.date_fin_decade, q.date_fin_decade)
                            jours_conflit = (fin_conflit - debut_conflit).days + 1
                            
                            errors['date_debut_decade'] = (
                                f"Cette période chevauche avec le quittancement N°{q.numero_quittance} "
                                f"({q.date_debut_decade.strftime('%d/%m/%Y')} au "
                                f"{q.date_fin_decade.strftime('%d/%m/%Y')}). "
                                f"{jours_conflit} jour(s) en conflit."
                            )
                            break
                    
                    # 2. Vérifier aussi avec les quittancements journaliers
                    # Une décade ne peut pas contenir un jour déjà quittancé individuellement
                    from datetime import timedelta
                    dates_decade = []
                    current_date = self.date_debut_decade
                    while current_date <= self.date_fin_decade:
                        dates_decade.append(current_date)
                        current_date += timedelta(days=1)
                    
                    quittancements_journaliers = Quittancement.objects.filter(
                        poste=self.poste,
                        type_declaration='journaliere',
                        date_recette__in=dates_decade
                    ).exclude(pk=self.pk if self.pk else None)
                    
                    if quittancements_journaliers.exists():
                        jours_conflits = list(quittancements_journaliers.values_list('date_recette', flat=True))
                        jours_str = ', '.join([d.strftime('%d/%m/%Y') for d in jours_conflits[:3]])
                        if len(jours_conflits) > 3:
                            jours_str += f" et {len(jours_conflits) - 3} autre(s)"
                        
                        errors['date_debut_decade'] = (
                            f"Cette décade contient des jours déjà quittancés individuellement : {jours_str}"
                        )
            
            # Nettoyer le champ date_recette
            self.date_recette = None
        
        if errors:
            raise ValidationError(errors)
            
    def save(self, *args, **kwargs):
        """Sauvegarde avec validation et verrouillage automatique"""
        self.full_clean()
        self.verrouille = True  # Toujours verrouillé
        super().save(*args, **kwargs)
    
    def get_periode_display(self):
        """Affichage de la période"""
        if self.type_declaration == 'journaliere':
            return f"Jour : {self.date_recette.strftime('%d/%m/%Y') if self.date_recette else 'N/A'}"
        else:
            if self.date_debut_decade and self.date_fin_decade:
                return f"Décade : {self.date_debut_decade.strftime('%d/%m/%Y')} au {self.date_fin_decade.strftime('%d/%m/%Y')}"
            return "Décade : N/A"

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



class CouleurTicket(models.Model):
    """
    Modèle pour gérer les couleurs de tickets de manière normalisée
    """
    code_normalise = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Code normalisé"),
        help_text=_("Code avec underscores (ex: bleu_clair)")
    )
    
    libelle_affichage = models.CharField(
        max_length=50,
        verbose_name=_("Libellé d'affichage"),
        help_text=_("Libellé original saisi (ex: Bleu Clair)")
    )
    
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de création")
    )
    
    class Meta:
        verbose_name = _("Couleur de ticket")
        verbose_name_plural = _("Couleurs de tickets")
        ordering = ['code_normalise']
    
    def __str__(self):
        return self.libelle_affichage
    
    @staticmethod
    def normaliser_couleur(couleur_saisie):
        """
        Normalise une couleur saisie : 
        - Supprime les espaces multiples
        - Remplace les espaces par des underscores
        - Convertit en minuscules
        
        Exemples:
        "Bleu Clair" -> "bleu_clair"
        " bleu  clair " -> "bleu_clair"
        "ROUGE" -> "rouge"
        """
        if not couleur_saisie:
            return ""
        
        # Supprimer les espaces en début/fin
        couleur = couleur_saisie.strip()
        
        # Remplacer les espaces multiples par un seul
        couleur = re.sub(r'\s+', ' ', couleur)
        
        # Remplacer les espaces par des underscores
        couleur = couleur.replace(' ', '_')
        
        # Convertir en minuscules
        couleur = couleur.lower()
        
        return couleur
    
    @classmethod
    def obtenir_ou_creer(cls, couleur_saisie):
        """
        Obtient ou crée une couleur de manière normalisée
        
        Args:
            couleur_saisie: Couleur saisie par l'utilisateur
        
        Returns:
            Instance de CouleurTicket
        """
        code_normalise = cls.normaliser_couleur(couleur_saisie)
        
        # Conserver le libellé original pour l'affichage
        libelle_affichage = couleur_saisie.strip()
        
        couleur, created = cls.objects.get_or_create(
            code_normalise=code_normalise,
            defaults={'libelle_affichage': libelle_affichage}
        )
        
        return couleur


class SerieTicket(models.Model):
    """
    Modèle pour gérer les séries de tickets avec leur couleur
    Une série = ensemble de tickets numérotés d'une certaine couleur
    """
    
    STATUT_CHOICES = [
        ('stock', _('En stock')),
        ('vendu', _('Vendu')),
        ('transfere', _('Transféré')),
    ]
    
    poste = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='series_tickets',
        verbose_name=_("Poste")
    )
    
    couleur = models.ForeignKey(
        CouleurTicket,
        on_delete=models.PROTECT,
        related_name='series',
        verbose_name=_("Couleur")
    )
    
    numero_premier = models.IntegerField(
        validators=[MinValueValidator(1)],
        verbose_name=_("Numéro du premier ticket")
    )
    
    numero_dernier = models.IntegerField(
        validators=[MinValueValidator(1)],
        verbose_name=_("Numéro du dernier ticket")
    )
    
    nombre_tickets = models.IntegerField(
        verbose_name=_("Nombre de tickets"),
        help_text=_("Calculé automatiquement")
    )
    
    valeur_monetaire = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Valeur monétaire (FCFA)"),
        help_text=_("Calculée automatiquement : nombre_tickets * 500")
    )
    
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='stock',
        verbose_name=_("Statut")
    )
    
    type_entree = models.CharField(
        max_length=30,
        choices=[
            ('imprimerie_nationale', _('Imprimerie Nationale')),
            ('regularisation', _('Régularisation')),
            ('transfert_recu', _('Transfert reçu')),
        ],
        null=True,
        blank=True,
        verbose_name=_("Type d'entrée")
    )
    
    date_reception = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Date de réception")
    )
    
    date_utilisation = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date d'utilisation/vente")
    )
    
    reference_recette = models.ForeignKey(
        'RecetteJournaliere',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='series_tickets_utilisees',
        verbose_name=_("Recette associée")
    )
    
    poste_destination_transfert = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='series_tickets_recues',
        verbose_name=_("Poste de destination (si transféré)")
    )
    
    commentaire = models.TextField(
        blank=True,
        verbose_name=_("Commentaire")
    )

    responsable_reception = models.ForeignKey(
       'accounts.UtilisateurSUPPER',
       on_delete=models.SET_NULL,
       null=True,
       blank=True,
       related_name='series_receptionnees',
       verbose_name=_("Responsable de la réception"),
       help_text=_("Utilisateur qui a réceptionné cette série")
   )
    
    class Meta:
        verbose_name = _("Série de tickets")
        verbose_name_plural = _("Séries de tickets")
        ordering = ['-date_reception', 'couleur', 'numero_premier']
        indexes = [
            models.Index(fields=['poste', 'statut']),
            models.Index(fields=['couleur', 'statut']),
            models.Index(fields=['statut', 'date_reception']),
        ]
        # Contrainte : pas de chevauchement de numéros pour même poste et couleur en stock
        constraints = [
            models.CheckConstraint(
                check=models.Q(numero_premier__lte=models.F('numero_dernier')),
                name='numero_premier_inferieur_dernier'
            )
        ]
    @classmethod
    def verifier_disponibilite_serie_complete(cls, poste, couleur, numero_premier, numero_dernier):
        """
        Vérification COMPLÈTE de disponibilité d'une série de tickets pour VENTE
        
        CORRECTION MAJEURE :
        - Ne vérifie QUE les tickets vendus (pas les tickets en stock)
        - Accepte les chevauchements avec des séries en stock du MÊME poste
        
        Vérifie :
        1. Que les numéros sont cohérents
        2. Qu'aucun ticket de la plage n'a déjà été vendu (n'importe quel poste)
        3. Que la plage est disponible en stock pour CE poste
        
        Returns:
            tuple (bool, str, list): (est_disponible, message_erreur, tickets_problematiques)
        """
        from django.db.models import Q
        
        # Vérification 1 : Numéros cohérents
        if numero_premier > numero_dernier:
            return False, "Le numéro du premier ticket doit être inférieur ou égal au dernier", []
        
        if numero_premier < 1:
            return False, "Les numéros de tickets doivent être positifs", []
        
        # ===== CORRECTION : Vérification 2 - Tickets VENDUS uniquement =====
        # Ne chercher QUE les tickets avec statut 'vendu'
        # Ignorer les tickets en 'stock' car ils sont disponibles pour vente
        tickets_deja_vendus = cls.objects.filter(
            couleur=couleur,
            statut='vendu',  # ← IMPORTANT : Seulement les vendus
            # Chevauchement : (debut1 <= fin2) AND (fin1 >= debut2)
            numero_premier__lte=numero_dernier,
            numero_dernier__gte=numero_premier
        ).values_list('numero_premier', 'numero_dernier', 'date_utilisation', 'poste__nom')
        
        if tickets_deja_vendus.exists():
            tickets_problematiques = []
            for prem, dern, date_vente, nom_poste in tickets_deja_vendus:
                tickets_problematiques.append({
                    'premier': prem,
                    'dernier': dern,
                    'date_vente': date_vente,
                    'poste': nom_poste
                })
            
            # Construire message détaillé
            if len(tickets_problematiques) == 1:
                ticket = tickets_problematiques[0]
                msg = (
                    f"❌ TICKET DÉJÀ VENDU : La série {couleur.libelle_affichage} "
                    f"#{ticket['premier']}-{ticket['dernier']} a déjà été vendue "
                    f"le {ticket['date_vente'].strftime('%d/%m/%Y')} "
                    f"au poste {ticket['poste']}"
                )
            else:
                msg = (
                    f"❌ TICKETS DÉJÀ VENDUS : {len(tickets_problematiques)} série(s) "
                    f"de la couleur {couleur.libelle_affichage} chevauchent votre saisie et "
                    f"ont déjà été vendues"
                )
            
            return False, msg, tickets_problematiques
        
        # ===== CORRECTION : Vérification 3 - Disponibilité en stock POUR CE POSTE =====
        # Chercher uniquement les séries en stock du poste concerné
        series_stock_poste = cls.objects.filter(
            poste=poste,  # ← IMPORTANT : Seulement CE poste
            couleur=couleur,
            statut='stock'
        )
        
        if not series_stock_poste.exists():
            return False, (
                f"Aucun stock de tickets {couleur.libelle_affichage} disponible "
                f"pour le poste {poste.nom}"
            ), []
        
        # Vérifier que la plage demandée est couverte par UNE série en stock
        plage_couverte = False
        serie_couvrante = None
        
        for serie in series_stock_poste:
            # La série en stock doit CONTENIR complètement la plage demandée
            if (numero_premier >= serie.numero_premier and 
                numero_dernier <= serie.numero_dernier):
                plage_couverte = True
                serie_couvrante = serie
                break
        
        if not plage_couverte:
            # Lister les séries disponibles pour aider l'utilisateur
            series_dispo = [
                f"#{s.numero_premier}-{s.numero_dernier}" 
                for s in series_stock_poste
            ]
            
            msg = (
                f"❌ Série {couleur.libelle_affichage} #{numero_premier}-{numero_dernier} "
                f"non disponible en stock au poste {poste.nom}. "
                f"Séries disponibles : {', '.join(series_dispo) if series_dispo else 'Aucune'}"
            )
            
            return False, msg, []
        
        # ===== Tout est OK - La série peut être vendue =====
        return True, f"✅ Série {couleur.libelle_affichage} #{numero_premier}-{numero_dernier} disponible", []

    @classmethod
    def verifier_unicite_annuelle(cls, numero_ticket, couleur, annee):
            """
            Vérifie l'unicité d'un numéro de ticket pour une année donnée
            Règle métier : Un numéro de ticket ne peut apparaître qu'une seule fois par an
            
            Args:
                numero_ticket: Numéro du ticket à vérifier
                couleur: Instance de CouleurTicket
                annee: Année à vérifier (int)
            
            Returns:
                tuple (bool, str, dict): (est_unique, message, historique)
            """
            from django.db.models import Q
            from datetime import date
            
            # Date de début et fin de l'année
            debut_annee = date(annee, 1, 1)
            fin_annee = date(annee, 12, 31)
            
            # Chercher toutes les séries qui contiennent ce numéro dans l'année
            series_contenant_numero = cls.objects.filter(
                couleur=couleur,
                numero_premier__lte=numero_ticket,
                numero_dernier__gte=numero_ticket,
                date_reception__range=[debut_annee, fin_annee]
            ).select_related('poste', 'poste_destination_transfert')
            
            if not series_contenant_numero.exists():
                return True, f"Ticket #{numero_ticket} unique en {annee}", {}
            
            # Si le ticket existe déjà dans l'année
            serie = series_contenant_numero.first()
            
            historique = {
                'numero': numero_ticket,
                'couleur': couleur.libelle_affichage,
                'annee': annee,
                'poste_reception': serie.poste.nom,
                'date_reception': serie.date_reception,
                'statut': serie.statut,
                'type_entree': serie.get_type_entree_display() if serie.type_entree else 'Non défini'
            }
            
            if serie.statut == 'vendu' and serie.date_utilisation:
                historique['date_vente'] = serie.date_utilisation
                historique['poste_vente'] = serie.poste.nom
            elif serie.statut == 'transfere' and serie.poste_destination_transfert:
                historique['poste_transfere'] = serie.poste_destination_transfert.nom
            
            msg = (
                f"⚠️ Le ticket {couleur.libelle_affichage} #{numero_ticket} "
                f"existe déjà en {annee} au poste {serie.poste.nom} "
                f"(reçu le {serie.date_reception.strftime('%d/%m/%Y')})"
            )
            
            return False, msg, historique
    
    @classmethod
    def verifier_unicite_annuelle_chargement(cls, couleur, numero_premier, numero_dernier, annee=None):
        """
        Vérifie l'unicité des numéros de tickets pour une année donnée.
        Cette vérification est UNIQUEMENT effectuée lors du chargement 
        (Imprimerie Nationale ou Régularisation), PAS lors des transferts.
        
        RÈGLE MÉTIER CRITIQUE:
        - Un numéro de ticket ne peut appartenir qu'à UN SEUL poste par année
        - En 2025, on peut avoir un ticket #10 même s'il existait en 2024
        - Mais en 2025, le ticket #10 ne peut pas être chargé dans 2 postes différents
        
        Args:
            couleur: Instance de CouleurTicket
            numero_premier: Premier numéro de la série
            numero_dernier: Dernier numéro de la série
            annee: Année à vérifier (par défaut: année en cours)
        
        Returns:
            tuple (bool, str, dict): (est_unique, message_erreur, details)
        """
        if annee is None:
            annee = date.today().year
        
        # Dates limites de l'année
        debut_annee = timezone.make_aware(datetime(annee, 1, 1, 0, 0, 0))
        fin_annee = timezone.make_aware(datetime(annee, 12, 31, 23, 59, 59))
        
        # Chercher TOUS les tickets de cette couleur chargés cette année
        # qui chevauchent la plage demandée
        # IMPORTANT: On ne regarde QUE les types d'entrée 'imprimerie_nationale' et 'regularisation'
        # Les 'transfert_recu' ne comptent pas car ce sont les mêmes tickets qui bougent
        series_existantes = cls.objects.filter(
            couleur=couleur,
            type_entree__in=['imprimerie_nationale', 'regularisation'],  # Seulement les chargements initiaux
            date_reception__range=[debut_annee, fin_annee],
            statut='stock',
            # Chevauchement: (debut1 <= fin2) AND (fin1 >= debut2)
            numero_premier__lte=numero_dernier,
            numero_dernier__gte=numero_premier
        ).select_related('poste')
        
        if not series_existantes.exists():
            return True, f"✅ Série {couleur.libelle_affichage} #{numero_premier}-{numero_dernier} disponible pour {annee}", {}
        
        # Construire le rapport des conflits
        conflits = []
        for serie in series_existantes:
            # Calculer la plage en conflit
            debut_conflit = max(numero_premier, serie.numero_premier)
            fin_conflit = min(numero_dernier, serie.numero_dernier)
            
            conflits.append({
                'poste_nom': serie.poste.nom,
                'poste_code': serie.poste.code,
                'serie_complete': f"#{serie.numero_premier}-{serie.numero_dernier}",
                'plage_conflit': f"#{debut_conflit}-{fin_conflit}",
                'nombre_tickets_conflit': fin_conflit - debut_conflit + 1,
                'date_chargement': serie.date_reception.strftime('%d/%m/%Y'),
                'type_entree': serie.get_type_entree_display() if serie.type_entree else 'Non défini'
            })
        
        # Message d'erreur détaillé
        premier_conflit = conflits[0]
        msg = (
            f"❌ UNICITÉ ANNUELLE VIOLÉE en {annee} !\n"
            f"Les tickets {couleur.libelle_affichage} {premier_conflit['plage_conflit']} "
            f"ont déjà été chargés au poste {premier_conflit['poste_nom']} "
            f"le {premier_conflit['date_chargement']} ({premier_conflit['type_entree']}).\n"
            f"Un même ticket ne peut pas être chargé dans deux postes différents la même année."
        )
        
        if len(conflits) > 1:
            msg += f"\n{len(conflits)} série(s) en conflit au total."
        
        return False, msg, {'annee': annee, 'conflits': conflits}

    
    @classmethod
    def verifier_disponibilite_serie_complete(cls, poste, couleur, numero_premier, numero_dernier):
        """
        Vérifie UNIQUEMENT la disponibilité au poste ORIGINE pour vente/transfert.
        
        CHANGEMENT MAJEUR:
        - Ne vérifie PLUS les chevauchements au poste destination
        - Vérifie seulement que la série existe en stock au poste origine
        - Vérifie qu'aucun ticket n'a été vendu
        
        Returns:
            tuple (bool, str, list): (est_disponible, message_erreur, tickets_problematiques)
        """
        # Validation de base des numéros
        if numero_premier > numero_dernier:
            return False, "Le numéro du premier ticket doit être inférieur ou égal au dernier", []
        
        if numero_premier < 1:
            return False, "Les numéros de tickets doivent être positifs", []
        
        # === ÉTAPE 1: Vérifier que la série existe en stock au poste origine ===
        serie_source = cls.objects.filter(
            poste=poste,
            couleur=couleur,
            statut='stock',
            numero_premier__lte=numero_premier,
            numero_dernier__gte=numero_dernier
        ).first()
        
        if not serie_source:
            # Aider l'utilisateur en listant ce qui est disponible
            series_dispo = cls.objects.filter(
                poste=poste,
                couleur=couleur,
                statut='stock'
            ).order_by('numero_premier')
            
            if series_dispo.exists():
                series_str = ', '.join([
                    f"#{s.numero_premier}-{s.numero_dernier}" 
                    for s in series_dispo
                ])
                msg = (
                    f"❌ La série {couleur.libelle_affichage} #{numero_premier}-{numero_dernier} "
                    f"n'est pas disponible au poste {poste.nom}. "
                    f"Séries disponibles: {series_str}"
                )
            else:
                msg = (
                    f"❌ Aucun stock de tickets {couleur.libelle_affichage} "
                    f"au poste {poste.nom}"
                )
            
            return False, msg, []
        
        # === ÉTAPE 2: Vérifier qu'aucun ticket de cette plage n'a été vendu ===
        tickets_vendus = cls.objects.filter(
            couleur=couleur,
            statut='vendu',
            numero_premier__lte=numero_dernier,
            numero_dernier__gte=numero_premier
        ).select_related('poste')
        
        if tickets_vendus.exists():
            tickets_problematiques = []
            for ticket in tickets_vendus:
                tickets_problematiques.append({
                    'premier': ticket.numero_premier,
                    'dernier': ticket.numero_dernier,
                    'date_vente': ticket.date_utilisation,
                    'poste': ticket.poste.nom
                })
            
            msg = (
                f"❌ IMPOSSIBLE : Des tickets ont déjà été vendus ! "
            )
            for t in tickets_problematiques[:2]:
                date_str = t['date_vente'].strftime('%d/%m/%Y') if t['date_vente'] else 'date inconnue'
                msg += f"#{t['premier']}-{t['dernier']} (vendu le {date_str} au poste {t['poste']}), "
            
            return False, msg.rstrip(', '), tickets_problematiques
        
        # === TOUT EST OK ===
        return True, f"✅ Série disponible pour transfert/vente", []
    # @classmethod
    # def verifier_disponibilite_serie_complete(cls, poste, couleur, numero_premier, numero_dernier):
    #     """
    #     VERSION CORRIGÉE - Vérifie UNIQUEMENT la disponibilité au poste ORIGINE
    #     Ne vérifie PAS les chevauchements au poste destination
        
    #     Cette méthode est utilisée UNIQUEMENT pour vérifier qu'une série peut être :
    #     1. VENDUE depuis ce poste
    #     2. TRANSFÉRÉE depuis ce poste
        
    #     Returns:
    #         tuple (bool, str, list): (est_disponible, message_erreur, tickets_problematiques)
    #     """
    #     from django.db.models import Q
        
    #     # Vérification 1 : Numéros cohérents
    #     if numero_premier > numero_dernier:
    #         return False, "Le numéro du premier ticket doit être inférieur ou égal au dernier", []
        
    #     if numero_premier < 1:
    #         return False, "Les numéros de tickets doivent être positifs", []
        
    #     # Vérification 2 : La série est-elle en stock au poste ORIGINE ?
    #     series_stock_origine = cls.objects.filter(
    #         poste=poste,
    #         couleur=couleur,
    #         statut='stock',
    #         numero_premier__lte=numero_dernier,
    #         numero_dernier__gte=numero_premier
    #     )
        
    #     if not series_stock_origine.exists():
    #         # Lister les séries disponibles pour aider
    #         series_dispo = cls.objects.filter(
    #             poste=poste,
    #             couleur=couleur,
    #             statut='stock'
    #         ).order_by('numero_premier')
            
    #         if series_dispo.exists():
    #             series_str = ', '.join([
    #                 f"#{s.numero_premier}-{s.numero_dernier}" 
    #                 for s in series_dispo
    #             ])
    #             return False, (
    #                 f"❌ La série {couleur.libelle_affichage} #{numero_premier}-{numero_dernier} "
    #                 f"n'est pas disponible au poste {poste.nom}. "
    #                 f"Séries disponibles: {series_str}"
    #             ), []
    #         else:
    #             return False, (
    #                 f"❌ Aucun stock de tickets {couleur.libelle_affichage} "
    #                 f"disponible au poste {poste.nom}"
    #             ), []
        
    #     # Vérification 3 : La plage complète est-elle couverte ?
    #     # Trouver une série qui contient ENTIÈREMENT la plage demandée
    #     serie_couvrante = None
    #     for serie in series_stock_origine:
    #         if (numero_premier >= serie.numero_premier and 
    #             numero_dernier <= serie.numero_dernier):
    #             serie_couvrante = serie
    #             break
        
    #     if not serie_couvrante:
    #         # La plage demandée n'est pas entièrement couverte
    #         return False, (
    #             f"❌ La série {couleur.libelle_affichage} #{numero_premier}-{numero_dernier} "
    #             f"n'est pas entièrement disponible en stock au poste {poste.nom}. "
    #             f"Vérifiez que toute la plage est dans une seule série."
    #         ), []
        
    #     # Vérification 4 : Certains tickets ont-ils déjà été vendus ?
    #     # Vérifier dans TOUTE la base si ces numéros ont été vendus
    #     tickets_vendus = cls.objects.filter(
    #         couleur=couleur,
    #         statut='vendu',
    #         numero_premier__lte=numero_dernier,
    #         numero_dernier__gte=numero_premier
    #     ).select_related('poste')
        
    #     if tickets_vendus.exists():
    #         tickets_problematiques = []
    #         for ticket in tickets_vendus:
    #             tickets_problematiques.append({
    #                 'premier': ticket.numero_premier,
    #                 'dernier': ticket.numero_dernier,
    #                 'date_vente': ticket.date_utilisation,
    #                 'poste': ticket.poste.nom
    #             })
            
    #         msg = (
    #             f"❌ IMPOSSIBLE : Des tickets de cette plage ont déjà été vendus ! "
    #             f"Ticket(s) vendu(s) : "
    #         )
    #         for t in tickets_problematiques[:2]:  # Afficher max 2 exemples
    #             msg += f"#{t['premier']}-{t['dernier']} (vendu le {t['date_vente'].strftime('%d/%m/%Y') if t['date_vente'] else 'date inconnue'} au poste {t['poste']}), "
            
    #         return False, msg.rstrip(', '), tickets_problematiques
        
    #     # ✅ Tout est OK - La série peut être transférée ou vendue
    #     return True, f"✅ Série disponible pour transfert/vente", []



    @classmethod
    def consommer_serie(cls, poste, couleur, numero_premier, numero_dernier, recette):
        """
        Consomme (marque comme vendue) une série de tickets
        Gère le découpage des séries si nécessaire
        
        Args:
            poste: Poste concerné
            couleur: CouleurTicket
            numero_premier: Premier numéro vendu
            numero_dernier: Dernier numéro vendu
            recette: Instance de RecetteJournaliere
        
        Returns:
            tuple (bool, str, list): (success, message, series_creees)
        """
        from django.db import transaction
        
        disponible, msg = cls.verifier_disponibilite_serie(
            poste, couleur, numero_premier, numero_dernier
        )
        
        if not disponible:
            return False, msg, []
        
        with transaction.atomic():
            # Trouver la série parente qui contient cette plage
            serie_parente = cls.objects.filter(
                poste=poste,
                couleur=couleur,
                statut='stock',
                numero_premier__lte=numero_premier,
                numero_dernier__gte=numero_dernier
            ).first()
            
            if not serie_parente:
                return False, "Série parente non trouvée", []
            
            series_creees = []
            
            # CAS 1 : Vente de toute la série
            if (numero_premier == serie_parente.numero_premier and 
                numero_dernier == serie_parente.numero_dernier):
                serie_parente.statut = 'vendu'
                serie_parente.date_utilisation = recette.date
                serie_parente.reference_recette = recette
                serie_parente.save()
                series_creees.append(serie_parente)
            
            # CAS 2 : Vente au début de la série
            elif numero_premier == serie_parente.numero_premier:
                # Créer série vendue
                serie_vendue = cls.objects.create(
                    poste=poste,
                    couleur=couleur,
                    numero_premier=numero_premier,
                    numero_dernier=numero_dernier,
                    statut='vendu',
                    date_utilisation=recette.date,
                    reference_recette=recette,
                    type_entree=serie_parente.type_entree
                )
                series_creees.append(serie_vendue)
                
                # Mettre à jour la série parente (reste en stock)
                serie_parente.numero_premier = numero_dernier + 1
                serie_parente.save()
            
            # CAS 3 : Vente à la fin de la série
            elif numero_dernier == serie_parente.numero_dernier:
                # Créer série vendue
                serie_vendue = cls.objects.create(
                    poste=poste,
                    couleur=couleur,
                    numero_premier=numero_premier,
                    numero_dernier=numero_dernier,
                    statut='vendu',
                    date_utilisation=recette.date,
                    reference_recette=recette,
                    type_entree=serie_parente.type_entree
                )
                series_creees.append(serie_vendue)
                
                # Mettre à jour la série parente
                serie_parente.numero_dernier = numero_premier - 1
                serie_parente.save()
            
            # CAS 4 : Vente au milieu de la série (découpage en 3)
            else:
                # Série vendue (milieu)
                serie_vendue = cls.objects.create(
                    poste=poste,
                    couleur=couleur,
                    numero_premier=numero_premier,
                    numero_dernier=numero_dernier,
                    statut='vendu',
                    date_utilisation=recette.date,
                    reference_recette=recette,
                    type_entree=serie_parente.type_entree
                )
                series_creees.append(serie_vendue)
                
                # Série après (reste en stock)
                serie_apres = cls.objects.create(
                    poste=poste,
                    couleur=couleur,
                    numero_premier=numero_dernier + 1,
                    numero_dernier=serie_parente.numero_dernier,
                    statut='stock',
                    type_entree=serie_parente.type_entree
                )
                series_creees.append(serie_apres)
                
                # Mettre à jour série parente (devient série avant)
                serie_parente.numero_dernier = numero_premier - 1
                serie_parente.save()
            
            return True, "Série consommée avec succès", series_creees

    
    @classmethod
    def transferer_serie(cls, poste_origine, poste_destination, couleur, numero_premier, numero_dernier, user, commentaire=''):
        """
        Transfert de tickets entre postes - VERSION CORRIGÉE FINALE
        
        PRINCIPES:
        1. On vérifie UNIQUEMENT que la série existe au poste origine
        2. On ne vérifie PAS les chevauchements au poste destination
        3. On fusionne les séries contiguës de même couleur au destination
        4. Si pas contiguës, on ajoute simplement la nouvelle série
        
        Returns:
            tuple (bool, str, SerieTicket, SerieTicket): (success, message, serie_origine, serie_destination)
        """
        from django.db import transaction
        from inventaire.models import GestionStock, HistoriqueStock, StockEvent
        from accounts.models import NotificationUtilisateur, UtilisateurSUPPER
        
        try:
            with transaction.atomic():
                logger.info(f"=== DÉBUT TRANSFERT (VERSION CORRIGÉE) ===")
                logger.info(f"De: {poste_origine.nom} vers: {poste_destination.nom}")
                logger.info(f"Série: {couleur.libelle_affichage} #{numero_premier}-{numero_dernier}")
                
                # === VALIDATION DE BASE ===
                if poste_origine.id == poste_destination.id:
                    return False, "Les postes origine et destination doivent être différents", None, None
                
                if numero_premier > numero_dernier:
                    return False, "Le numéro premier doit être inférieur ou égal au dernier", None, None
                
                nombre_tickets = numero_dernier - numero_premier + 1
                montant = Decimal(nombre_tickets) * Decimal('500')
                timestamp = timezone.now()
                
                # === ÉTAPE 1: VÉRIFIER DISPONIBILITÉ AU POSTE ORIGINE UNIQUEMENT ===
                disponible, msg, _ = cls.verifier_disponibilite_serie_complete(
                    poste_origine, couleur, numero_premier, numero_dernier
                )
                
                if not disponible:
                    logger.error(f"Vérification échouée: {msg}")
                    return False, msg, None, None
                
                # === ÉTAPE 2: TROUVER ET TRAITER LA SÉRIE AU POSTE ORIGINE ===
                serie_source = cls.objects.filter(
                    poste=poste_origine,
                    couleur=couleur,
                    statut='stock',
                    numero_premier__lte=numero_premier,
                    numero_dernier__gte=numero_dernier
                ).first()
                
                if not serie_source:
                    return False, "Série source introuvable (erreur inattendue)", None, None
                
                serie_transferee = None
                
                # CAS A: Transfert de la série complète
                if (serie_source.numero_premier == numero_premier and 
                    serie_source.numero_dernier == numero_dernier):
                    
                    logger.info("→ Transfert complet de la série")
                    serie_source.statut = 'transfere'
                    serie_source.date_utilisation = timestamp.date()
                    serie_source.poste_destination_transfert = poste_destination
                    serie_source.commentaire = f"Transféré vers {poste_destination.nom} - {commentaire}"
                    serie_source.save(update_fields=['statut', 'date_utilisation', 
                                                    'poste_destination_transfert', 'commentaire'])
                    serie_transferee = serie_source
                
                # CAS B: Transfert partiel - découpage
                else:
                    logger.info("→ Transfert partiel - découpage de la série")
                    
                    # Conserver les infos originales
                    original_premier = serie_source.numero_premier
                    original_dernier = serie_source.numero_dernier
                    type_entree_original = serie_source.type_entree
                    responsable_original = serie_source.responsable_reception
                    
                    # 1. Créer la partie AVANT si nécessaire
                    if original_premier < numero_premier:
                        cls.objects.create(
                            poste=poste_origine,
                            couleur=couleur,
                            numero_premier=original_premier,
                            numero_dernier=numero_premier - 1,
                            nombre_tickets=(numero_premier - 1) - original_premier + 1,
                            valeur_monetaire=Decimal((numero_premier - 1) - original_premier + 1) * Decimal('500'),
                            statut='stock',
                            type_entree=type_entree_original,
                            responsable_reception=responsable_original,
                            commentaire="Reste après transfert partiel"
                        )
                        logger.info(f"  → Partie avant: #{original_premier}-{numero_premier - 1}")
                    
                    # 2. Créer la partie APRÈS si nécessaire
                    if original_dernier > numero_dernier:
                        cls.objects.create(
                            poste=poste_origine,
                            couleur=couleur,
                            numero_premier=numero_dernier + 1,
                            numero_dernier=original_dernier,
                            nombre_tickets=original_dernier - (numero_dernier + 1) + 1,
                            valeur_monetaire=Decimal(original_dernier - (numero_dernier + 1) + 1) * Decimal('500'),
                            statut='stock',
                            type_entree=type_entree_original,
                            responsable_reception=responsable_original,
                            commentaire="Reste après transfert partiel"
                        )
                        logger.info(f"  → Partie après: #{numero_dernier + 1}-{original_dernier}")
                    
                    # 3. Transformer la série originale en série transférée
                    serie_source.numero_premier = numero_premier
                    serie_source.numero_dernier = numero_dernier
                    serie_source.nombre_tickets = nombre_tickets
                    serie_source.valeur_monetaire = montant
                    serie_source.statut = 'transfere'
                    serie_source.date_utilisation = timestamp.date()
                    serie_source.poste_destination_transfert = poste_destination
                    serie_source.commentaire = f"Transféré vers {poste_destination.nom} - {commentaire}"
                    serie_source.save()
                    
                    serie_transferee = serie_source
                
                # === ÉTAPE 3: CRÉER/FUSIONNER LA SÉRIE AU POSTE DESTINATION ===
                logger.info("Création/fusion de la série au poste DESTINATION...")
                
                # Chercher des séries contiguës de même couleur au poste destination
                serie_destination = cls._fusionner_ou_creer_serie_destination(
                    poste_destination, couleur, numero_premier, numero_dernier,
                    user, poste_origine, commentaire, timestamp
                )
                
                # === ÉTAPE 4: MISE À JOUR DES STOCKS GLOBAUX ===
                logger.info("Mise à jour des stocks globaux...")
                
                # Stock origine
                stock_origine, _ = GestionStock.objects.get_or_create(
                    poste=poste_origine,
                    defaults={'valeur_monetaire': Decimal('0')}
                )
                stock_origine_avant = stock_origine.valeur_monetaire
                stock_origine.valeur_monetaire = max(Decimal('0'), stock_origine.valeur_monetaire - montant)
                stock_origine.save()
                
                # Stock destination
                stock_destination, _ = GestionStock.objects.get_or_create(
                    poste=poste_destination,
                    defaults={'valeur_monetaire': Decimal('0')}
                )
                stock_destination_avant = stock_destination.valeur_monetaire
                stock_destination.valeur_monetaire += montant
                stock_destination.save()
                
                logger.info(f"Stock {poste_origine.nom}: {stock_origine_avant} → {stock_origine.valeur_monetaire}")
                logger.info(f"Stock {poste_destination.nom}: {stock_destination_avant} → {stock_destination.valeur_monetaire}")
                
                # === ÉTAPE 5: CRÉER LES HISTORIQUES ET ÉVÉNEMENTS ===
                numero_bordereau = cls._generer_numero_bordereau_transfert()
                
                # Historique origine (DEBIT)
                HistoriqueStock.objects.create(
                    poste=poste_origine,
                    type_mouvement='DEBIT',
                    type_stock='reapprovisionnement',
                    montant=montant,
                    nombre_tickets=nombre_tickets,
                    stock_avant=stock_origine_avant,
                    stock_apres=stock_origine.valeur_monetaire,
                    effectue_par=user,
                    poste_origine=poste_origine,
                    poste_destination=poste_destination,
                    numero_bordereau=numero_bordereau,
                    commentaire=f"Cession {couleur.libelle_affichage} #{numero_premier}-{numero_dernier}"
                )
                
                # Historique destination (CREDIT)
                HistoriqueStock.objects.create(
                    poste=poste_destination,
                    type_mouvement='CREDIT',
                    type_stock='reapprovisionnement',
                    montant=montant,
                    nombre_tickets=nombre_tickets,
                    stock_avant=stock_destination_avant,
                    stock_apres=stock_destination.valeur_monetaire,
                    effectue_par=user,
                    poste_origine=poste_origine,
                    poste_destination=poste_destination,
                    numero_bordereau=numero_bordereau,
                    commentaire=f"Réception {couleur.libelle_affichage} #{numero_premier}-{numero_dernier}"
                )
                
                # Events sourcing
                metadata = {
                    'couleur': couleur.libelle_affichage,
                    'numero_premier': numero_premier,
                    'numero_dernier': numero_dernier,
                    'nombre_tickets': nombre_tickets,
                    'valeur': str(montant),
                    'numero_bordereau': numero_bordereau
                }
                
                StockEvent.objects.create(
                    poste=poste_origine,
                    event_type='TRANSFERT_OUT',
                    event_datetime=timestamp,
                    montant_variation=-montant,
                    nombre_tickets_variation=-nombre_tickets,
                    stock_resultant=stock_origine.valeur_monetaire,
                    tickets_resultants=int(stock_origine.valeur_monetaire / 500),
                    effectue_par=user,
                    metadata={'serie': metadata, 'poste_destination': {'nom': poste_destination.nom}},
                    commentaire=f"Transfert vers {poste_destination.nom}"
                )
                
                StockEvent.objects.create(
                    poste=poste_destination,
                    event_type='TRANSFERT_IN',
                    event_datetime=timestamp,
                    montant_variation=montant,
                    nombre_tickets_variation=nombre_tickets,
                    stock_resultant=stock_destination.valeur_monetaire,
                    tickets_resultants=int(stock_destination.valeur_monetaire / 500),
                    effectue_par=user,
                    metadata={'serie': metadata, 'poste_origine': {'nom': poste_origine.nom}},
                    commentaire=f"Réception depuis {poste_origine.nom}"
                )
                
                # Notifications
                cls._envoyer_notifications_transfert(
                    poste_origine, poste_destination,
                    couleur, numero_premier, numero_dernier,
                    montant, nombre_tickets, numero_bordereau, user
                )
                
                logger.info(f"=== ✅ TRANSFERT RÉUSSI - Bordereau {numero_bordereau} ===")
                
                return True, f"Transfert réussi - Bordereau {numero_bordereau}", serie_transferee, serie_destination
                
        except Exception as e:
            logger.error(f"❌ ERREUR TRANSFERT: {str(e)}", exc_info=True)
            return False, f"Erreur lors du transfert: {str(e)}", None, None
    
    @classmethod
    def _fusionner_ou_creer_serie_destination(cls, poste_destination, couleur, numero_premier, 
                                            numero_dernier, user, poste_origine, commentaire, timestamp):
        """
        Crée une nouvelle série au poste destination ou fusionne avec des séries existantes
        si elles sont contiguës et de même couleur.
        
        RÈGLES DE FUSION:
        - Si une série existante finit à (numero_premier - 1), on l'étend
        - Si une série existante commence à (numero_dernier + 1), on l'étend
        - Si fusion possible des deux côtés, on fusionne tout
        - Sinon, on crée une nouvelle série indépendante
        """
        nombre_tickets = numero_dernier - numero_premier + 1
        montant = Decimal(nombre_tickets) * Decimal('500')
        
        # Chercher les séries contiguës au poste destination
        serie_avant = cls.objects.filter(
            poste=poste_destination,
            couleur=couleur,
            statut='stock',
            numero_dernier=numero_premier - 1  # Série qui finit juste avant
        ).first()
        
        serie_apres = cls.objects.filter(
            poste=poste_destination,
            couleur=couleur,
            statut='stock',
            numero_premier=numero_dernier + 1  # Série qui commence juste après
        ).first()
        
        serie_destination = None
        
        # CAS 1: Fusion des deux côtés (séries avant ET après contiguës)
        if serie_avant and serie_apres:
            logger.info(f"→ Fusion triple: #{serie_avant.numero_premier}-{serie_avant.numero_dernier} "
                    f"+ #{numero_premier}-{numero_dernier} "
                    f"+ #{serie_apres.numero_premier}-{serie_apres.numero_dernier}")
            
            # Étendre la série avant pour tout englober
            nouveau_dernier = serie_apres.numero_dernier
            nouveau_nb_tickets = nouveau_dernier - serie_avant.numero_premier + 1
            
            serie_avant.numero_dernier = nouveau_dernier
            serie_avant.nombre_tickets = nouveau_nb_tickets
            serie_avant.valeur_monetaire = Decimal(nouveau_nb_tickets) * Decimal('500')
            serie_avant.commentaire = f"Fusion après transfert depuis {poste_origine.nom}"
            serie_avant.save()
            
            # Supprimer la série après (maintenant fusionnée)
            serie_apres.delete()
            
            serie_destination = serie_avant
            logger.info(f"  → Résultat: #{serie_avant.numero_premier}-{serie_avant.numero_dernier}")
        
        # CAS 2: Fusion avec série avant uniquement
        elif serie_avant:
            logger.info(f"→ Fusion avec série précédente: #{serie_avant.numero_premier}-{serie_avant.numero_dernier} "
                    f"+ #{numero_premier}-{numero_dernier}")
            
            nouveau_nb_tickets = numero_dernier - serie_avant.numero_premier + 1
            
            serie_avant.numero_dernier = numero_dernier
            serie_avant.nombre_tickets = nouveau_nb_tickets
            serie_avant.valeur_monetaire = Decimal(nouveau_nb_tickets) * Decimal('500')
            serie_avant.commentaire = f"Étendue après transfert depuis {poste_origine.nom}"
            serie_avant.save()
            
            serie_destination = serie_avant
            logger.info(f"  → Résultat: #{serie_avant.numero_premier}-{serie_avant.numero_dernier}")
        
        # CAS 3: Fusion avec série après uniquement
        elif serie_apres:
            logger.info(f"→ Fusion avec série suivante: #{numero_premier}-{numero_dernier} "
                    f"+ #{serie_apres.numero_premier}-{serie_apres.numero_dernier}")
            
            nouveau_nb_tickets = serie_apres.numero_dernier - numero_premier + 1
            
            serie_apres.numero_premier = numero_premier
            serie_apres.nombre_tickets = nouveau_nb_tickets
            serie_apres.valeur_monetaire = Decimal(nouveau_nb_tickets) * Decimal('500')
            serie_apres.commentaire = f"Étendue après transfert depuis {poste_origine.nom}"
            serie_apres.save()
            
            serie_destination = serie_apres
            logger.info(f"  → Résultat: #{serie_apres.numero_premier}-{serie_apres.numero_dernier}")
        
        # CAS 4: Pas de fusion possible - créer nouvelle série
        else:
            logger.info(f"→ Création nouvelle série: #{numero_premier}-{numero_dernier}")
            
            serie_destination = cls.objects.create(
                poste=poste_destination,
                couleur=couleur,
                numero_premier=numero_premier,
                numero_dernier=numero_dernier,
                nombre_tickets=nombre_tickets,
                valeur_monetaire=montant,
                statut='stock',
                type_entree='transfert_recu',
                date_reception=timestamp,
                responsable_reception=user,
                commentaire=f"Reçu de {poste_origine.nom} - {commentaire}"
            )
        
        return serie_destination

    @classmethod
    def _generer_numero_bordereau_transfert(cls):
        """Génère un numéro unique de bordereau pour le transfert"""
        from datetime import datetime
        from inventaire.models import HistoriqueStock
        
        now = datetime.now()
        
        # Compter les transferts du jour
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        count_today = HistoriqueStock.objects.filter(
            type_stock='reapprovisionnement',
            date_mouvement__gte=today_start
        ).count()
        
        # Format : TR-YYYYMMDD-HHMMSS-XXX
        numero = f"TR-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}-{count_today+1:03d}"
        
        return numero


    @staticmethod
    def _envoyer_notifications_transfert(poste_origine, poste_destination, 
                                        couleur, numero_premier, numero_dernier,
                                        montant, nombre_tickets, numero_bordereau, user):
        """
        ✅ NOUVELLE MÉTHODE STATIQUE : Envoie les notifications de transfert
        """
        from accounts.models import UtilisateurSUPPER, NotificationUtilisateur
        
        # Chef du poste origine
        chefs_origine = UtilisateurSUPPER.objects.filter(
            poste_affectation=poste_origine,
            habilitation__in=['chef_peage', 'chef_pesage'],
            is_active=True
        )
        
        for chef in chefs_origine:
            NotificationUtilisateur.objects.create(
                destinataire=chef,
                expediteur=user,
                titre="Tickets cédés à un autre poste",
                message=(
                    f"Transfert de {nombre_tickets} tickets "
                    f"{couleur.libelle_affichage} #{numero_premier}-{numero_dernier} "
                    f"vers {poste_destination.nom}.\n"
                    f"Montant : {montant:,.0f} FCFA\n"
                    f"Bordereau N°{numero_bordereau}"
                ),
                type_notification='warning'
            )
        
        # Chef du poste destination
        chefs_destination = UtilisateurSUPPER.objects.filter(
            poste_affectation=poste_destination,
            habilitation__in=['chef_peage', 'chef_pesage'],
            is_active=True
        )
        
        for chef in chefs_destination:
            NotificationUtilisateur.objects.create(
                destinataire=chef,
                expediteur=user,
                titre="Nouveaux tickets reçus",
                message=(
                    f"Réception de {nombre_tickets} tickets "
                    f"{couleur.libelle_affichage} #{numero_premier}-{numero_dernier} "
                    f"en provenance de {poste_origine.nom}.\n"
                    f"Montant : {montant:,.0f} FCFA\n"
                    f"Bordereau N°{numero_bordereau}"
                ),
                type_notification='success'
            )

    @classmethod
    def obtenir_historique_complet_ticket(cls, numero_ticket, couleur, annee=None):
        """
        Obtient l'historique complet d'un numéro de ticket (tous postes, toutes années)
        
        AMÉLIORATION : Inclut les transferts entre postes
        
        Args:
            numero_ticket: Numéro du ticket
            couleur: Instance de CouleurTicket
            annee: Année spécifique (optionnel)
        
        Returns:
            dict avec l'historique complet par année et par poste
        """
        from django.db.models import Q
        from datetime import date
        
        # Construire la requête
        query = Q(
            numero_premier__lte=numero_ticket,
            numero_dernier__gte=numero_ticket,
            couleur=couleur
        )
        
        if annee:
            debut_annee = date(annee, 1, 1)
            fin_annee = date(annee, 12, 31)
            query &= Q(date_reception__range=[debut_annee, fin_annee])
        
        # Récupérer toutes les séries contenant ce ticket
        series = cls.objects.filter(query).select_related(
            'poste', 'poste_destination_transfert', 'reference_recette'
        ).order_by('date_reception')
        
        # Grouper par année et poste
        historique = {}
        
        for serie in series:
            annee_serie = serie.date_reception.year
            
            if annee_serie not in historique:
                historique[annee_serie] = []
            
            info = {
                'poste': serie.poste.nom,
                'date_reception': serie.date_reception,
                'statut': serie.statut,
                'type_entree': serie.get_type_entree_display() if serie.type_entree else 'Non défini',
                'serie_complete': f"#{serie.numero_premier}-{serie.numero_dernier}",
                'nombre_tickets': serie.nombre_tickets
            }
            
            # Ajouter les détails selon le statut
            if serie.statut == 'stock':
                info['message'] = f"✅ En stock au poste {serie.poste.nom}"
            
            elif serie.statut == 'vendu':
                info['date_vente'] = serie.date_utilisation
                info['message'] = f"💰 Vendu le {serie.date_utilisation.strftime('%d/%m/%Y')} au poste {serie.poste.nom}"
                
                if serie.reference_recette:
                    info['recette'] = serie.reference_recette.montant_declare
            
            elif serie.statut == 'transfere':
                if serie.poste_destination_transfert:
                    info['poste_destination'] = serie.poste_destination_transfert.nom
                    info['message'] = (
                        f"📦 Transféré du poste {serie.poste.nom} "
                        f"vers {serie.poste_destination_transfert.nom}"
                    )
                else:
                    info['message'] = f"📦 Transféré depuis {serie.poste.nom}"
            
            if serie.commentaire:
                info['commentaire'] = serie.commentaire
            
            historique[annee_serie].append(info)
        
        return historique



    def __str__(self):
        return f"{self.couleur.libelle_affichage} #{self.numero_premier}-{self.numero_dernier} ({self.get_statut_display()})"
    
    
    def clean(self):
        """
        Validation MINIMALE - uniquement cohérence des données
        Pas de vérification d'unicité ici
        """
        from django.core.exceptions import ValidationError
        
        if self.numero_premier and self.numero_dernier:
            if self.numero_premier > self.numero_dernier:
                raise ValidationError({
                    'numero_dernier': "Le numéro du dernier ticket doit être supérieur ou égal au premier"
                })
    
    def save(self, *args, **kwargs):
        """
        Sauvegarde SIMPLE - calculs automatiques uniquement
        Pas d'appel à clean() - les vues gèrent la validation
        """
        from decimal import Decimal
        
        # Calculs automatiques
        if self.numero_premier and self.numero_dernier:
            self.nombre_tickets = self.numero_dernier - self.numero_premier + 1
            self.valeur_monetaire = Decimal(self.nombre_tickets) * Decimal('500')
        
        # Sauvegarde directe sans validation métier
        super().save(*args, **kwargs)


class DetailVenteTicket(models.Model):
    """
    Détail d'une vente de tickets (pour une recette)
    Permet de gérer plusieurs séries vendues dans une même journée
    """
    recette = models.ForeignKey(
        'RecetteJournaliere',
        on_delete=models.CASCADE,
        related_name='details_ventes_tickets',
        verbose_name=_("Recette")
    )
    
    couleur = models.ForeignKey(
        CouleurTicket,
        on_delete=models.PROTECT,
        verbose_name=_("Couleur")
    )
    
    numero_premier = models.IntegerField(
        validators=[MinValueValidator(1)],
        verbose_name=_("Premier ticket vendu")
    )
    
    numero_dernier = models.IntegerField(
        validators=[MinValueValidator(1)],
        verbose_name=_("Dernier ticket vendu")
    )
    
    nombre_tickets = models.IntegerField(
        verbose_name=_("Nombre de tickets vendus")
    )
    
    montant = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Montant (FCFA)")
    )
    
    ordre = models.IntegerField(
        default=1,
        verbose_name=_("Ordre de saisie"),
        help_text=_("Pour conserver l'ordre de saisie des séries")
    )
    
    class Meta:
        verbose_name = _("Détail vente tickets")
        verbose_name_plural = _("Détails ventes tickets")
        ordering = ['recette', 'ordre']
        indexes = [
            models.Index(fields=['recette', 'ordre']),
        ]
    
    def __str__(self):
        return f"{self.couleur.libelle_affichage} #{self.numero_premier}-{self.numero_dernier} - {self.montant} FCFA"
    
    def save(self, *args, **kwargs):
        # Calcul automatique
        self.nombre_tickets = self.numero_dernier - self.numero_premier + 1
        self.montant = Decimal(self.nombre_tickets) * Decimal('500')
        
        super().save(*args, **kwargs)


from django.db import models
from django.db.models import Sum, Q
from decimal import Decimal
from datetime import datetime, date, timedelta

class StockEvent(models.Model):
    """
    Modèle Event Sourcing pour les mouvements de stock
    Chaque ligne représente un événement immuable dans l'historique du stock
    """
    
    EVENT_TYPES = [
        ('INITIAL', 'Stock Initial'),
        ('CHARGEMENT', 'Chargement de Stock'),
        ('VENTE', 'Vente de Tickets'),
        ('TRANSFERT_IN', 'Transfert Entrant'),
        ('TRANSFERT_OUT', 'Transfert Sortant'),
        ('AJUSTEMENT', 'Ajustement Manuel'),
        ('REGULARISATION', 'Régularisation'),
    ]
    
    # Identifiants
    poste = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='stock_events',
        verbose_name="Poste"
    )
    
    # Type et timing de l'événement
    event_type = models.CharField(
        max_length=20,
        choices=EVENT_TYPES,
        verbose_name="Type d'événement"
    )
    
    event_datetime = models.DateTimeField(
        verbose_name="Date et heure de l'événement",
        db_index=True
    )
    
    # Valeurs de l'événement
    montant_variation = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Variation du stock (+ ou -)",
        help_text="Positif pour ajout, négatif pour retrait"
    )
    
    nombre_tickets_variation = models.IntegerField(
        verbose_name="Variation en nombre de tickets",
        help_text="Positif pour ajout, négatif pour retrait"
    )
    
    # Stock résultant après cet événement
    stock_resultant = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Stock après l'événement",
        help_text="Valeur du stock après application de cet événement"
    )
    
    tickets_resultants = models.IntegerField(
        verbose_name="Nombre de tickets après l'événement"
    )
    
    # Métadonnées
    effectue_par = models.ForeignKey(
        'accounts.UtilisateurSUPPER',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Effectué par"
    )
    
    reference_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="ID de référence",
        help_text="ID de la recette, transfert, etc."
    )
    
    reference_type = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Type de référence",
        help_text="RecetteJournaliere, HistoriqueStock, etc."
    )
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Métadonnées",
        help_text="Données additionnelles (séries, couleurs, etc.)"
    )
    
    commentaire = models.TextField(
        blank=True,
        verbose_name="Commentaire"
    )
    
    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Créé le"
    )
    
    # Flag pour événements annulés/corrigés
    is_cancelled = models.BooleanField(
        default=False,
        verbose_name="Événement annulé"
    )
    
    cancellation_event = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_by',
        verbose_name="Annulé par l'événement"
    )
    
    class Meta:
        verbose_name = "Événement de stock"
        verbose_name_plural = "Événements de stock"
        ordering = ['poste', 'event_datetime']
        indexes = [
            models.Index(fields=['poste', 'event_datetime']),
            models.Index(fields=['poste', '-event_datetime']),
            models.Index(fields=['event_type']),
            models.Index(fields=['reference_type', 'reference_id']),
        ]
    
    def save(self, *args, **kwargs):
        """Calcul automatique du stock résultant"""
        if not self.pk:  # Nouvelle création
            # Calculer le stock résultant basé sur l'événement précédent
            previous_stock = self.get_previous_stock_value()
            self.stock_resultant = previous_stock + self.montant_variation
            self.tickets_resultants = int(self.stock_resultant / 500)
        
        super().save(*args, **kwargs)
    
    def get_previous_stock_value(self):
        """Obtient la valeur du stock avant cet événement"""
        previous_event = StockEvent.objects.filter(
            poste=self.poste,
            event_datetime__lt=self.event_datetime,
            is_cancelled=False
        ).order_by('-event_datetime').first()
        
        if previous_event:
            return previous_event.stock_resultant
        return Decimal('0')
    

    @classmethod
    def get_stock_at_date(cls, poste, target_date, exclude_event_id=None):
        """
        Calcule le stock exact à une date donnée via Event Sourcing
        Corrige le problème du stock initial à 0
        
        Args:
            poste: Instance du Poste
            target_date: Date/DateTime cible
            exclude_event_id: ID d'un event à exclure (optionnel)
        
        Returns:
            tuple: (valeur_monetaire, nombre_tickets)
        """
        
        # S'assurer qu'on a un datetime
        if isinstance(target_date, datetime):
            datetime_target = target_date
        else:
            # Convertir date en datetime avec l'heure maximale du jour
            datetime_target = timezone.make_aware(
                datetime.combine(target_date, time.max)
            )
        
        # Requête de base pour les événements
        events_query = cls.objects.filter(
            poste=poste,
            event_datetime__lte=datetime_target,
            is_cancelled=False  # Important: exclure les événements annulés
        )
        
        # Exclure un événement spécifique si demandé
        if exclude_event_id:
            events_query = events_query.exclude(id=exclude_event_id)
        
        # Calculer les totaux cumulés
        totaux = events_query.aggregate(
            total_valeur=Sum('montant_variation'),
            total_tickets=Sum('nombre_tickets_variation')
        )
        
        valeur_totale = totaux['total_valeur'] if totaux['total_valeur'] is not None else Decimal('0')
        tickets_total = totaux['total_tickets'] if totaux['total_tickets'] is not None else 0
        
        # S'assurer que les valeurs ne sont pas négatives
        if valeur_totale < 0:
            valeur_totale = Decimal('0')
        if tickets_total < 0:
            tickets_total = 0
        
        return valeur_totale, tickets_total


    @classmethod
    def recalculate_stock_from_historique(cls, poste, up_to_date=None):
        """
        Recalcule le stock complet depuis l'historique
        Pour corriger les incohérences
        
        Args:
            poste: Instance du Poste
            up_to_date: Date limite (optionnel)
        """
        from inventaire.models import HistoriqueStock
        from decimal import Decimal
        
        # Supprimer les anciens events pour ce poste
        cls.objects.filter(poste=poste).delete()
        
        # Récupérer tous les historiques
        historiques = HistoriqueStock.objects.filter(
            poste=poste
        ).order_by('date_mouvement')
        
        if up_to_date:
            historiques = historiques.filter(date_mouvement__lte=up_to_date)
        
        stock_courant = Decimal('0')
        tickets_courant = 0
        
        for hist in historiques:
            # Calculer la variation
            if hist.type_mouvement == 'CREDIT':
                variation_montant = hist.montant
                variation_tickets = hist.nombre_tickets
            else:  # DEBIT
                variation_montant = -hist.montant
                variation_tickets = -hist.nombre_tickets
            
            # Mettre à jour le stock courant
            stock_courant += variation_montant
            tickets_courant += variation_tickets
            
            # S'assurer que le stock ne devient pas négatif
            if stock_courant < 0:
                stock_courant = Decimal('0')
            if tickets_courant < 0:
                tickets_courant = 0
            
            # Déterminer le type d'événement
            if hist.type_mouvement == 'CREDIT':
                if hist.type_stock == 'imprimerie_nationale':
                    event_type = 'CHARGEMENT'
                elif hist.type_stock == 'regularisation':
                    event_type = 'REGULARISATION'
                elif hist.poste_origine:
                    event_type = 'TRANSFERT_IN'
                else:
                    event_type = 'CHARGEMENT'  # Par défaut pour CREDIT
            else:  # DEBIT
                if hasattr(hist, 'reference_recette') and hist.reference_recette:
                    event_type = 'VENTE'
                elif hist.poste_destination:
                    event_type = 'TRANSFERT_OUT'
                else:
                    event_type = 'AJUSTEMENT'  # Par défaut pour DEBIT
            
            # Créer l'event
            cls.objects.create(
                poste=poste,
                event_type=event_type,
                event_datetime=hist.date_mouvement,
                montant_variation=variation_montant,
                nombre_tickets_variation=variation_tickets,
                stock_resultant=stock_courant,
                tickets_resultants=tickets_courant,
                effectue_par=hist.effectue_par,
                reference_id=str(hist.id),
                reference_type='HistoriqueStock',
                commentaire=hist.commentaire or ''
            )
        
        return stock_courant, tickets_courant


    @classmethod
    def get_stock_history(cls, poste, date_debut, date_fin, interval='daily'):
        """
        Obtient l'historique du stock sur une période
        
        Args:
            poste: Instance du Poste
            date_debut: Date de début
            date_fin: Date de fin
            interval: 'daily', 'weekly', 'monthly'
        
        Returns:
            list: Liste de dictionnaires avec date et valeur du stock
        """
        from datetime import timedelta
        
        history = []
        current_date = date_debut
        
        # Déterminer l'incrément selon l'intervalle
        if interval == 'daily':
            delta = timedelta(days=1)
        elif interval == 'weekly':
            delta = timedelta(weeks=1)
        elif interval == 'monthly':
            delta = timedelta(days=30)  # Approximation
        else:
            delta = timedelta(days=1)
        
        while current_date <= date_fin:
            valeur, nombre_tickets = cls.get_stock_at_date(poste, current_date)
            history.append({
                'date': current_date,
                'valeur': valeur,
                'nombre_tickets': nombre_tickets
            })
            current_date += delta
        
        return history

    @classmethod
    def create_from_historique(cls, historique):
        """
        Crée un StockEvent à partir d'un HistoriqueStock existant
        Utilisé pour la migration des données
        """
        # Déterminer le type d'événement
        if historique.type_mouvement == 'CREDIT':
            if historique.type_stock == 'regularisation':
                event_type = 'REGULARISATION'
            elif historique.type_stock == 'reapprovisionnement':
                event_type = 'TRANSFERT_IN'
            else:
                event_type = 'CHARGEMENT'
        else:  # DEBIT
            if historique.poste_destination:
                event_type = 'TRANSFERT_OUT'
            else:
                event_type = 'VENTE'
        
        # Créer les métadonnées
        metadata = {
            'stock_avant': str(historique.stock_avant),
            'stock_apres': str(historique.stock_apres),
            'type_stock': historique.type_stock
        }
        
        if historique.poste_origine:
            metadata['poste_origine_id'] = historique.poste_origine.id
        if historique.poste_destination:
            metadata['poste_destination_id'] = historique.poste_destination.id
        if historique.numero_bordereau:
            metadata['numero_bordereau'] = historique.numero_bordereau
        
        # Calculer la variation
        variation = historique.stock_apres - historique.stock_avant
        
        return cls.objects.create(
            poste=historique.poste,
            event_type=event_type,
            event_datetime=historique.date_mouvement,
            montant_variation=variation,
            nombre_tickets_variation=historique.nombre_tickets if historique.type_mouvement == 'CREDIT' else -historique.nombre_tickets,
            stock_resultant=historique.stock_apres,
            tickets_resultants=int(historique.stock_apres / 500),
            effectue_par=historique.effectue_par,
            reference_id=str(historique.id),
            reference_type='HistoriqueStock',
            metadata=metadata,
            commentaire=historique.commentaire or ''
        )


class StockSnapshot(models.Model):
    """
    Snapshots périodiques pour optimiser les calculs
    Permet d'éviter de recalculer depuis le début à chaque fois
    """
    
    poste = models.ForeignKey(
        'accounts.Poste',
        on_delete=models.CASCADE,
        related_name='stock_snapshots',
        verbose_name="Poste"
    )
    
    snapshot_date = models.DateField(
        verbose_name="Date du snapshot",
        db_index=True
    )
    
    valeur_stock = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Valeur du stock"
    )
    
    nombre_tickets = models.IntegerField(
        verbose_name="Nombre de tickets"
    )
    
    nombre_events = models.IntegerField(
        verbose_name="Nombre d'événements inclus"
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Créé le"
    )
    
    class Meta:
        verbose_name = "Snapshot de stock"
        verbose_name_plural = "Snapshots de stock"
        unique_together = [['poste', 'snapshot_date']]
        ordering = ['poste', '-snapshot_date']
        indexes = [
            models.Index(fields=['poste', '-snapshot_date']),
        ]
    
    @classmethod
    def create_snapshot(cls, poste, target_date=None):
        """Crée un snapshot pour un poste à une date donnée"""
        if target_date is None:
            target_date = date.today()
        
        stock_data = StockEvent.get_stock_at_date(poste, target_date, use_cache=False)
        
        snapshot, created = cls.objects.update_or_create(
            poste=poste,
            snapshot_date=target_date,
            defaults={
                'valeur_stock': stock_data['valeur'],
                'nombre_tickets': stock_data['nombre_tickets'],
                'nombre_events': stock_data['nombre_events']
            }
        )
        
        return snapshot, created

# inventaire/models.py - AJOUT AU FICHIER EXISTANT

class EtatInventaireSnapshot(models.Model):
    """
    Snapshots périodiques pour capturer l'état d'un poste à un moment donné
    Permet la reconstruction historique des indicateurs
    """
    
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='snapshots_inventaire',
        verbose_name=_("Poste")
    )
    
    date_snapshot = models.DateField(
        verbose_name=_("Date du snapshot"),
        db_index=True
    )
    
    # Taux de déperdition à cette date
    taux_deperdition = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Taux de déperdition (%)")
    )
    
    # Risque de baisse annuel à cette date
    risque_baisse_annuel = models.BooleanField(
        default=False,
        verbose_name=_("En risque de baisse annuel")
    )
    
    recettes_periode_actuelle = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Recettes cumulées période actuelle")
    )
    
    recettes_periode_n1 = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Recettes même période N-1")
    )
    
    pourcentage_evolution = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("Pourcentage d'évolution (%)")
    )
    
    # Stock à cette date
    stock_valeur = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name=_("Valeur du stock (FCFA)")
    )
    
    stock_tickets = models.IntegerField(
        default=0,
        verbose_name=_("Nombre de tickets en stock")
    )
    
    date_epuisement_prevu = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Date d'épuisement prévue du stock")
    )
    
    risque_grand_stock = models.BooleanField(
        default=False,
        verbose_name=_("Risque de grand stock"),
        help_text=_("Stock qui dépasse le 31 décembre")
    )
    
    # Métadonnées
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Créé le")
    )
    
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Métadonnées additionnelles")
    )
    
    class Meta:
        verbose_name = _("Snapshot état inventaire")
        verbose_name_plural = _("Snapshots états inventaires")
        unique_together = [['poste', 'date_snapshot']]
        ordering = ['poste', '-date_snapshot']
        indexes = [
            models.Index(fields=['poste', '-date_snapshot']),
            models.Index(fields=['date_snapshot']),
            models.Index(fields=['risque_baisse_annuel']),
            models.Index(fields=['risque_grand_stock']),
        ]
    
    def __str__(self):
        return f"Snapshot {self.poste.nom} - {self.date_snapshot}"
    
    @classmethod
    def creer_snapshot(cls, poste, date_snapshot=None):
        """
        Crée un snapshot de l'état actuel d'un poste
        
        Args:
            poste: Instance du Poste
            date_snapshot: Date du snapshot (par défaut aujourd'hui)
        
        Returns:
            EtatInventaireSnapshot: Le snapshot créé
        """
        from django.db.models import Sum
        from decimal import Decimal
        from datetime import date, timedelta
        
        if date_snapshot is None:
            date_snapshot = date.today()
        
        # Calculer le taux de déperdition à cette date
        derniere_recette = RecetteJournaliere.objects.filter(
            poste=poste,
            date__lte=date_snapshot,
            taux_deperdition__isnull=False
        ).order_by('-date').first()
        
        taux_deperdition = derniere_recette.taux_deperdition if derniere_recette else None
        
        # Calculer le risque de baisse annuel à cette date
        annee = date_snapshot.year
        debut_annee = date(annee, 1, 1)
        
        recettes_actuelles = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[debut_annee, date_snapshot]
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        # Même période année précédente
        debut_annee_prec = date(annee - 1, 1, 1)
        date_fin_prec = date(annee - 1, date_snapshot.month, date_snapshot.day)
        
        recettes_n1 = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[debut_annee_prec, date_fin_prec]
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        
        # Calculer le risque de baisse
        risque_baisse = False
        pourcentage_evolution = None
        
        if recettes_n1 > 0:
            pourcentage_evolution = ((recettes_actuelles - recettes_n1) / recettes_n1) * 100
            risque_baisse = pourcentage_evolution < -5
        
        # Calculer le stock à cette date via Event Sourcing
        stock_valeur, stock_tickets = StockEvent.get_stock_at_date(poste, date_snapshot)
        
        # Calculer la date d'épuisement du stock
        date_epuisement = None
        risque_grand_stock = False
        
        if stock_valeur > 0:
            # Utiliser la moyenne des 30 jours précédents
            date_debut_moyenne = date_snapshot - timedelta(days=30)
            
            ventes_moyennes = RecetteJournaliere.objects.filter(
                poste=poste,
                date__range=[date_debut_moyenne, date_snapshot]
            ).aggregate(
                total=Sum('montant_declare'),
                count=models.Count('id')
            )
            
            if ventes_moyennes['total'] and ventes_moyennes['count'] > 0:
                vente_moy_jour = ventes_moyennes['total'] / ventes_moyennes['count']
                
                if vente_moy_jour > 0:
                    jours_restants = int(stock_valeur / vente_moy_jour)
                    date_epuisement = date_snapshot + timedelta(days=jours_restants)
                    
                    # Vérifier si dépasse le 31 décembre
                    fin_annee = date(date_snapshot.year, 12, 31)
                    risque_grand_stock = date_epuisement > fin_annee
        
        # Créer ou mettre à jour le snapshot
        snapshot, created = cls.objects.update_or_create(
            poste=poste,
            date_snapshot=date_snapshot,
            defaults={
                'taux_deperdition': taux_deperdition,
                'risque_baisse_annuel': risque_baisse,
                'recettes_periode_actuelle': recettes_actuelles,
                'recettes_periode_n1': recettes_n1,
                'pourcentage_evolution': pourcentage_evolution,
                'stock_valeur': stock_valeur,
                'stock_tickets': stock_tickets,
                'date_epuisement_prevu': date_epuisement,
                'risque_grand_stock': risque_grand_stock,
                'metadata': {
                    'annee_reference': annee,
                    'derniere_recette_date': derniere_recette.date.isoformat() if derniere_recette else None,
                }
            }
        )
        
        return snapshot
    
    @classmethod
    def obtenir_ou_creer_snapshot(cls, poste, date_snapshot):
        """
        Récupère un snapshot existant ou le crée s'il n'existe pas
        
        Args:
            poste: Instance du Poste
            date_snapshot: Date du snapshot
        
        Returns:
            EtatInventaireSnapshot: Le snapshot
        """
        try:
            return cls.objects.get(poste=poste, date_snapshot=date_snapshot)
        except cls.DoesNotExist:
            return cls.creer_snapshot(poste, date_snapshot)
    
    def calculer_impact_taux_deperdition(self, snapshot_precedent):
        """
        Calcule l'impact sur le taux de déperdition
        
        Args:
            snapshot_precedent: Snapshot de la période précédente
        
        Returns:
            str: 'positif', 'negatif', ou 'nul'
        """
        if not self.taux_deperdition or not snapshot_precedent or not snapshot_precedent.taux_deperdition:
            return 'nul'
        
        # Cas 1: Régression du taux (amélioration)
        # Ex: -35% → -32% = positif
        if self.taux_deperdition > snapshot_precedent.taux_deperdition:
            return 'positif'
        
        # Cas 2: Passage en zone critique
        # Ex: -25% → -32% = négatif
        if snapshot_precedent.taux_deperdition >= -30 and self.taux_deperdition < -30:
            return 'negatif'
        
        # Cas 3: Amélioration continue
        # Ex: -40% → -28% = positif
        if snapshot_precedent.taux_deperdition < -30 and self.taux_deperdition >= -30:
            return 'positif'
        
        # Cas 4: Dégradation
        if self.taux_deperdition < snapshot_precedent.taux_deperdition:
            return 'negatif'
        
        return 'nul'
    
    def calculer_impact_risque_baisse(self, snapshot_precedent):
        """
        Calcule l'impact sur le risque de baisse annuel
        
        Returns:
            str: 'positif', 'negatif', ou 'nul'
        """
        if not snapshot_precedent:
            return 'nul'
        
        # Était en risque et ne l'est plus = positif
        if snapshot_precedent.risque_baisse_annuel and not self.risque_baisse_annuel:
            return 'positif'
        
        # N'était pas en risque et l'est maintenant = négatif
        if not snapshot_precedent.risque_baisse_annuel and self.risque_baisse_annuel:
            return 'negatif'
        
        # Pas de changement
        return 'nul'
    
    def calculer_impact_grand_stock(self, snapshot_precedent):
        """
        Calcule l'impact sur le risque de grand stock
        
        Returns:
            str: 'positif', 'negatif', ou 'nul'
        """
        if not snapshot_precedent or not self.date_epuisement_prevu or not snapshot_precedent.date_epuisement_prevu:
            return 'nul'
        
        # Si la date d'épuisement s'est rapprochée = positif
        if self.date_epuisement_prevu < snapshot_precedent.date_epuisement_prevu:
            return 'positif'
        
        # Si la date d'épuisement s'est éloignée = négatif
        if self.date_epuisement_prevu > snapshot_precedent.date_epuisement_prevu:
            return 'negatif'
        
        # Même date
        return 'nul'


class JourneeImpertinente(models.Model):
    """
    Modèle pour suivre les journées impertinentes par poste
    """
    
    poste = models.ForeignKey(
        Poste,
        on_delete=models.CASCADE,
        related_name='journees_impertinentes',
        verbose_name=_("Poste")
    )
    
    date = models.DateField(
        verbose_name=_("Date de la journée impertinente"),
        db_index=True
    )
    
    recette_declaree = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Recette déclarée")
    )
    
    recette_potentielle = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Recette potentielle")
    )
    
    ecart = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Écart")
    )
    
    commentaire = models.TextField(
        blank=True,
        verbose_name=_("Commentaire")
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Créé le")
    )
    
    class Meta:
        verbose_name = _("Journée impertinente")
        verbose_name_plural = _("Journées impertinentes")
        unique_together = [['poste', 'date']]
        ordering = ['-date', 'poste__nom']
        indexes = [
            models.Index(fields=['poste', '-date']),
            models.Index(fields=['date']),
        ]
    
    def __str__(self):
        return f"{self.poste.nom} - {self.date} (Impertinente)"
    
    @classmethod
    def compter_pour_periode(cls, poste, date_debut, date_fin):
        """
        Compte les journées impertinentes pour un poste sur une période
        
        Args:
            poste: Instance du Poste
            date_debut: Date de début
            date_fin: Date de fin
        
        Returns:
            int: Nombre de journées impertinentes
        """
        return cls.objects.filter(
            poste=poste,
            date__range=[date_debut, date_fin]
        ).count()