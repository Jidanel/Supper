# inventaire/views_rapports_defaillants.py
"""
Vue améliorée pour générer le rapport des postes défaillants avec estimations
Version corrigée avec calculs complets du mois
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Sum, Avg, Count, Q
from django.utils import timezone
from datetime import date, timedelta, datetime
from decimal import Decimal
import calendar

from accounts.models import Poste
from inventaire.models import RecetteJournaliere

import logging
logger = logging.getLogger('supper')


def is_admin_or_manager(user):
    """Vérifie si l'utilisateur peut accéder aux rapports"""
    if not user.is_authenticated:
        return False
    
    allowed_roles = [
        'admin_principal',
        'coord_psrr',
        'serv_info',
        'serv_emission',
        'chef_service',
        'focal_regional'
    ]
    
    return (
        user.is_superuser or 
        user.is_staff or
        user.habilitation in allowed_roles
    )


@login_required
@user_passes_test(is_admin_or_manager)
def selection_rapport_defaillants(request):
    """Vue pour sélectionner la période du rapport"""
    
    date_fin_default = date.today()
    date_debut_default = date(date_fin_default.year, date_fin_default.month, 1)
    
    context = {
        'date_debut_default': date_debut_default,
        'date_fin_default': date_fin_default,
        'date_max': date.today(),
        'title': 'Sélection de la période - Rapport Défaillants'
    }
    
    return render(request, 'inventaire/selection_rapport_defaillants.html', context)


@login_required
@user_passes_test(is_admin_or_manager)
def rapport_defaillants_peage(request):
    """
    Vue principale pour générer le rapport des postes défaillants
    Version améliorée avec calculs complets du mois
    """
    
    # Récupérer les paramètres de date
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    action = request.GET.get('action', 'preview')
    
    # Date de fin (par défaut aujourd'hui)
    if date_fin_str:
        try:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
        except ValueError:
            date_fin = date.today()
    else:
        date_fin = date.today()
    
    # Date de début (par défaut début du mois)
    if date_debut_str:
        try:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        except ValueError:
            date_debut = date(date_fin.year, date_fin.month, 1)
    else:
        date_debut = date(date_fin.year, date_fin.month, 1)
    
    # Vérifier la cohérence des dates
    if date_debut > date_fin:
        messages.error(request, "La date de début doit être antérieure à la date de fin")
        return redirect('inventaire:selection_rapport_defaillants')
    
    # Calculer toutes les données nécessaires
    donnees = calculer_donnees_defaillants_complet(date_debut, date_fin)
    
    if action == 'pdf':
        return generer_pdf_defaillants_complet(donnees, date_debut, date_fin)
    # elif action == 'excel':
    #     return generer_excel_defaillants(donnees, date_debut, date_fin)
    
    # Afficher la vue HTML
    context = {
        'date_debut': date_debut,
        'date_fin': date_fin,
        'donnees': donnees,
        'title': f'Fiche Synoptique du Péage - {date_fin.strftime("%d/%m/%Y")}'
    }
    
    return render(request, 'inventaire/rapport_defaillants_peage.html', context)


