#inventaire/views_rapports.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum
from django.http import HttpResponse
from datetime import date, timedelta, datetime
import calendar
from decimal import Decimal

from accounts.models import Poste
from inventaire.models import *
from inventaire.models_config import *

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

import os
from django.conf import settings


@login_required
def selection_compte_emploi(request):
    """
    VERSION AMÉLIORÉE : Permet de choisir entre aperçu et génération directe PDF
    """
    from datetime import date, timedelta
    from django.shortcuts import render, redirect
    from django.contrib import messages
    from accounts.models import Poste
    
    # Vérifier les permissions
    if not (request.user.is_admin or request.user.is_chef_poste):
        messages.error(request, "Accès non autorisé")
        return redirect('common:dashboard')
    
    # Postes accessibles
    if request.user.is_admin:
        postes = Poste.objects.filter(is_active=True).order_by('nom')
    else:
        postes = [request.user.poste_affectation] if request.user.poste_affectation else []
    
    # Dates par défaut suggérées
    today = date.today()
    
    # Suggestion : début du mois précédent → fin du mois précédent
    premier_jour_mois_actuel = today.replace(day=1)
    dernier_jour_mois_precedent = premier_jour_mois_actuel - timedelta(days=1)
    premier_jour_mois_precedent = dernier_jour_mois_precedent.replace(day=1)
    
    date_debut_suggestion = premier_jour_mois_precedent
    date_fin_suggestion = dernier_jour_mois_precedent
    
    if request.method == 'POST':
        poste_id = request.POST.get('poste_id')
        date_debut_str = request.POST.get('date_debut')
        date_fin_str = request.POST.get('date_fin')
        action = request.POST.get('action', 'apercu')  # Par défaut : aperçu
        
        # Validations
        if not poste_id:
            messages.error(request, "Veuillez sélectionner un poste")
        elif not date_debut_str or not date_fin_str:
            messages.error(request, "Veuillez sélectionner une date de début et une date de fin")
        else:
            try:
                date_debut = date.fromisoformat(date_debut_str)
                date_fin = date.fromisoformat(date_fin_str)
                
                # Validation logique
                if date_debut > date_fin:
                    messages.error(request, "La date de début doit être antérieure à la date de fin")
                elif date_fin > today:
                    messages.error(request, "La date de fin ne peut pas être dans le futur")
                elif (date_fin - date_debut).days > 365:
                    messages.error(request, "La période ne peut pas dépasser 1 an")
                else:
                    # ✅ Redirection selon l'action choisie
                    if action == 'apercu':
                        # Afficher l'aperçu HTML
                        return redirect('inventaire:apercu_compte_emploi', 
                                      poste_id=poste_id,
                                      date_debut=date_debut_str,
                                      date_fin=date_fin_str)
                    else:
                        # Générer directement le PDF
                        return redirect('inventaire:generer_compte_emploi', 
                                      poste_id=poste_id,
                                      date_debut=date_debut_str,
                                      date_fin=date_fin_str)
            
            except ValueError:
                messages.error(request, "Format de date invalide")
    
    context = {
        'postes': postes,
        'date_debut_suggestion': date_debut_suggestion,
        'date_fin_suggestion': date_fin_suggestion,
        'date_max': today,
        'title': "Compte d'Emploi des Tickets"
    }
    
    return render(request, 'inventaire/selection_compte_emploi.html', context)

def creer_section_details_series(titre, series_par_couleur, styles, 
                                 inclure_destination=False, 
                                 inclure_date_vente=False,
                                 highlight_color=None):
    """
    ✅ Crée une section détaillée des séries par couleur pour le PDF
    
    Args:
        titre: Titre de la section
        series_par_couleur: Dict avec couleur_key -> {couleur, series[], totaux}
        styles: Styles ReportLab
        inclure_destination: Si True, affiche le poste de destination (transferts cédés)
        inclure_date_vente: Si True, affiche la date de vente
        highlight_color: Couleur de highlight (pour stock final par ex)
    """
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    
    from decimal import Decimal
    
    elements = []
    
    # Titre de section
    section_style = ParagraphStyle(
        'SectionDetail',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=highlight_color or colors.HexColor('#1a1a1a'),
        spaceAfter=10,
        spaceBefore=5
    )
    
    elements.append(Paragraph(titre, section_style))
    
    if not series_par_couleur:
        elements.append(Paragraph(
            "<i>Aucune donnée pour cette section</i>",
            styles['Normal']
        ))
        return elements
    
    # Créer tableau par couleur
    for couleur_nom, groupe in series_par_couleur.items():
        # En-tête couleur
        data = [[
            f"{couleur_nom}",
            f"Total: {groupe['total_tickets']} tickets",
            f"{groupe['valeur_totale']:,.0f} FCFA".replace(',', ' ')
        ]]
        
        # Lignes des séries
        for serie in groupe['series']:
            ligne = [
                f"#{serie.numero_premier} → #{serie.numero_dernier}",
                f"{serie.nombre_tickets} tickets",
                f"{serie.valeur_monetaire:,.0f} FCFA".replace(',', ' ')
            ]
            
            # Ajouter destination si demandé
            if inclure_destination and hasattr(serie, 'poste_destination_transfert') and serie.poste_destination_transfert:
                ligne.append(f"→ {serie.poste_destination_transfert.nom}")
            
            # Ajouter date de vente si demandé
            if inclure_date_vente and serie.date_utilisation:
                ligne.append(serie.date_utilisation.strftime('%d/%m/%Y'))
            
            data.append(ligne)
        
        # Définir largeurs de colonnes
        if inclure_destination:
            col_widths = [6*cm, 3*cm, 3.5*cm, 3*cm]
        elif inclure_date_vente:
            col_widths = [6*cm, 3*cm, 3.5*cm, 3*cm]
        else:
            col_widths = [7*cm, 4*cm, 5*cm]
        
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), highlight_color or colors.HexColor('#f3f4f6')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 0.2*cm))
    
    return elements


