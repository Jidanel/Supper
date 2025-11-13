# inventaire/views_rapport_inventaires.py
"""
Vues pour générer le rapport des inventaires sur une période donnée
VERSION COMPLÈTE avec inventaires administratifs et moyennes intelligentes
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import HttpResponse
from django.db.models import Q, Avg
from datetime import date, datetime
from decimal import Decimal

from accounts.models import Poste
from inventaire.models import (
    EtatInventaireSnapshot, ProgrammationInventaire, 
    InventaireJournalier, RecetteJournaliere
)
from inventaire.services.snapshot_service import SnapshotService

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
def selection_rapport_inventaires(request):
    """
    Vue pour sélectionner la période du rapport d'inventaires
    """
    
    # Valeurs par défaut
    date_fin_default = date.today()
    
    # Premier jour du mois en cours
    date_debut_default = date(date_fin_default.year, date_fin_default.month, 1)
    
    context = {
        'date_debut_default': date_debut_default,
        'date_fin_default': date_fin_default,
        'date_max': date.today(),
        'title': 'Sélection de la période - Rapport Inventaires'
    }
    
    return render(request, 'inventaire/selection_rapport_inventaires.html', context)


@login_required
@user_passes_test(is_admin_or_manager)
def rapport_inventaires(request):
    """
    Vue principale pour générer le rapport des inventaires
    Analyse l'évolution des indicateurs sur une période
    """
    
    # Récupérer les paramètres
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    action = request.GET.get('action', 'preview')
    
    # Parser les dates
    if date_fin_str:
        try:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
        except ValueError:
            date_fin = date.today()
    else:
        date_fin = date.today()
    
    if date_debut_str:
        try:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        except ValueError:
            date_debut = date(date_fin.year, date_fin.month, 1)
    else:
        date_debut = date(date_fin.year, date_fin.month, 1)
    
    # Vérifier la cohérence
    if date_debut > date_fin:
        messages.error(request, "La date de début doit être antérieure à la date de fin")
        return redirect('inventaire:selection_rapport_inventaires')
    
    # Générer les données
    donnees = calculer_donnees_rapport_inventaires(date_debut, date_fin)
    
    # Vérifier s'il y a des postes
    if not donnees['postes']:
        messages.warning(
            request, 
            f"Aucun poste avec inventaire programmé pour la période "
            f"du {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"
        )
    
    # Générer PDF si demandé
    if action == 'pdf':
        return generer_pdf_rapport_inventaires(donnees, date_debut, date_fin)
    
    # Afficher la vue HTML
    context = {
        'date_debut': date_debut,
        'date_fin': date_fin,
        'donnees': donnees,
        'title': f'Rapport des Inventaires - {date_debut.strftime("%d/%m/%Y")} au {date_fin.strftime("%d/%m/%Y")}'
    }
    
    return render(request, 'inventaire/rapport_inventaires.html', context)


def calculer_taux_moyen_intelligent(taux_normaux, taux_admins):
    """
    Calcule le taux moyen intelligent selon les règles métier
    
    Règles:
    - Si les deux types ont des taux valides (non impertinents, non None): moyenne des deux moyennes
    - Si un seul type a des taux valides: utiliser ce taux
    - Si les deux sont impertinents ou None: retourner None
    
    Args:
        taux_normaux: Liste des taux de déperdition normaux
        taux_admins: Liste des taux de déperdition administratifs
        
    Returns:
        dict: {
            'taux_moyen_normal': Decimal ou None,
            'taux_moyen_admin': Decimal ou None,
            'taux_final': Decimal ou None,
            'nb_taux_normaux': int,
            'nb_taux_admins': int
        }
    """
    
    # Filtrer les taux valides (non impertinents, non None, <= 0)
    taux_normaux_valides = [t for t in taux_normaux if t is not None and t <= 0]
    taux_admins_valides = [t for t in taux_admins if t is not None and t <= 0]
    
    # Calculer les moyennes
    taux_moyen_normal = (
        sum(taux_normaux_valides) / len(taux_normaux_valides) 
        if taux_normaux_valides else None
    )
    
    taux_moyen_admin = (
        sum(taux_admins_valides) / len(taux_admins_valides) 
        if taux_admins_valides else None
    )
    
    # Calculer le taux final
    if taux_moyen_normal is not None and taux_moyen_admin is not None:
        # Les deux sont valides: moyenne des deux
        taux_final = (taux_moyen_normal + taux_moyen_admin) / 2
    elif taux_moyen_normal is not None:
        # Seulement normal valide
        taux_final = taux_moyen_normal
    elif taux_moyen_admin is not None:
        # Seulement admin valide
        taux_final = taux_moyen_admin
    else:
        # Aucun taux valide
        taux_final = None
    
    return {
        'taux_moyen_normal': taux_moyen_normal,
        'taux_moyen_admin': taux_moyen_admin,
        'taux_final': taux_final,
        'nb_taux_normaux': len(taux_normaux_valides),
        'nb_taux_admins': len(taux_admins_valides)
    }


def calculer_donnees_rapport_inventaires(date_debut, date_fin):
    """
    Calcule toutes les données nécessaires pour le rapport des inventaires
    VERSION COMPLÈTE avec inventaires administratifs
    
    Args:
        date_debut: Date de début de la période
        date_fin: Date de fin de la période
        
    Returns:
        dict: Données structurées du rapport
    """
    
    # ÉTAPE 1: Récupérer les postes avec inventaires programmés
    mois_debut = date(date_debut.year, date_debut.month, 1)
    mois_fin = date(date_fin.year, date_fin.month, 1)
    
    programmations = ProgrammationInventaire.objects.filter(
        mois__gte=mois_debut,
        mois__lte=mois_fin,
        actif=True
    ).select_related('poste').distinct()
    
    # Dictionnaire poste_id -> programmations
    postes_programmations = {}
    for prog in programmations:
        if prog.poste.id not in postes_programmations:
            postes_programmations[prog.poste.id] = {
                'poste': prog.poste,
                'programmations': []
            }
        postes_programmations[prog.poste.id]['programmations'].append(prog)
    
    # ÉTAPE 2: Ajouter les postes avec inventaires administratifs dans la période
    inventaires_admins = InventaireJournalier.objects.filter(
        type_inventaire='administratif',
        date__range=[date_debut, date_fin]
    ).select_related('poste').values_list('poste_id', flat=True).distinct()
    
    for poste_id in inventaires_admins:
        if poste_id not in postes_programmations:
            try:
                poste = Poste.objects.get(id=poste_id)
                postes_programmations[poste_id] = {
                    'poste': poste,
                    'programmations': []  # Pas de programmation, juste admin
                }
            except Poste.DoesNotExist:
                continue
    
    # Si aucun poste, retourner structure vide
    if not postes_programmations:
        return {
            'postes': [],
            'taux_moyen_periode': None,
            'statistiques': {
                'total_postes': 0,
                'postes_avec_inventaire': 0,
                'total_journees_impertinentes': 0,
                'impacts_positifs': 0,
                'impacts_negatifs': 0,
            }
        }
    
    donnees_postes = []
    
    # ÉTAPE 3: Pour chaque poste, calculer les indicateurs
    for poste_id, poste_data in postes_programmations.items():
        poste = poste_data['poste']
        programmations_poste = poste_data['programmations']
        
        # Déterminer les motifs de programmation
        motifs = []
        if programmations_poste:
            motifs_set = set()
            for prog in programmations_poste:
                motifs_set.add(prog.get_motif_display())
            motifs = list(motifs_set)
        
        motifs_taux_deperdition = any(
            prog.motif == 'taux_deperdition'
            for prog in programmations_poste
        )
        motifs_risque_baisse = any(
            prog.motif == 'risque_baisse'
            for prog in programmations_poste
        )
        motifs_grand_stock = any(
            prog.motif == 'grand_stock'
            for prog in programmations_poste
        )
        motifs_presence_admin = any(
            prog.motif == 'presence_admin'
            for prog in programmations_poste
        )
        
        # NOUVEAU: Récupérer tous les taux de déperdition de la période
        # Séparés par type d'inventaire
        recettes_periode = RecetteJournaliere.objects.filter(
            poste=poste,
            date__range=[date_debut, date_fin],
            taux_deperdition__isnull=False
        ).select_related('inventaire_associe')
        
        taux_normaux = []
        taux_admins = []
        types_inventaires = set()
        
        for recette in recettes_periode:
            if recette.inventaire_associe:
                if recette.inventaire_associe.type_inventaire == 'administratif':
                    taux_admins.append(recette.taux_deperdition)
                    types_inventaires.add('administratif')
                else:
                    taux_normaux.append(recette.taux_deperdition)
                    types_inventaires.add('normal')
            else:
                # Par défaut, considérer comme normal si pas d'inventaire associé
                taux_normaux.append(recette.taux_deperdition)
                types_inventaires.add('normal')
        
        # Calculer les moyennes intelligentes
        moyennes = calculer_taux_moyen_intelligent(taux_normaux, taux_admins)
        
        # Obtenir les snapshots
        snapshot_initial = SnapshotService.obtenir_snapshot(
            poste, date_debut, creer_si_absent=True
        )
        
        snapshot_actuel = SnapshotService.obtenir_snapshot(
            poste, date_fin, creer_si_absent=True
        )
        
        # Calculer les impacts
        impact_taux = SnapshotService.calculer_impact_taux_deperdition(
            snapshot_actuel, snapshot_initial
        )
        
        impact_risque_baisse = SnapshotService.calculer_impact_risque_baisse(
            snapshot_actuel, snapshot_initial
        )
        
        impact_stock = SnapshotService.calculer_impact_grand_stock(
            snapshot_actuel, snapshot_initial
        )
        
        # Compter les journées impertinentes
        nb_journees_impertinentes = SnapshotService.compter_journees_impertinentes(
            poste, date_debut, date_fin
        )
        
        # Calculer l'impact pour la présence administrative
        impact_presence_admin = None
        if motifs_presence_admin:
            taux_actuel = moyennes['taux_final']  # Utiliser le taux final
            if taux_actuel is not None:
                if taux_actuel > 0:
                    impact_presence_admin = 'impertinent'
                elif taux_actuel > -30:
                    impact_presence_admin = 'positif'
                else:
                    impact_presence_admin = 'negatif'
        
        # Construire les données du poste
        donnee_poste = {
            'poste': poste,
            'a_inventaire_programme': len(programmations_poste) > 0,
            'a_inventaire_admin': 'administratif' in types_inventaires,
            
            # NOUVEAU: Types d'inventaires et motifs
            'types_inventaires': list(types_inventaires),
            'motifs_programmation': motifs,
            
            # NOUVEAU: Taux détaillés
            'taux_moyen_normal': moyennes['taux_moyen_normal'],
            'taux_moyen_admin': moyennes['taux_moyen_admin'],
            'taux_final': moyennes['taux_final'],
            'nb_taux_normaux': moyennes['nb_taux_normaux'],
            'nb_taux_admins': moyennes['nb_taux_admins'],
            
            # Taux actuel (pour l'affichage et le tri)
            'taux_deperdition_actuel': moyennes['taux_final'],
            
            # Affichage conditionnel
            'afficher_taux_deperdition': motifs_taux_deperdition,
            'taux_deperdition_initial': snapshot_initial.taux_deperdition if (motifs_taux_deperdition and snapshot_initial) else None,
            'impact_taux_deperdition': impact_taux if motifs_taux_deperdition else None,
            
            'afficher_risque_baisse': motifs_risque_baisse,
            'risque_baisse_initial': snapshot_initial.risque_baisse_annuel if (motifs_risque_baisse and snapshot_initial) else None,
            'risque_baisse_actuel': snapshot_actuel.risque_baisse_annuel if (motifs_risque_baisse and snapshot_actuel) else None,
            'impact_risque_baisse': impact_risque_baisse if motifs_risque_baisse else None,
            
            'afficher_grand_stock': motifs_grand_stock,
            'grand_stock_initial': snapshot_initial.risque_grand_stock if (motifs_grand_stock and snapshot_initial) else None,
            'date_epuisement_initiale': snapshot_initial.date_epuisement_prevu if (motifs_grand_stock and snapshot_initial) else None,
            'grand_stock_actuel': snapshot_actuel.risque_grand_stock if (motifs_grand_stock and snapshot_actuel) else None,
            'date_epuisement_actuelle': snapshot_actuel.date_epuisement_prevu if (motifs_grand_stock and snapshot_actuel) else None,
            'impact_grand_stock': impact_stock if motifs_grand_stock else None,
            
            'afficher_presence_admin': motifs_presence_admin,
            'impact_presence_admin': impact_presence_admin,
            
            'journees_impertinentes': nb_journees_impertinentes,
            
            'snapshot_initial': snapshot_initial,
            'snapshot_actuel': snapshot_actuel,
            
            'motifs': {
                'taux_deperdition': motifs_taux_deperdition,
                'risque_baisse': motifs_risque_baisse,
                'grand_stock': motifs_grand_stock,
                'presence_admin': motifs_presence_admin,
            }
        }
        
        donnees_postes.append(donnee_poste)
    
    # ÉTAPE 4: Trier par taux final (plus proche de 0 en premier)
    donnees_postes_triees = sorted(
        donnees_postes,
        key=lambda x: abs(x['taux_final']) if x['taux_final'] is not None else float('inf')
    )
    
    # ÉTAPE 5: Calculer le taux moyen global de la période
    taux_finaux_valides = [
        d['taux_final'] 
        for d in donnees_postes 
        if d['taux_final'] is not None and d['taux_final'] <= 0
    ]
    
    taux_moyen = sum(taux_finaux_valides) / len(taux_finaux_valides) if taux_finaux_valides else None
    
    # ÉTAPE 6: Statistiques globales
    total_postes = len(donnees_postes)
    postes_avec_inventaire = total_postes
    total_journees_impertinentes = sum(d['journees_impertinentes'] for d in donnees_postes)
    
    # Compter les impacts
    impacts_positifs = sum(
        1 for d in donnees_postes 
        if (
            (d['afficher_taux_deperdition'] and d['impact_taux_deperdition'] == 'positif') or
            (d['afficher_risque_baisse'] and d['impact_risque_baisse'] == 'positif') or
            (d['afficher_grand_stock'] and d['impact_grand_stock'] == 'positif') or
            (d['afficher_presence_admin'] and d['impact_presence_admin'] == 'positif')
        )
    )
    
    impacts_negatifs = sum(
        1 for d in donnees_postes 
        if (
            (d['afficher_taux_deperdition'] and d['impact_taux_deperdition'] == 'negatif') or
            (d['afficher_risque_baisse'] and d['impact_risque_baisse'] == 'negatif') or
            (d['afficher_grand_stock'] and d['impact_grand_stock'] == 'negatif') or
            (d['afficher_presence_admin'] and d['impact_presence_admin'] == 'negatif')
        )
    )
    
    # Statistiques par type d'inventaire
    postes_avec_admin = sum(1 for d in donnees_postes if d['a_inventaire_admin'])
    postes_avec_normal = sum(1 for d in donnees_postes if 'normal' in d['types_inventaires'])
    postes_avec_les_deux = sum(1 for d in donnees_postes if len(d['types_inventaires']) == 2)
    
    return {
        'postes': donnees_postes_triees,
        'taux_moyen_periode': taux_moyen,
        'statistiques': {
            'total_postes': total_postes,
            'postes_avec_inventaire': postes_avec_inventaire,
            'total_journees_impertinentes': total_journees_impertinentes,
            'impacts_positifs': impacts_positifs,
            'impacts_negatifs': impacts_negatifs,
            'postes_avec_admin': postes_avec_admin,
            'postes_avec_normal': postes_avec_normal,
            'postes_avec_les_deux': postes_avec_les_deux,
        }
    }


def generer_pdf_rapport_inventaires(donnees, date_debut, date_fin):
    """
    Génère le PDF du rapport des inventaires
    VERSION COMPLÈTE avec inventaires administratifs
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER
    from io import BytesIO
    
    buffer = BytesIO()
    
    # Document en paysage
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=0.8*cm,
        leftMargin=0.8*cm,
        topMargin=1.5*cm,
        bottomMargin=1*cm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Style titre
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=colors.HexColor('#6B46C1'),
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    # Titre
    title = Paragraph(
        f"<b>RAPPORT DES INVENTAIRES<br/>"
        f"Période du {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}</b>",
        title_style
    )
    elements.append(title)
    elements.append(Spacer(1, 0.4*cm))
    
    # Vérifier s'il y a des postes
    if not donnees['postes']:
        no_data = Paragraph(
            "<i>Aucun poste avec inventaire programmé pour cette période</i>",
            ParagraphStyle('NoData', fontSize=10, alignment=TA_CENTER)
        )
        elements.append(no_data)
    else:
        # En-tête dynamique
        headers = ['N°', 'Poste', 'Type Inv.', 'Motifs', 'Taux\nNormal', 'Taux\nAdmin', 'Taux\nFinal', 'J.I.']
        
        # Vérifier présence des motifs
        a_taux_deperdition = any(d['afficher_taux_deperdition'] for d in donnees['postes'])
        a_risque_baisse = any(d['afficher_risque_baisse'] for d in donnees['postes'])
        a_grand_stock = any(d['afficher_grand_stock'] for d in donnees['postes'])
        a_presence_admin = any(d['afficher_presence_admin'] for d in donnees['postes'])
        
        if a_taux_deperdition:
            headers.extend(['Taux Ini.', 'Impact\nTaux'])
        if a_risque_baisse:
            headers.extend(['RBA Ini.', 'RBA Act.', 'Impact\nRBA'])
        if a_grand_stock:
            headers.extend(['Stock Ini.', 'Stock Act.', 'Impact\nStock'])
        if a_presence_admin:
            headers.append('Impact\nPA')
        
        data = [headers]
        
        # Construire les lignes
        for idx, poste_data in enumerate(donnees['postes'][:40], 1):
            # Types d'inventaires
            types_str = ', '.join([t[0].upper() for t in poste_data['types_inventaires']])
            
            # Motifs
            motifs_str = '\n'.join(poste_data['motifs_programmation'][:2]) if poste_data['motifs_programmation'] else 'Admin'
            
            row = [
                str(idx),
                poste_data['poste'].nom[:20],
                types_str,
                motifs_str[:15],
                f"{poste_data['taux_moyen_normal']:.1f}%" if poste_data['taux_moyen_normal'] else "-",
                f"{poste_data['taux_moyen_admin']:.1f}%" if poste_data['taux_moyen_admin'] else "-",
                f"{poste_data['taux_final']:.2f}%" if poste_data['taux_final'] else "-",
                str(poste_data['journees_impertinentes']),
            ]
            
            # Colonnes conditionnelles
            if a_taux_deperdition:
                taux_ini = f"{poste_data['taux_deperdition_initial']:.1f}%" if poste_data['afficher_taux_deperdition'] and poste_data['taux_deperdition_initial'] else "-"
                impact = "+" if poste_data['afficher_taux_deperdition'] and poste_data['impact_taux_deperdition'] == 'positif' else ("-" if poste_data['afficher_taux_deperdition'] and poste_data['impact_taux_deperdition'] == 'negatif' else "")
                row.extend([taux_ini, impact])
            
            if a_risque_baisse:
                rba_ini = "O" if poste_data['afficher_risque_baisse'] and poste_data['risque_baisse_initial'] else ""
                rba_act = "O" if poste_data['afficher_risque_baisse'] and poste_data['risque_baisse_actuel'] else ""
                impact_rba = "+" if poste_data['afficher_risque_baisse'] and poste_data['impact_risque_baisse'] == 'positif' else ("-" if poste_data['afficher_risque_baisse'] and poste_data['impact_risque_baisse'] == 'negatif' else "")
                row.extend([rba_ini, rba_act, impact_rba])
            
            if a_grand_stock:
                stock_ini = poste_data['date_epuisement_initiale'].strftime('%d/%m') if poste_data['afficher_grand_stock'] and poste_data['date_epuisement_initiale'] else ""
                stock_act = poste_data['date_epuisement_actuelle'].strftime('%d/%m') if poste_data['afficher_grand_stock'] and poste_data['date_epuisement_actuelle'] else ""
                impact_stock = "+" if poste_data['afficher_grand_stock'] and poste_data['impact_grand_stock'] == 'positif' else ("-" if poste_data['afficher_grand_stock'] and poste_data['impact_grand_stock'] == 'negatif' else "")
                row.extend([stock_ini, stock_act, impact_stock])
            
            if a_presence_admin:
                impact_pa = "B" if poste_data['afficher_presence_admin'] and poste_data['impact_presence_admin'] == 'positif' else ("M" if poste_data['afficher_presence_admin'] and poste_data['impact_presence_admin'] == 'negatif' else ("I" if poste_data['afficher_presence_admin'] and poste_data['impact_presence_admin'] == 'impertinent' else ""))
                row.append(impact_pa)
            
            data.append(row)
        
        # Ligne totaux
        total_row = ['', 'TOTAL', '', '', '', '', 
                    f"{donnees['taux_moyen_periode']:.2f}%" if donnees['taux_moyen_periode'] else '-',
                    str(donnees['statistiques']['total_journees_impertinentes'])]
        total_row.extend([''] * (len(headers) - len(total_row)))
        data.append(total_row)
        
        # Largeurs de colonnes
        col_widths = [0.6*cm, 2.5*cm, 1*cm, 1.8*cm, 1.2*cm, 1.2*cm, 1.2*cm, 0.8*cm]
        if a_taux_deperdition:
            col_widths.extend([1.2*cm, 1*cm])
        if a_risque_baisse:
            col_widths.extend([0.8*cm, 0.8*cm, 1*cm])
        if a_grand_stock:
            col_widths.extend([1.2*cm, 1.2*cm, 1*cm])
        if a_presence_admin:
            col_widths.append(1*cm)
        
        # Créer le tableau
        table = Table(data, colWidths=col_widths)
        
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6B46C1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 6),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F8FAFC')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
        ]))
        
        elements.append(table)
    
    # Footer
    elements.append(Spacer(1, 0.8*cm))
    footer = Paragraph(
        f"<i>PSRR {date_fin.year} - Rapport inventaires - "
        f"Édition: {datetime.now().strftime('%d/%m/%Y, %H:%M')}</i>",
        ParagraphStyle('Footer', fontSize=6, textColor=colors.grey, alignment=TA_CENTER)
    )
    elements.append(footer)
    
    # Construire le PDF
    doc.build(elements)
    
    # Préparer la réponse
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    filename = f'rapport_inventaires_{date_debut.strftime("%Y%m%d")}_{date_fin.strftime("%Y%m%d")}.pdf'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response