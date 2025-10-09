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
from inventaire.models import GestionStock, HistoriqueStock, RecetteJournaliere
from inventaire.models_config import ConfigurationGlobale

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
    """Sélection du poste et du mois pour le compte d'emploi"""
    
    # Vérifier les permissions
    if not (request.user.is_admin or request.user.is_chef_poste):
        messages.error(request, "Accès non autorisé")
        return redirect('common:dashboard')
    
    # Calculer les mois disponibles
    today = date.today()
    
    # Règle : disponible à partir du 2 du mois
    if today.day >= 2:
        mois_actuel_disponible = True
    else:
        mois_actuel_disponible = False
    
    # Générer liste des mois disponibles (12 derniers mois max)
    mois_disponibles = []
    for i in range(12):
        if i == 0 and not mois_actuel_disponible:
            continue
        
        date_mois = today.replace(day=1) - timedelta(days=i*30)
        date_mois = date_mois.replace(day=1)
        
        if date_mois > today:
            continue
        
        mois_disponibles.append({
            'valeur': f"{date_mois.year}-{date_mois.month:02d}",
            'affichage': f"{calendar.month_name[date_mois.month]} {date_mois.year}"
        })
    
    # Postes accessibles
    if request.user.is_admin:
        postes = Poste.objects.filter(is_active=True).order_by('nom')
    else:
        postes = [request.user.poste_affectation] if request.user.poste_affectation else []
    
    if request.method == 'POST':
        poste_id = request.POST.get('poste_id')
        mois_selection = request.POST.get('mois')
        
        if not poste_id or not mois_selection:
            messages.error(request, "Veuillez sélectionner un poste et un mois")
        else:
            return redirect('inventaire:generer_compte_emploi', 
                          poste_id=poste_id, 
                          mois=mois_selection)
    
    context = {
        'postes': postes,
        'mois_disponibles': mois_disponibles,
        'title': "Compte d'Emploi des Tickets"
    }
    
    return render(request, 'inventaire/selection_compte_emploi.html', context)


