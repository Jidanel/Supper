# inventaire/views_transferts.py
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from decimal import Decimal
from datetime import datetime
from django.db.models import Sum, Avg, Count, Q

from accounts.models import Poste, NotificationUtilisateur
from inventaire.models import *
from common.utils import log_user_action
import logging

logger = logging.getLogger('supper')

def is_admin(user):
    return user.is_authenticated and (
        user.is_superuser or 
        user.is_staff or
        (hasattr(user, 'is_admin') and user.is_admin())
    )

@login_required
@user_passes_test(is_admin)
def selection_transfert_stock(request):
    """Sélection des postes pour le transfert"""
    
    postes = Poste.objects.filter(is_active=True).order_by('nom')
    
    # Récupérer les stocks actuels
    postes_data = []
    for poste in postes:
        stock = GestionStock.objects.filter(poste=poste).first()
        postes_data.append({
            'poste': poste,
            'stock_actuel': stock.valeur_monetaire if stock else Decimal('0'),
            'tickets_actuels': stock.nombre_tickets if stock else 0
        })
    
    if request.method == 'POST':
        poste_origine_id = request.POST.get('poste_origine_id')
        poste_destination_id = request.POST.get('poste_destination_id')
        
        if not poste_origine_id or not poste_destination_id:
            messages.error(request, "Veuillez sélectionner les deux postes")
            return redirect('inventaire:selection_transfert_stock')
        
        if poste_origine_id == poste_destination_id:
            messages.error(request, "Les postes d'origine et de destination doivent être différents")
            return redirect('inventaire:selection_transfert_stock')
        
        return redirect('inventaire:formulaire_transfert_stock', 
                       origine_id=poste_origine_id,
                       destination_id=poste_destination_id)
    
    context = {
        'postes': postes_data,
        'title': 'Transférer du Stock Entre Postes'
    }
    
    return render(request, 'inventaire/selection_transfert_stock.html', context)