def creer_pied_page(poste, config, user):
    """
    ✅ Crée le pied de page avec signatures pour le compte d'emploi
    """
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Table, TableStyle, Spacer
    from datetime import datetime
    
    elements = []
    
    # Tableau des signatures
    signature_data = [
        ['LE CHEF DE POSTE', 'LE COMPTABLE MATIÈRES', 'VISA DU CONTRÔLEUR'],
        ['', '', ''],
        ['', '', ''],
        ['_____________________', '_____________________', '_____________________'],
        [f"{poste.nom}", '', '']
    ]
    
    sig_table = Table(signature_data, colWidths=[6*cm, 6*cm, 6*cm])
    sig_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    elements.append(sig_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Footer info
    footer_data = [[
        f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
        f"Par: {user.nom_complet}",
        f"SUPPER - {config.nom_application}"
    ]]
    
    footer_table = Table(footer_data, colWidths=[6*cm, 6*cm, 6*cm])
    footer_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 6),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.grey),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
    ]))
    
    elements.append(footer_table)
    
    return elements


def generer_compte_emploi_pdf(request, poste_id, date_debut, date_fin):
    """
    VERSION CORRIGÉE : Génère le PDF avec régularisations incluses
    """
    from datetime import datetime
    from django.shortcuts import get_object_or_404, redirect
    from django.contrib import messages
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.enums import TA_CENTER
    from accounts.models import Poste
    from inventaire.models import ConfigurationGlobale
    
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Vérifier les permissions
    if not request.user.is_admin:
        if not request.user.poste_affectation or request.user.poste_affectation != poste:
            messages.error(request, "Accès non autorisé")
            return redirect('inventaire:selection_compte_emploi')
    
    # Parser les dates
    try:
        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
    except:
        messages.error(request, "Format de dates invalide")
        return redirect('inventaire:selection_compte_emploi')
    
    # Récupérer config
    config = ConfigurationGlobale.get_config()
    
    # Calcul des données avec la fonction corrigée
    donnees = calculer_donnees_compte_emploi(poste, date_debut_obj, date_fin_obj)
    
    # Générer PDF
    response = HttpResponse(content_type='application/pdf')
    filename = f'compte_emploi_{poste.nom}_{date_debut}_au_{date_fin}.pdf'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    
    doc = SimpleDocTemplate(
        response,
        pagesize=landscape(A4),
        rightMargin=1*cm,
        leftMargin=1*cm,
        topMargin=1*cm,
        bottomMargin=1*cm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # En-tête
    elements.append(creer_entete_bilingue(config, poste))
    elements.append(Spacer(1, 0.5*cm))
    
    # Titre
    titre_style = ParagraphStyle(
        'TitreCompte',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=colors.HexColor('#1a1a1a'),
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    titre = Paragraph(
        f"COMPTE D'EMPLOI DES TICKETS<br/>"
        f"Période du {date_debut_obj.strftime('%d/%m/%Y')} au {date_fin_obj.strftime('%d/%m/%Y')}",
        titre_style
    )
    elements.append(titre)
    elements.append(Spacer(1, 0.3*cm))
    
    # ========== TABLEAU SYNTHÈSE AMÉLIORÉ ==========
    # Inclure RÉGULARISATION comme colonne séparée
    
    table_data = [
        ['PÉRIODE', 'STOCK DÉBUT', '', 'APPROV IMP.', '', 'RÉGULARISATION', '', 
         'REAPPROV REÇU', '', 'REAPPROV CÉDÉ', '', 'VENTE', '', 'STOCK FINAL', ''],
        ['', 'Qté', 'Valeur', 'Qté', 'Valeur', 'Qté', 'Valeur', 
         'Qté', 'Valeur', 'Qté', 'Valeur', 'Qté', 'Valeur', 'Qté', 'Valeur'],
        [
            f"{date_debut_obj.strftime('%d/%m')} - {date_fin_obj.strftime('%d/%m')}",
            str(donnees['stock_debut_qte']),
            f"{donnees['stock_debut_valeur']:,.0f}".replace(',', ' '),
            str(donnees['approv_imprimerie_qte']),
            f"{donnees['approv_imprimerie_valeur']:,.0f}".replace(',', ' '),
            str(donnees.get('approv_regularisation_qte', 0)),
            f"{donnees.get('approv_regularisation_valeur', 0):,.0f}".replace(',', ' '),
            str(donnees['reapprov_recu_qte']),
            f"{donnees['reapprov_recu_valeur']:,.0f}".replace(',', ' '),
            str(donnees['reapprov_cede_qte']),
            f"{donnees['reapprov_cede_valeur']:,.0f}".replace(',', ' '),
            str(donnees['vente_qte']),
            f"{donnees['vente_valeur']:,.0f}".replace(',', ' '),
            str(donnees['stock_final_qte']),
            f"{donnees['stock_final_valeur']:,.0f}".replace(',', ' ')
        ],
        [
            'TOTAL',
            str(donnees['stock_debut_qte']),
            f"{donnees['stock_debut_valeur']:,.0f}".replace(',', ' '),
            str(donnees['approv_imprimerie_qte']),
            f"{donnees['approv_imprimerie_valeur']:,.0f}".replace(',', ' '),
            str(donnees.get('approv_regularisation_qte', 0)),
            f"{donnees.get('approv_regularisation_valeur', 0):,.0f}".replace(',', ' '),
            str(donnees['reapprov_recu_qte']),
            f"{donnees['reapprov_recu_valeur']:,.0f}".replace(',', ' '),
            str(donnees['reapprov_cede_qte']),
            f"{donnees['reapprov_cede_valeur']:,.0f}".replace(',', ' '),
            str(donnees['vente_qte']),
            f"{donnees['vente_valeur']:,.0f}".replace(',', ' '),
            str(donnees['stock_final_qte']),
            f"{donnees['stock_final_valeur']:,.0f}".replace(',', ' ')
        ]
    ]
    
    # Largeurs de colonnes ajustées pour inclure RÉGULARISATION
    col_widths = [1.5*cm, 1*cm, 1.7*cm, 1*cm, 1.7*cm, 1*cm, 1.7*cm, 
                  1*cm, 1.7*cm, 1*cm, 1.7*cm, 1*cm, 1.7*cm, 1*cm, 1.7*cm]
    
    table = Table(table_data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 6),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#e2e8f0')),
        ('FONTSIZE', (0, 1), (-1, -1), 6),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#cbd5e0')),
        ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        # Fusion des cellules d'en-tête
        ('SPAN', (0, 0), (0, 1)),
        ('SPAN', (1, 0), (2, 0)),
        ('SPAN', (3, 0), (4, 0)),
        ('SPAN', (5, 0), (6, 0)),
        ('SPAN', (7, 0), (8, 0)),
        ('SPAN', (9, 0), (10, 0)),
        ('SPAN', (11, 0), (12, 0)),
        ('SPAN', (13, 0), (14, 0)),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 0.5*cm))
    
    # ========== SECTIONS DÉTAILLÉES ==========
    
    # Stock de début
    if donnees['stock_debut_par_couleur']:
        elements.extend(creer_section_details_series(
            "DÉTAIL DU STOCK DE DÉBUT",
            donnees['stock_debut_par_couleur'],
            styles
        ))
        elements.append(Spacer(1, 0.3*cm))
    
    # Approvisionnements Imprimerie
    if donnees['approv_imp_par_couleur']:
        elements.append(creer_section_details_series(
            "DÉTAIL DES APPROVISIONNEMENTS - IMPRIMERIE NATIONALE",
            donnees['approv_imp_par_couleur'],
            styles
        ))
        elements.append(Spacer(1, 0.3*cm))
    
    # Approvisionnements Régularisation
    if donnees.get('approv_reg_par_couleur'):
        elements.extend(creer_section_details_series(
            "DÉTAIL DES RÉGULARISATIONS",
            donnees['approv_reg_par_couleur'],
            styles,
            highlight_color=colors.HexColor('#fbbf24')  # Couleur jaune pour distinguer
        ))
        elements.append(Spacer(1, 0.3*cm))
    
    # Transferts reçus
    if donnees['transferts_recus_par_couleur']:
        elements.extend(creer_section_details_series(
            "DÉTAIL DES TRANSFERTS REÇUS",
            donnees['transferts_recus_par_couleur'],
            styles
        ))
        elements.append(Spacer(1, 0.3*cm))
    
    # Saut de page
    elements.append(PageBreak())
    
    # Transferts cédés
    if donnees['transferts_cedes_par_couleur']:
        elements.extend(creer_section_transferts_cedes(
            "DÉTAIL DES TRANSFERTS CÉDÉS",
            donnees['transferts_cedes_par_couleur'],
            styles
        ))
        elements.append(Spacer(1, 0.5*cm))
    
    # Ventes par semaine
    if donnees['ventes_par_semaine']:
        elements.extend(creer_section_ventes_par_semaine(
            donnees['ventes_par_semaine'],
            styles,
        ))
        elements.append(Spacer(1, 0.5*cm))
    
    # Stock Final
    if donnees['stock_final_par_couleur']:
        elements.append(creer_section_details_series(
            "DÉTAIL DU STOCK FINAL (RESTE EN CIRCULATION)",
            donnees['stock_final_par_couleur'],
            styles,
        ))
    
    # Note de vérification
    elements.append(Spacer(1, 0.5*cm))
    
    # Ajout d'une note de vérification de cohérence
    note_style = ParagraphStyle(
        'Note',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor('#4b5563'),
        alignment=TA_CENTER
    )
    
    # Calcul de vérification
    total_entrees = (
        donnees['stock_debut_valeur'] + 
        donnees['approv_imprimerie_valeur'] + 
        donnees.get('approv_regularisation_valeur', 0) +
        donnees['reapprov_recu_valeur']
    )
    
    total_sorties = donnees['reapprov_cede_valeur'] + donnees['vente_valeur']
    stock_calcule = total_entrees - total_sorties
    
    ecart = abs(stock_calcule - donnees['stock_final_valeur'])
    
    if ecart < 1000:
        note_text = "✓ Cohérence vérifiée : Stock final = Stock début + Entrées - Sorties"
        note_color = colors.HexColor('#10b981')
    else:
        note_text = f"⚠ Écart détecté : {ecart:,.0f} FCFA".replace(',', ' ')
        note_color = colors.HexColor('#ef4444')
    
    note_paragraph = Paragraph(
        f"<font color='{note_color}'>{note_text}</font>", 
        note_style
    )
    elements.append(note_paragraph)
    
    # Pied de page
    elements.append(Spacer(1, 0.5*cm))
    elements.append(creer_pied_page(poste, config, request.user))
    
    # Générer le PDF
    doc.build(elements)
    
    return response