@login_required
def generer_compte_emploi_pdf(request, poste_id, mois):
    """Génère le PDF du compte d'emploi"""
    
    poste = get_object_or_404(Poste, id=poste_id)
    
    # Vérifier les permissions
    if not request.user.is_admin:
        if not request.user.poste_affectation or request.user.poste_affectation != poste:
            messages.error(request, "Accès non autorisé")
            return redirect('inventaire:selection_compte_emploi')
    
    # Parser le mois
    try:
        annee, mois_num = map(int, mois.split('-'))
        date_debut = date(annee, mois_num, 1)
        dernier_jour = calendar.monthrange(annee, mois_num)[1]
        date_fin = date(annee, mois_num, dernier_jour)
    except:
        messages.error(request, "Format de mois invalide")
        return redirect('inventaire:selection_compte_emploi')
    
    # Vérifier que le mois est disponible
    today = date.today()
    if date_debut > today or (date_debut.month == today.month and today.day < 2):
        messages.error(request, "Ce mois n'est pas encore disponible pour impression")
        return redirect('inventaire:selection_compte_emploi')
    
    # Récupérer la configuration
    config = ConfigurationGlobale.get_config()
    
    # Calculer les données du compte d'emploi
    donnees = calculer_donnees_compte_emploi(poste, date_debut, date_fin)
    
    # Générer le PDF
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="compte_emploi_{poste.code}_{mois}.pdf"'
    
    # ✅ Créer le PDF en paysage (landscape déjà importé en haut)
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
    
    # En-tête bilingue
    elements.append(creer_entete_bilingue(config, poste))
    elements.append(Spacer(1, 0.5*cm))
    
    # Titre du document
    titre_style = ParagraphStyle(
        'TitreCompte',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=colors.HexColor('#1a1a1a'),
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    # Noms des mois
    mois_noms_fr = {
        1: 'JANVIER', 2: 'FÉVRIER', 3: 'MARS', 4: 'AVRIL',
        5: 'MAI', 6: 'JUIN', 7: 'JUILLET', 8: 'AOÛT',
        9: 'SEPTEMBRE', 10: 'OCTOBRE', 11: 'NOVEMBRE', 12: 'DÉCEMBRE'
    }
    
    mois_abrege = {
        1: 'JAN', 2: 'FEV', 3: 'MAR', 4: 'AVR',
        5: 'MAI', 6: 'JUN', 7: 'JUL', 8: 'AOU',
        9: 'SEP', 10: 'OCT', 11: 'NOV', 12: 'DEC'
    }
    
    titre = Paragraph(
        f"COMPTE D'EMPLOI DES TICKETS DU MOIS DE {mois_noms_fr[mois_num]} {annee}",
        titre_style
    )
    elements.append(titre)
    elements.append(Spacer(1, 0.3*cm))
    
    # Tableau avec toutes les colonnes (y compris réapprovisionnements)
    table_data = [
        ['MOIS', 'STOCK DEBUT', '', 'APPROV IMP.NAT', '', 'REAPPROV REÇU', '', 'REAPPROV CÉDÉ', '', 'VENTE', '', 'STOCK FINAL(RESTANT)', ''],
        ['', 'Qté', 'valeur', 'Qté', 'valeur', 'Qté', 'valeur', 'Qté', 'valeur', 'Qté', 'valeur', 'Qté', 'valeur'],
        [
            mois_abrege[mois_num],
            str(donnees['stock_debut_qte']),
            f"{donnees['stock_debut_valeur']:,.0f}".replace(',', '.'),
            str(donnees['approv_imprimerie_qte']),
            f"{donnees['approv_imprimerie_valeur']:,.0f}".replace(',', '.'),
            str(donnees['reapprov_recu_qte']),
            f"{donnees['reapprov_recu_valeur']:,.0f}".replace(',', '.'),
            str(donnees['reapprov_cede_qte']),
            f"{donnees['reapprov_cede_valeur']:,.0f}".replace(',', '.'),
            str(donnees['vente_qte']),
            f"{donnees['vente_valeur']:,.0f}".replace(',', '.'),
            str(donnees['stock_final_qte']),
            f"{donnees['stock_final_valeur']:,.0f}".replace(',', '.')
        ],
        [
            'TOTAL',
            str(donnees['stock_debut_qte']),
            f"{donnees['stock_debut_valeur']:,.0f}".replace(',', '.'),
            str(donnees['approv_imprimerie_qte']),
            f"{donnees['approv_imprimerie_valeur']:,.0f}".replace(',', '.'),
            str(donnees['reapprov_recu_qte']),
            f"{donnees['reapprov_recu_valeur']:,.0f}".replace(',', '.'),
            str(donnees['reapprov_cede_qte']),
            f"{donnees['reapprov_cede_valeur']:,.0f}".replace(',', '.'),
            str(donnees['vente_qte']),
            f"{donnees['vente_valeur']:,.0f}".replace(',', '.'),
            str(donnees['stock_final_qte']),
            f"{donnees['stock_final_valeur']:,.0f}".replace(',', '.')
        ]
    ]

    # Largeurs des colonnes ajustées
    col_widths = [1.2*cm, 1.3*cm, 2*cm, 1.3*cm, 2*cm, 1.3*cm, 2*cm, 1.3*cm, 2*cm, 1.3*cm, 2*cm, 1.3*cm, 2*cm]

    table = Table(table_data, colWidths=col_widths)

    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a5568')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 7),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#e2e8f0')),
        ('FONTSIZE', (0, 1), (-1, -1), 7),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#cbd5e0')),
        ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('SPAN', (0, 0), (0, 1)),  # MOIS
        ('SPAN', (1, 0), (2, 0)),  # STOCK DEBUT
        ('SPAN', (3, 0), (4, 0)),  # APPROV IMP.NAT
        ('SPAN', (5, 0), (6, 0)),  # REAPPROV REÇU
        ('SPAN', (7, 0), (8, 0)),  # REAPPROV CÉDÉ
        ('SPAN', (9, 0), (10, 0)), # VENTE
        ('SPAN', (11, 0), (12, 0)), # STOCK FINAL
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 0.5*cm))
    
    # Pied de page
    elements.append(creer_pied_page(poste, config, request.user))
    
    # ✅ Générer le PDF
    doc.build(elements)
    
    return response

