# ===================================================================
# inventaire/views_annulation_transfert.py - ANNULATION DE TRANSFERT
# Application SUPPER - Suivi des Péages et Pesages Routiers
# Chemin: inventaire/views_annulation_transfert.py
#
# INSTRUCTIONS: CRÉER ce nouveau fichier dans inventaire/
# ===================================================================

import logging
from datetime import date, datetime
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.http import JsonResponse

from .models import (
    Poste, SerieTicket, CouleurTicket, GestionStock, 
    HistoriqueStock, StockEvent
)
from common.utils import log_user_action

logger = logging.getLogger('supper')


# ===================================================================
# FONCTIONS UTILITAIRES DE PERMISSIONS
# ===================================================================

def is_admin_user(user):
    """Vérifie si l'utilisateur est administrateur."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return getattr(user, 'habilitation', None) in [
        'admin_principal', 'coord_psrr', 'serv_info'
    ]


def get_user_short_description(user):
    """Retourne une description courte de l'utilisateur pour les logs."""
    if not user:
        return "Utilisateur inconnu"
    
    nom = getattr(user, 'nom_complet', None) or user.username
    habilitation = getattr(user, 'habilitation', 'inconnu')
    poste = getattr(user, 'poste_affectation', None)
    
    if poste:
        return f"{nom} ({habilitation}, {poste.code})"
    return f"{nom} ({habilitation})"


def log_acces_refuse(user, ressource, raison):
    """Journalise un accès refusé."""
    logger.warning(
        f"🚫 ACCÈS REFUSÉ | {get_user_short_description(user)} | "
        f"Ressource: {ressource} | Raison: {raison}"
    )


# ===================================================================
# SERVICE D'ANNULATION DE TRANSFERT
# ===================================================================

