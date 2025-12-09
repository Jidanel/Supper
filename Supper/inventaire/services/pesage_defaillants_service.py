# ===================================================================
# inventaire/services/pesage_defaillants_service.py
# Service pour calculer les données du rapport défaillants pesage
# ===================================================================

from django.db.models import Sum, Avg, Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import date, timedelta, datetime
from decimal import Decimal
from calendar import monthrange
import logging

# Imports des modèles - ADAPTER SELON VOTRE STRUCTURE
from accounts.models import Poste
from inventaire.models_pesage import *

logger = logging.getLogger('supper')


class PesageDefaillantsService:
    """
    Service pour calculer toutes les données nécessaires au rapport
    des postes défaillants du pesage
    """
    
    @staticmethod
    def get_stations_pesage():
        """
        Récupère toutes les stations de pesage actives
        Utilise is_active et type (pas actif/type_poste)
        """
        return Poste.objects.filter(type='pesage', is_active=True).order_by('nom')
    
    @staticmethod
    def get_recettes_periode(station, date_debut, date_fin):
        """
        Calcule le total des amendes payées pour une station sur une période
        Utilise date_paiement (dates normales, pas le cycle 9h-9h du péage)
        """
        total = AmendeEmise.objects.filter(
            station=station,
            statut=StatutAmende.PAYE,
            date_paiement__date__gte=date_debut,
            date_paiement__date__lte=date_fin
        ).aggregate(total=Sum('montant_amende'))['total']
        
        return total or Decimal('0')
    
    @staticmethod
    def get_jours_declares(station, date_debut, date_fin):
        """
        Retourne les dates où la station a eu de l'activité.
        Un jour est "déclaré" si :
        - Il y a eu des émissions d'amendes ce jour
        - OU il y a eu des paiements ce jour
        - OU il y a un enregistrement de pesées journalières
        """
        jours_declares = set()
        
        # Jours avec émissions
        try:
            emissions = AmendeEmise.objects.filter(
                station=station,
                date_heure_emission__date__gte=date_debut,
                date_heure_emission__date__lte=date_fin
            ).annotate(
                jour=TruncDate('date_heure_emission')
            ).values_list('jour', flat=True).distinct()
            jours_declares.update([j for j in emissions if j])
        except Exception as e:
            logger.warning(f"Erreur get_jours_declares emissions: {e}")
        
        # Jours avec paiements
        try:
            paiements = AmendeEmise.objects.filter(
                station=station,
                statut=StatutAmende.PAYE,
                date_paiement__date__gte=date_debut,
                date_paiement__date__lte=date_fin
            ).annotate(
                jour=TruncDate('date_paiement')
            ).values_list('jour', flat=True).distinct()
            jours_declares.update([j for j in paiements if j])
        except Exception as e:
            logger.warning(f"Erreur get_jours_declares paiements: {e}")
        
        # Jours avec pesées journalières
        try:
            pesees = PeseesJournalieres.objects.filter(
                station=station,
                date__gte=date_debut,
                date__lte=date_fin
            ).values_list('date', flat=True).distinct()
            jours_declares.update([j for j in pesees if j])
        except Exception as e:
            logger.warning(f"Erreur get_jours_declares pesees: {e}")
        
        return sorted(list(jours_declares))
    
    @staticmethod
    def get_jours_manquants(station, date_debut, date_fin):
        """
        Retourne la liste des jours sans activité (manquants)
        """
        jours_declares = set(PesageDefaillantsService.get_jours_declares(station, date_debut, date_fin))
        
        tous_les_jours = set()
        current = date_debut
        while current <= date_fin:
            tous_les_jours.add(current)
            current += timedelta(days=1)
        
        jours_manquants = sorted(list(tous_les_jours - jours_declares))
        return jours_manquants
    
    @staticmethod
    def formater_dates_consecutives(dates):
        """
        Formate une liste de dates en groupes consécutifs.
        Ex: [1, 2, 3, 5, 7, 8] -> "1er au 3, 5, 7 et 8"
        """
        if not dates:
            return ""
        
        dates = sorted(dates)
        groupes = []
        debut_groupe = dates[0]
        fin_groupe = dates[0]
        
        for i in range(1, len(dates)):
            if (dates[i] - dates[i-1]).days == 1:
                fin_groupe = dates[i]
            else:
                groupes.append((debut_groupe, fin_groupe))
                debut_groupe = dates[i]
                fin_groupe = dates[i]
        
        groupes.append((debut_groupe, fin_groupe))
        
        # Formater
        parties = []
        for debut, fin in groupes:
            if debut == fin:
                jour = debut.day
                parties.append(f"{jour}{'er' if jour == 1 else ''}")
            else:
                jour_debut = debut.day
                jour_fin = fin.day
                parties.append(f"{jour_debut}{'er' if jour_debut == 1 else ''} au {jour_fin}")
        
        if len(parties) == 1:
            return parties[0]
        elif len(parties) == 2:
            return f"{parties[0]} et {parties[1]}"
        else:
            return ", ".join(parties[:-1]) + f" et {parties[-1]}"
    
    @staticmethod
    def calculer_donnees_defaillants_complet(date_debut, date_fin):
        """
        Calcule toutes les données nécessaires pour le rapport complet
        """
        stations = PesageDefaillantsService.get_stations_pesage()
        
        annee = date_fin.year
        annee_n1 = annee - 1
        annee_n2 = annee - 2
        mois = date_fin.month
        
        # Date du début du mois courant
        debut_mois = date(annee, mois, 1)
        
        # Dates pour comparaisons - Mois complet N-1
        _, dernier_jour_mois_n1 = monthrange(annee_n1, mois)
        debut_mois_n1 = date(annee_n1, mois, 1)
        fin_mois_n1 = date(annee_n1, mois, dernier_jour_mois_n1)
        
        # Mois complet N-2
        _, dernier_jour_mois_n2 = monthrange(annee_n2, mois)
        debut_mois_n2 = date(annee_n2, mois, 1)
        fin_mois_n2 = date(annee_n2, mois, dernier_jour_mois_n2)
        
        # Cumul annuel - du 1er janvier à date_fin
        debut_annee = date(annee, 1, 1)
        debut_annee_n1 = date(annee_n1, 1, 1)
        fin_meme_date_n1 = date(annee_n1, mois, min(date_fin.day, dernier_jour_mois_n1))
        debut_annee_n2 = date(annee_n2, 1, 1)
        fin_meme_date_n2 = date(annee_n2, mois, min(date_fin.day, dernier_jour_mois_n2))
        
        # ========== DONNÉES PAR STATION ==========
        realisations_periode = []
        total_realisation_periode = Decimal('0')
        total_mois_n1 = Decimal('0')
        total_jours_manquants = 0
        
        for station in stations:
            # Réalisation période actuelle (du début du mois à date_fin)
            realisation = PesageDefaillantsService.get_recettes_periode(station, debut_mois, date_fin)
            
            # Réalisation même mois N-1 (mois complet)
            realisation_n1 = PesageDefaillantsService.get_recettes_periode(station, debut_mois_n1, fin_mois_n1)
            
            # Progression
            progression = realisation - realisation_n1
            
            # Jours manquants (du début du mois à date_fin)
            jours_manquants = PesageDefaillantsService.get_jours_manquants(station, debut_mois, date_fin)
            nb_jours_manquants = len(jours_manquants)
            dates_manquantes_str = PesageDefaillantsService.formater_dates_consecutives(jours_manquants)
            
            realisations_periode.append({
                'station': station,
                'realisation_periode': realisation,
                'realisation_n1': realisation_n1,
                'progression': progression,
                'jours_manquants': nb_jours_manquants,
                'dates_manquantes': dates_manquantes_str,
            })
            
            total_realisation_periode += realisation
            total_mois_n1 += realisation_n1
            total_jours_manquants += nb_jours_manquants
        
        # ========== TOTAUX MOIS N-2 ==========
        total_mois_n2 = AmendeEmise.objects.filter(
            station__in=stations,
            statut=StatutAmende.PAYE,
            date_paiement__date__gte=debut_mois_n2,
            date_paiement__date__lte=fin_mois_n2
        ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
        
        # ========== PROGRESSION VS N-1 ==========
        progression_vs_n1 = total_realisation_periode - total_mois_n1
        if total_mois_n1 > 0:
            indice_progression_n1 = ((total_realisation_periode - total_mois_n1) / total_mois_n1) * 100
        else:
            indice_progression_n1 = Decimal('0')
        
        # ========== PROGRESSION VS N-2 ==========
        progression_vs_n2 = total_realisation_periode - total_mois_n2
        if total_mois_n2 > 0:
            indice_progression_n2 = ((total_realisation_periode - total_mois_n2) / total_mois_n2) * 100
        else:
            indice_progression_n2 = Decimal('0')
        
        # ========== CUMUL ANNUEL ==========
        cumul_annuel = AmendeEmise.objects.filter(
            station__in=stations,
            statut=StatutAmende.PAYE,
            date_paiement__date__gte=debut_annee,
            date_paiement__date__lte=date_fin
        ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
        
        cumul_n1_meme_date = AmendeEmise.objects.filter(
            station__in=stations,
            statut=StatutAmende.PAYE,
            date_paiement__date__gte=debut_annee_n1,
            date_paiement__date__lte=fin_meme_date_n1
        ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
        
        cumul_n2_meme_date = AmendeEmise.objects.filter(
            station__in=stations,
            statut=StatutAmende.PAYE,
            date_paiement__date__gte=debut_annee_n2,
            date_paiement__date__lte=fin_meme_date_n2
        ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
        
        # Écarts et indices cumul
        ecart_cumul_n1 = cumul_annuel - cumul_n1_meme_date
        ecart_cumul_n2 = cumul_annuel - cumul_n2_meme_date
        
        if cumul_n1_meme_date > 0:
            indice_cumul_n1 = ((cumul_annuel - cumul_n1_meme_date) / cumul_n1_meme_date) * 100
        else:
            indice_cumul_n1 = Decimal('0')
        
        if cumul_n2_meme_date > 0:
            indice_cumul_n2 = ((cumul_annuel - cumul_n2_meme_date) / cumul_n2_meme_date) * 100
        else:
            indice_cumul_n2 = Decimal('0')
        
        # ========== OBJECTIF ANNUEL ==========
        objectif_annuel = ObjectifAnnuelPesage.objects.filter(
            annee=annee
        ).aggregate(total=Sum('montant_objectif'))['total'] or Decimal('0')
        
        realisation_objectif = cumul_annuel
        ecart_objectif = realisation_objectif - objectif_annuel
        
        if objectif_annuel > 0:
            taux_realisation_objectif = (realisation_objectif / objectif_annuel) * 100
        else:
            taux_realisation_objectif = Decimal('0')
        
        # ========== NOUVEAUX POSTES - AVEC DÉTAILS ==========
        # Récupérer les nouveaux postes (champ nouveau=True)
        try:
            nouveaux_postes_qs = stations.filter(nouveau=True)
        except:
            nouveaux_postes_qs = Poste.objects.none()
        
        # Liste détaillée des nouveaux postes avec leurs contributions
        nouveaux_postes_details = []
        contribution_nouveaux_periode = Decimal('0')
        contribution_nouveaux_annee = Decimal('0')
        
        for station in nouveaux_postes_qs:
            # Contribution sur la période
            contrib_periode = PesageDefaillantsService.get_recettes_periode(
                station, debut_mois, date_fin
            )
            
            # Contribution annuelle
            contrib_annee = AmendeEmise.objects.filter(
                station=station,
                statut=StatutAmende.PAYE,
                date_paiement__date__gte=debut_annee,
                date_paiement__date__lte=date_fin
            ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
            
            nouveaux_postes_details.append({
                'station': station,
                'contribution_periode': contrib_periode,
                'contribution_annee': contrib_annee,
            })
            
            contribution_nouveaux_periode += contrib_periode
            contribution_nouveaux_annee += contrib_annee
        
        # Trier par contribution période décroissante
        nouveaux_postes_details.sort(key=lambda x: x['contribution_periode'], reverse=True)
        
        # ========== POSTES EN BAISSE ==========
        postes_baisse_mensuel_n1 = []
        postes_baisse_annuel_n1 = []
        
        for r in realisations_periode:
            # Baisse mensuelle (> 5%)
            if r['realisation_n1'] > 0:
                taux_mensuel = ((r['realisation_periode'] - r['realisation_n1']) / r['realisation_n1']) * 100
                if taux_mensuel < -5:
                    postes_baisse_mensuel_n1.append({
                        'station': r['station'],
                        'realise_actuel': r['realisation_periode'],
                        'realise_n1': r['realisation_n1'],
                        'taux': float(taux_mensuel)
                    })
        
        # Baisse annuelle
        for station in stations:
            cumul_station = AmendeEmise.objects.filter(
                station=station,
                statut=StatutAmende.PAYE,
                date_paiement__date__gte=debut_annee,
                date_paiement__date__lte=date_fin
            ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
            
            cumul_station_n1 = AmendeEmise.objects.filter(
                station=station,
                statut=StatutAmende.PAYE,
                date_paiement__date__gte=debut_annee_n1,
                date_paiement__date__lte=fin_meme_date_n1
            ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
            
            if cumul_station_n1 > 0:
                taux_annuel = ((cumul_station - cumul_station_n1) / cumul_station_n1) * 100
                if taux_annuel < -5:
                    postes_baisse_annuel_n1.append({
                        'station': station,
                        'realise_actuel': cumul_station,
                        'realise_n1': cumul_station_n1,
                        'taux': float(taux_annuel)
                    })
        
        # Trier par taux de baisse (le plus négatif en premier)
        postes_baisse_mensuel_n1.sort(key=lambda x: x['taux'])
        postes_baisse_annuel_n1.sort(key=lambda x: x['taux'])
        
        # ========== LIBELLÉS DES PÉRIODES ==========
        # Noms des mois en français
        MOIS_FR = {
            1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
            5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
            9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
        }
        
        nom_mois = MOIS_FR.get(mois, f"Mois {mois}")
        
        # Libellé période actuelle: "1er au 9 décembre 2025"
        jour_debut = date_debut.day
        jour_fin = date_fin.day
        if jour_debut == 1:
            libelle_periode = f"1er au {jour_fin} {nom_mois.lower()} {annee}"
        else:
            libelle_periode = f"{jour_debut} au {jour_fin} {nom_mois.lower()} {annee}"
        
        # Libellé mois N-1: "Décembre 2024 (complet)"
        libelle_mois_n1 = f"{nom_mois} {annee_n1} (complet)"
        
        # Libellé mois N-2: "Décembre 2023 (complet)"
        libelle_mois_n2 = f"{nom_mois} {annee_n2} (complet)"
        
        # Libellé cumul actuel: "1er janvier au 9 décembre 2025"
        libelle_cumul = f"1er janvier au {date_fin.day} {nom_mois.lower()} {annee}"
        
        # Libellé cumul N-1: "1er janvier au 9 décembre 2024"
        libelle_cumul_n1 = f"1er janvier au {fin_meme_date_n1.day} {MOIS_FR.get(fin_meme_date_n1.month, '').lower()} {annee_n1}"
        
        # Libellé cumul N-2: "1er janvier au 9 décembre 2023"
        libelle_cumul_n2 = f"1er janvier au {fin_meme_date_n2.day} {MOIS_FR.get(fin_meme_date_n2.month, '').lower()} {annee_n2}"
        
        # ========== RETOUR DES DONNÉES ==========
        return {
            # Années de référence
            'annee': annee,
            'annee_n1': annee_n1,
            'annee_n2': annee_n2,
            
            # Libellés des périodes (pour affichage clair)
            'nom_mois': nom_mois,
            'libelle_periode': libelle_periode,
            'libelle_mois_n1': libelle_mois_n1,
            'libelle_mois_n2': libelle_mois_n2,
            'libelle_cumul': libelle_cumul,
            'libelle_cumul_n1': libelle_cumul_n1,
            'libelle_cumul_n2': libelle_cumul_n2,
            
            # Réalisations par station
            'realisations_periode': realisations_periode,
            
            # Totaux période
            'total_realisation_periode': total_realisation_periode,
            'total_mois_n1': total_mois_n1,
            'total_mois_n2': total_mois_n2,
            'progression_vs_n1': progression_vs_n1,
            'indice_progression_n1': float(indice_progression_n1),
            'progression_vs_n2': progression_vs_n2,
            'indice_progression_n2': float(indice_progression_n2),
            'total_jours_manquants': total_jours_manquants,
            
            # Cumul annuel
            'cumul_annuel': cumul_annuel,
            'cumul_n1_meme_date': cumul_n1_meme_date,
            'cumul_n2_meme_date': cumul_n2_meme_date,
            'ecart_cumul_n1': ecart_cumul_n1,
            'ecart_cumul_n2': ecart_cumul_n2,
            'indice_cumul_n1': float(indice_cumul_n1),
            'indice_cumul_n2': float(indice_cumul_n2),
            
            # Objectif
            'objectif_annuel': objectif_annuel,
            'realisation_objectif': realisation_objectif,
            'ecart_objectif': ecart_objectif,
            'taux_realisation_objectif': float(taux_realisation_objectif),
            
            # Nouveaux postes - LISTE DÉTAILLÉE
            'nouveaux_postes': list(nouveaux_postes_qs),  # Liste simple pour vérifier si non vide
            'nouveaux_postes_details': nouveaux_postes_details,  # Liste avec contributions
            'contribution_nouveaux_periode': contribution_nouveaux_periode,
            'contribution_nouveaux_annee': contribution_nouveaux_annee,
            
            # Postes en baisse
            'postes_baisse_mensuel_n1': postes_baisse_mensuel_n1,
            'postes_baisse_annuel_n1': postes_baisse_annuel_n1,
        }
    
    @staticmethod
    def estimer_recettes_manquantes(station, jours_manquants):
        """
        Estime les recettes pour les jours manquants d'une station de pesage
        Utilise la moyenne des amendes payées des 30 derniers jours
        """
        if not jours_manquants:
            return Decimal('0')
        
        date_reference = min(jours_manquants)
        date_fin_historique = date_reference - timedelta(days=1)
        date_debut_historique = date_fin_historique - timedelta(days=30)
        
        # Moyenne journalière sur les 30 derniers jours
        total_30j = AmendeEmise.objects.filter(
            station=station,
            statut=StatutAmende.PAYE,
            date_paiement__date__range=[date_debut_historique, date_fin_historique]
        ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
        
        # Compter les jours avec activité dans cette période
        jours_actifs = AmendeEmise.objects.filter(
            station=station,
            statut=StatutAmende.PAYE,
            date_paiement__date__range=[date_debut_historique, date_fin_historique]
        ).annotate(
            jour=TruncDate('date_paiement')
        ).values('jour').distinct().count()
        
        if jours_actifs > 0:
            moyenne_journaliere = total_30j / jours_actifs
            return moyenne_journaliere * len(jours_manquants)
        
        return Decimal('0')