def calculer_donnees_defaillants_complet(date_debut, date_fin):
    """
    Calcule toutes les données nécessaires pour le rapport des défaillants
    Version améliorée avec calculs du mois complet
    """
    
    annee = date_fin.year
    mois = date_fin.month
    
    # IMPORTANT: Toujours calculer depuis le début du mois pour les défaillants
    debut_mois = date(annee, mois, 1)
    dernier_jour_mois = calendar.monthrange(annee, mois)[1]
    fin_mois = date(annee, mois, dernier_jour_mois)
    
    # Initialiser la structure de données
    donnees = {
        # Section A: Défaillants (du 1er du mois à la date de fin)
        'defaillants': [],
        'total_jours_manquants': 0,
        'total_estimation_manquante': Decimal('0'),
        
        # Section B: Recettes comparées et prévisionnelles
        'recettes_declarees': Decimal('0'),
        'estimation_jours_non_declares': Decimal('0'),
        'estimation_date_fin': Decimal('0'),
        'estimation_fin_mois': Decimal('0'),
        'date_fin_mois': fin_mois,  # Variable pour le template

        # NOUVELLE SECTION: Comparaison mensuelle même mois N-1 et N-2
        'comparaison_mois_n1': {
            'annee': annee - 1,  # Entier, pas de décimal
            'mois_nom': calendar.month_name[mois],
            'recettes_mois_complet': Decimal('0'),
            'estimation_mois_actuel': Decimal('0'),
            'ecart': Decimal('0'),
            'indice': 0.0
        },
        'comparaison_mois_n2': {
            'annee': annee - 2,  # Entier, pas de décimal
            'mois_nom': calendar.month_name[mois],
            'recettes_mois_complet': Decimal('0'),
            'estimation_mois_actuel': Decimal('0'),
            'ecart': Decimal('0'),
            'indice': 0.0
        },
        
        # Comparaisons mensuelles
        'rendement_n1_mois': Decimal('0'),
        'rendement_n2_mois': Decimal('0'),
        'ecart_n1_mois': Decimal('0'),
        'ecart_n2_mois': Decimal('0'),
        'indice_n1_mois': 0.0,
        'indice_n2_mois': 0.0,
        
        # Cumul annuel
        'estimation_cumul_annuel': Decimal('0'),
        'estimation_cumul_fin_mois': Decimal('0'),
        'realisation_n1_cumul': Decimal('0'),
        'realisation_n2_cumul': Decimal('0'),
        'ecart_n1_cumul': Decimal('0'),
        'ecart_n2_cumul': Decimal('0'),
        'indice_n1_cumul': 0.0,
        'indice_n2_cumul': 0.0,
        
        # Cumul jusqu'à la même date N-1 et N-2
        'realisation_n1_meme_date': Decimal('0'),
        'realisation_n2_meme_date': Decimal('0'),
        'ecart_n1_meme_date': Decimal('0'),
        'ecart_n2_meme_date': Decimal('0'),
        'indice_n1_meme_date': 0.0,
        'indice_n2_meme_date': 0.0,
        
        # Objectif annuel
        'objectif_annuel': Decimal('10000000000'),  # 10 milliards
        'reste_a_realiser': Decimal('0'),
        'taux_progression_objectif': 0.0,  # Nouveau : taux de progression
        
        # Section C: Contribution nouveaux postes
        'nouveaux_postes': [],
        'total_nouveaux_postes': Decimal('0'),
        
        # Section D: Postes à risque
        'postes_risque_mensuel_n1': [],
        'postes_risque_mensuel_n2': [],
        'postes_risque_annuel': [],
    }
    
    # ========== SECTION A: POSTES DÉFAILLANTS (du 1er du mois à date) ==========
    
    postes_actifs = Poste.objects.filter(is_active=True)
    
    # Pour chaque poste, vérifier les jours manquants DU DÉBUT DU MOIS
    for poste in postes_actifs:
        # Jours avec recettes déclarées depuis le début du mois
        jours_declares = set(
            RecetteJournaliere.objects.filter(
                poste=poste,
                date__range=[debut_mois, date_fin]  # Du 1er du mois à la date de fin
            ).values_list('date', flat=True)
        )
        
        # Tous les jours du 1er du mois à la date de fin
        jours_periode = set()
        current_date = debut_mois
        while current_date <= date_fin:
            jours_periode.add(current_date)
            current_date += timedelta(days=1)
        
        # Jours manquants
        jours_manquants = sorted(jours_periode - jours_declares)
        
        if jours_manquants:
            # Estimer les recettes manquantes
            estimation = estimer_recettes_manquantes(poste, jours_manquants)
            
            # Formater les dates manquantes
            dates_str = formater_dates_consecutives(jours_manquants)
            
            donnees['defaillants'].append({
                'poste': poste,
                'dates_manquantes': dates_str,
                'jours_manquants': jours_manquants,
                'nombre_jours': len(jours_manquants),
                'estimation_moyenne': estimation
            })
            
            donnees['total_jours_manquants'] += len(jours_manquants)
            donnees['total_estimation_manquante'] += estimation
    
    # ========== SECTION B: RECETTES COMPARÉES ==========
    
    # Recettes déclarées sur la période sélectionnée
    donnees['recettes_declarees'] = RecetteJournaliere.objects.filter(
        date__range=[date_debut, date_fin]
    ).aggregate(Sum('montant_declare'))['montant_declare__sum'] or Decimal('0')
    
    # Estimation des jours non déclarés (du 1er du mois à date_fin)
    donnees['estimation_jours_non_declares'] = donnees['total_estimation_manquante']
    
    # Estimation à la date de fin
    donnees['estimation_date_fin'] = donnees['recettes_declarees'] + donnees['estimation_jours_non_declares']
    
    # Estimation jusqu'à la fin du mois
    if date_fin < fin_mois:
        # Estimer les jours futurs du mois
        jours_futurs = []
        date_future = date_fin + timedelta(days=1)
        while date_future <= fin_mois:
            jours_futurs.append(date_future)
            date_future += timedelta(days=1)
        
        # Estimer pour chaque poste
        estimation_future_totale = Decimal('0')
        for poste in postes_actifs:
            if jours_futurs:
                estimation_future_totale += estimer_recettes_manquantes(poste, jours_futurs)
        
        donnees['estimation_fin_mois'] = donnees['estimation_date_fin'] + estimation_future_totale
    else:
        donnees['estimation_fin_mois'] = donnees['estimation_date_fin']
    
    # ========== COMPARAISONS AVEC N-1 et N-2 ==========
    
    # Rendement même mois N-1
    donnees['rendement_n1_mois'] = RecetteJournaliere.objects.filter(
        date__year=annee - 1,
        date__month=mois
    ).aggregate(Sum('montant_declare'))['montant_declare__sum'] or Decimal('0')
    
    donnees['ecart_n1_mois'] = donnees['estimation_fin_mois'] - donnees['rendement_n1_mois']
    
    if donnees['rendement_n1_mois'] > 0:
        donnees['indice_n1_mois'] = float(
            (donnees['ecart_n1_mois'] / donnees['rendement_n1_mois']) * 100
        )
    
    # Rendement même mois N-2
    donnees['rendement_n2_mois'] = RecetteJournaliere.objects.filter(
        date__year=annee - 2,
        date__month=mois
    ).aggregate(Sum('montant_declare'))['montant_declare__sum'] or Decimal('0')
    
    donnees['ecart_n2_mois'] = donnees['estimation_fin_mois'] - donnees['rendement_n2_mois']
    
    if donnees['rendement_n2_mois'] > 0:
        donnees['indice_n2_mois'] = float(
            (donnees['ecart_n2_mois'] / donnees['rendement_n2_mois']) * 100
        )
    
    # ========== CUMUL ANNUEL (1er janvier à date) ==========
    
    # Cumul réel jusqu'à date_fin
    donnees['estimation_cumul_annuel'] = RecetteJournaliere.objects.filter(
        date__year=annee,
        date__lte=date_fin
    ).aggregate(Sum('montant_declare'))['montant_declare__sum'] or Decimal('0')
    
    # Ajouter l'estimation de TOUS les jours non déclarés de l'année jusqu'à date_fin
    debut_annee = date(annee, 1, 1)
    for poste in postes_actifs:
        jours_declares_annee = set(
            RecetteJournaliere.objects.filter(
                poste=poste,
                date__range=[debut_annee, date_fin]
            ).values_list('date', flat=True)
        )
        
        jours_annee = set()
        current = debut_annee
        while current <= date_fin:
            jours_annee.add(current)
            current += timedelta(days=1)
        
        jours_manquants_annee = sorted(jours_annee - jours_declares_annee)
        if jours_manquants_annee:
            donnees['estimation_cumul_annuel'] += estimer_recettes_manquantes(poste, jours_manquants_annee)
    
    # Estimation cumul fin de mois
    if date_fin < fin_mois:
        donnees['estimation_cumul_fin_mois'] = donnees['estimation_cumul_annuel']
        # Ajouter estimation des jours futurs jusqu'à fin mois
        for poste in postes_actifs:
            jours_futurs_mois = []
            date_fut = date_fin + timedelta(days=1)
            while date_fut <= fin_mois:
                jours_futurs_mois.append(date_fut)
                date_fut += timedelta(days=1)
            if jours_futurs_mois:
                donnees['estimation_cumul_fin_mois'] += estimer_recettes_manquantes(poste, jours_futurs_mois)
    else:
        donnees['estimation_cumul_fin_mois'] = donnees['estimation_cumul_annuel']
    
    # Réalisations N-1 et N-2 (1er janvier au même jour et mois)
    donnees['realisation_n1_meme_date'] = RecetteJournaliere.objects.filter(
        date__year=annee - 1,
        date__lte=date(annee - 1, mois, min(date_fin.day, calendar.monthrange(annee - 1, mois)[1]))
    ).aggregate(Sum('montant_declare'))['montant_declare__sum'] or Decimal('0')
    
    donnees['realisation_n2_meme_date'] = RecetteJournaliere.objects.filter(
        date__year=annee - 2,
        date__lte=date(annee - 2, mois, min(date_fin.day, calendar.monthrange(annee - 2, mois)[1]))
    ).aggregate(Sum('montant_declare'))['montant_declare__sum'] or Decimal('0')
    
    # Écarts et indices pour cumul à même date
    donnees['ecart_n1_meme_date'] = donnees['estimation_cumul_annuel'] - donnees['realisation_n1_meme_date']
    donnees['ecart_n2_meme_date'] = donnees['estimation_cumul_annuel'] - donnees['realisation_n2_meme_date']
    
    if donnees['realisation_n1_meme_date'] > 0:
        donnees['indice_n1_meme_date'] = float(
            (donnees['ecart_n1_meme_date'] / donnees['realisation_n1_meme_date']) * 100
        )
    
    if donnees['realisation_n2_meme_date'] > 0:
        donnees['indice_n2_meme_date'] = float(
            (donnees['ecart_n2_meme_date'] / donnees['realisation_n2_meme_date']) * 100
        )
    
    # ========== OBJECTIF ANNUEL ET TAUX DE PROGRESSION ==========
    
    donnees['reste_a_realiser'] = donnees['objectif_annuel'] - donnees['estimation_cumul_annuel']
    
    # Calculer le taux de progression vers l'objectif
    if donnees['objectif_annuel'] > 0:
        donnees['taux_progression_objectif'] = float(
            (donnees['estimation_cumul_annuel'] / donnees['objectif_annuel']) * 100
        )
    
    # ========== POSTES À RISQUE ==========
    
    identifier_postes_risque_complet(donnees, postes_actifs, annee, mois, date_fin)
    donnees['annee_n1'] = annee - 1
    donnees['annee_n2'] = annee - 2
    
    return donnees