class AnnulationTransfertService:
    """
    Service pour annuler un transfert de tickets.
    
    L'annulation:
    1. Vérifie que les tickets n'ont pas été vendus au poste destination
    2. Remet les tickets au poste d'origine avec statut 'stock'
    3. Supprime ou marque comme annulée la série au poste destination
    4. Met à jour les stocks globaux des deux postes
    5. Crée les historiques d'annulation
    """
    
    @staticmethod
    def peut_annuler_transfert(numero_bordereau):
        """
        Vérifie si un transfert peut être annulé.
        
        Conditions:
        - Le transfert doit exister
        - Les tickets ne doivent pas avoir été vendus au poste destination
        - Les tickets ne doivent pas avoir été re-transférés
        
        Returns:
            tuple (bool, str, dict): (peut_annuler, message, details)
        """
        try:
            # Récupérer les historiques du transfert
            hist_cession = HistoriqueStock.objects.filter(
                numero_bordereau=numero_bordereau,
                type_mouvement='DEBIT'
            ).select_related('poste', 'effectue_par').first()
            
            hist_reception = HistoriqueStock.objects.filter(
                numero_bordereau=numero_bordereau,
                type_mouvement='CREDIT'
            ).select_related('poste').first()
            
            if not hist_cession or not hist_reception:
                return False, "Bordereau de transfert introuvable.", {}
            
            poste_origine = hist_cession.poste
            poste_destination = hist_reception.poste
            
            # Récupérer les détails du transfert depuis l'historique
            details_transfert = hist_cession.details_approvisionnement or {}
            
            # Récupérer les séries concernées
            # Option 1: Depuis les séries associées à l'historique
            series_associees = hist_cession.series_tickets_associees.all()
            
            if not series_associees.exists():
                # Option 2: Chercher les séries transférées ce jour-là
                series_associees = SerieTicket.objects.filter(
                    poste=poste_origine,
                    statut='transfere',
                    poste_destination_transfert=poste_destination,
                    date_utilisation=hist_cession.date_mouvement.date()
                )
            
            if not series_associees.exists():
                return False, "Aucune série trouvée pour ce transfert.", {}
            
            # Vérifier si les tickets ont été vendus ou re-transférés au poste destination
            problemes = []
            series_info = []
            
            for serie_origine in series_associees:
                # Chercher la série correspondante au poste destination
                series_destination = SerieTicket.objects.filter(
                    poste=poste_destination,
                    couleur=serie_origine.couleur,
                    numero_premier__lte=serie_origine.numero_dernier,
                    numero_dernier__gte=serie_origine.numero_premier,
                    type_entree='transfert_recu'
                )
                
                for serie_dest in series_destination:
                    if serie_dest.statut == 'vendu':
                        problemes.append(
                            f"❌ Série {serie_dest.couleur.libelle_affichage} "
                            f"#{serie_dest.numero_premier}-{serie_dest.numero_dernier} "
                            f"a été VENDUE le {serie_dest.date_utilisation.strftime('%d/%m/%Y') if serie_dest.date_utilisation else 'date inconnue'}"
                        )
                    elif serie_dest.statut == 'transfere':
                        problemes.append(
                            f"❌ Série {serie_dest.couleur.libelle_affichage} "
                            f"#{serie_dest.numero_premier}-{serie_dest.numero_dernier} "
                            f"a été RE-TRANSFÉRÉE vers {serie_dest.poste_destination_transfert.nom if serie_dest.poste_destination_transfert else 'inconnu'}"
                        )
                    else:
                        # Série encore en stock - peut être annulée
                        series_info.append({
                            'serie_origine': serie_origine,
                            'serie_destination': serie_dest,
                            'couleur': serie_origine.couleur.libelle_affichage,
                            'numero_premier': serie_origine.numero_premier,
                            'numero_dernier': serie_origine.numero_dernier,
                            'nombre_tickets': serie_origine.nombre_tickets,
                            'montant': serie_origine.valeur_monetaire
                        })
            
            if problemes:
                return False, "Annulation impossible:\n" + "\n".join(problemes), {
                    'poste_origine': poste_origine,
                    'poste_destination': poste_destination,
                    'problemes': problemes
                }
            
            if not series_info:
                return False, "Aucune série annulable trouvée pour ce transfert.", {}
            
            # Calcul du montant total
            montant_total = sum(s['montant'] for s in series_info)
            nombre_tickets_total = sum(s['nombre_tickets'] for s in series_info)
            
            return True, "✅ Le transfert peut être annulé.", {
                'poste_origine': poste_origine,
                'poste_destination': poste_destination,
                'hist_cession': hist_cession,
                'hist_reception': hist_reception,
                'series_info': series_info,
                'montant_total': montant_total,
                'nombre_tickets_total': nombre_tickets_total,
                'date_transfert': hist_cession.date_mouvement
            }
            
        except Exception as e:
            logger.error(f"Erreur vérification annulation: {str(e)}", exc_info=True)
            return False, f"Erreur lors de la vérification: {str(e)}", {}
    
    @staticmethod
    def executer_annulation(numero_bordereau, user, motif=""):
        """
        Exécute l'annulation d'un transfert.
        
        Args:
            numero_bordereau: Numéro du bordereau à annuler
            user: Utilisateur effectuant l'annulation
            motif: Motif de l'annulation
        
        Returns:
            tuple (bool, str): (succès, message)
        """
        timestamp = timezone.now()
        
        # Vérifier d'abord si l'annulation est possible
        peut_annuler, message, details = AnnulationTransfertService.peut_annuler_transfert(
            numero_bordereau
        )
        
        if not peut_annuler:
            return False, message
        
        poste_origine = details['poste_origine']
        poste_destination = details['poste_destination']
        series_info = details['series_info']
        montant_total = details['montant_total']
        nombre_tickets_total = details['nombre_tickets_total']
        hist_cession = details['hist_cession']
        hist_reception = details['hist_reception']
        
        logger.info(
            f"🔄 DÉBUT ANNULATION TRANSFERT | {get_user_short_description(user)} | "
            f"Bordereau: {numero_bordereau} | "
            f"{poste_origine.nom} ← {poste_destination.nom} | "
            f"{nombre_tickets_total} tickets = {montant_total:,.0f} FCFA"
        )
        
        try:
            with transaction.atomic():
                # ============================================================
                # ÉTAPE 1: Remettre les séries au poste d'origine
                # ============================================================
                for info in series_info:
                    serie_origine = info['serie_origine']
                    serie_destination = info['serie_destination']
                    
                    logger.info(
                        f"  📦 Restauration série: {info['couleur']} "
                        f"#{info['numero_premier']}-{info['numero_dernier']}"
                    )
                    
                    # Remettre la série d'origine en stock
                    serie_origine.statut = 'stock'
                    serie_origine.date_utilisation = None
                    serie_origine.poste_destination_transfert = None
                    serie_origine.commentaire = (
                        f"Remise en stock suite à annulation du transfert {numero_bordereau} "
                        f"le {timestamp.strftime('%d/%m/%Y à %H:%M')} par {user.nom_complet}. "
                        f"Motif: {motif or 'Non spécifié'}"
                    )
                    serie_origine.save()
                    
                    # Supprimer la série au poste destination
                    serie_destination.delete()
                
                # ============================================================
                # ÉTAPE 2: Mettre à jour les stocks globaux
                # ============================================================
                
                # Stock poste origine: +montant (les tickets reviennent)
                stock_origine, _ = GestionStock.objects.get_or_create(
                    poste=poste_origine,
                    defaults={'valeur_monetaire': Decimal('0')}
                )
                stock_origine_avant = stock_origine.valeur_monetaire
                stock_origine.valeur_monetaire += montant_total
                stock_origine.save()
                
                logger.info(
                    f"  📊 Stock {poste_origine.code}: "
                    f"{stock_origine_avant:,.0f} → {stock_origine.valeur_monetaire:,.0f} FCFA "
                    f"(+{montant_total:,.0f})"
                )
                
                # Stock poste destination: -montant (les tickets partent)
                stock_destination, _ = GestionStock.objects.get_or_create(
                    poste=poste_destination,
                    defaults={'valeur_monetaire': Decimal('0')}
                )
                stock_destination_avant = stock_destination.valeur_monetaire
                stock_destination.valeur_monetaire = max(
                    Decimal('0'), 
                    stock_destination.valeur_monetaire - montant_total
                )
                stock_destination.save()
                
                logger.info(
                    f"  📊 Stock {poste_destination.code}: "
                    f"{stock_destination_avant:,.0f} → {stock_destination.valeur_monetaire:,.0f} FCFA "
                    f"(-{montant_total:,.0f})"
                )
                
                # ============================================================
                # ÉTAPE 3: Créer les historiques d'annulation
                # ============================================================
                
                numero_annulation = f"ANN-{numero_bordereau}"
                commentaire_annulation = (
                    f"ANNULATION du transfert {numero_bordereau} | "
                    f"Motif: {motif or 'Non spécifié'} | "
                    f"Par: {user.nom_complet}"
                )
                
                # Historique CRÉDIT au poste origine (retour des tickets)
                hist_retour_origine = HistoriqueStock.objects.create(
                    poste=poste_origine,
                    type_mouvement='CREDIT',
                    type_stock='regularisation',
                    montant=montant_total,
                    nombre_tickets=nombre_tickets_total,
                    stock_avant=stock_origine_avant,
                    stock_apres=stock_origine.valeur_monetaire,
                    effectue_par=user,
                    poste_origine=poste_destination,  # Les tickets viennent de la destination
                    numero_bordereau=numero_annulation,
                    commentaire=commentaire_annulation,
                    details_approvisionnement={
                        'type': 'annulation_transfert',
                        'bordereau_original': numero_bordereau,
                        'motif': motif,
                        'series': [
                            {
                                'couleur': s['couleur'],
                                'premier': s['numero_premier'],
                                'dernier': s['numero_dernier'],
                                'tickets': s['nombre_tickets']
                            }
                            for s in series_info
                        ]
                    }
                )
                
                # Historique DÉBIT au poste destination (départ des tickets)
                hist_retour_destination = HistoriqueStock.objects.create(
                    poste=poste_destination,
                    type_mouvement='DEBIT',
                    type_stock='regularisation',
                    montant=montant_total,
                    nombre_tickets=nombre_tickets_total,
                    stock_avant=stock_destination_avant,
                    stock_apres=stock_destination.valeur_monetaire,
                    effectue_par=user,
                    poste_destination=poste_origine,  # Les tickets partent vers l'origine
                    numero_bordereau=numero_annulation,
                    commentaire=commentaire_annulation,
                    details_approvisionnement={
                        'type': 'annulation_transfert',
                        'bordereau_original': numero_bordereau,
                        'motif': motif
                    }
                )
                
                # ============================================================
                # ÉTAPE 4: Marquer les historiques originaux comme annulés
                # ============================================================
                
                hist_cession.commentaire = (
                    f"{hist_cession.commentaire or ''} | "
                    f"⚠️ ANNULÉ le {timestamp.strftime('%d/%m/%Y à %H:%M')} "
                    f"(voir {numero_annulation})"
                )
                hist_cession.save()
                
                hist_reception.commentaire = (
                    f"{hist_reception.commentaire or ''} | "
                    f"⚠️ ANNULÉ le {timestamp.strftime('%d/%m/%Y à %H:%M')} "
                    f"(voir {numero_annulation})"
                )
                hist_reception.save()
                
                # ============================================================
                # ÉTAPE 5: Créer les événements de stock
                # ============================================================
                
                StockEvent.objects.create(
                    poste=poste_origine,
                    event_type='ANNULATION_TRANSFERT',
                    event_datetime=timestamp,
                    montant_variation=montant_total,
                    nombre_tickets_variation=nombre_tickets_total,
                    stock_resultant=stock_origine.valeur_monetaire,
                    tickets_resultants=int(stock_origine.valeur_monetaire / 500),
                    effectue_par=user,
                    reference_id=numero_annulation,
                    reference_type='AnnulationTransfert',
                    metadata={
                        'bordereau_original': numero_bordereau,
                        'poste_destination': poste_destination.code,
                        'motif': motif
                    },
                    commentaire=f"Annulation transfert - Retour de {poste_destination.nom}"
                )
                
                StockEvent.objects.create(
                    poste=poste_destination,
                    event_type='ANNULATION_TRANSFERT',
                    event_datetime=timestamp,
                    montant_variation=-montant_total,
                    nombre_tickets_variation=-nombre_tickets_total,
                    stock_resultant=stock_destination.valeur_monetaire,
                    tickets_resultants=int(stock_destination.valeur_monetaire / 500),
                    effectue_par=user,
                    reference_id=numero_annulation,
                    reference_type='AnnulationTransfert',
                    metadata={
                        'bordereau_original': numero_bordereau,
                        'poste_origine': poste_origine.code,
                        'motif': motif
                    },
                    commentaire=f"Annulation transfert - Retour vers {poste_origine.nom}"
                )
                
                logger.info(
                    f"✅ ANNULATION TRANSFERT RÉUSSIE | {get_user_short_description(user)} | "
                    f"Bordereau: {numero_bordereau} | "
                    f"{nombre_tickets_total} tickets remis à {poste_origine.nom}"
                )
                
                return True, (
                    f"✅ Transfert {numero_bordereau} annulé avec succès. "
                    f"{nombre_tickets_total} tickets ({montant_total:,.0f} FCFA) "
                    f"remis en stock au poste {poste_origine.nom}."
                )
                
        except Exception as e:
            logger.error(
                f"❌ ERREUR ANNULATION TRANSFERT | {get_user_short_description(user)} | "
                f"Bordereau: {numero_bordereau} | Erreur: {str(e)}",
                exc_info=True
            )
            return False, f"Erreur lors de l'annulation: {str(e)}"


