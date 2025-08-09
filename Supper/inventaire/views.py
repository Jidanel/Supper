# ===================================================================
# inventaire/views.py - Vues corrigées pour la gestion des inventaires
# ===================================================================

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import View, ListView, DetailView, CreateView, UpdateView
from django.http import JsonResponse, HttpResponseForbidden
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation
import json
import logging

from .models import (
    InventaireJournalier, DetailInventairePeriode, RecetteJournaliere,
    ConfigurationJour, StatistiquesPeriodiques
)
from accounts.models import Poste
from common.mixins import RoleRequiredMixin
from common.utils import log_user_action

logger = logging.getLogger('supper')


class SaisieInventaireView(LoginRequiredMixin, RoleRequiredMixin, View):
    """Vue pour la saisie d'inventaire par les agents"""
    required_permission = 'peut_gerer_inventaire'
    template_name = 'admin/saisie_inventaire.html'
    
    def get(self, request, poste_id=None, date=None):
        """Affichage du formulaire de saisie"""
        try:
            # Récupérer les postes accessibles à l'utilisateur
            postes_accessibles = request.user.get_postes_accessibles()
            
            # Si un poste spécifique est demandé, vérifier l'accès
            if poste_id:
                poste = get_object_or_404(Poste, id=poste_id)
                if not request.user.peut_acceder_poste(poste):
                    messages.error(request, "Vous n'avez pas accès à ce poste.")
                    return redirect('inventaire:saisie_inventaire')
            else:
                # Prendre le poste d'affectation par défaut
                poste = request.user.poste_affectation
                if not poste:
                    if postes_accessibles.exists():
                        poste = postes_accessibles.first()
                    else:
                        messages.error(request, "Aucun poste accessible trouvé.")
                        return redirect('common:dashboard')
            
            # Date par défaut = aujourd'hui
            if not date:
                date = timezone.now().date()
            else:
                from datetime import datetime
                try:
                    date = datetime.strptime(date, '%Y-%m-%d').date()
                except ValueError:
                    messages.error(request, "Format de date invalide.")
                    return redirect('inventaire:saisie_inventaire')
            
            # Vérifier si le jour est ouvert pour la saisie
            if not ConfigurationJour.est_jour_ouvert(date):
                messages.warning(request, f"Le jour {date.strftime('%d/%m/%Y')} n'est pas ouvert pour la saisie.")
                return redirect('inventaire:saisie_inventaire')
            
            # Récupérer ou créer l'inventaire
            inventaire, created = InventaireJournalier.objects.get_or_create(
                poste=poste,
                date=date,
                defaults={
                    'agent_saisie': request.user,
                }
            )
            
            # Vérifier si l'inventaire peut être modifié
            if not inventaire.peut_etre_modifie():
                messages.error(request, "Cet inventaire est verrouillé et ne peut plus être modifié.")
                return redirect('inventaire:inventaire_detail', pk=inventaire.pk)
            
            # Récupérer les détails existants
            details_existants = {
                detail.periode: detail for detail in inventaire.details_periodes.all()
            }
            
            # Périodes horaires disponibles
            from django.conf import settings
            periodes = getattr(settings, 'SUPPER_CONFIG', {}).get('PERIODES_INVENTAIRE', [
                '08h-09h', '09h-10h', '10h-11h', '11h-12h',
                '12h-13h', '13h-14h', '14h-15h', '15h-16h',
                '16h-17h', '17h-18h'
            ])
            
            context = {
                'inventaire': inventaire,
                'poste': poste,
                'date': date,
                'postes_accessibles': postes_accessibles,
                'periodes': periodes,
                'details_existants': details_existants,
                'created': created,
                'can_edit': inventaire.peut_etre_modifie(),
            }
            
            return render(request, self.template_name, context)
            
        except Exception as e:
            logger.error(f"Erreur lors de l'affichage saisie inventaire: {str(e)}")
            messages.error(request, "Une erreur est survenue lors du chargement de la page.")
            return redirect('common:dashboard')
    
    def post(self, request, poste_id=None, date=None):
        """Traitement de la sauvegarde de l'inventaire"""
        try:
            with transaction.atomic():
                # Récupérer les données du formulaire
                poste_id = request.POST.get('poste_id')
                date_str = request.POST.get('date')
                action = request.POST.get('action', 'sauvegarder')
                
                # Validation des données de base
                if not poste_id or not date_str:
                    messages.error(request, "Données manquantes dans le formulaire.")
                    return redirect('inventaire:saisie_inventaire')
                
                # Récupérer le poste et vérifier l'accès
                poste = get_object_or_404(Poste, id=poste_id)
                if not request.user.peut_acceder_poste(poste):
                    messages.error(request, "Vous n'avez pas accès à ce poste.")
                    return redirect('inventaire:saisie_inventaire')
                
                # Parser la date
                from datetime import datetime
                try:
                    date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    messages.error(request, "Format de date invalide.")
                    return redirect('inventaire:saisie_inventaire')
                
                # Vérifier si le jour est ouvert
                if not ConfigurationJour.est_jour_ouvert(date):
                    messages.error(request, "Ce jour n'est pas ouvert pour la saisie.")
                    return redirect('inventaire:saisie_inventaire')
                
                # Récupérer l'inventaire existant
                try:
                    inventaire = InventaireJournalier.objects.get(poste=poste, date=date)
                except InventaireJournalier.DoesNotExist:
                    messages.error(request, "Inventaire introuvable.")
                    return redirect('inventaire:saisie_inventaire')
                
                # Vérifier si l'inventaire peut être modifié
                if not inventaire.peut_etre_modifie():
                    messages.error(request, "Cet inventaire est verrouillé et ne peut plus être modifié.")
                    return redirect('inventaire:inventaire_detail', pk=inventaire.pk)
                
                # Traitement des données par période
                periodes_sauvegardees = 0
                erreurs_validation = []
                
                # Récupérer toutes les périodes du formulaire
                for key, value in request.POST.items():
                    if key.startswith('periode_'):
                        periode = key.replace('periode_', '')
                        
                        # Validation de la valeur
                        if value.strip():
                            try:
                                nombre_vehicules = int(value.strip())
                                if nombre_vehicules < 0:
                                    erreurs_validation.append(f"Période {periode}: le nombre ne peut pas être négatif")
                                    continue
                                if nombre_vehicules > 1000:
                                    erreurs_validation.append(f"Période {periode}: le nombre ne peut pas dépasser 1000")
                                    continue
                            except ValueError:
                                erreurs_validation.append(f"Période {periode}: valeur invalide '{value}'")
                                continue
                        else:
                            # Supprimer le détail s'il existe et que la valeur est vide
                            DetailInventairePeriode.objects.filter(
                                inventaire=inventaire,
                                periode=periode
                            ).delete()
                            continue
                        
                        # Récupérer les observations pour cette période
                        observations = request.POST.get(f'observations_{periode}', '').strip()
                        
                        # Créer ou mettre à jour le détail
                        try:
                            detail, created = DetailInventairePeriode.objects.update_or_create(
                                inventaire=inventaire,
                                periode=periode,
                                defaults={
                                    'nombre_vehicules': nombre_vehicules,
                                    'observations_periode': observations
                                }
                            )
                            periodes_sauvegardees += 1
                            
                        except IntegrityError as e:
                            erreurs_validation.append(f"Période {periode}: erreur de sauvegarde")
                            logger.error(f"Erreur IntegrityError pour période {periode}: {str(e)}")
                
                # Vérifier s'il y a des erreurs de validation
                if erreurs_validation:
                    for erreur in erreurs_validation:
                        messages.error(request, erreur)
                    return redirect('inventaire:saisie_inventaire', poste_id=poste.id, date=date_str)
                
                # Recalculer les totaux de l'inventaire
                inventaire.recalculer_totaux()
                
                # Traitement selon l'action demandée
                if action == 'verrouiller' and periodes_sauvegardees > 0:
                    # Verrouiller l'inventaire
                    inventaire.verrouiller(request.user)
                    
                    # Log de l'action
                    log_user_action(
                        request.user,
                        "Verrouillage inventaire",
                        f"Poste: {poste.nom}, Date: {date}, Périodes: {periodes_sauvegardees}",
                        request
                    )
                    
                    messages.success(request, f"Inventaire verrouillé avec succès ({periodes_sauvegardees} périodes sauvegardées).")
                    return redirect('inventaire:inventaire_detail', pk=inventaire.pk)
                
                elif action == 'sauvegarder':
                    # Simple sauvegarde
                    log_user_action(
                        request.user,
                        "Sauvegarde inventaire",
                        f"Poste: {poste.nom}, Date: {date}, Périodes: {periodes_sauvegardees}",
                        request
                    )
                    
                    if periodes_sauvegardees > 0:
                        messages.success(request, f"Inventaire sauvegardé avec succès ({periodes_sauvegardees} périodes).")
                    else:
                        messages.info(request, "Aucune donnée à sauvegarder.")
                    
                    return redirect('inventaire:saisie_inventaire', poste_id=poste.id, date=date_str)
                
                else:
                    messages.error(request, "Action non reconnue.")
                    return redirect('inventaire:saisie_inventaire', poste_id=poste.id, date=date_str)
                    
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde inventaire: {str(e)}")
            messages.error(request, f"Erreur lors de la sauvegarde: {str(e)}")
            return redirect('inventaire:saisie_inventaire')