def identifier_postes_risque_complet(donnees, postes_actifs, annee, mois, date_fin):
    """Identifie les postes à risque de baisse - version améliorée"""
    
    # Postes à risque mensuel N-1
    for poste in postes_actifs:
        recettes_mois_actuel = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee,
            date__month=mois,
            date__lte=date_fin
        ).aggregate(Sum('montant_declare'))['montant_declare__sum'] or Decimal('0')
        
        recettes_mois_n1 = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee - 1,
            date__month=mois
        ).aggregate(Sum('montant_declare'))['montant_declare__sum'] or Decimal('0')
        
        if recettes_mois_n1 > 0:
            # Projeter sur le mois complet si on n'est pas à la fin
            dernier_jour = calendar.monthrange(annee, mois)[1]
            jour_actuel = date_fin.day
            
            if jour_actuel < dernier_jour:
                # Projection simple
                recettes_projetees = (recettes_mois_actuel / jour_actuel) * dernier_jour
            else:
                recettes_projetees = recettes_mois_actuel
            
            taux = float(((recettes_projetees - recettes_mois_n1) / recettes_mois_n1) * 100)
            
            if taux < -5:  # Baisse de plus de 5%
                donnees['postes_risque_mensuel_n1'].append({
                    'poste': poste,
                    'taux': taux,
                    'recettes_actuelles': recettes_mois_actuel,
                    'recettes_n1': recettes_mois_n1
                })
    
    # Trier par taux de baisse
    donnees['postes_risque_mensuel_n1'].sort(key=lambda x: x['taux'])
    
    # Même chose pour N-2
    for poste in postes_actifs:
        recettes_mois_actuel = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee,
            date__month=mois,
            date__lte=date_fin
        ).aggregate(Sum('montant_declare'))['montant_declare__sum'] or Decimal('0')
        
        recettes_mois_n2 = RecetteJournaliere.objects.filter(
            poste=poste,
            date__year=annee - 2,
            date__month=mois
        ).aggregate(Sum('montant_declare'))['montant_declare__sum'] or Decimal('0')
        
        if recettes_mois_n2 > 0:
            dernier_jour = calendar.monthrange(annee, mois)[1]
            jour_actuel = date_fin.day
            
            if jour_actuel < dernier_jour:
                recettes_projetees = (recettes_mois_actuel / jour_actuel) * dernier_jour
            else:
                recettes_projetees = recettes_mois_actuel
            
            taux = float(((recettes_projetees - recettes_mois_n2) / recettes_mois_n2) * 100)
            
            if taux < -5:
                donnees['postes_risque_mensuel_n2'].append({
                    'poste': poste,
                    'taux': taux,
                    'recettes_actuelles': recettes_mois_actuel,
                    'recettes_n2': recettes_mois_n2
                })
    
    donnees['postes_risque_mensuel_n2'].sort(key=lambda x: x['taux'])