# ===================================================================
# VUES D'ANNULATION DE TRANSFERT
# ===================================================================

@login_required
def annuler_transfert(request, numero_bordereau):
    """
    Vue pour annuler un transfert de tickets.
    
    RÉSERVÉ AUX ADMINISTRATEURS.
    
    Étapes:
    1. GET: Affiche la page de confirmation avec les détails
    2. POST: Exécute l'annulation après confirmation
    """
    user = request.user
    
    # Vérification: Admin uniquement
    if not is_admin_user(user):
        log_acces_refuse(
            user,
            f"Annulation transfert {numero_bordereau}",
            "Administrateur requis"
        )
        messages.error(request, "Accès réservé aux administrateurs.")
        return redirect('inventaire:liste_bordereaux')
    
    logger.info(
        f"🔄 ANNULATION TRANSFERT | {get_user_short_description(user)} | "
        f"Consultation bordereau: {numero_bordereau}"
    )
    
    # Vérifier si l'annulation est possible
    peut_annuler, message, details = AnnulationTransfertService.peut_annuler_transfert(
        numero_bordereau
    )
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'confirmer':
            if not peut_annuler:
                messages.error(request, message)
                return redirect('inventaire:liste_bordereaux')
            
            motif = request.POST.get('motif', '').strip()
            
            if not motif:
                messages.error(request, "Veuillez indiquer un motif pour l'annulation.")
                return redirect('inventaire:annuler_transfert', numero_bordereau=numero_bordereau)
            
            # Exécuter l'annulation
            success, result_message = AnnulationTransfertService.executer_annulation(
                numero_bordereau, user, motif
            )
            
            if success:
                # Log de l'action
                log_user_action(
                    user,
                    "ANNULATION_TRANSFERT",
                    f"Annulation du transfert {numero_bordereau} - "
                    f"{details['poste_origine'].nom} ← {details['poste_destination'].nom} - "
                    f"Motif: {motif}",
                    request,
                    bordereau=numero_bordereau,
                    poste_origine=details['poste_origine'].nom,
                    poste_destination=details['poste_destination'].nom,
                    montant=str(details['montant_total']),
                    motif=motif
                )
                
                messages.success(request, result_message)
            else:
                messages.error(request, result_message)
            
            return redirect('inventaire:liste_bordereaux')
        
        elif action == 'annuler':
            messages.info(request, "Annulation abandonnée.")
            return redirect('inventaire:liste_bordereaux')
    
    # Affichage GET
    context = {
        'numero_bordereau': numero_bordereau,
        'peut_annuler': peut_annuler,
        'message': message,
        'details': details,
        'title': f'Annuler le transfert {numero_bordereau}'
    }
    
    return render(request, 'inventaire/annuler_transfert.html', context)


@login_required
def ajax_verifier_annulation(request, numero_bordereau):
    """
    Vue AJAX pour vérifier si un transfert peut être annulé.
    
    Retourne un JSON avec:
    - peut_annuler: bool
    - message: str
    - details: dict (si peut_annuler)
    """
    user = request.user
    
    if not is_admin_user(user):
        return JsonResponse({
            'peut_annuler': False,
            'message': 'Accès réservé aux administrateurs.',
            'code': 'permission_denied'
        }, status=403)
    
    peut_annuler, message, details = AnnulationTransfertService.peut_annuler_transfert(
        numero_bordereau
    )
    
    response_data = {
        'peut_annuler': peut_annuler,
        'message': message
    }
    
    if peut_annuler and details:
        response_data['details'] = {
            'poste_origine': details['poste_origine'].nom,
            'poste_destination': details['poste_destination'].nom,
            'montant_total': str(details['montant_total']),
            'nombre_tickets_total': details['nombre_tickets_total'],
            'date_transfert': details['date_transfert'].strftime('%d/%m/%Y à %H:%M'),
            'nb_series': len(details['series_info'])
        }
    
    return JsonResponse(response_data)