def creer_section_details_series(titre, donnees_par_couleur, styles, 
                                inclure_destination=False, inclure_date_vente=False):
    """
    ✅ NOUVELLE FONCTION : Crée une section détaillée avec séries par couleur
    """
    
    section_elements = []
    
    # Titre de la section
    titre_style = ParagraphStyle(
        'TitreSection',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=colors.HexColor('#2d3748'),
        spaceAfter=10
    )
    
    section_elements.append(Paragraph(titre, titre_style))
    
    # Tableau pour chaque couleur
    for couleur_nom, groupe in donnees_par_couleur.items():
        # En-tête couleur
        data = [[
            Paragraph(f"<b>{couleur_nom}</b>", styles['Normal']),
            f"Total: {groupe['total_tickets']} tickets",
            f"{groupe['valeur_totale']:,.0f} FCFA".replace(',', '.')
        ]]
        
        # Lignes de séries
        for serie in groupe['series']:
            ligne = [
                f"#{serie.numero_premier} → #{serie.numero_dernier}",
                f"{serie.nombre_tickets} tickets",
                f"{serie.valeur_monetaire:,.0f} FCFA".replace(',', '')
            ]
            
            if inclure_destination:
                if hasattr(serie, 'poste_destination_transfert') and serie.poste_destination_transfert:
                    ligne.append(f"→ {serie.poste_destination_transfert.nom}")
                else:
                    ligne.append("-")

            if inclure_date_vente:
                if hasattr(serie, 'date_utilisation') and serie.date_utilisation:
                    ligne.append(serie.date_utilisation.strftime('%d/%m/%Y'))
                else:
                    ligne.append("-")

            data.append(ligne)
        
        # Déterminer largeurs colonnes
        if inclure_destination or inclure_date_vente:
            col_widths = [6*cm, 3*cm, 3*cm, 6*cm]
        else:
            col_widths = [7*cm, 4*cm, 5*cm]
        
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        
        section_elements.append(table)
        section_elements.append(Spacer(1, 0.2*cm))
    
    return Table([[section_elements]], colWidths=[26*cm])