def formater_dates_consecutives(dates):
    """
    Formate une liste de dates en groupant les dates consécutives
    Ex: [1,2,3,5,7,8] -> "1er au 3, 5, 7 et 8"
    """
    if not dates:
        return ""
    
    grouped = []
    current_group = [dates[0]]
    
    for i in range(1, len(dates)):
        if dates[i] - dates[i-1] == timedelta(days=1):
            current_group.append(dates[i])
        else:
            if len(current_group) > 2:
                # Groupe de 3+ jours consécutifs
                if current_group[0].day == 1:
                    grouped.append(f"1er au {current_group[-1].strftime('%d/%m/%Y')}")
                else:
                    grouped.append(f"{current_group[0].day} au {current_group[-1].strftime('%d/%m/%Y')}")
            elif len(current_group) == 2:
                # Exactement 2 jours consécutifs
                grouped.append(f"{current_group[0].day} et {current_group[1].strftime('%d/%m/%Y')}")
            else:
                # Un seul jour
                grouped.append(current_group[0].strftime('%d/%m/%Y'))
            current_group = [dates[i]]
    
    # Traiter le dernier groupe
    if len(current_group) > 2:
        if current_group[0].day == 1:
            grouped.append(f"1er au {current_group[-1].strftime('%d/%m/%Y')}")
        else:
            grouped.append(f"{current_group[0].day} au {current_group[-1].strftime('%d/%m/%Y')}")
    elif len(current_group) == 2:
        grouped.append(f"{current_group[0].day} et {current_group[1].strftime('%d/%m/%Y')}")
    else:
        grouped.append(current_group[0].strftime('%d/%m/%Y'))
    
    # Joindre avec des virgules
    if len(grouped) == 1:
        return grouped[0]
    elif len(grouped) == 2:
        return " et ".join(grouped)
    else:
        return ", ".join(grouped[:-1]) + " et " + grouped[-1]