@login_required
@user_passes_test(is_admin)
def formulaire_transfert_stock(request, origine_id, destination_id):
    """Formulaire de saisie du montant à transférer"""
    
    poste_origine = get_object_or_404(Poste, id=origine_id)
    poste_destination = get_object_or_404(Poste, id=destination_id)
    
    # Récupérer le stock de l'origine
    stock_origine, _ = GestionStock.objects.get_or_create(
        poste=poste_origine,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    stock_destination, _ = GestionStock.objects.get_or_create(
        poste=poste_destination,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    if request.method == 'POST':
        try:
            montant = Decimal(request.POST.get('montant', '0'))
            commentaire = request.POST.get('commentaire', '')
            
            # Validations
            if montant <= 0:
                messages.error(request, "Le montant doit être positif")
                return redirect('inventaire:formulaire_transfert_stock', 
                              origine_id=origine_id, 
                              destination_id=destination_id)
            
            if montant > stock_origine.valeur_monetaire:
                messages.error(request, 
                             f"Stock insuffisant. Disponible : {stock_origine.valeur_monetaire:,.0f} FCFA")
                return redirect('inventaire:formulaire_transfert_stock', 
                              origine_id=origine_id, 
                              destination_id=destination_id)
            
            # Stocker en session pour confirmation
            request.session['transfert_stock'] = {
                'origine_id': origine_id,
                'destination_id': destination_id,
                'montant': str(montant),
                'commentaire': commentaire
            }
            
            return redirect('inventaire:confirmation_transfert_stock')
            
        except Exception as e:
            messages.error(request, f"Erreur : {str(e)}")
            return redirect('inventaire:formulaire_transfert_stock', 
                          origine_id=origine_id, 
                          destination_id=destination_id)
    
    context = {
        'poste_origine': poste_origine,
        'poste_destination': poste_destination,
        'stock_origine': stock_origine,
        'stock_destination': stock_destination,
        'title': 'Formulaire de Transfert'
    }
    
    return render(request, 'inventaire/formulaire_transfert_stock.html', context)



@login_required
@user_passes_test(is_admin)
def confirmation_transfert_stock(request):
    """
    ✅ VERSION AMÉLIORÉE : Meilleure gestion de la redirection
    """
    transfert_data = request.session.get('transfert_stock')
    
    if not transfert_data:
        messages.error(request, "Aucune donnée de transfert en attente")
        return redirect('inventaire:selection_transfert_stock')
    
    poste_origine = get_object_or_404(Poste, id=transfert_data['origine_id'])
    poste_destination = get_object_or_404(Poste, id=transfert_data['destination_id'])
    montant = Decimal(transfert_data['montant'])
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirmer':
            try:
                logger.info(f"DEBUT TRANSFERT : {montant} FCFA de {poste_origine.code} vers {poste_destination.code}")
                
                with transaction.atomic():
                    numero_bordereau = generer_numero_bordereau()
                    logger.info(f"Bordereau généré : {numero_bordereau}")
                    
                    hist_origine, hist_destination = executer_transfert_stock(
                        poste_origine,
                        poste_destination,
                        montant,
                        request.user,
                        transfert_data['commentaire'],
                        numero_bordereau
                    )
                    
                    logger.info(f"Transaction OK - Hist Origine: {hist_origine.id}, Hist Dest: {hist_destination.id}")
                
                # ✅ NOUVEAU : Nettoyer la session ET rediriger vers page de succès
                if 'transfert_stock' in request.session:
                    del request.session['transfert_stock']
                
                messages.success(
                    request, 
                    f"✅ Transfert réussi ! {montant:,.0f} FCFA transférés. Bordereau N°{numero_bordereau}"
                )
                
                # ✅ CORRECTION : Redirection vers une page de succès avec liens bordereaux
                return redirect('inventaire:detail_transfert_succes', numero_bordereau=numero_bordereau)
                
            except ValueError as ve:
                logger.error(f"Erreur validation : {str(ve)}")
                messages.error(request, f"❌ Validation : {str(ve)}")
                return redirect('inventaire:formulaire_transfert_stock', 
                              origine_id=poste_origine.id, 
                              destination_id=poste_destination.id)
            
            except Exception as e:
                logger.error(f"Erreur transfert : {str(e)}", exc_info=True)
                messages.error(request, f"❌ Erreur : {str(e)}")
                return redirect('inventaire:selection_transfert_stock')
        
        elif action == 'annuler':
            if 'transfert_stock' in request.session:
                del request.session['transfert_stock']
            messages.info(request, "Transfert annulé")
            return redirect('inventaire:selection_transfert_stock')
    
    context = {
        'poste_origine': poste_origine,
        'poste_destination': poste_destination,
        'montant': montant,
        'nombre_tickets': int(montant / 500),
        'commentaire': transfert_data['commentaire'],
        'title': 'Confirmation du Transfert'
    }
    
    return render(request, 'inventaire/confirmation_transfert_stock.html', context)



@login_required
@user_passes_test(is_admin)
def detail_transfert_succes(request, numero_bordereau):
    """
    ✅ NOUVELLE PAGE : Affiche les détails du transfert avec liens de téléchargement
    """
    # Récupérer les deux historiques
    hist_cession = get_object_or_404(
        HistoriqueStock,
        numero_bordereau=numero_bordereau,
        type_mouvement='DEBIT'
    )
    
    hist_reception = HistoriqueStock.objects.filter(
        numero_bordereau=numero_bordereau,
        type_mouvement='CREDIT'
    ).first()
    
    context = {
        'numero_bordereau': numero_bordereau,
        'hist_cession': hist_cession,
        'hist_reception': hist_reception,
        'poste_origine': hist_cession.poste_origine,
        'poste_destination': hist_cession.poste_destination,
        'montant': hist_cession.montant,
        'nombre_tickets': hist_cession.nombre_tickets,
        'title': 'Transfert Réussi'
    }
    
    return render(request, 'inventaire/detail_transfert_succes.html', context)

# ===== MODIFICATIONS À APPORTER DANS inventaire/views_transferts.py =====

# 1. AJOUTER ces imports au début du fichier :
from inventaire.models import StockEvent
from datetime import datetime


# 2. REMPLACER la fonction executer_transfert_stock (environ ligne 200-300)
# par cette version modifiée :

def executer_transfert_stock(poste_origine, poste_destination, montant, 
                            user, commentaire, numero_bordereau):
    """
    VERSION MODIFIÉE avec Event Sourcing
    Exécute le transfert de stock entre deux postes
    """
    
    # CORRECTION : Utiliser get_or_create au lieu de get
    stock_origine, created_origine = GestionStock.objects.select_for_update().get_or_create(
        poste=poste_origine,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    stock_destination, created_dest = GestionStock.objects.select_for_update().get_or_create(
        poste=poste_destination,
        defaults={'valeur_monetaire': Decimal('0')}
    )
    
    # Vérification finale du stock disponible
    if stock_origine.valeur_monetaire < montant:
        raise ValueError(f"Stock insuffisant à l'origine. Disponible: {stock_origine.valeur_monetaire}, Demandé: {montant}")
    
    nombre_tickets = int(montant / 500)
    
    # Sauvegarder les états avant
    stock_origine_avant = stock_origine.valeur_monetaire
    stock_destination_avant = stock_destination.valeur_monetaire
    
    # Mettre à jour les stocks
    stock_origine.valeur_monetaire -= montant
    stock_origine.save()
    
    stock_destination.valeur_monetaire += montant
    stock_destination.save()
    
    # LOG pour débogage
    logger.info(f"TRANSFERT STOCK - Origine {poste_origine.code}: {stock_origine_avant} -> {stock_origine.valeur_monetaire}")
    logger.info(f"TRANSFERT STOCK - Destination {poste_destination.code}: {stock_destination_avant} -> {stock_destination.valeur_monetaire}")
    
    # ===== NOUVEAU CODE EVENT SOURCING =====
    timestamp = timezone.now()
    
    # Créer l'événement de SORTIE pour le poste origine
    StockEvent.objects.create(
        poste=poste_origine,
        event_type='TRANSFERT_OUT',
        event_datetime=timestamp,
        montant_variation=-montant,  # NÉGATIF car sortie
        nombre_tickets_variation=-nombre_tickets,
        stock_resultant=stock_origine.valeur_monetaire,
        tickets_resultants=int(stock_origine.valeur_monetaire / 500),
        effectue_par=user,
        metadata={
            'poste_destination': {
                'id': poste_destination.id,
                'nom': poste_destination.nom,
                'code': poste_destination.code
            },
            'numero_bordereau': numero_bordereau,
            'type_operation': 'cession'
        },
        commentaire=f"Transfert vers {poste_destination.nom} - {commentaire}"
    )
    
    # Créer l'événement d'ENTRÉE pour le poste destination
    StockEvent.objects.create(
        poste=poste_destination,
        event_type='TRANSFERT_IN',
        event_datetime=timestamp,
        montant_variation=montant,  # POSITIF car entrée
        nombre_tickets_variation=nombre_tickets,
        stock_resultant=stock_destination.valeur_monetaire,
        tickets_resultants=int(stock_destination.valeur_monetaire / 500),
        effectue_par=user,
        metadata={
            'poste_origine': {
                'id': poste_origine.id,
                'nom': poste_origine.nom,
                'code': poste_origine.code
            },
            'numero_bordereau': numero_bordereau,
            'type_operation': 'reception'
        },
        commentaire=f"Transfert depuis {poste_origine.nom} - {commentaire}"
    )
    # ===== FIN NOUVEAU CODE =====
    
    # Créer l'historique pour le poste ORIGINE (CODE EXISTANT - garder)
    hist_origine = HistoriqueStock.objects.create(
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
        commentaire=f"{commentaire}"
    )
    
    logger.info(f"Historique ORIGINE créé - ID: {hist_origine.id}, Bordereau: {hist_origine.numero_bordereau}")
    
    # Créer l'historique pour le poste DESTINATION (CODE EXISTANT - garder)
    hist_destination = HistoriqueStock.objects.create(
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
        commentaire=f"{commentaire}"
    )
    
    logger.info(f"Historique DESTINATION créé - ID: {hist_destination.id}, Bordereau: {hist_destination.numero_bordereau}")
    
    # RESTE DU CODE EXISTANT (notifications, etc.) - GARDER TEL QUEL
    # Notifier les chefs de poste concernés
    from accounts.models import UtilisateurSUPPER
    
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
            titre="Stock cédé à un autre poste",
            message=f"Votre stock a été réduit de {montant:,.0f} FCFA ({nombre_tickets} tickets) au profit de {poste_destination.nom}. Bordereau N°{numero_bordereau}",
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
            titre="Nouveau stock reçu",
            message=f"Votre stock a été augmenté de {montant:,.0f} FCFA ({nombre_tickets} tickets) en provenance de {poste_origine.nom}. Bordereau N°{numero_bordereau}",
            type_notification='success'
        )
    
    # Journaliser l'action
    log_user_action(
        user,
        "Transfert de stock inter-postes",
        f"Transfert : {montant:,.0f} FCFA de {poste_origine.nom} vers {poste_destination.nom}. Bordereau N°{numero_bordereau}",
        None
    )
    
    logger.info(f"Transfert stock TERMINÉ avec succès - Bordereau {numero_bordereau}")
    
    return hist_origine, hist_destination

def generer_numero_bordereau():
    """Génère un numéro unique de bordereau de transfert"""
    from datetime import datetime
    
    # Format : TR-YYYYMMDD-HHMMSS-XXX
    now = datetime.now()
    
    # Compter les transferts du jour
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    count_today = HistoriqueStock.objects.filter(
        type_stock='reapprovisionnement',
        date_mouvement__gte=today_start
    ).count()
    
    numero = f"TR-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}-{count_today+1:03d}"
    
    return numero


@login_required
def bordereaux_transfert(request, numero_bordereau):
    """
    ✅ VERSION CORRIGÉE : Détection automatique du type de bordereau
    
    Génère DEUX PDF (cession + réception) ou UN seul selon le paramètre GET
    """
    from django.shortcuts import get_object_or_404, render
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.enums import TA_CENTER
    from datetime import datetime
    from decimal import Decimal
    
    # ========== RÉCUPÉRER LE TYPE DEMANDÉ (ou par défaut 'cession') ==========
    type_bordereau = request.GET.get('type', 'cession')
    
    # Validation du type
    if type_bordereau not in ['cession', 'reception']:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("Type de bordereau invalide. Utilisez 'cession' ou 'reception'")
    
    # ========== RÉCUPÉRER L'HISTORIQUE SELON LE TYPE ==========
    try:
        if type_bordereau == 'cession':
            hist = HistoriqueStock.objects.select_related(
                'poste', 'poste_origine', 'poste_destination', 'effectue_par'
            ).get(
                numero_bordereau=numero_bordereau,
                type_mouvement='DEBIT'
            )
        else:
            hist = HistoriqueStock.objects.select_related(
                'poste', 'poste_origine', 'poste_destination', 'effectue_par'
            ).get(
                numero_bordereau=numero_bordereau,
                type_mouvement='CREDIT'
            )
    except HistoriqueStock.DoesNotExist:
        from django.http import Http404
        raise Http404(f"Bordereau {numero_bordereau} ({type_bordereau}) introuvable")
    
    # ========== CONTRÔLE D'ACCÈS ==========
    if not request.user.is_admin:
        if not request.user.poste_affectation or \
           request.user.poste_affectation not in [hist.poste_origine, hist.poste_destination]:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Vous n'avez pas accès à ce bordereau")
    
    # ========== RÉCUPÉRER LES SÉRIES TRANSFÉRÉES ==========
    if type_bordereau == 'cession':
        series_transferees = SerieTicket.objects.filter(
            poste=hist.poste_origine,
            statut='transfere',
            poste_destination_transfert=hist.poste_destination,
            date_utilisation=hist.date_mouvement.date()
        ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
    else:
        series_transferees = SerieTicket.objects.filter(
            poste=hist.poste_destination,
            type_entree='transfert_recu',
            date_reception__date=hist.date_mouvement.date()
        ).select_related('couleur').order_by('couleur__code_normalise', 'numero_premier')
    
    # Grouper par couleur
    series_par_couleur = {}
    for serie in series_transferees:
        couleur_key = serie.couleur.libelle_affichage
        if couleur_key not in series_par_couleur:
            series_par_couleur[couleur_key] = {
                'couleur': serie.couleur,
                'series': [],
                'total_tickets': 0,
                'valeur_totale': Decimal('0')
            }
        
        series_par_couleur[couleur_key]['series'].append(serie)
        series_par_couleur[couleur_key]['total_tickets'] += serie.nombre_tickets
        series_par_couleur[couleur_key]['valeur_totale'] += serie.valeur_monetaire
    
    # ========== GÉNÉRER LE PDF ==========
    response = HttpResponse(content_type='application/pdf')
    filename = f'bordereau_{type_bordereau}_{numero_bordereau}.pdf'
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    
    doc = SimpleDocTemplate(
        response, 
        pagesize=A4,
        rightMargin=2*cm, 
        leftMargin=2*cm,
        topMargin=2*cm, 
        bottomMargin=2*cm
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Récupérer la config globale
    from inventaire.models import ConfigurationGlobale
    config = ConfigurationGlobale.get_config()
    
    # ========== EN-TÊTE ==========
    from inventaire.views_rapports import creer_entete_bilingue
    poste_concerne = hist.poste_origine if type_bordereau == 'cession' else hist.poste_destination
    elements.append(creer_entete_bilingue(config, poste_concerne))
    elements.append(Spacer(1, 1*cm))
    
    # ========== TITRE ==========
    titre_style = ParagraphStyle(
        'Titre',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#d32f2f' if type_bordereau == 'cession' else '#388e3c'),
        alignment=TA_CENTER,
        spaceAfter=20
    )
    
    titre_text = (
        "BORDEREAU DE CESSION DE TICKETS" 
        if type_bordereau == 'cession' 
        else "BORDEREAU DE RÉCEPTION DE TICKETS"
    )
    elements.append(Paragraph(titre_text, titre_style))
    elements.append(Spacer(1, 0.5*cm))
    
    # ========== INFORMATIONS GÉNÉRALES ==========
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
        ['MONTANT TOTAL TRANSFÉRÉ:', f"{hist.montant:,.0f} FCFA".replace(',', ' ')],
        ['NOMBRE TOTAL DE TICKETS:', f"{hist.nombre_tickets} tickets"],
    ])
    
    table = Table(data, colWidths=[6*cm, 10*cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(table)
    elements.append(Spacer(1, 0.5*cm))
    
    # ========== DÉTAIL DES SÉRIES ==========
    titre_series = ParagraphStyle(
        'TitreSeries',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=10
    )
    
    elements.append(Paragraph("DÉTAIL DES SÉRIES TRANSFÉRÉES", titre_series))
    
    if series_par_couleur:
        for couleur_nom, groupe in series_par_couleur.items():
            couleur_header = [[
                Paragraph(f"<b>Couleur : {couleur_nom}</b>", styles['Normal']),
                f"Total: {groupe['total_tickets']} tickets",
                f"{groupe['valeur_totale']:,.0f} FCFA".replace(',', ' ')
            ]]
            
            for serie in groupe['series']:
                couleur_header.append([
                    f"Série #{serie.numero_premier} → #{serie.numero_dernier}",
                    f"{serie.nombre_tickets} tickets",
                    f"{serie.valeur_monetaire:,.0f} FCFA".replace(',', ' ')
                ])
            
            serie_table = Table(couleur_header, colWidths=[7*cm, 4*cm, 5*cm])
            serie_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            
            elements.append(serie_table)
            elements.append(Spacer(1, 0.3*cm))
    
    elements.append(Spacer(1, 0.5*cm))
    
    # ========== ÉTAT DES STOCKS ==========
    elements.append(Paragraph("ÉTAT DES STOCKS", titre_series))
    
    stock_data = [
        ['STOCK AVANT:', f"{hist.stock_avant:,.0f} FCFA".replace(',', ' ')],
        ['STOCK APRÈS:', f"{hist.stock_apres:,.0f} FCFA".replace(',', ' ')],
        ['EFFECTUÉ PAR:', hist.effectue_par.nom_complet],
    ]
    
    if hist.commentaire:
        stock_data.append(['COMMENTAIRE:', hist.commentaire[:100]])
    
    stock_table = Table(stock_data, colWidths=[6*cm, 10*cm])
    stock_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    
    elements.append(stock_table)
    elements.append(Spacer(1, 1.5*cm))
    
    # ========== SIGNATURES ==========
    signature_data = [
        ['LE CHEF ÉMETTEUR', 'LE CHEF DESTINATAIRE', 'L\'ADMINISTRATEUR'],
        ['', '', ''],
        ['_________________', '_________________', '_________________'],
        [hist.poste_origine.nom, hist.poste_destination.nom, hist.effectue_par.nom_complet]
    ]
    
    sig_table = Table(signature_data, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    sig_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    
    elements.append(sig_table)
    
    # Générer le PDF
    doc.build(elements)
    
    return response

@login_required
def liste_bordereaux(request):
    """
    Liste de tous les bordereaux de transfert
    Admin : tous les bordereaux
    Chef : uniquement les bordereaux de son poste
    """
    
    # Récupérer tous les transferts (un par bordereau)
    bordereaux = HistoriqueStock.objects.filter(
        type_stock='reapprovisionnement',
        type_mouvement='DEBIT'  # On prend uniquement les cessions pour éviter les doublons
    ).select_related('poste', 'poste_origine', 'poste_destination', 'effectue_par')
    
    # Filtrer selon les permissions
    if not request.user.is_admin:
        if request.user.poste_affectation:
            # Chef de poste : voir les transferts qui concernent son poste
            bordereaux = bordereaux.filter(
                Q(poste_origine=request.user.poste_affectation) |
                Q(poste_destination=request.user.poste_affectation)
            )
        else:
            bordereaux = HistoriqueStock.objects.none()
    
    # Filtres
    poste_filter = request.GET.get('poste')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')
    
    if poste_filter:
        bordereaux = bordereaux.filter(
            Q(poste_origine_id=poste_filter) | Q(poste_destination_id=poste_filter)
        )
    
    if date_debut:
        bordereaux = bordereaux.filter(date_mouvement__gte=date_debut)
    
    if date_fin:
        bordereaux = bordereaux.filter(date_mouvement__lte=date_fin)
    
    bordereaux = bordereaux.order_by('-date_mouvement')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(bordereaux, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Statistiques
    stats = bordereaux.aggregate(
        total_transferts=Count('id'),
        montant_total=Sum('montant')
    )
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
        'postes': Poste.objects.filter(is_active=True).order_by('nom'),
        'filters': {
            'poste': poste_filter,
            'date_debut': date_debut,
            'date_fin': date_fin
        },
        'title': 'Liste des Bordereaux de Transfert'
    }
    
    return render(request, 'inventaire/liste_bordereaux.html', context)