def creer_section_transferts_cedes(titre, series_par_couleur, styles):
    """
    Fonction spécifique pour afficher les transferts cédés avec destination
    """
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    
    elements = []
    
    # Titre
    section_style = ParagraphStyle(
        'SectionTransfertsCedes',
        parent=styles['Heading2'],
        fontSize=10,
        textColor=colors.HexColor('#dc2626'),
        spaceAfter=10,
        spaceBefore=5
    )
    
    elements.append(Paragraph(titre, section_style))
    
    if not series_par_couleur:
        elements.append(Paragraph(
            "<i>Aucun transfert cédé</i>",
            styles['Normal']
        ))
        return elements
    
    # Tableau par couleur
    for couleur_nom, groupe in series_par_couleur.items():
        data = [[
            f"{couleur_nom}",
            f"Total: {groupe['total_tickets']} tickets",
            f"{groupe['valeur_totale']:,.0f} FCFA".replace(',', ' '),
            "Destination"
        ]]
        
        for serie in groupe['series']:
            destination = "-"
            if hasattr(serie, 'poste_destination_transfert') and serie.poste_destination_transfert:
                destination = f"→ {serie.poste_destination_transfert.nom}"
            
            ligne = [
                f"#{serie.numero_premier} → #{serie.numero_dernier}",
                f"{serie.nombre_tickets} tickets",
                f"{serie.valeur_monetaire:,.0f} FCFA".replace(',', ' '),
                destination
            ]
            data.append(ligne)
        
        table = Table(data, colWidths=[6*cm, 3*cm, 3.5*cm, 3*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fee2e2')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 0.2*cm))
    
    return elements

def creer_section_ventes_par_semaine(ventes_par_semaine, styles):
    """
    ✅ NOUVEAU : Crée une section des ventes regroupées par semaine et par couleur
    
    Format :
    SEMAINE DU 01/10 AU 07/10/2025
      Bleu clair : #100 → #201 | 102 tickets | 51 000 FCFA
      Rouge : #5000 → #5626 | 627 tickets | 313 500 FCFA
    
    SEMAINE DU 08/10 AU 14/10/2025
      ...
    """
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    
    elements = []
    
    # Titre de section
    section_style = ParagraphStyle(
        'SectionVentesSemaine',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.HexColor('#dc2626'),  # Rouge pour les ventes
        spaceAfter=10,
        spaceBefore=10
    )
    
    elements.append(Paragraph("DÉTAIL DES VENTES PAR SEMAINE", section_style))
    
    if not ventes_par_semaine:
        elements.append(Paragraph(
            "<i>Aucune vente enregistrée sur cette période</i>",
            styles['Normal']
        ))
        return elements
    
    # Trier les semaines chronologiquement
    semaines_triees = sorted(
        ventes_par_semaine.items(),
        key=lambda x: x[1]['date_debut']
    )
    
    # Créer un tableau pour chaque semaine
    for semaine_key, semaine_data in semaines_triees:
        # En-tête de semaine
        semaine_style = ParagraphStyle(
            'SemaineTitre',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.whitesmoke,
            alignment=TA_CENTER,
            spaceAfter=5
        )
        
        data = [[
            Paragraph(f"<b>SEMAINE DU {semaine_key}</b>", semaine_style)
        ]]
        
        # Lignes par couleur
        for couleur_nom, couleur_data in semaine_data['couleurs'].items():
            premier = couleur_data['premier_ticket']
            dernier = couleur_data['dernier_ticket']
            total_tickets = couleur_data['total_tickets']
            valeur = couleur_data['valeur_totale']
            
            ligne_texte = (
                f"<b>{couleur_nom}</b> : "
                f"#{premier} → #{dernier} | "
                f"{total_tickets} tickets | "
                f"{valeur:,.0f} FCFA".replace(',', ' ')
            )
            
            data.append([Paragraph(ligne_texte, styles['Normal'])])
        
        # Créer le tableau
        table = Table(data, colWidths=[18*cm])
        table.setStyle(TableStyle([
            # En-tête de semaine
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Lignes de couleurs
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fef2f2')),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('LEFTPADDING', (0, 1), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            
            # Bordures
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#dc2626')),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 0.3*cm))
    
    return elements



def calculer_donnees_compte_emploi(poste, date_debut, date_fin):
    """
    VERSION FINALE CORRIGÉE
    
    CORRECTIONS:
    1. Semaines commencent à date_debut (pas forcément lundi)
    2. Type d'entrée correct pour imprimerie nationale
    3. Vérification stricte des séries pour éviter les mélanges
    """
    from decimal import Decimal
    from django.db.models import Sum, Q
    from inventaire.models import SerieTicket, StockEvent
    from datetime import timedelta, datetime
    from django.utils import timezone
    from collections import defaultdict
    import logging
    
    logger = logging.getLogger('supper')
    
    # Initialiser la structure de données
    donnees = {
        'stock_debut_qte': 0,
        'stock_debut_valeur': Decimal('0'),
        'approv_imprimerie_qte': 0,
        'approv_imprimerie_valeur': Decimal('0'),
        'approv_regularisation_qte': 0,
        'approv_regularisation_valeur': Decimal('0'),
        'reapprov_recu_qte': 0,
        'reapprov_recu_valeur': Decimal('0'),
        'reapprov_cede_qte': 0,
        'reapprov_cede_valeur': Decimal('0'),
        'vente_qte': 0,
        'vente_valeur': Decimal('0'),
        'stock_final_qte': 0,
        'stock_final_valeur': Decimal('0'),
        
        'stock_debut_par_couleur': {},
        'approv_imp_par_couleur': {},
        'approv_reg_par_couleur': {},
        'transferts_recus_par_couleur': {},
        'transferts_cedes_par_couleur': {},
        'ventes_par_couleur': {},
        'ventes_par_semaine': {},
        'stock_final_par_couleur': {},
    }
    
    # ========== 1. STOCK AU DÉBUT ==========
    # Stock début = tout ce qui s'est passé AVANT date_debut (veille à 23h59:59)
    
    veille_debut = date_debut - timedelta(days=1)
    debut_datetime = timezone.make_aware(
        datetime.combine(veille_debut, datetime.max.time().replace(microsecond=999999))
    )
    
    # Event Sourcing pour le stock début
    events_avant_debut = StockEvent.objects.filter(
        poste=poste,
        event_datetime__lte=debut_datetime
    ).aggregate(
        total_valeur=Sum('montant_variation'),
        total_tickets=Sum('nombre_tickets_variation')
    )
    
    stock_debut_valeur = events_avant_debut['total_valeur'] or Decimal('0')
    stock_debut_qte = events_avant_debut['total_tickets'] or 0
    
    if stock_debut_valeur < 0:
        stock_debut_valeur = Decimal('0')
    if stock_debut_qte < 0:
        stock_debut_qte = 0
    
    donnees['stock_debut_valeur'] = stock_debut_valeur
    donnees['stock_debut_qte'] = stock_debut_qte
    
    # Détail du stock début par couleur
    series_stock_debut = SerieTicket.objects.filter(
        poste=poste,
        date_reception__lte=veille_debut,
        statut='stock'
    ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
    
    for serie in series_stock_debut:
        couleur_key = serie.couleur.libelle_affichage
        if couleur_key not in donnees['stock_debut_par_couleur']:
            donnees['stock_debut_par_couleur'][couleur_key] = {
                'couleur': serie.couleur,
                'series': [],
                'total_tickets': 0,
                'valeur_totale': Decimal('0')
            }
        
        donnees['stock_debut_par_couleur'][couleur_key]['series'].append(serie)
        donnees['stock_debut_par_couleur'][couleur_key]['total_tickets'] += serie.nombre_tickets
        donnees['stock_debut_par_couleur'][couleur_key]['valeur_totale'] += serie.valeur_monetaire
    
    # ========== 2. MOUVEMENTS PENDANT LA PÉRIODE ==========
    
    fin_datetime = timezone.make_aware(
        datetime.combine(date_fin, datetime.max.time().replace(microsecond=999999))
    )
    
    # 2.1 APPROVISIONNEMENTS IMPRIMERIE NATIONALE
    # CORRECTION : Vérifier les types d'entrée possibles
    types_imprimerie = ['imprimerie_nationale', 'imprimerie']
    
    series_imprimerie = SerieTicket.objects.filter(
        poste=poste,
        type_entree__in=types_imprimerie,  # Utiliser IN pour couvrir les variantes
        date_reception__gte=date_debut,
        date_reception__lte=date_fin
    ).exclude(
        statut__in=['vendu', 'epuise']  # EXCLURE les séries vendues
    ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
    
    # Logger pour débug
    logger.info(f"Approvisionnements Imprimerie trouvés: {series_imprimerie.count()} séries")
    
    for serie in series_imprimerie:
        donnees['approv_imprimerie_qte'] += serie.nombre_tickets
        donnees['approv_imprimerie_valeur'] += serie.valeur_monetaire
        
        couleur_key = serie.couleur.libelle_affichage
        if couleur_key not in donnees['approv_imp_par_couleur']:
            donnees['approv_imp_par_couleur'][couleur_key] = {
                'couleur': serie.couleur,
                'series': [],
                'total_tickets': 0,
                'valeur_totale': Decimal('0')
            }
        
        donnees['approv_imp_par_couleur'][couleur_key]['series'].append(serie)
        donnees['approv_imp_par_couleur'][couleur_key]['total_tickets'] += serie.nombre_tickets
        donnees['approv_imp_par_couleur'][couleur_key]['valeur_totale'] += serie.valeur_monetaire
        
        logger.debug(f"Imprimerie: Série {couleur_key} #{serie.numero_premier}-{serie.numero_dernier} = {serie.valeur_monetaire}")
    
    # 2.2 APPROVISIONNEMENTS PAR RÉGULARISATION
    series_regularisation = SerieTicket.objects.filter(
        poste=poste,
        type_entree='regularisation',
        date_reception__gte=date_debut,
        date_reception__lte=date_fin
    ).exclude(
        statut__in=['vendu', 'epuise']  # EXCLURE les séries vendues
    ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
    
    for serie in series_regularisation:
        donnees['approv_regularisation_qte'] += serie.nombre_tickets
        donnees['approv_regularisation_valeur'] += serie.valeur_monetaire
        
        couleur_key = serie.couleur.libelle_affichage
        if couleur_key not in donnees['approv_reg_par_couleur']:
            donnees['approv_reg_par_couleur'][couleur_key] = {
                'couleur': serie.couleur,
                'series': [],
                'total_tickets': 0,
                'valeur_totale': Decimal('0')
            }
        
        donnees['approv_reg_par_couleur'][couleur_key]['series'].append(serie)
        donnees['approv_reg_par_couleur'][couleur_key]['total_tickets'] += serie.nombre_tickets
        donnees['approv_reg_par_couleur'][couleur_key]['valeur_totale'] += serie.valeur_monetaire
    
    # 2.3 TRANSFERTS REÇUS
    series_recues = SerieTicket.objects.filter(
        poste=poste,
        type_entree='transfert_recu',
        date_reception__gte=date_debut,
        date_reception__lte=date_fin
    ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
    
    for serie in series_recues:
        donnees['reapprov_recu_qte'] += serie.nombre_tickets
        donnees['reapprov_recu_valeur'] += serie.valeur_monetaire
        
        couleur_key = serie.couleur.libelle_affichage
        if couleur_key not in donnees['transferts_recus_par_couleur']:
            donnees['transferts_recus_par_couleur'][couleur_key] = {
                'couleur': serie.couleur,
                'series': [],
                'total_tickets': 0,
                'valeur_totale': Decimal('0')
            }
        
        donnees['transferts_recus_par_couleur'][couleur_key]['series'].append(serie)
        donnees['transferts_recus_par_couleur'][couleur_key]['total_tickets'] += serie.nombre_tickets
        donnees['transferts_recus_par_couleur'][couleur_key]['valeur_totale'] += serie.valeur_monetaire
    
    # 2.4 TRANSFERTS CÉDÉS
    series_cedees = SerieTicket.objects.filter(
        poste=poste,
        statut='transfere',
        date_utilisation__gte=date_debut,
        date_utilisation__lte=date_fin
    ).select_related('couleur', 'poste_destination_transfert').order_by('couleur__code_normalise', 'numero_premier')
    
    for serie in series_cedees:
        donnees['reapprov_cede_qte'] += serie.nombre_tickets
        donnees['reapprov_cede_valeur'] += serie.valeur_monetaire
        
        couleur_key = serie.couleur.libelle_affichage
        if couleur_key not in donnees['transferts_cedes_par_couleur']:
            donnees['transferts_cedes_par_couleur'][couleur_key] = {
                'couleur': serie.couleur,
                'series': [],
                'total_tickets': 0,
                'valeur_totale': Decimal('0')
            }
        
        donnees['transferts_cedes_par_couleur'][couleur_key]['series'].append(serie)
        donnees['transferts_cedes_par_couleur'][couleur_key]['total_tickets'] += serie.nombre_tickets
        donnees['transferts_cedes_par_couleur'][couleur_key]['valeur_totale'] += serie.valeur_monetaire
    
    # 2.5 VENTES (avec détail par semaine CORRIGÉ)
    series_vendues = SerieTicket.objects.filter(
        poste=poste,
        statut__in=['vendu', 'epuise'],
        date_utilisation__gte=date_debut,
        date_utilisation__lte=date_fin
    ).select_related('couleur').order_by('date_utilisation', 'couleur__code_normalise', 'numero_premier')
    
    for serie in series_vendues:
        donnees['vente_qte'] += serie.nombre_tickets
        donnees['vente_valeur'] += serie.valeur_monetaire
        
        couleur_key = serie.couleur.libelle_affichage
        
        if couleur_key not in donnees['ventes_par_couleur']:
            donnees['ventes_par_couleur'][couleur_key] = {
                'couleur': serie.couleur,
                'series': [],
                'total_tickets': 0,
                'valeur_totale': Decimal('0')
            }
        
        donnees['ventes_par_couleur'][couleur_key]['series'].append(serie)
        donnees['ventes_par_couleur'][couleur_key]['total_tickets'] += serie.nombre_tickets
        donnees['ventes_par_couleur'][couleur_key]['valeur_totale'] += serie.valeur_monetaire
        
        # CORRECTION : Regroupement par semaine commençant à date_debut
        if serie.date_utilisation:
            # Calculer le nombre de jours depuis date_debut
            jours_depuis_debut = (serie.date_utilisation - date_debut).days
            
            # Calculer le numéro de semaine (0, 1, 2, ...)
            numero_semaine = jours_depuis_debut // 7
            
            # Calculer les dates de début et fin de cette semaine
            semaine_debut = date_debut + timedelta(days=numero_semaine * 7)
            
            # La fin de semaine est soit +6 jours, soit date_fin si on dépasse
            semaine_fin_theorique = semaine_debut + timedelta(days=6)
            semaine_fin = min(semaine_fin_theorique, date_fin)
            
            # Clé de la semaine
            semaine_key = f"{semaine_debut.strftime('%d/%m')} au {semaine_fin.strftime('%d/%m/%Y')}"
            
            if semaine_key not in donnees['ventes_par_semaine']:
                donnees['ventes_par_semaine'][semaine_key] = {
                    'date_debut': semaine_debut,
                    'date_fin': semaine_fin,
                    'couleurs': {}
                }
            
            if couleur_key not in donnees['ventes_par_semaine'][semaine_key]['couleurs']:
                donnees['ventes_par_semaine'][semaine_key]['couleurs'][couleur_key] = {
                    'couleur': serie.couleur,
                    'series': [],
                    'total_tickets': 0,
                    'valeur_totale': Decimal('0'),
                    'premier_ticket': None,
                    'dernier_ticket': None
                }
            
            donnees['ventes_par_semaine'][semaine_key]['couleurs'][couleur_key]['series'].append(serie)
            donnees['ventes_par_semaine'][semaine_key]['couleurs'][couleur_key]['total_tickets'] += serie.nombre_tickets
            donnees['ventes_par_semaine'][semaine_key]['couleurs'][couleur_key]['valeur_totale'] += serie.valeur_monetaire
            
            couleur_data = donnees['ventes_par_semaine'][semaine_key]['couleurs'][couleur_key]
            if couleur_data['premier_ticket'] is None or serie.numero_premier < couleur_data['premier_ticket']:
                couleur_data['premier_ticket'] = serie.numero_premier
            if couleur_data['dernier_ticket'] is None or serie.numero_dernier > couleur_data['dernier_ticket']:
                couleur_data['dernier_ticket'] = serie.numero_dernier
    
    # ========== 3. CALCUL DU STOCK FINAL ==========
    
    total_entrees = (
        donnees['approv_imprimerie_valeur'] +
        donnees['approv_regularisation_valeur'] +
        donnees['reapprov_recu_valeur']
    )
    
    total_sorties = (
        donnees['reapprov_cede_valeur'] +
        donnees['vente_valeur']
    )
    
    donnees['stock_final_valeur'] = donnees['stock_debut_valeur'] + total_entrees - total_sorties
    donnees['stock_final_qte'] = int(donnees['stock_final_valeur'] / 500) if donnees['stock_final_valeur'] > 0 else 0
    
    # Vérification par Event Sourcing
    events_jusqu_fin = StockEvent.objects.filter(
        poste=poste,
        event_datetime__lte=fin_datetime
    ).aggregate(
        total_valeur=Sum('montant_variation'),
        total_tickets=Sum('nombre_tickets_variation')
    )
    
    stock_final_event_sourcing = events_jusqu_fin['total_valeur'] or Decimal('0')
    
    if abs(stock_final_event_sourcing - donnees['stock_final_valeur']) > Decimal('1000'):
        logger.warning(
            f"Écart détecté pour {poste.nom}: "
            f"Calcul direct={donnees['stock_final_valeur']}, "
            f"Event Sourcing={stock_final_event_sourcing}"
        )
    
    # Détail du stock final par couleur
    # CORRECTION : Chercher les séries qui sont TOUJOURS en stock à date_fin
    series_stock_final = SerieTicket.objects.filter(
        poste=poste,
        date_reception__lte=date_fin
    ).filter(
        Q(statut='stock') |  # Soit toujours en stock
        Q(statut__in=['vendu', 'epuise', 'transfere'], date_utilisation__gt=date_fin)  # Soit utilisées APRÈS date_fin
    ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
    
    for serie in series_stock_final:
        couleur_key = serie.couleur.libelle_affichage
        if couleur_key not in donnees['stock_final_par_couleur']:
            donnees['stock_final_par_couleur'][couleur_key] = {
                'couleur': serie.couleur,
                'series': [],
                'total_tickets': 0,
                'valeur_totale': Decimal('0')
            }
        
        donnees['stock_final_par_couleur'][couleur_key]['series'].append(serie)
        donnees['stock_final_par_couleur'][couleur_key]['total_tickets'] += serie.nombre_tickets
        donnees['stock_final_par_couleur'][couleur_key]['valeur_totale'] += serie.valeur_monetaire
    
    # LOG pour vérification
    logger.info(f"Compte d'emploi {poste.nom} du {date_debut} au {date_fin}:")
    logger.info(f"  Stock début: {stock_debut_qte} tickets = {stock_debut_valeur}")
    logger.info(f"  Approv. Imprimerie: {donnees['approv_imprimerie_qte']} tickets = {donnees['approv_imprimerie_valeur']}")
    logger.info(f"  Ventes: {donnees['vente_qte']} tickets = {donnees['vente_valeur']}")
    logger.info(f"  Stock final: {donnees['stock_final_qte']} tickets = {donnees['stock_final_valeur']}")
    
    return donnees

def creer_entete_bilingue(config, poste):
    """Crée l'en-tête bilingue du document"""
    
    styles = getSampleStyleSheet()
    
    header_style = ParagraphStyle(
        'HeaderStyle',
        parent=styles['Normal'],
        fontSize=8,
        alignment=TA_CENTER,
        leading=10
    )
    
    col_gauche = [
        Paragraph(f"<b>{config.republique_fr}</b>", header_style),
        Paragraph(config.devise_fr, header_style),
        Paragraph("*****", header_style),
        Paragraph(f"<b>{config.ministere_fr}</b>", header_style),
        Paragraph("*****", header_style),
        Paragraph(f"<b>{config.direction_fr}</b>", header_style),
        Paragraph("**********", header_style),
        Paragraph(f"<b>{config.programme_fr}</b>", header_style),
        Paragraph("*********", header_style),
        Paragraph(f"<b>POSTE DE {poste.nom.upper()}</b>", header_style),  # UTILISE poste.nom
        Paragraph("*********", header_style)
    ]
    
    logo_cell = ""
    if config.logo:
        try:
            logo_path = os.path.join(settings.MEDIA_ROOT, config.logo.name)
            if os.path.exists(logo_path):
                logo_cell = Image(logo_path, width=3*cm, height=3*cm)
        except:
            pass
    
    col_droite = [
        Paragraph(f"<b>{config.republique_en}</b>", header_style),
        Paragraph(config.devise_en, header_style),
        Paragraph("*****", header_style),
        Paragraph(f"<b>{config.ministere_en}</b>", header_style),
        Paragraph("*****", header_style),
        Paragraph(f"<b>{config.direction_en}</b>", header_style),
        Paragraph("**********", header_style),
        Paragraph(f"<b>{config.programme_en}</b>", header_style),
        Paragraph("*********", header_style),
        Paragraph(f"<b>POST OF {poste.nom.upper()}</b>", header_style),  # UTILISE poste.nom
        Paragraph("*********", header_style)
    ]
    
    if logo_cell:
        header_data = [[col_gauche, logo_cell, col_droite]]
    else:
        header_data = [[col_gauche, "DGI", col_droite]]
    
    header_table = Table(header_data, colWidths=[8*cm, 4*cm, 8*cm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
    ]))
    
    return header_table

@login_required
@user_passes_test(lambda u: u.is_admin)
def parametrage_global(request):
    """Vue de paramétrage global pour tous les postes"""
    
    config = ConfigurationGlobale.get_config()
    
    if request.method == 'POST':
        config.republique_fr = request.POST.get('republique_fr', config.republique_fr)
        config.devise_fr = request.POST.get('devise_fr', config.devise_fr)
        config.ministere_fr = request.POST.get('ministere_fr', config.ministere_fr)
        config.direction_fr = request.POST.get('direction_fr', config.direction_fr)
        config.programme_fr = request.POST.get('programme_fr', config.programme_fr)
        
        config.republique_en = request.POST.get('republique_en', config.republique_en)
        config.devise_en = request.POST.get('devise_en', config.devise_en)
        config.ministere_en = request.POST.get('ministere_en', config.ministere_en)
        config.direction_en = request.POST.get('direction_en', config.direction_en)
        config.programme_en = request.POST.get('programme_en', config.programme_en)
        
        if 'logo' in request.FILES:
            config.logo = request.FILES['logo']
        
        config.save()
        
        messages.success(request, "Configuration globale mise à jour avec succès")
        return redirect('inventaire:parametrage_global')
    
    context = {
        'config': config,
        'title': 'Paramétrage Global des Documents'
    }
    
    return render(request, 'inventaire/parametrage_global.html', context)

def creer_pied_page(poste, config, user):
    """Crée le pied de page avec signature et horodatage"""
    
    styles = getSampleStyleSheet()
    
    footer_style = ParagraphStyle(
        'FooterStyle',
        parent=styles['Normal'],
        fontSize=9,
        alignment=TA_CENTER
    )
    
    date_impression = datetime.now().strftime("%d/%m/%Y à %H:%M")
    
    footer_data = [
        [Paragraph(f"le {date_impression}", footer_style)],
        [Spacer(1, 0.3*cm)],
        [Paragraph("<b>LE CHEF DE POSTE</b>", footer_style)],
        [Spacer(1, 1*cm)],
        [Paragraph("_________________________", footer_style)],
        [Spacer(1, 0.3*cm)],
        [Paragraph(f"<i>Document généré par SUPPER - Utilisateur: {user.nom_complet}</i>", 
                   ParagraphStyle('FooterItalic', parent=footer_style, fontSize=7, textColor=colors.grey))]
    ]
    
    footer_table = Table(footer_data, colWidths=[20*cm])
    
    return footer_table

# inventaire/views_rapports.py - Vue à AJOUTER

@login_required
def apercu_compte_emploi(request, poste_id, date_debut, date_fin):
    """
    Vue pour afficher un aperçu du compte d'emploi avant génération du PDF
    Utilise le calcul amélioré avec stocks à date précis
    """
    from django.shortcuts import render, get_object_or_404, redirect
    from django.contrib import messages
    from datetime import datetime
    from accounts.models import Poste
    
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Vérifier les permissions
    if not request.user.is_admin:
        if not request.user.poste_affectation or request.user.poste_affectation != poste:
            messages.error(request, "Accès non autorisé")
            return redirect('inventaire:selection_compte_emploi')
    
    # Parser les dates
    try:
        date_debut_obj = datetime.strptime(date_debut, '%Y-%m-%d').date()
        date_fin_obj = datetime.strptime(date_fin, '%Y-%m-%d').date()
    except:
        messages.error(request, "Format de dates invalide")
        return redirect('inventaire:selection_compte_emploi')
    
    # Calculer le nombre de jours
    nombre_jours = (date_fin_obj - date_debut_obj).days + 1
    
    # Calculer les données avec la nouvelle fonction
    donnees = calculer_donnees_compte_emploi(poste, date_debut_obj, date_fin_obj)
    
    # Vérifier la cohérence des données
    entrees_totales = (
        donnees['stock_debut_valeur'] +
        donnees['approv_imprimerie_valeur'] +
        donnees['reapprov_recu_valeur']
    )
    
    sorties_totales = (
        donnees['reapprov_cede_valeur'] +
        donnees['vente_valeur']
    )
    
    stock_final_calcule = entrees_totales - sorties_totales
    
    # Alerte si incohérence
    coherence_ok = abs(stock_final_calcule - donnees['stock_final_valeur']) < 1000
    
    if not coherence_ok:
        messages.warning(
            request,
            f"⚠️ Attention : Écart détecté dans le calcul. "
            f"Stock final calculé : {stock_final_calcule:,.0f} FCFA, "
            f"Stock final réel : {donnees['stock_final_valeur']:,.0f} FCFA"
        )
    
    context = {
        'poste': poste,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'date_debut_obj': date_debut_obj,
        'date_fin_obj': date_fin_obj,
        'nombre_jours': nombre_jours,
        'donnees': donnees,
        'coherence_ok': coherence_ok,
        'title': f"Compte d'Emploi - {poste.nom}"
    }
    
    return render(request, 'inventaire/compte_emploi_pdf_preview.html', context)

# def creer_section_details_series(titre, series_par_couleur, styles, 
#                                  inclure_date_vente=False, 
#                                  inclure_destination=False):
#     """
#     ✅ Crée une section détaillée des séries groupées par couleur
    
#     Args:
#         titre: Titre de la section
#         series_par_couleur: Dict {couleur: {'series': [...], 'total_tickets': X, ...}}
#         styles: Styles ReportLab
#         inclure_date_vente: Ajouter colonne date de vente
#         inclure_destination: Ajouter colonne poste destination
    
#     Returns:
#         Liste d'éléments ReportLab (Paragraph + Table)
#     """
#     from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
#     from reportlab.lib import colors
#     from reportlab.lib.units import cm
#     from reportlab.lib.styles import ParagraphStyle
    
#     elements = []
    
#     # Titre de la section
#     titre_style = ParagraphStyle(
#         'TitreSection',
#         parent=styles['Heading2'],
#         fontSize=10,
#         textColor=colors.HexColor('#1a1a1a'),
#         spaceAfter=10,
#         spaceBefore=10
#     )
    
#     elements.append(Paragraph(titre, titre_style))
    
#     # Construire le tableau
#     if not series_par_couleur:
#         elements.append(Paragraph("<i>Aucune donnée</i>", styles['Normal']))
#         return elements
    
#     # En-têtes dynamiques
#     headers = ['Couleur', 'Série (Début → Fin)', 'Nombre Tickets', 'Valeur (FCFA)']
    
#     if inclure_date_vente:
#         headers.insert(1, 'Date Vente')
    
#     if inclure_destination:
#         headers.append('Poste Destination')
    
#     # Construire les données
#     table_data = [headers]
    
#     for couleur_nom in sorted(series_par_couleur.keys()):
#         groupe = series_par_couleur[couleur_nom]
        
#         # Ligne d'en-tête couleur (fusion)
#         nb_cols = len(headers)
#         couleur_header = [couleur_nom] + [''] * (nb_cols - 3) + [
#             f"{groupe['total_tickets']} tickets",
#             f"{groupe['valeur_totale']:,.0f}".replace(',', ' ')
#         ]
#         table_data.append(couleur_header)
        
#         # Lignes de détail des séries
#         for serie in groupe['series'][:20]:  # Limiter à 20 séries par couleur
#             row = [
#                 '',  # Couleur (vide car déjà dans header)
#                 f"#{serie.numero_premier} → #{serie.numero_dernier}",
#                 str(serie.nombre_tickets),
#                 f"{serie.valeur_monetaire:,.0f}".replace(',', ' ')
#             ]
            
#             if inclure_date_vente:
#                 date_str = serie.date_utilisation.strftime('%d/%m/%Y') if serie.date_utilisation else '-'
#                 row.insert(1, date_str)
            
#             if inclure_destination:
#                 if serie.poste_destination_transfert:
#                     row.append(f"{serie.poste_destination_transfert.code}")
#                 else:
#                     row.append('-')
            
#             table_data.append(row)
        
#         # Si trop de séries, ajouter une ligne "..."
#         if len(groupe['series']) > 20:
#             row_etc = [''] * (nb_cols - 2) + [
#                 f"... ({len(groupe['series']) - 20} séries supplémentaires)",
#                 ''
#             ]
#             table_data.append(row_etc)
    
#     # Définir les largeurs de colonnes
#     if inclure_date_vente and inclure_destination:
#         col_widths = [3*cm, 2*cm, 4*cm, 2*cm, 3*cm, 3*cm]
#     elif inclure_date_vente:
#         col_widths = [3*cm, 2*cm, 4*cm, 2*cm, 3*cm]
#     elif inclure_destination:
#         col_widths = [3*cm, 4*cm, 2*cm, 3*cm, 3*cm]
#     else:
#         col_widths = [3*cm, 5*cm, 2.5*cm, 3.5*cm]
    
#     # Créer le tableau
#     table = Table(table_data, colWidths=col_widths)
    
#     # Style du tableau
#     style_list = [
#         ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
#         ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
#         ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
#         ('FONTSIZE', (0, 0), (-1, 0), 8),
#         ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
#         ('ALIGN', (-2, 0), (-1, -1), 'RIGHT'),
#         ('FONTSIZE', (0, 1), (-1, -1), 7),
#         ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
#         ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
#     ]
    
#     # Identifier les lignes d'en-tête couleur pour les mettre en gras
#     row_idx = 1
#     for couleur_nom in sorted(series_par_couleur.keys()):
#         groupe = series_par_couleur[couleur_nom]
        
#         # Ligne header couleur
#         style_list.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#e2e8f0')))
#         style_list.append(('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold'))
#         style_list.append(('SPAN', (0, row_idx), (len(headers)-3, row_idx)))
        
#         # Passer les lignes de détail
#         nb_series_affichees = min(len(groupe['series']), 20)
#         row_idx += nb_series_affichees + 1
        
#         if len(groupe['series']) > 20:
#             row_idx += 1
    
#     table.setStyle(TableStyle(style_list))
    
#     elements.append(table)
    
#     return elements