class CalculAutomatiqueAPIView(LoginRequiredMixin, View):
    """API pour les calculs automatiques en temps réel"""
    
    def post(self, request):
        """Calcule les totaux et estimations en temps réel"""
        try:
            data = json.loads(request.body)
            periodes_data = data.get('periodes', {})
            
            # Calculer les totaux
            total_vehicules = 0
            nombre_periodes = 0
            
            for periode, nombre in periodes_data.items():
                if nombre and str(nombre).strip():
                    try:
                        nb = int(nombre)
                        if nb >= 0:
                            total_vehicules += nb
                            nombre_periodes += 1
                    except (ValueError, TypeError):
                        continue
            
            # Calculs selon la formule SUPPER
            moyenne_horaire = total_vehicules / nombre_periodes if nombre_periodes > 0 else 0
            estimation_24h = moyenne_horaire * 24
            
            # Configuration SUPPER
            from django.conf import settings
            config = getattr(settings, 'SUPPER_CONFIG', {})
            tarif = config.get('TARIF_VEHICULE_LEGER', 500)
            pourcentage_legers = config.get('POURCENTAGE_VEHICULES_LEGERS', 75)
            
            # Recette potentielle
            recette_potentielle = (estimation_24h * pourcentage_legers * tarif) / 100
            
            return JsonResponse({
                'success': True,
                'total_vehicules': total_vehicules,
                'nombre_periodes': nombre_periodes,
                'moyenne_horaire': round(moyenne_horaire, 2),
                'estimation_24h': round(estimation_24h, 2),
                'recette_potentielle': round(recette_potentielle, 2)
            })
            
        except Exception as e:
            logger.error(f"Erreur calcul automatique: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'Erreur lors du calcul'
            })


