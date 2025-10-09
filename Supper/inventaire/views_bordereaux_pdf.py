# inventaire/views_bordereaux_pdf.py
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER
from datetime import datetime

from inventaire.models import HistoriqueStock
from inventaire.models_config import ConfigurationGlobale

@login_required
def bordereau_transfert_pdf(request, numero_bordereau, type_bordereau):
    """
    Génère le PDF du bordereau (cession ou reception)
    type_bordereau: 'cession' ou 'reception'
    """
    
    # Récupérer l'historique
    if type_bordereau == 'cession':
        hist = get_object_or_404(
            HistoriqueStock,
            numero_bordereau=numero_bordereau,
            type_mouvement='DEBIT'
        )
    else:
        hist = get_object_or_404(
            HistoriqueStock,
            numero_bordereau=numero_bordereau,
            type_mouvement='CREDIT'
        )
    
    # Contrôle d'accès
    if not request.user.is_admin:
        if not request.user.poste_affectation or \
           request.user.poste_affectation not in [hist.poste_origine, hist.poste_destination]:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Accès non autorisé")
    
    # Créer la réponse PDF
    response = HttpResponse(content_type='application/pdf')
    filename = f'bordereau_{type_bordereau}_{numero_bordereau}.pdf'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    
    # Créer le document
    doc = SimpleDocTemplate(response, pagesize=A4, 
                           rightMargin=2*cm, leftMargin=2*cm,
                           topMargin=2*cm, bottomMargin=2*cm)
    
    elements = []
    styles = getSampleStyleSheet()
    config = ConfigurationGlobale.get_config()
    
    # En-tête
    from inventaire.views_rapports import creer_entete_bilingue
    poste_concerne = hist.poste_origine if type_bordereau == 'cession' else hist.poste_destination
    elements.append(creer_entete_bilingue(config, poste_concerne))
    elements.append(Spacer(1, 1*cm))
    
    # Titre
    titre_style = ParagraphStyle(
        'Titre',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#d32f2f' if type_bordereau == 'cession' else '#388e3c'),
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    titre_text = "CESSION DE TICKETS" if type_bordereau == 'cession' else "APPROVISIONNEMENT DE TICKETS"
    elements.append(Paragraph(titre_text, titre_style))
    elements.append(Spacer(1, 0.5*cm))
    
    # Informations du bordereau
    data = [
        ['N° Bordereau:', numero_bordereau],
        ['Date et Heure:', hist.date_mouvement.strftime('%d/%m/%Y à %H:%M')],
        ['', ''],
    ]
    
    if type_bordereau == 'cession':
        data.extend([
            ['POSTE ÉMETTEUR (CÈDE):', f"{hist.poste_origine.nom} ({hist.poste_origine.code})"],
            ['POSTE DESTINATAIRE:', f"{hist.poste_destination.nom} ({hist.poste_destination.code})"],
        ])
    else:
        data.extend([
            ['POSTE BÉNÉFICIAIRE (REÇOIT):', f"{hist.poste_destination.nom} ({hist.poste_destination.code})"],
            ['POSTE ÉMETTEUR:', f"{hist.poste_origine.nom} ({hist.poste_origine.code})"],
        ])
    
    data.extend([
        ['', ''],
        ['MONTANT TRANSFÉRÉ:', f"{hist.montant:,.0f} FCFA".replace(',', ' ')],
        ['NOMBRE DE TICKETS:', f"{hist.nombre_tickets} tickets"],
        ['', ''],
        ['STOCK AVANT OPÉRATION:', f"{hist.stock_avant:,.0f} FCFA".replace(',', ' ')],
        ['STOCK APRÈS OPÉRATION:', f"{hist.stock_apres:,.0f} FCFA".replace(',', ' ')],
        ['', ''],
        ['EFFECTUÉ PAR:', hist.effectue_par.nom_complet],
    ])
    
    if hist.commentaire:
        data.append(['COMMENTAIRE:', hist.commentaire[:100]])
    
    table = Table(data, colWidths=[6*cm, 10*cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1a1a1a')),
        ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#333333')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e3f2fd')),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 2*cm))
    
    # Signatures
    signature_data = [
        ['LE CHEF DE POSTE ÉMETTEUR', 'LE CHEF DE POSTE DESTINATAIRE', 'L\'ADMINISTRATEUR'],
        ['', '', ''],
        ['', '', ''],
        ['_______________________', '_______________________', '_______________________'],
        [f"{hist.poste_origine.nom}", f"{hist.poste_destination.nom}", f"{hist.effectue_par.nom_complet}"]
    ]
    
    sig_table = Table(signature_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    sig_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    elements.append(sig_table)
    elements.append(Spacer(1, 1*cm))
    
    # Pied de page
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    
    footer_text = f"Document généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} par SUPPER - Utilisateur: {request.user.nom_complet}"
    elements.append(Paragraph(footer_text, footer_style))
    
    # Générer le PDF
    doc.build(elements)
    
    return response