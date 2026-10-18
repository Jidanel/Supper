# inventaire/services/forecasting_service.py
# ===================================================================
# FICHIER ORIGINAL + NOUVELLES MÉTHODES POUR COMMANDES PAR PÉRIODE
# ===================================================================

from decimal import Decimal
from datetime import date, timedelta
import pandas as pd
import numpy as np
from django.db.models import Sum, Count, Avg
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.seasonal import seasonal_decompose
import warnings
warnings.filterwarnings('ignore')

from inventaire.models import RecetteJournaliere
from accounts.models import Poste

import logging
logger = logging.getLogger('supper')


class ForecastingService:
    """
    Service de prévisions des recettes utilisant des modèles statistiques avancés
    """

    # ===================================================================
    # MÉTHODES EXISTANTES (NE PAS MODIFIER)
    # ===================================================================

    @staticmethod
    def preparer_donnees_historiques(poste, date_fin=None, nb_jours_min=90):
        """
        Prépare les données historiques pour l'analyse
        Minimum 90 jours pour avoir des prévisions fiables
        """
        if date_fin is None:
            date_fin = date.today()

        date_debut = date_fin - timedelta(days=365)  # 1 an d'historique

        # Récupérer toutes les recettes
        recettes = RecetteJournaliere.objects.filter(
            poste=poste,
            date__gte=date_debut,
            date__lte=date_fin
        ).order_by('date').values('date', 'montant_declare')

        if not recettes or len(recettes) < nb_jours_min:
            return None, f"Pas assez de données (minimum {nb_jours_min} jours requis)"

        # Créer DataFrame pandas
        df = pd.DataFrame(list(recettes))
        df['date'] = pd.to_datetime(df['date'])
        df['montant'] = df['montant_declare'].astype(float)
        df = df.set_index('date')

        # Compléter les dates manquantes avec interpolation
        df = df.resample('D').asfreq()
        df['montant'] = df['montant'].interpolate(method='linear', limit=7)
        df = df.fillna(df['montant'].mean())

        return df, None

    @staticmethod
    def detecter_saisonnalite(serie_temporelle):
        """
        Détecte la saisonnalité dans les données (hebdomadaire, mensuelle)
        """
        try:
            # Décomposition pour détecter saisonnalité
            decomposition = seasonal_decompose(
                serie_temporelle,
                model='additive',
                period=7,  # Saisonnalité hebdomadaire
                extrapolate_trend='freq'
            )

            # Calculer la force de la saisonnalité
            seasonal_strength = np.var(decomposition.seasonal) / np.var(decomposition.resid + decomposition.seasonal)

            return {
                'has_seasonality': seasonal_strength > 0.3,
                'seasonal_strength': float(seasonal_strength),
                'trend': decomposition.trend,
                'seasonal': decomposition.seasonal
            }
        except:
            return {'has_seasonality': False, 'seasonal_strength': 0}

    @staticmethod
    def prevoir_recettes(poste, nb_jours_future=365, date_reference=None):
        """
        Prévoit les recettes futures en utilisant Holt-Winters Exponential Smoothing

        Args:
            poste: Instance du poste
            nb_jours_future: Nombre de jours à prévoir
            date_reference: Date de référence (par défaut aujourd'hui)

        Returns:
            dict avec prévisions détaillées
        """
        if date_reference is None:
            date_reference = date.today()

        # Préparer les données
        df, erreur = ForecastingService.preparer_donnees_historiques(poste, date_reference)

        if df is None:
            return {
                'success': False,
                'error': erreur,
                'predictions': None
            }

        try:
            # Détecter saisonnalité
            saisonnalite = ForecastingService.detecter_saisonnalite(df['montant'])

            # Configurer le modèle Holt-Winters
            if saisonnalite['has_seasonality']:
                # Avec saisonnalité
                model = ExponentialSmoothing(
                    df['montant'],
                    seasonal_periods=7,  # Cycle hebdomadaire
                    trend='add',
                    seasonal='add',
                    initialization_method='estimated'
                )
            else:
                # Sans saisonnalité (tendance uniquement)
                model = ExponentialSmoothing(
                    df['montant'],
                    trend='add',
                    seasonal=None,
                    initialization_method='estimated'
                )

            # Entraîner le modèle
            fitted_model = model.fit(optimized=True, remove_bias=True)

            # Faire les prévisions
            forecast = fitted_model.forecast(steps=nb_jours_future)

            # Créer les dates futures
            date_debut_prevision = date_reference + timedelta(days=1)
            dates_futures = pd.date_range(
                start=date_debut_prevision,
                periods=nb_jours_future,
                freq='D'
            )

            # Créer DataFrame des prévisions
            df_previsions = pd.DataFrame({
                'date': dates_futures,
                'montant_prevu': forecast.values
            })

            # S'assurer que les prévisions sont positives
            df_previsions['montant_prevu'] = df_previsions['montant_prevu'].clip(lower=0)

            # Calculer intervalles de confiance (simulation simple)
            std_residuals = np.std(fitted_model.resid)
            df_previsions['borne_inf'] = (df_previsions['montant_prevu'] - 1.96 * std_residuals).clip(lower=0)
            df_previsions['borne_sup'] = df_previsions['montant_prevu'] + 1.96 * std_residuals

            return {
                'success': True,
                'poste': poste,
                'date_reference': date_reference,
                'has_seasonality': saisonnalite['has_seasonality'],
                'seasonal_strength': saisonnalite['seasonal_strength'],
                'predictions': df_previsions,
                'model_params': {
                    'alpha': fitted_model.params['smoothing_level'],
                    'beta': fitted_model.params.get('smoothing_trend', None),
                    'gamma': fitted_model.params.get('smoothing_seasonal', None)
                },
                'quality_metrics': {
                    'aic': fitted_model.aic,
                    'bic': fitted_model.bic,
                    'mse': np.mean(fitted_model.resid ** 2)
                }
            }

        except Exception as e:
            return {
                'success': False,
                'error': f"Erreur lors de la prévision: {str(e)}",
                'predictions': None
            }

    @staticmethod
    def calculer_estimations_periodes(poste, date_reference=None):
        """
        Calcule les estimations pour différentes périodes futures
        """
        if date_reference is None:
            date_reference = date.today()

        # Obtenir prévisions pour 1 an
        resultats = ForecastingService.prevoir_recettes(
            poste,
            nb_jours_future=365,
            date_reference=date_reference
        )

        if not resultats['success']:
            return None

        df_prev = resultats['predictions']

        # Calculer les estimations par période
        estimations = {
            'hebdomadaire': float(df_prev['montant_prevu'].iloc[:7].sum()),
            'mensuelle': float(df_prev['montant_prevu'].iloc[:30].sum()),
            'trimestrielle': float(df_prev['montant_prevu'].iloc[:90].sum()),
            'semestrielle': float(df_prev['montant_prevu'].iloc[:180].sum()),
            'annuelle': float(df_prev['montant_prevu'].sum()),
        }

        # Ajouter les intervalles de confiance
        estimations_ic = {}
        for periode, jours in [('hebdomadaire', 7), ('mensuelle', 30),
                               ('trimestrielle', 90), ('semestrielle', 180),
                               ('annuelle', 365)]:
            estimations_ic[periode] = {
                'prevision': float(df_prev['montant_prevu'].iloc[:jours].sum()),
                'borne_inf': float(df_prev['borne_inf'].iloc[:jours].sum()),
                'borne_sup': float(df_prev['borne_sup'].iloc[:jours].sum())
            }

        return {
            'estimations_simples': estimations,
            'estimations_avec_ic': estimations_ic,
            'qualite_modele': resultats['quality_metrics'],
            'saisonnalite': resultats['has_seasonality']
        }

    @staticmethod
    def calculer_commande_tickets_optimale(poste, date_cible=None):
        """
        Calcule la commande optimale de tickets jusqu'au 24 décembre
        en utilisant les prévisions
        """
        if date_cible is None:
            # Par défaut : 24 décembre de l'année en cours
            annee_actuelle = date.today().year
            date_cible = date(annee_actuelle, 12, 24)

        today = date.today()

        if date_cible <= today:
            return {
                'success': False,
                'error': "La date cible doit être dans le futur"
            }

        jours_restants = (date_cible - today).days

        # Obtenir les prévisions
        resultats_prevision = ForecastingService.prevoir_recettes(
            poste,
            nb_jours_future=jours_restants
        )

        if not resultats_prevision['success']:
            return resultats_prevision

        df_prev = resultats_prevision['predictions']

        # Ventes prévues jusqu'à la date cible
        ventes_prevues = float(df_prev['montant_prevu'].sum())
        ventes_prevues_inf = float(df_prev['borne_inf'].sum())
        ventes_prevues_sup = float(df_prev['borne_sup'].sum())

        # Stock actuel
        from inventaire.models import GestionStock
        try:
            stock_obj = GestionStock.objects.get(poste=poste)
            stock_actuel = float(stock_obj.valeur_monetaire)
        except GestionStock.DoesNotExist:
            stock_actuel = 0

        # Recettes déjà réalisées cette année
        recettes_annee = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=today.year,
            date__lte=today
        ).aggregate(total=Sum('montant_declare'))['total'] or Decimal('0')
        recettes_annee = float(recettes_annee)

        # Calcul de la commande optimale (scénario moyen)
        montant_a_commander = max(0, ventes_prevues - stock_actuel)

        # Calcul conservateur (scénario pessimiste)
        montant_conservateur = max(0, ventes_prevues_sup - stock_actuel)

        # Calcul optimiste
        montant_optimiste = max(0, ventes_prevues_inf - stock_actuel)

        # Nombre de tickets (500 FCFA par ticket)
        tickets_moyen = int(montant_a_commander / 500)
        tickets_conservateur = int(montant_conservateur / 500)
        tickets_optimiste = int(montant_optimiste / 500)

        # Stock final estimé
        stock_final_prevu = stock_actuel + montant_a_commander - ventes_prevues

        return {
            'success': True,
            'poste': poste,
            'date_cible': date_cible,
            'jours_restants': jours_restants,
            'stock_actuel': stock_actuel,
            'recettes_annee': recettes_annee,
            'ventes_prevues': ventes_prevues,
            'scenarios': {
                'optimiste': {
                    'montant': montant_optimiste,
                    'tickets': tickets_optimiste
                },
                'moyen': {
                    'montant': montant_a_commander,
                    'tickets': tickets_moyen
                },
                'conservateur': {
                    'montant': montant_conservateur,
                    'tickets': tickets_conservateur
                }
            },
            'stock_final_prevu': stock_final_prevu,
            'total_estime_annee': recettes_annee + ventes_prevues,
            'qualite_prevision': resultats_prevision['quality_metrics']
        }

    # ===================================================================
    # NOUVELLES MÉTHODES - COMMANDES PAR PÉRIODE SPÉCIFIQUE
    # Ajoutées le 14/04/2026 pour le module Commandes et Livraisons
    # ===================================================================

    # Constantes pour les calculs
    PRIX_TICKET = Decimal('500')
    TICKETS_PAR_CARNET = 100
    MONTANT_PAR_CARNET = Decimal('50000')  # 100 tickets × 500 FCFA

    @staticmethod
    def calculer_commande_periode(
        poste,
        exercice: int,
        type_periode: str,
        mois: int = None,
        trimestre: int = None,
        semestre: int = None
    ) -> dict:
        """
        NOUVELLE MÉTHODE: Calcule la commande optimale pour une période spécifique.

        L'algorithme:
        1. Détermine la date de fin de période (31 mars pour T1, 30 juin pour S1, etc.)
        2. Calcule les jours restants depuis aujourd'hui
        3. Utilise prevoir_recettes() existante pour les prévisions
        4. Calcule le stock actuel
        5. Détermine le stock à commander pour que rupture = fin de période

        Args:
            poste: Instance du modèle Poste
            exercice: Année de l'exercice (ex: 2026)
            type_periode: 'mensuelle', 'trimestrielle', 'semestrielle', 'annuelle'
            mois: Numéro du mois (1-12) si mensuelle
            trimestre: Numéro du trimestre (1-4) si trimestrielle
            semestre: Numéro du semestre (1-2) si semestrielle

        Returns:
            dict avec:
                - success: bool
                - montant_estime: Montant total à commander
                - nombre_tickets: Nombre de tickets à commander
                - nombre_carnets: Nombre de carnets à commander
                - stock_actuel: Dict avec infos du stock
                - vente_journaliere_estimee: Estimation vente par jour
                - jours_restants: Jours jusqu'à fin de période
                - date_fin_periode: Date de fin de la période
                - date_rupture_estimee: Date de rupture sans commande
                - details_analyse: Détails du forecasting
        """
        today = date.today()

        try:
            # 1. Déterminer les dates de la période
            date_debut, date_fin = ForecastingService._get_dates_periode(
                exercice, type_periode, mois, trimestre, semestre
            )

            # 2. Calculer les jours restants
            jours_restants = max(0, (date_fin - today).days)

            # Si la période est déjà passée
            if jours_restants == 0:
                return ForecastingService._resultat_periode_passee(poste, date_fin)

            # 3. Obtenir les prévisions via prevoir_recettes()
            resultats_forecast = ForecastingService.prevoir_recettes(
                poste,
                nb_jours_future=jours_restants
            )

            if resultats_forecast['success'] and resultats_forecast['predictions'] is not None:
                df_prev = resultats_forecast['predictions']
                vente_journaliere = Decimal(str(df_prev['montant_prevu'].mean()))
                montant_total_prevu = Decimal(str(df_prev['montant_prevu'].sum()))

                # Analyser la tendance
                if len(df_prev) > 1:
                    premiere_moitie = df_prev.head(len(df_prev) // 2)['montant_prevu'].mean()
                    seconde_moitie = df_prev.tail(len(df_prev) // 2)['montant_prevu'].mean()

                    if seconde_moitie > premiere_moitie * 1.1:
                        tendance = 'hausse'
                    elif seconde_moitie < premiere_moitie * 0.9:
                        tendance = 'baisse'
                    else:
                        tendance = 'stable'
                else:
                    tendance = 'inconnue'

                details_analyse = {
                    'methode': 'holt_winters',
                    'tendance': tendance,
                    'saisonnalite': resultats_forecast.get('has_seasonality', False),
                    'nb_jours_prevus': len(df_prev),
                    'qualite': resultats_forecast.get('quality_metrics', {}),
                }
            else:
                # Fallback sur moyenne simple
                vente_journaliere, details_analyse = ForecastingService._moyenne_simple_30j(poste)
                montant_total_prevu = vente_journaliere * jours_restants

            # 4. Calculer le stock actuel
            stock_actuel = ForecastingService._calculer_stock_actuel_poste(poste)

            # 5. Calculer le reliquat des commandes antérieures non livrées
            reliquat_info = ForecastingService._calculer_reliquat_non_livre(poste)

            # 6. Calculer les besoins
            # Stock nécessaire = ventes prévues - stock actuel - reliquat déjà commandé non livré
            stock_necessaire = max(
                Decimal('0'),
                montant_total_prevu
                - stock_actuel['montant_disponible']
                - reliquat_info['montant_reliquat']
            )

            # 7. Convertir en carnets (arrondi supérieur)
            nombre_tickets = int(stock_necessaire / ForecastingService.PRIX_TICKET)
            nombre_carnets = (nombre_tickets + ForecastingService.TICKETS_PAR_CARNET - 1) // ForecastingService.TICKETS_PAR_CARNET

            # Recalculer le montant exact basé sur les carnets
            montant_commande = Decimal(nombre_carnets) * ForecastingService.MONTANT_PAR_CARNET

            # Calculer la date de rupture estimée sans commande
            date_rupture = None
            if vente_journaliere > 0:
                jours_avant_rupture = int(stock_actuel['montant_disponible'] / vente_journaliere)
                date_rupture = today + timedelta(days=jours_avant_rupture)

            return {
                'success': True,
                'montant_estime': montant_commande,
                'nombre_tickets': nombre_carnets * ForecastingService.TICKETS_PAR_CARNET,
                'nombre_carnets': nombre_carnets,
                'stock_actuel': stock_actuel,
                'reliquat_non_livre': reliquat_info,
                'vente_journaliere_estimee': round(float(vente_journaliere), 2),
                'jours_restants': jours_restants,
                'date_debut_periode': date_debut,
                'date_fin_periode': date_fin,
                'date_rupture_estimee': date_rupture,
                'montant_total_periode': round(float(montant_total_prevu), 2),
                'details_analyse': details_analyse,
            }

        except Exception as e:
            logger.error(f"Erreur calculer_commande_periode pour {poste.nom}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'montant_estime': Decimal('0'),
                'nombre_tickets': 0,
                'nombre_carnets': 0,
            }

    @staticmethod
    def _get_dates_periode(
        exercice: int,
        type_periode: str,
        mois: int = None,
        trimestre: int = None,
        semestre: int = None
    ) -> tuple:
        """
        Retourne les dates de début et fin de la période.
        """
        if type_periode == 'mensuelle' and mois:
            mois = int(mois)
            date_debut = date(exercice, mois, 1)
            if mois == 12:
                date_fin = date(exercice + 1, 1, 1) - timedelta(days=1)
            else:
                date_fin = date(exercice, mois + 1, 1) - timedelta(days=1)

        elif type_periode == 'trimestrielle' and trimestre:
            trimestre = int(trimestre)
            mois_debut = (trimestre - 1) * 3 + 1
            date_debut = date(exercice, mois_debut, 1)
            if trimestre == 4:
                date_fin = date(exercice + 1, 1, 1) - timedelta(days=1)
            else:
                date_fin = date(exercice, mois_debut + 3, 1) - timedelta(days=1)

        elif type_periode == 'semestrielle' and semestre:
            semestre = int(semestre)
            if semestre == 1:
                date_debut = date(exercice, 1, 1)
                date_fin = date(exercice, 6, 30)
            else:
                date_debut = date(exercice, 7, 1)
                date_fin = date(exercice, 12, 31)

        else:  # Annuelle
            date_debut = date(exercice, 1, 1)
            date_fin = date(exercice, 12, 31)

        return date_debut, date_fin

    @staticmethod
    def _calculer_stock_actuel_poste(poste) -> dict:
        """
        Calcule le stock actuel disponible pour le poste.
        Essaie GestionStock puis HistoriqueStock comme fallback.
        """
        try:
            from inventaire.models import GestionStock
            stock = GestionStock.objects.filter(poste=poste).first()

            if stock and stock.valeur_monetaire:
                stock_montant = Decimal(str(stock.valeur_monetaire))
                stock_tickets = int(stock_montant / ForecastingService.PRIX_TICKET)

                return {
                    'tickets_disponibles': stock_tickets,
                    'carnets_disponibles': stock_tickets // ForecastingService.TICKETS_PAR_CARNET,
                    'montant_disponible': stock_montant,
                    'source': 'GestionStock',
                }
        except Exception as e:
            logger.debug(f"GestionStock non disponible: {str(e)}")

        try:
            from inventaire.models import HistoriqueStock
            dernier_historique = HistoriqueStock.objects.filter(
                poste=poste
            ).order_by('-date_mouvement', '-id').first()

            if dernier_historique and dernier_historique.solde_apres:
                stock_tickets = dernier_historique.solde_apres
                stock_montant = Decimal(stock_tickets) * ForecastingService.PRIX_TICKET

                return {
                    'tickets_disponibles': stock_tickets,
                    'carnets_disponibles': stock_tickets // ForecastingService.TICKETS_PAR_CARNET,
                    'montant_disponible': stock_montant,
                    'source': 'HistoriqueStock',
                }
        except Exception as e:
            logger.debug(f"HistoriqueStock non disponible: {str(e)}")

        return {
            'tickets_disponibles': 0,
            'carnets_disponibles': 0,
            'montant_disponible': Decimal('0'),
            'source': 'aucun',
        }

    @staticmethod
    def _moyenne_simple_30j(poste) -> tuple:
        """
        Calcule une moyenne simple des ventes sur les 30 derniers jours.
        Fallback si le forecasting avancé échoue.
        """
        today = date.today()
        date_debut = today - timedelta(days=30)

        stats = RecetteJournaliere.objects.filter(
            poste=poste,
            date__gte=date_debut,
            date__lt=today
        ).aggregate(
            total=Sum('montant_declare'),
            nb_jours=Count('id'),
            moyenne=Avg('montant_declare')
        )

        moyenne = Decimal(str(stats['moyenne'] or 0))

        return moyenne, {
            'methode': 'moyenne_simple_30j',
            'tendance': 'inconnue',
            'nb_jours_analysés': stats['nb_jours'] or 0,
            'total_periode': float(stats['total'] or 0),
        }

    @staticmethod
    def _resultat_periode_passee(poste, date_fin: date) -> dict:
        """
        Retourne un résultat pour une période déjà passée.
        """
        return {
            'success': True,
            'montant_estime': Decimal('0'),
            'nombre_tickets': 0,
            'nombre_carnets': 0,
            'stock_actuel': ForecastingService._calculer_stock_actuel_poste(poste),
            'vente_journaliere_estimee': 0,
            'jours_restants': 0,
            'date_fin_periode': date_fin,
            'date_rupture_estimee': None,
            'montant_total_periode': 0,
            'details_analyse': {
                'message': 'Période déjà passée',
            }
        }


# ===================================================================
# FONCTION UTILITAIRE POUR views_commandes.py
# ===================================================================

def calculer_commande_avec_forecasting(
    poste,
    exercice: int,
    type_periode: str,
    mois: int = None,
    trimestre: int = None,
    semestre: int = None
) -> dict:
    """
    Fonction wrapper pour faciliter l'utilisation dans views_commandes.py

    Usage:
        from inventaire.services.forecasting_service import calculer_commande_avec_forecasting

        resultat = calculer_commande_avec_forecasting(
            poste=poste,
            exercice=2026,
            type_periode='trimestrielle',
            trimestre=1
        )

        montant = resultat['montant_estime']
        carnets = resultat['nombre_carnets']
    """
    return ForecastingService.calculer_commande_periode(
        poste=poste,
        exercice=exercice,
        type_periode=type_periode,
        mois=mois,
        trimestre=trimestre,
        semestre=semestre
    )

    # inventaire/services/forecasting_service.py

@staticmethod
def _calculer_reliquat_non_livre(poste) -> dict:
        """
        NOUVELLE MÉTHODE: Calcule le reliquat de carnets déjà commandés
        mais pas encore livrés pour ce poste (toutes commandes antérieures
        confondues).

        Une commande antérieure peut être en attente de livraison
        (DetailCommandePoste.est_complet=False). Ce reliquat couvre déjà
        une partie des besoins futurs du poste : il ne faut pas le
        recommander une seconde fois, sinon le poste se retrouve
        sur-approvisionné dès que les deux commandes finissent par être
        livrées.

        Args:
            poste: Instance du modèle Poste

        Returns:
            dict avec:
                - carnets_reliquat: Total des carnets en attente de livraison
                - montant_reliquat: Équivalent en FCFA
                - details: Liste des commandes concernées (pour affichage/debug)
        """
        from inventaire.models_commandes import DetailCommandePoste

        details_non_livres = DetailCommandePoste.objects.filter(
            poste=poste,
            est_complet=False
        ).select_related('commande')

        carnets_reliquat = 0
        details_info = []

        for detail in details_non_livres:
            reliquat = max(0, detail.nombre_carnets - detail.carnets_livres)
            if reliquat > 0:
                carnets_reliquat += reliquat
                details_info.append({
                    'commande': detail.commande.get_titre_complet(),
                    'commande_id': detail.commande_id,
                    'carnets_commandes': detail.nombre_carnets,
                    'carnets_livres': detail.carnets_livres,
                    'carnets_reliquat': reliquat,
                })

        montant_reliquat = Decimal(carnets_reliquat) * ForecastingService.MONTANT_PAR_CARNET

        return {
            'carnets_reliquat': carnets_reliquat,
            'montant_reliquat': montant_reliquat,
            'details': details_info,
        }