def estimer_recettes_manquantes(poste, jours_manquants):
    """
    Estime les recettes pour les jours manquants d'un poste
    Utilise la moyenne historique des 30 derniers jours
    """
    if not jours_manquants:
        return Decimal('0')
    
    # Date de référence = jour le plus ancien des jours manquants
    date_reference = min(jours_manquants)
    
    # Chercher les données historiques des 30 derniers jours avant la date de référence
    date_fin_historique = date_reference - timedelta(days=1)
    date_debut_historique = date_fin_historique - timedelta(days=30)
    
    # Moyenne sur les 30 derniers jours
    moyenne = RecetteJournaliere.objects.filter(
        poste=poste,
        date__range=[date_debut_historique, date_fin_historique]
    ).aggregate(Avg('montant_declare'))['montant_declare__avg']
    
    if moyenne:
        return Decimal(str(moyenne)) * len(jours_manquants)
    
    # Si pas de données récentes, prendre la moyenne de l'année précédente même mois
    annee = date_reference.year
    mois = date_reference.month
    moyenne_n1 = RecetteJournaliere.objects.filter(
        poste=poste,
        date__year=annee - 1,
        date__month=mois
    ).aggregate(Avg('montant_declare'))['montant_declare__avg']
    
    if moyenne_n1:
        return Decimal(str(moyenne_n1)) * len(jours_manquants)
    
    # En dernier recours, moyenne générale du poste
    moyenne_generale = RecetteJournaliere.objects.filter(
        poste=poste
    ).aggregate(Avg('montant_declare'))['montant_declare__avg']
    
    if moyenne_generale:
        return Decimal(str(moyenne_generale)) * len(jours_manquants)
    
    return Decimal('0')


