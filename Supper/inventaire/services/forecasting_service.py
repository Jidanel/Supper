# inventaire/services/forecasting_service.py
from decimal import Decimal
from datetime import date, timedelta
import pandas as pd
import numpy as np
from django.db.models import Sum, Count
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.seasonal import seasonal_decompose
import warnings
warnings.filterwarnings('ignore')

from inventaire.models import RecetteJournaliere
from accounts.models import Poste

class ForecastingService:
    """
    Service de prévisions des recettes utilisant des modèles statistiques avancés
    """
    
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