def calculer_donnees_compte_emploi(poste, date_debut, date_fin):
    """
    Calcule toutes les données nécessaires pour le compte d'emploi
    MISE À JOUR : Inclut maintenant les réapprovisionnements inter-postes
    """
    
    # Stock début
    stock_debut_hist = HistoriqueStock.objects.filter(
        poste=poste,
        date_mouvement__lt=date_debut
    ).order_by('-date_mouvement').first()
    
    stock_debut_valeur = stock_debut_hist.stock_apres if stock_debut_hist else Decimal('0')
    stock_debut_qte = int(stock_debut_valeur / 500)
    
    # Approvisionnements Imprimerie Nationale (CREDIT imprimerie_nationale)
    approvs_imprimerie = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='CREDIT',
        type_stock='imprimerie_nationale',
        date_mouvement__range=[date_debut, date_fin]
    ).aggregate(total=Sum('montant'))
    
    approv_imprimerie_valeur = approvs_imprimerie['total'] or Decimal('0')
    approv_imprimerie_qte = int(approv_imprimerie_valeur / 500)
    
    # NOUVEAU : Réapprovisionnements REÇUS (CREDIT reapprovisionnement)
    reapprovs_recus = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='CREDIT',
        type_stock='reapprovisionnement',
        date_mouvement__range=[date_debut, date_fin]
    ).aggregate(total=Sum('montant'))
    
    reapprov_recu_valeur = reapprovs_recus['total'] or Decimal('0')
    reapprov_recu_qte = int(reapprov_recu_valeur / 500)
    
    # NOUVEAU : Réapprovisionnements CÉDÉS (DEBIT reapprovisionnement)
    reapprovs_cedes = HistoriqueStock.objects.filter(
        poste=poste,
        type_mouvement='DEBIT',
        type_stock='reapprovisionnement',
        date_mouvement__range=[date_debut, date_fin]
    ).aggregate(total=Sum('montant'))
    
    reapprov_cede_valeur = reapprovs_cedes['total'] or Decimal('0')
    reapprov_cede_qte = int(reapprov_cede_valeur / 500)
    
    # Ventes du mois
    ventes = RecetteJournaliere.objects.filter(
        poste=poste,
        date__range=[date_debut, date_fin]
    ).aggregate(total=Sum('montant_declare'))
    
    vente_valeur = ventes['total'] or Decimal('0')
    vente_qte = int(vente_valeur / 500)
    
    # CALCUL DU STOCK FINAL
    # Stock final = stock début + approv imprimerie + reapprov reçu - reapprov cédé - vente
    stock_final_valeur = (
        stock_debut_valeur + 
        approv_imprimerie_valeur + 
        reapprov_recu_valeur - 
        reapprov_cede_valeur - 
        vente_valeur
    )
    stock_final_qte = (
        stock_debut_qte + 
        approv_imprimerie_qte + 
        reapprov_recu_qte - 
        reapprov_cede_qte - 
        vente_qte
    )
    
    return {
        'stock_debut_qte': stock_debut_qte,
        'stock_debut_valeur': stock_debut_valeur,
        'approv_imprimerie_qte': approv_imprimerie_qte,
        'approv_imprimerie_valeur': approv_imprimerie_valeur,
        'reapprov_recu_qte': reapprov_recu_qte,
        'reapprov_recu_valeur': reapprov_recu_valeur,
        'reapprov_cede_qte': reapprov_cede_qte,
        'reapprov_cede_valeur': reapprov_cede_valeur,
        'vente_qte': vente_qte,
        'vente_valeur': vente_valeur,
        'stock_final_qte': stock_final_qte,
        'stock_final_valeur': stock_final_valeur
    }

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