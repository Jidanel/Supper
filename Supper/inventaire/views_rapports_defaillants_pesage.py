# ===================================================================
# inventaire/views_rapports_defaillants_pesage.py
# Vues pour les rapports défaillants du pesage
# VERSION MISE À JOUR avec permissions granulaires et logs détaillés
# ===================================================================
"""
MISE À JOUR DES PERMISSIONS:
- Remplacement de is_admin par les permissions granulaires
- Ajout des logs détaillés avec log_user_action
- Utilisation des décorateurs du module common.decorators
- Ajout de peut_modifier pour contrôler l'affichage des boutons

Permissions utilisées:
- peut_voir_rapports_defaillants_pesage: Pour les rapports défaillants pesage
- peut_voir_objectifs_pesage: Pour la consultation des objectifs
- peut_parametrage_global: Pour les modifications d'objectifs


Variables de contexte:
- selection_rapport_defaillants_pesage: date_debut_default, date_fin_default
- rapport_defaillants_pesage: date_debut, date_fin, donnees, title
- gestion_objectifs_annuels_pesage: annee, annees, stations_data, total_objectif, 
                                     total_realise, taux_global, peut_modifier
- calculer_objectifs_pesage_automatique: annee_courante, annees_disponibles, annees_cibles
- dupliquer_objectifs_annee_pesage: (redirection, pas de contexte)
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from datetime import datetime, date, timedelta
from decimal import Decimal
from django.db.models import Sum

from accounts.models import Poste
from inventaire.models_pesage import ObjectifAnnuelPesage, AmendeEmise, StatutAmende
from .services.pesage_defaillants_service import PesageDefaillantsService

# Import des permissions granulaires et utilitaires
from common.decorators import permission_required_granular
from common.utils import log_user_action

import logging
logger = logging.getLogger('supper')


# ===================================================================
# SECTION 1: VUES RAPPORTS DÉFAILLANTS PESAGE
# ===================================================================

@login_required
@permission_required_granular('peut_voir_rapports_defaillants_pesage')
def selection_rapport_defaillants_pesage(request):
    """
    Vue pour sélectionner la période du rapport défaillants pesage
    
    Permission requise: peut_voir_rapports_defaillants_pesage
    Habilitations autorisées (selon matrice):
        - admin_principal, coord_psrr, serv_info
        - serv_controle, cisop_pesage
    """
    today = date.today()
    
    # Log de l'accès
    log_user_action(
        user=request.user,
        action="ACCES_SELECTION_RAPPORT_DEFAILLANTS_PESAGE",
        details="Accès à la page de sélection de période pour le rapport défaillants pesage",
        request=request,
        module="pesage",
        sous_module="rapport_defaillants"
    )
    
    context = {
        'date_debut_default': date(today.year, today.month, 1).strftime('%Y-%m-%d'),
        'date_fin_default': today.strftime('%Y-%m-%d'),
    }
    
    return render(request, 'pesage/selection_rapport_defaillants_pesage.html', context)


@login_required
@permission_required_granular('peut_voir_rapports_defaillants_pesage')
def rapport_defaillants_pesage(request):
    """
    Vue principale pour générer le rapport des postes défaillants du pesage
    
    Permission requise: peut_voir_rapports_defaillants_pesage
    Habilitations autorisées (selon matrice):
        - admin_principal, coord_psrr, serv_info
        - serv_controle, cisop_pesage
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
        
        # Log de l'erreur
        log_user_action(
            user=request.user,
            action="ERREUR_RAPPORT_DEFAILLANTS_PESAGE",
            details=f"Dates incohérentes: début={date_debut_str}, fin={date_fin_str}",
            request=request,
            module="pesage",
            sous_module="rapport_defaillants",
            succes=False
        )
        
        return redirect('inventaire:selection_rapport_defaillants_pesage')
    
    # Log de la génération du rapport
    log_user_action(
        user=request.user,
        action="GENERATION_RAPPORT_DEFAILLANTS_PESAGE",
        details=(
            f"Génération du rapport défaillants pesage | "
            f"Période: {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')} | "
            f"Action: {action}"
        ),
        request=request,
        module="pesage",
        sous_module="rapport_defaillants",
        date_debut=date_debut.isoformat(),
        date_fin=date_fin.isoformat()
    )
    
    # Calculer toutes les données nécessaires
    donnees = PesageDefaillantsService.calculer_donnees_defaillants_complet(date_debut, date_fin)
    
    if action == 'pdf':
        # Log de l'export PDF
        log_user_action(
            user=request.user,
            action="EXPORT_PDF_RAPPORT_DEFAILLANTS_PESAGE",
            details=(
                f"Export PDF du rapport défaillants pesage | "
                f"Période: {date_debut.strftime('%d/%m/%Y')} au {date_fin.strftime('%d/%m/%Y')}"
            ),
            request=request,
            module="pesage",
            sous_module="rapport_defaillants"
        )
        return generer_pdf_defaillants_pesage(donnees, date_debut, date_fin)
    
    # Afficher la vue HTML
    context = {
        'date_debut': date_debut,
        'date_fin': date_fin,
        'donnees': donnees,
        'title': f'Fiche Synoptique du Pesage - {date_fin.strftime("%d/%m/%Y")}'
    }
    
    return render(request, 'pesage/rapport_defaillants_pesage.html', context)