def generer_pdf_defaillants_complet(donnees, date_debut, date_fin):
    """
    Génère le PDF complet du rapport des défaillants avec toutes les statistiques
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from io import BytesIO
    
    # Créer le buffer
    buffer = BytesIO()
    
    # Créer le document en paysage
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=1*cm,
        leftMargin=1*cm,
        topMargin=1.5*cm,
        bottomMargin=1*cm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Styles personnalisés
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=colors.HexColor('#6B46C1'),
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.HexColor('#6B46C1'),
        spaceBefore=15,
        spaceAfter=10
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=8,
        leading=10
    )
    
    # Titre principal
    title = Paragraph(
        f"<b>FICHE SYNOPTIQUE DU PÉAGE AU {date_fin.strftime('%d/%m/%Y')}</b>",
        title_style
    )
    elements.append(title)
    elements.append(Spacer(1, 0.3*cm))
    
    # ========== SECTION A : DÉFAILLANTS ==========
    elements.append(Paragraph("<b>Défaillants - Dates manquantes</b>", section_style))
    
    if donnees['defaillants']:
        data = [['Poste', 'Dates manquantes', 'Nbre de\njournées', 'Estimation\nmoyenne']]
        
        for defaillant in donnees['defaillants'][:65]:  # Limiter à 65 pour l'espace
            data.append([
                defaillant['poste'].nom[:30],  # Tronquer les noms trop longs
                defaillant['dates_manquantes'][:40],
                str(defaillant['nombre_jours']),
                f"{int(defaillant['estimation_moyenne']):,}".replace(',', ' ')
            ])
        
        # Total
        data.append([
            'Total',
            '',
            str(donnees['total_jours_manquants']),
            f"{int(donnees['total_estimation_manquante']):,}".replace(',', ' ')
        ])
        
        table = Table(data, colWidths=[5*cm, 7*cm, 2.5*cm, 3.5*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F8FAFC')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#334155')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),
            ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F8FAFC')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        
        elements.append(table)
    else:
        elements.append(Paragraph("Aucun poste défaillant sur cette période", normal_style))
    
    elements.append(Spacer(1, 0.5*cm))
    
    # ========== SECTION B : RECETTES COMPARÉES ==========
    elements.append(Paragraph("<b>Recettes comparées et prévisionnelles</b>", section_style))
    
    # Tableau principal des recettes
    recettes_data = [
        ['Indicateur', 'Montant (FCFA)'],
        ['Recettes déclarées', f"{int(donnees['recettes_declarees']):,}".replace(',', ' ')],
        ['Estimation jours non déclarés', f"{int(donnees['estimation_jours_non_declares']):,}".replace(',', ' ')],
        [f'Estimation au {date_fin.strftime("%d/%m/%Y")}', f"{int(donnees['estimation_date_fin']):,}".replace(',', ' ')],
        [f'Estimation fin {donnees["date_fin_mois"].strftime("%B %Y")}', f"{int(donnees['estimation_fin_mois']):,}".replace(',', ' ')],
        ['', ''],  # Ligne vide
        [f'Rdt {date_fin.strftime("%B")} {date_fin.year-1}', f"{int(donnees['rendement_n1_mois']):,}".replace(',', ' ')],
        ['Écart', f"{int(donnees['ecart_n1_mois']):,}".replace(',', ' ')],
        ['Indice de progression', f"{donnees['indice_n1_mois']:.2f}%"],
        ['', ''],  # Ligne vide
        [f'Rdt {date_fin.strftime("%B")} {date_fin.year-2}', f"{int(donnees['rendement_n2_mois']):,}".replace(',', ' ')],
        ['Écart', f"{int(donnees['ecart_n2_mois']):,}".replace(',', ' ')],
        ['Indice de progression', f"{donnees['indice_n2_mois']:.2f}%"],
    ]
    
    table_recettes = Table(recettes_data, colWidths=[10*cm, 6*cm])
    table_recettes.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6B46C1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(table_recettes)
    elements.append(PageBreak())
    
    # ========== CUMUL ANNUEL ==========
    elements.append(Paragraph("<b>Cumul Annuel (1er janvier au " + date_fin.strftime("%d %B %Y") + ")</b>", section_style))
    
    cumul_data = [
        ['Indicateur', 'Montant (FCFA)', 'Évolution'],
        ['Estimation cumul ' + str(date_fin.year), f"{int(donnees['estimation_cumul_annuel']):,}".replace(',', ' '), '-'],
        ['Estimation cumul fin ' + donnees['date_fin_mois'].strftime("%B"), f"{int(donnees['estimation_cumul_fin_mois']):,}".replace(',', ' '), '-'],
        ['Réalisation ' + str(date_fin.year-1) + ' (même date)', f"{int(donnees['realisation_n1_meme_date']):,}".replace(',', ' '), f"{donnees['indice_n1_meme_date']:.1f}%"],
        ['Réalisation ' + str(date_fin.year-2) + ' (même date)', f"{int(donnees['realisation_n2_meme_date']):,}".replace(',', ' '), f"{donnees['indice_n2_meme_date']:.1f}%"],
    ]
    
    table_cumul = Table(cumul_data, colWidths=[8*cm, 6*cm, 3*cm])
    table_cumul.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6B46C1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (2, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(table_cumul)
    elements.append(Spacer(1, 0.5*cm))
    
    # ========== OBJECTIF ANNUEL ==========
    elements.append(Paragraph("<b>Objectif Annuel " + str(date_fin.year) + "</b>", section_style))
    
    objectif_data = [
        ['Objectif annuel', f"{int(donnees['objectif_annuel']):,}".replace(',', ' ') + ' FCFA'],
        ['Réalisé à ce jour', f"{int(donnees['estimation_cumul_annuel']):,}".replace(',', ' ') + ' FCFA'],
        ['Reste à réaliser', f"{int(donnees['reste_a_realiser']):,}".replace(',', ' ') + ' FCFA'],
        ['Taux de progression', f"{donnees['taux_progression_objectif']:.1f}%"],
    ]
    
    table_objectif = Table(objectif_data, colWidths=[8*cm, 8*cm])
    table_objectif.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8FAFC')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(table_objectif)
    
    # Footer
    elements.append(Spacer(1, 1*cm))
    footer = Paragraph(
        f"<i>PSRR {date_fin.year} - Extrait des recettes du péage routier - "
        f"Édition du {datetime.now().strftime('%d/%m/%Y, %H:%M')}</i>",
        ParagraphStyle('Footer', fontSize=7, textColor=colors.grey, alignment=TA_CENTER)
    )
    elements.append(footer)
    
    # Construire le PDF
    doc.build(elements)
    
    # Préparer la réponse
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    filename = f'fiche_synoptique_peage_{date_fin.strftime("%Y%m%d")}.pdf'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response