class VerificationJourAPIView(LoginRequiredMixin, View):
    """API pour vérifier si un jour est ouvert pour la saisie"""
    
    def get(self, request):
        """Vérifie si une date est ouverte pour la saisie"""
        try:
            date_str = request.GET.get('date')
            if not date_str:
                return JsonResponse({'success': False, 'error': 'Date manquante'})
            
            from datetime import datetime
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Format de date invalide'})
            
            est_ouvert = ConfigurationJour.est_jour_ouvert(date)
            
            return JsonResponse({
                'success': True,
                'ouvert': est_ouvert,
                'date': date_str
            })
            
        except Exception as e:
            logger.error(f"Erreur vérification jour: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'Erreur lors de la vérification'
            })


# Vues basiques pour les autres fonctionnalités
class InventaireListView(LoginRequiredMixin, ListView):
    """Liste des inventaires"""
    model = InventaireJournalier
    template_name = 'inventaire/inventaire_list.html'
    context_object_name = 'inventaires'
    paginate_by = 25
    
    def get_queryset(self):
        queryset = InventaireJournalier.objects.select_related(
            'poste', 'agent_saisie', 'valide_par'
        ).order_by('-date', 'poste__nom')
        
        # Filtrer selon les postes accessibles
        if not self.request.user.acces_tous_postes:
            postes_accessibles = self.request.user.get_postes_accessibles()
            queryset = queryset.filter(poste__in=postes_accessibles)
        
        return queryset


class InventaireDetailView(LoginRequiredMixin, DetailView):
    """Détail d'un inventaire"""
    model = InventaireJournalier
    template_name = 'inventaire/inventaire_detail.html'
    context_object_name = 'inventaire'
    
    def get_queryset(self):
        queryset = InventaireJournalier.objects.select_related(
            'poste', 'agent_saisie', 'valide_par'
        ).prefetch_related('details_periodes')
        
        # Filtrer selon les postes accessibles
        if not self.request.user.acces_tous_postes:
            postes_accessibles = self.request.user.get_postes_accessibles()
            queryset = queryset.filter(poste__in=postes_accessibles)
        
        return queryset


# Autres vues de base (à développer selon les besoins)
class RecetteListView(LoginRequiredMixin, ListView):
    model = RecetteJournaliere
    template_name = 'inventaire/recette_list.html'
    paginate_by = 25


class SaisieRecetteView(LoginRequiredMixin, View):
    template_name = 'inventaire/saisie_recette.html'
    
    def get(self, request):
        return render(request, self.template_name)
    
    def post(self, request):
        # À implémenter selon les besoins
        pass


class StatistiquesView(LoginRequiredMixin, View):
    template_name = 'inventaire/statistiques.html'
    
    def get(self, request):
        return render(request, self.template_name)


class ConfigurationJourListView(LoginRequiredMixin, RoleRequiredMixin, ListView):
    model = ConfigurationJour
    template_name = 'inventaire/config_jour_list.html'
    required_permission = 'is_admin'  # Seuls les admins peuvent gérer les jours