def generer_pdf_defaillants_pesage(donnees, date_debut, date_fin):
    """
    Génère le PDF complet du rapport des défaillants pesage
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from io import BytesIO
    
    buffer = BytesIO()
    
    # Couleur teal pour le pesage
    TEAL_COLOR = colors.HexColor('#0D9488')
    TEAL_DARK = colors.HexColor('#0F766E')
    
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
        textColor=TEAL_COLOR,
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=TEAL_COLOR,
        spaceBefore=15,
        spaceAfter=10
    )
    
    # Titre principal
    title = Paragraph(
        f"<b>FICHE SYNOPTIQUE DU PESAGE AU {date_fin.strftime('%d/%m/%Y')}</b>",
        title_style
    )
    elements.append(title)
    elements.append(Spacer(1, 0.3*cm))
    
    # ========== SECTION A : RÉALISATIONS PAR STATION ==========
    elements.append(Paragraph("<b>Réalisations par Station de Pesage</b>", section_style))
    
    # En-tête du tableau
    data = [
        ['Station', f'Réal. Période', 
         f'Réal. {donnees["annee_n1"]}', 'Progression',
         'Jours manq.', 'Dates manquantes']
    ]
    
    # Données des stations
    for r in donnees['realisations_periode'][:50]:  # Limiter pour l'espace
        progression_str = f"{int(r['progression']):,}".replace(',', ' ')
        if r['progression'] >= 0:
            progression_str = f"+{progression_str}"
        
        data.append([
            r['station'].nom[:25],
            f"{int(r['realisation_periode']):,}".replace(',', ' '),
            f"{int(r['realisation_n1']):,}".replace(',', ' '),
            progression_str,
            str(r['jours_manquants']),
            r['dates_manquantes'][:30] if r['dates_manquantes'] else '-'
        ])
    
    # Total
    data.append([
        'TOTAL',
        f"{int(donnees['total_realisation_periode']):,}".replace(',', ' '),
        f"{int(donnees['total_mois_n1']):,}".replace(',', ' '),
        f"{int(donnees['progression_vs_n1']):,}".replace(',', ' '),
        str(donnees['total_jours_manquants']),
        ''
    ])
    
    table = Table(data, colWidths=[4*cm, 3*cm, 3*cm, 3*cm, 2*cm, 5*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TEAL_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (4, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F0FDFA')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(table)
    elements.append(PageBreak())
    
    # ========== SECTION B : COMPARAISONS ==========
    elements.append(Paragraph("<b>Comparaisons Annuelles</b>", section_style))
    
    comparison_data = [
        ['Indicateur', 'Valeur', 'Écart', 'Indice'],
        [f'Cumul {donnees["annee"]} (au {date_fin.strftime("%d/%m")})', 
         f"{int(donnees['cumul_annuel']):,}".replace(',', ' ') + ' FCFA', '-', '-'],
        [f'Cumul {donnees["annee_n1"]} (même date)',
         f"{int(donnees['cumul_n1_meme_date']):,}".replace(',', ' ') + ' FCFA',
         f"{int(donnees['ecart_cumul_n1']):,}".replace(',', ' '),
         f"{donnees['indice_cumul_n1']:.1f}%"],
        [f'Cumul {donnees["annee_n2"]} (même date)',
         f"{int(donnees['cumul_n2_meme_date']):,}".replace(',', ' ') + ' FCFA',
         f"{int(donnees['ecart_cumul_n2']):,}".replace(',', ' '),
         f"{donnees['indice_cumul_n2']:.1f}%"],
    ]
    
    table_comp = Table(comparison_data, colWidths=[6*cm, 5*cm, 4*cm, 3*cm])
    table_comp.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), TEAL_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(table_comp)
    elements.append(Spacer(1, 0.5*cm))
    
    # ========== SECTION C : OBJECTIF ANNUEL ==========
    elements.append(Paragraph("<b>Objectif Annuel " + str(donnees['annee']) + "</b>", section_style))
    
    objectif_data = [
        ['Objectif annuel pesage', f"{int(donnees['objectif_annuel']):,}".replace(',', ' ') + ' FCFA'],
        ['Réalisé à ce jour', f"{int(donnees['realisation_objectif']):,}".replace(',', ' ') + ' FCFA'],
        ['Reste à réaliser', f"{int(max(0, donnees['objectif_annuel'] - donnees['realisation_objectif'])):,}".replace(',', ' ') + ' FCFA'],
        ['Taux de réalisation', f"{donnees['taux_realisation_objectif']:.1f}%"],
    ]
    
    table_objectif = Table(objectif_data, colWidths=[6*cm, 6*cm])
    table_objectif.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F0FDFA')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(table_objectif)
    elements.append(Spacer(1, 0.5*cm))
    
    # ========== SECTION D : POSTES EN BAISSE ==========
    if donnees['postes_baisse_mensuel_n1']:
        elements.append(Paragraph("<b>Postes en Baisse (Mensuel vs N-1)</b>", section_style))
        
        baisse_data = [['Station', 'Réal. Actuelle', f'Réal. {donnees["annee_n1"]}', 'Évolution']]
        for p in donnees['postes_baisse_mensuel_n1'][:20]:
            baisse_data.append([
                p['station'].nom[:30],
                f"{int(p['realise_actuel']):,}".replace(',', ' '),
                f"{int(p['realise_n1']):,}".replace(',', ' '),
                f"{p['taux']:.1f}%"
            ])
        
        table_baisse = Table(baisse_data, colWidths=[6*cm, 4*cm, 4*cm, 3*cm])
        table_baisse.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        
        elements.append(table_baisse)
    
    # Footer
    elements.append(Spacer(1, 1*cm))
    footer = Paragraph(
        f"<i>PSRR {date_fin.year} - Rapport Pesage - "
        f"Édition du {datetime.now().strftime('%d/%m/%Y, %H:%M')}</i>",
        ParagraphStyle('Footer', fontSize=7, textColor=colors.grey, alignment=TA_CENTER)
    )
    elements.append(footer)
    
    # Construire le PDF
    doc.build(elements)
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    filename = f'fiche_synoptique_pesage_{date_fin.strftime("%Y%m%d")}.pdf'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


# ===================================================================
# SECTION 2: GESTION DES OBJECTIFS PESAGE
# ===================================================================

def utilisateur_peut_modifier_objectifs(user):
    """
    Vérifie si l'utilisateur peut modifier les objectifs pesage
    
    Retourne True si:
    - L'utilisateur est superuser, OU
    - L'utilisateur a la permission peut_parametrage_global
    """
    if user.is_superuser:
        return True
    
    # Vérifier la permission granulaire
    if getattr(user, 'peut_parametrage_global', False):
        return True
    
    return False


@login_required
@permission_required_granular('peut_voir_objectifs_pesage')
def gestion_objectifs_annuels_pesage(request):
    """
    Vue pour gérer les objectifs annuels de pesage
    
    Permission consultation: peut_voir_objectifs_pesage
    Permission modification (POST): peut_parametrage_global OU is_superuser
    
    Habilitations consultation (selon matrice):
        - admin_principal, coord_psrr, serv_info
        - serv_emission, serv_controle, cisop_pesage
        - chef_station_pesage, regisseur_pesage, chef_equipe_pesage
    
    Habilitations modification:
        - admin_principal, coord_psrr, serv_info
        - chef_ag, serv_controle, serv_ordre
    """
    
    annee = int(request.GET.get('annee', date.today().year))
    
    # Vérifier si l'utilisateur peut modifier
    peut_modifier = utilisateur_peut_modifier_objectifs(request.user)
    
    # Log de l'accès
    log_user_action(
        user=request.user,
        action="ACCES_GESTION_OBJECTIFS_PESAGE",
        details=f"Consultation des objectifs pesage pour l'année {annee} | Mode: {'modification' if peut_modifier else 'lecture'}",
        request=request,
        module="pesage",
        sous_module="objectifs",
        annee=annee
    )
    
    # Récupérer toutes les stations de pesage
    stations = Poste.objects.filter(type='pesage', is_active=True).order_by('region', 'nom')
    
    if request.method == 'POST':
        # Vérifier la permission de modification
        if not peut_modifier:
            messages.error(request, "Vous n'avez pas la permission de modifier les objectifs.")
            
            log_user_action(
                user=request.user,
                action="TENTATIVE_MODIFICATION_OBJECTIFS_PESAGE_NON_AUTORISEE",
                details=f"Tentative de modification des objectifs sans permission",
                request=request,
                module="pesage",
                sous_module="objectifs",
                succes=False
            )
            
            return redirect(f"{request.path}?annee={annee}")
        
        # Sauvegarder les objectifs
        nb_modifies = 0
        details_modifications = []
        
        for station in stations:
            montant_str = request.POST.get(f'objectif_{station.id}', '0')
            try:
                montant = Decimal(montant_str.replace(' ', '').replace(',', '.'))
            except:
                montant = Decimal('0')
            
            if montant > 0:
                ObjectifAnnuelPesage.objects.update_or_create(
                    station=station,
                    annee=annee,
                    defaults={
                        'montant_objectif': montant,
                        'cree_par': request.user
                    }
                )
                nb_modifies += 1
                details_modifications.append(f"{station.nom}: {montant:,.0f} FCFA")
        
        # Log de la modification
        log_user_action(
            user=request.user,
            action="MODIFICATION_OBJECTIFS_PESAGE",
            details=(
                f"Modification des objectifs pesage {annee} | "
                f"{nb_modifies} stations modifiées | "
                f"Détails: {', '.join(details_modifications[:5])}{'...' if len(details_modifications) > 5 else ''}"
            ),
            request=request,
            module="pesage",
            sous_module="objectifs",
            annee=annee,
            nb_modifies=nb_modifies
        )
        
        messages.success(request, f"{nb_modifies} objectifs enregistrés pour {annee}")
        return redirect(f"{request.path}?annee={annee}")
    
    # Récupérer les objectifs existants
    objectifs_dict = {
        obj.station_id: obj 
        for obj in ObjectifAnnuelPesage.objects.filter(annee=annee)
    }
    
    # Construire les données pour le template
    stations_data = []
    total_objectif = Decimal('0')
    total_realise = Decimal('0')
    
    for station in stations:
        objectif = objectifs_dict.get(station.id)
        montant_objectif = objectif.montant_objectif if objectif else Decimal('0')
        
        # Calculer la réalisation
        realise = AmendeEmise.objects.filter(
            station=station,
            statut=StatutAmende.PAYE,
            date_paiement__year=annee
        ).aggregate(total=Sum('montant_amende'))['total'] or Decimal('0')
        
        reste = montant_objectif - realise
        taux = (realise / montant_objectif * 100) if montant_objectif > 0 else Decimal('0')
        
        stations_data.append({
            'station': station,
            'objectif': montant_objectif,
            'realise': realise,
            'reste': reste,
            'taux': taux,
        })
        
        total_objectif += montant_objectif
        total_realise += realise
    
    taux_global = (total_realise / total_objectif * 100) if total_objectif > 0 else Decimal('0')
    
    # Années disponibles
    annees = list(range(2020, date.today().year + 6))
    
    context = {
        'annee': annee,
        'annees': annees,
        'stations_data': stations_data,
        'total_objectif': total_objectif,
        'total_realise': total_realise,
        'taux_global': taux_global,
        # NOUVELLE VARIABLE pour contrôler l'affichage des boutons de modification
        'peut_modifier': peut_modifier,
    }
    
    return render(request, 'pesage/gestion_objectifs_annuels_pesage.html', context)


@login_required
@permission_required_granular(['peut_voir_objectifs_pesage', 'peut_parametrage_global'])
def calculer_objectifs_pesage_automatique(request):
    """
    Vue pour calculer automatiquement les objectifs pesage 
    à partir des OBJECTIFS d'une année source avec un pourcentage
    
    Permissions requises: peut_voir_objectifs_pesage ET peut_parametrage_global
    Habilitations autorisées (selon matrice):
        - admin_principal, coord_psrr, serv_info
    """
    
    annee_courante = date.today().year
    
    # Log de l'accès
    log_user_action(
        user=request.user,
        action="ACCES_CALCUL_AUTO_OBJECTIFS_PESAGE",
        details="Accès à la page de calcul automatique des objectifs pesage",
        request=request,
        module="pesage",
        sous_module="objectifs"
    )
    
    # Années disponibles pour la source (avec des objectifs)
    annees_disponibles = list(range(annee_courante - 5, annee_courante + 3))
    
    # Années cibles possibles
    annees_cibles = list(range(annee_courante - 1, annee_courante + 5))
    
    if request.method == 'POST':
        try:
            annee_source = int(request.POST.get('annee_source'))
            annee_cible = int(request.POST.get('annee_cible'))
            pourcentage = float(request.POST.get('pourcentage', 0))
            
            # Validation
            if annee_source == annee_cible:
                messages.error(request, "L'année source et l'année cible doivent être différentes.")
                
                log_user_action(
                    user=request.user,
                    action="ERREUR_CALCUL_OBJECTIFS_PESAGE",
                    details=f"Années identiques: source={annee_source}, cible={annee_cible}",
                    request=request,
                    module="pesage",
                    sous_module="objectifs",
                    succes=False
                )
                
                return redirect('inventaire:calculer_objectifs_pesage')
            
            if pourcentage < -100 or pourcentage > 500:
                messages.error(request, "Le pourcentage doit être entre -100% et +500%.")
                
                log_user_action(
                    user=request.user,
                    action="ERREUR_CALCUL_OBJECTIFS_PESAGE",
                    details=f"Pourcentage invalide: {pourcentage}%",
                    request=request,
                    module="pesage",
                    sous_module="objectifs",
                    succes=False
                )
                
                return redirect('inventaire:calculer_objectifs_pesage')
            
            # Récupérer les OBJECTIFS de l'année source
            objectifs_source = ObjectifAnnuelPesage.objects.filter(annee=annee_source)
            
            if not objectifs_source.exists():
                messages.error(request, f"Aucun objectif trouvé pour l'année {annee_source}. Veuillez d'abord définir les objectifs de cette année.")
                
                log_user_action(
                    user=request.user,
                    action="ERREUR_CALCUL_OBJECTIFS_PESAGE",
                    details=f"Aucun objectif source pour {annee_source}",
                    request=request,
                    module="pesage",
                    sous_module="objectifs",
                    succes=False
                )
                
                return redirect('inventaire:calculer_objectifs_pesage')
            
            # Calculer le multiplicateur
            multiplicateur = Decimal(str(1 + (pourcentage / 100)))
            
            nb_crees = 0
            nb_modifies = 0
            
            for objectif_source in objectifs_source:
                # Calculer le nouvel objectif à partir de l'OBJECTIF source
                nouvel_objectif = (objectif_source.montant_objectif * multiplicateur).quantize(Decimal('1'))
                
                # Créer ou mettre à jour l'objectif cible
                objectif_cible, created = ObjectifAnnuelPesage.objects.update_or_create(
                    station=objectif_source.station,
                    annee=annee_cible,
                    defaults={
                        'montant_objectif': nouvel_objectif,
                        'cree_par': request.user
                    }
                )
                
                if created:
                    nb_crees += 1
                else:
                    nb_modifies += 1
            
            # Log du succès
            log_user_action(
                user=request.user,
                action="CALCUL_AUTO_OBJECTIFS_PESAGE",
                details=(
                    f"Calcul automatique des objectifs pesage | "
                    f"Source: {annee_source} → Cible: {annee_cible} | "
                    f"Ajustement: {pourcentage:+.0f}% | "
                    f"Créés: {nb_crees}, Modifiés: {nb_modifies}"
                ),
                request=request,
                module="pesage",
                sous_module="objectifs",
                annee_source=annee_source,
                annee_cible=annee_cible,
                pourcentage=pourcentage,
                nb_crees=nb_crees,
                nb_modifies=nb_modifies
            )
            
            messages.success(
                request,
                f"Objectifs {annee_cible} calculés avec succès ! "
                f"{nb_crees} créés, {nb_modifies} mis à jour "
                f"(base: objectifs {annee_source}, ajustement: {pourcentage:+.0f}%)"
            )
            
            return redirect('inventaire:gestion_objectifs_annuels_pesage')
            
        except (ValueError, TypeError) as e:
            messages.error(request, f"Erreur dans les paramètres : {str(e)}")
            
            log_user_action(
                user=request.user,
                action="ERREUR_CALCUL_OBJECTIFS_PESAGE",
                details=f"Erreur de paramètres: {str(e)}",
                request=request,
                module="pesage",
                sous_module="objectifs",
                succes=False
            )
            
            return redirect('inventaire:calculer_objectifs_pesage')
        except Exception as e:
            messages.error(request, f"Erreur lors du calcul : {str(e)}")
            
            log_user_action(
                user=request.user,
                action="ERREUR_CALCUL_OBJECTIFS_PESAGE",
                details=f"Erreur inattendue: {str(e)}",
                request=request,
                module="pesage",
                sous_module="objectifs",
                succes=False
            )
            
            return redirect('inventaire:calculer_objectifs_pesage')
    
    # GET - Afficher le formulaire
    context = {
        'annee_courante': annee_courante,
        'annees_disponibles': annees_disponibles,
        'annees_cibles': annees_cibles,
    }
    
    return render(request, 'pesage/calculer_objectifs_pesage.html', context)


@login_required
@permission_required_granular(['peut_voir_objectifs_pesage', 'peut_parametrage_global'])
def dupliquer_objectifs_annee_pesage(request):
    """
    Dupliquer les objectifs d'une année vers une autre
    
    Permissions requises: peut_voir_objectifs_pesage ET peut_parametrage_global
    Habilitations autorisées (selon matrice):
        - admin_principal, coord_psrr, serv_info
    """
    
    if request.method == 'POST':
        annee_source = int(request.POST.get('annee_source'))
        annee_cible = int(request.POST.get('annee_cible'))
        
        if annee_source == annee_cible:
            messages.error(request, "Les années source et cible doivent être différentes.")
            
            log_user_action(
                user=request.user,
                action="ERREUR_DUPLICATION_OBJECTIFS_PESAGE",
                details=f"Tentative de duplication vers la même année: {annee_source}",
                request=request,
                module="pesage",
                sous_module="objectifs",
                succes=False
            )
            
            return redirect('inventaire:gestion_objectifs_annuels_pesage')
        
        objectifs_source = ObjectifAnnuelPesage.objects.filter(annee=annee_source)
        
        if not objectifs_source.exists():
            messages.error(request, f"Aucun objectif trouvé pour {annee_source}")
            
            log_user_action(
                user=request.user,
                action="ERREUR_DUPLICATION_OBJECTIFS_PESAGE",
                details=f"Aucun objectif source pour {annee_source}",
                request=request,
                module="pesage",
                sous_module="objectifs",
                succes=False
            )
            
            return redirect('inventaire:gestion_objectifs_annuels_pesage')
        
        nb_dupliques = 0
        for obj in objectifs_source:
            ObjectifAnnuelPesage.objects.update_or_create(
                station=obj.station,
                annee=annee_cible,
                defaults={
                    'montant_objectif': obj.montant_objectif,
                    'cree_par': request.user
                }
            )
            nb_dupliques += 1
        
        # Log de la duplication
        log_user_action(
            user=request.user,
            action="DUPLICATION_OBJECTIFS_PESAGE",
            details=(
                f"Duplication des objectifs pesage | "
                f"Source: {annee_source} → Cible: {annee_cible} | "
                f"{nb_dupliques} objectifs dupliqués"
            ),
            request=request,
            module="pesage",
            sous_module="objectifs",
            annee_source=annee_source,
            annee_cible=annee_cible,
            nb_dupliques=nb_dupliques
        )
        
        messages.success(request, f"{nb_dupliques} objectifs dupliqués de {annee_source} vers {annee_cible}")
        return redirect(f"/pesage/objectifs-pesage/?annee={annee_cible}")
    
    return redirect('inventaire:gestion_objectifs_annuels_pesage')