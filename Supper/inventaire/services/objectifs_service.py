# inventaire/services/objectifs_service.py
"""
Service centralisé pour les calculs d'objectifs annuels
Garantit la cohérence entre toutes les vues
"""

from decimal import Decimal
from django.db.models import Sum
from django.utils import timezone
from django.db import transaction
import logging

logger = logging.getLogger('supper')


class ObjectifsService:
    """Service pour gérer les objectifs annuels"""
    
    @staticmethod
    def calculer_objectifs_annuels(annee=None, inclure_postes_inactifs=False):
        """
        Calcule les objectifs et réalisations pour une année donnée
        
        Args:
            annee: Année cible (défaut: année actuelle)
            inclure_postes_inactifs: Inclure les postes inactifs dans le calcul
            
        Returns:
            dict avec total_objectif, total_realise, reste_a_realiser, taux_realisation
        """
        from inventaire.models import ObjectifAnnuel, RecetteJournaliere
        
        if annee is None:
            annee = timezone.now().year
        
        # Filtrer les objectifs selon le critère postes actifs/inactifs
        if inclure_postes_inactifs:
            objectifs = ObjectifAnnuel.objects.filter(annee=annee)
        else:
            objectifs = ObjectifAnnuel.objects.filter(
                annee=annee,
                poste__is_active=True
            )
        
        # Calculer le total des objectifs
        total_objectif = objectifs.aggregate(
            total=Sum('montant_objectif')
        )['total'] or Decimal('0')
        
        # Récupérer les IDs des postes concernés
        postes_ids = list(objectifs.values_list('poste_id', flat=True))
        
        # Calculer le total réalisé pour ces postes uniquement
        if postes_ids:
            total_realise = RecetteJournaliere.objects.filter(
                poste_id__in=postes_ids,
                date__year=annee
            ).aggregate(
                total=Sum('montant_declare')
            )['total'] or Decimal('0')
        else:
            total_realise = Decimal('0')
        
        # Calcul du reste à réaliser
        reste_a_realiser = total_objectif - total_realise
        
        # Calcul du taux de réalisation
        if total_objectif > 0:
            taux_realisation = float(total_realise / total_objectif * 100)
        else:
            taux_realisation = 0.0
        
        return {
            'total_objectif': total_objectif,
            'total_realise': total_realise,
            'reste_a_realiser': reste_a_realiser,
            'taux_realisation': round(taux_realisation, 2),
            'nombre_postes': len(postes_ids),
            'annee': annee
        }
    
    @staticmethod
    def get_postes_avec_objectifs(annee=None, tous_postes=True):
        """
        Retourne la liste des postes avec leurs objectifs et réalisations
        
        Args:
            annee: Année cible
            tous_postes: Si True, retourne TOUS les postes (même sans objectif)
        """
        from inventaire.models import ObjectifAnnuel, RecetteJournaliere
        from accounts.models import Poste
        from django.db.models import Sum
        
        if annee is None:
            annee = timezone.now().year
        
        if tous_postes:
            postes = Poste.objects.filter(is_active=True).order_by('region', 'nom')
        else:
            postes_ids = ObjectifAnnuel.objects.filter(
                annee=annee
            ).values_list('poste_id', flat=True)
            postes = Poste.objects.filter(id__in=postes_ids).order_by('region', 'nom')
        
        resultats = []
        
        for poste in postes:
            # Chercher l'objectif
            try:
                objectif = ObjectifAnnuel.objects.get(poste=poste, annee=annee)
                montant_objectif = objectif.montant_objectif
            except ObjectifAnnuel.DoesNotExist:
                montant_objectif = Decimal('0')
            
            # Calculer le réalisé
            realise = RecetteJournaliere.objects.filter(
                poste=poste,
                date__year=annee
            ).aggregate(Sum('montant_declare'))['montant_declare__sum'] or Decimal('0')
            
            # Calcul du taux
            taux = (realise / montant_objectif * 100) if montant_objectif > 0 else 0
            
            resultats.append({
                'poste': poste,
                'montant_objectif': montant_objectif,
                'realise': realise,
                'reste': montant_objectif - realise,
                'taux': float(taux)
            })
        
        return resultats
    
    @staticmethod
    def calculer_objectifs_avec_pourcentage(annee_source, annee_cible, pourcentage_augmentation):
        """
        Calcule automatiquement les objectifs pour une année cible
        en appliquant un pourcentage d'augmentation sur l'année source
        
        Args:
            annee_source: Année de référence
            annee_cible: Année pour laquelle calculer les nouveaux objectifs
            pourcentage_augmentation: Pourcentage d'augmentation (ex: 13 pour +13%)
            
        Returns:
            dict avec nombre_postes, total_objectif_source, total_objectif_cible
        """
        from inventaire.models import ObjectifAnnuel
        
        # Récupérer les objectifs de l'année source
        objectifs_source = ObjectifAnnuel.objects.filter(
            annee=annee_source,
            poste__is_active=True
        ).select_related('poste')
        
        if not objectifs_source.exists():
            return {
                'success': False,
                'message': f"Aucun objectif trouvé pour l'année {annee_source}",
                'nombre_postes': 0
            }
        
        # Calculer le coefficient multiplicateur
        coefficient = Decimal('1') + (Decimal(str(pourcentage_augmentation)) / Decimal('100'))
        
        nouveaux_objectifs = []
        total_source = Decimal('0')
        total_cible = Decimal('0')
        
        for obj_source in objectifs_source:
            # Calculer le nouvel objectif
            nouveau_montant = obj_source.montant_objectif * coefficient
            nouveau_montant = nouveau_montant.quantize(Decimal('1'))  # Arrondir à l'entier
            
            nouveaux_objectifs.append({
                'poste': obj_source.poste,
                'montant_source': obj_source.montant_objectif,
                'montant_cible': nouveau_montant
            })
            
            total_source += obj_source.montant_objectif
            total_cible += nouveau_montant
        
        return {
            'success': True,
            'nombre_postes': len(nouveaux_objectifs),
            'objectifs': nouveaux_objectifs,
            'total_objectif_source': total_source,
            'total_objectif_cible': total_cible,
            'pourcentage_applique': float(pourcentage_augmentation),
            'annee_source': annee_source,
            'annee_cible': annee_cible
        }
    
    @staticmethod
    def appliquer_objectifs_calcules(annee_source, annee_cible, pourcentage_augmentation, utilisateur):
        """
        Applique et enregistre les objectifs calculés dans la base de données
        
        Args:
            annee_source: Année de référence
            annee_cible: Année pour laquelle créer les objectifs
            pourcentage_augmentation: Pourcentage d'augmentation
            utilisateur: Utilisateur qui effectue l'opération
            
        Returns:
            dict avec résultats de l'opération
        """
        from inventaire.models import ObjectifAnnuel
        
        # Calculer d'abord les objectifs
        resultats_calcul = ObjectifsService.calculer_objectifs_avec_pourcentage(
            annee_source, annee_cible, pourcentage_augmentation
        )
        
        if not resultats_calcul['success']:
            return resultats_calcul
        
        # Appliquer les objectifs en transaction atomique
        objectifs_crees = 0
        objectifs_modifies = 0
        
        try:
            with transaction.atomic():
                for obj_data in resultats_calcul['objectifs']:
                    objectif, created = ObjectifAnnuel.objects.update_or_create(
                        poste=obj_data['poste'],
                        annee=annee_cible,
                        defaults={
                            'montant_objectif': obj_data['montant_cible'],
                            'cree_par': utilisateur
                        }
                    )
                    
                    if created:
                        objectifs_crees += 1
                    else:
                        objectifs_modifies += 1
            
            # Journalisation
            logger.info(
                f"Objectifs {annee_cible} calculés : {objectifs_crees} créés, "
                f"{objectifs_modifies} modifiés (base: {annee_source}, {pourcentage_augmentation}%)"
            )
            
            return {
                'success': True,
                'objectifs_crees': objectifs_crees,
                'objectifs_modifies': objectifs_modifies,
                'total_objectif_cible': resultats_calcul['total_objectif_cible'],
                'annee_source': annee_source,
                'annee_cible': annee_cible,
                'pourcentage_applique': pourcentage_augmentation
            }
            
        except Exception as e:
            logger.error(f"Erreur lors de l'application des objectifs: {str(e)}")
            return {
                'success': False,
                'message': f"Erreur lors de l'enregistrement : {str(e)}"
            }