# ===================================================================
# common/management/commands/fix_user_permissions.py
# Commande Django pour reconfigurer les permissions selon les habilitations
# VERSION CORRIGÉE - 16 HABILITATIONS EXACTES
# ===================================================================
"""
Commande de gestion pour reconfigurer les permissions des utilisateurs
selon leur habilitation.

USAGE:
    # Simulation (voir ce qui sera modifié sans appliquer)
    python manage.py fix_user_permissions --dry-run
    
    # Application réelle
    python manage.py fix_user_permissions
    
    # Utilisateur spécifique
    python manage.py fix_user_permissions --user 1234567M
    
    # Habilitation spécifique
    python manage.py fix_user_permissions --habilitation chef_peage
    
    # Afficher les habilitations reconnues
    python manage.py fix_user_permissions --list-habilitations
    
    # Exporter le rapport
    python manage.py fix_user_permissions --export rapport.csv
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import UtilisateurSUPPER
import logging
import csv
from collections import defaultdict

logger = logging.getLogger('supper.management')


class Command(BaseCommand):
    help = 'Reconfigure les permissions des utilisateurs selon leurs habilitations'
    
    # ===============================================================
    # MAPPING DES 16 HABILITATIONS EXACTES
    # ===============================================================
    HABILITATIONS_VALIDES = {
        'admin_principal': 'Administrateur Principal',
        'coord_psrr': 'Coordonnateur PSRR',
        'serv_info': 'Service Informatique',
        'serv_emission': 'Service Émissions et Recouvrement',
        'chef_ag': 'Chef Affaires Générales',
        'serv_controle': 'Service Contrôle et Validation',
        'serv_ordre': 'Service Ordre/Secrétariat',
        'imprimerie': 'Imprimerie Nationale',
        'cisop_peage': 'CISOP Péage',
        'cisop_pesage': 'CISOP Pesage',
        'chef_peage': 'Chef de Poste Péage',
        'chef_station_pesage': 'Chef de Station Pesage',
        'regisseur_pesage': 'Régisseur Station Pesage',
        'chef_equipe_pesage': 'Chef d\'Équipe Pesage',
        'agent_inventaire': 'Agent Inventaire',
        'comptable_mat': 'Comptable Matières',
    }
    
    # Classification des habilitations
    HABILITATIONS_PESAGE = ['chef_station_pesage', 'regisseur_pesage', 'chef_equipe_pesage']
    HABILITATIONS_PEAGE = ['chef_peage', 'agent_inventaire']
    HABILITATIONS_MULTI_POSTES = [
        'admin_principal', 'coord_psrr', 'serv_info', 'serv_emission',
        'chef_ag', 'serv_controle', 'serv_ordre', 'imprimerie',
        'cisop_peage', 'cisop_pesage', 'comptable_mat'
    ]
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche les changements sans les appliquer'
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Corriger uniquement un utilisateur spécifique (matricule)'
        )
        parser.add_argument(
            '--habilitation',
            type=str,
            help='Corriger uniquement les utilisateurs d\'une habilitation spécifique'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Affiche les détails de toutes les permissions modifiées'
        )
        parser.add_argument(
            '--show-matrix',
            action='store_true',
            help='Affiche la matrice des permissions par habilitation et quitte'
        )
        parser.add_argument(
            '--list-habilitations',
            action='store_true',
            help='Liste toutes les habilitations reconnues et quitte'
        )
        parser.add_argument(
            '--export',
            type=str,
            help='Exporte le rapport dans un fichier CSV'
        )
        parser.add_argument(
            '--force-reset',
            action='store_true',
            help='Force la réinitialisation complète de toutes les permissions'
        )
        parser.add_argument(
            '--show-all',
            action='store_true',
            help='Affiche tous les utilisateurs, même ceux non modifiés'
        )
        parser.add_argument(
            '--category',
            type=str,
            help='Filtrer par catégorie (pesage, peage, multi_postes)'
        )
    
    def handle(self, *args, **options):
        # Mode liste des habilitations
        if options['list_habilitations']:
            self._list_habilitations()
            return
        
        # Mode affichage matrice
        if options['show_matrix']:
            self._show_matrix()
            return
        
        # Mode normal
        dry_run = options['dry_run']
        verbose = options['verbose']
        force_reset = options.get('force_reset', False)
        show_all = options.get('show_all', False)
        category = options.get('category')
        
        self.stdout.write(self.style.HTTP_INFO(
            f"\n{'='*70}\n"
            f"  RECONFIGURATION DES PERMISSIONS SUPPER\n"
            f"  Mode: {'SIMULATION' if dry_run else 'APPLICATION'}\n"
            f"  Force reset: {'OUI' if force_reset else 'NON'}\n"
            f"{'='*70}\n"
        ))
        
        # Construire le queryset
        users = UtilisateurSUPPER.objects.all()
        
        if options.get('user'):
            users = users.filter(username__iexact=options['user'])
            if not users.exists():
                self.stdout.write(self.style.ERROR(
                    f"Utilisateur '{options['user']}' non trouvé."
                ))
                return
        
        if options.get('habilitation'):
            hab = options['habilitation']
            if hab not in self.HABILITATIONS_VALIDES:
                self.stdout.write(self.style.ERROR(
                    f"Habilitation '{hab}' non reconnue. "
                    f"Utilisez --list-habilitations pour voir les options."
                ))
                return
            users = users.filter(habilitation=hab)
        
        if category:
            if category.lower() == 'pesage':
                users = users.filter(habilitation__in=self.HABILITATIONS_PESAGE)
            elif category.lower() == 'peage':
                users = users.filter(habilitation__in=self.HABILITATIONS_PEAGE)
            elif category.lower() == 'multi_postes':
                users = users.filter(habilitation__in=self.HABILITATIONS_MULTI_POSTES)
        
        total_users = users.count()
        self.stdout.write(f"  Utilisateurs à traiter: {total_users}\n")
        
        # Statistiques
        stats = {
            'total': total_users,
            'corrected': 0,
            'unchanged': 0,
            'errors': 0,
            'no_habilitation': 0,
        }
        
        # Liste pour export
        export_data = []
        
        for user in users:
            try:
                result = self._process_user(user, dry_run, verbose, force_reset, show_all)
                
                if result['status'] == 'corrected':
                    stats['corrected'] += 1
                elif result['status'] == 'unchanged':
                    stats['unchanged'] += 1
                elif result['status'] == 'no_habilitation':
                    stats['no_habilitation'] += 1
                
                if result.get('changes') or show_all:
                    export_data.append(result)
                    
            except Exception as e:
                stats['errors'] += 1
                self.stdout.write(self.style.ERROR(
                    f"  ✗ {user.username}: Erreur - {str(e)}"
                ))
                logger.exception(f"Erreur lors du traitement de {user.username}")
        
        # Export CSV si demandé
        if options.get('export') and export_data:
            self._export_csv(options['export'], export_data)
        
        # Résumé
        self.stdout.write(self.style.HTTP_INFO(
            f"\n{'='*70}\n"
            f"  RÉSUMÉ\n"
            f"  Total: {stats['total']} utilisateurs\n"
            f"  Corrigés: {stats['corrected']}\n"
            f"  Inchangés: {stats['unchanged']}\n"
            f"  Sans habilitation: {stats['no_habilitation']}\n"
            f"  Erreurs: {stats['errors']}\n"
            f"{'='*70}\n"
        ))
        
        if dry_run and stats['corrected'] > 0:
            self.stdout.write(self.style.WARNING(
                "\n  [DRY-RUN] Relancez sans --dry-run pour appliquer les changements.\n"
            ))
    
    def _process_user(self, user, dry_run, verbose, force_reset, show_all):
        """Traite un utilisateur et retourne le résultat."""
        result = {
            'username': user.username,
            'nom': user.nom_complet,
            'habilitation': user.habilitation,
            'status': 'unchanged',
            'changes': [],
        }
        
        # Vérifier l'habilitation
        if not user.habilitation:
            result['status'] = 'no_habilitation'
            if verbose or show_all:
                self.stdout.write(self.style.NOTICE(
                    f"  ⊘ {user.username}: Aucune habilitation définie"
                ))
            return result
        
        if user.habilitation not in self.HABILITATIONS_VALIDES:
            result['status'] = 'no_habilitation'
            self.stdout.write(self.style.WARNING(
                f"  ⚠ {user.username}: Habilitation '{user.habilitation}' non reconnue"
            ))
            return result
        
        # Capturer les permissions actuelles
        old_permissions = self._capture_permissions(user)
        
        # Recalculer les permissions
        if hasattr(user, '_reinitialiser_toutes_permissions'):
            user._reinitialiser_toutes_permissions()
        if hasattr(user, 'attribuer_permissions_automatiques'):
            user.attribuer_permissions_automatiques()
        else:
            self.stdout.write(self.style.ERROR(
                f"  ✗ {user.username}: Méthode attribuer_permissions_automatiques() manquante"
            ))
            result['status'] = 'error'
            return result
        
        # Capturer les nouvelles permissions
        new_permissions = self._capture_permissions(user)
        
        # Comparer
        changes = []
        for perm, old_val in old_permissions.items():
            new_val = new_permissions.get(perm)
            if old_val != new_val:
                changes.append({
                    'permission': perm,
                    'old': old_val,
                    'new': new_val,
                })
        
        result['changes'] = changes
        
        if changes:
            result['status'] = 'corrected'
            
            # Sauvegarder si pas en mode dry-run
            if not dry_run:
                user.save(skip_auto_permissions=True)
            
            # Affichage
            hab_display = self.HABILITATIONS_VALIDES.get(user.habilitation, user.habilitation)
            self.stdout.write(self.style.WARNING(
                f"  ✓ {user.username} ({hab_display}): {len(changes)} permission(s) modifiée(s)"
            ))
            
            if verbose:
                for change in changes[:10]:  # Limiter à 10 pour lisibilité
                    old_str = "✓" if change['old'] else "✗"
                    new_str = "✓" if change['new'] else "✗"
                    self.stdout.write(f"      {change['permission']}: {old_str} → {new_str}")
                if len(changes) > 10:
                    self.stdout.write(f"      ... et {len(changes) - 10} autres")
        else:
            if show_all:
                self.stdout.write(f"  ○ {user.username}: Aucun changement")
        
        return result
    
    def _capture_permissions(self, user):
        """Capture toutes les permissions d'un utilisateur."""
        PERMISSION_FIELDS = [
            # Système
            'is_superuser', 'is_staff',
            # Accès global
            'acces_tous_postes', 'peut_saisir_peage', 'peut_saisir_pesage',
            'voir_recettes_potentielles', 'voir_taux_deperdition',
            'voir_statistiques_globales', 'peut_saisir_pour_autres_postes',
            # Modules legacy
            'peut_gerer_peage', 'peut_gerer_pesage', 'peut_gerer_personnel',
            'peut_gerer_budget', 'peut_gerer_inventaire', 'peut_gerer_archives',
            'peut_gerer_stocks_psrr', 'peut_gerer_stock_info',
            # Inventaires
            'peut_saisir_inventaire_normal', 'peut_saisir_inventaire_admin',
            'peut_programmer_inventaire', 'peut_voir_programmation_active',
            'peut_desactiver_programmation', 'peut_voir_programmation_desactivee',
            'peut_voir_liste_inventaires', 'peut_voir_liste_inventaires_admin',
            'peut_voir_jours_impertinents', 'peut_voir_stats_deperdition',
            # Recettes péage
            'peut_saisir_recette_peage', 'peut_voir_liste_recettes_peage',
            'peut_voir_stats_recettes_peage', 'peut_importer_recettes_peage',
            'peut_voir_evolution_peage', 'peut_voir_objectifs_peage',
            # Quittances péage
            'peut_saisir_quittance_peage', 'peut_voir_liste_quittances_peage',
            'peut_comptabiliser_quittances_peage',
            # Pesage
            'peut_voir_historique_vehicule_pesage', 'peut_saisir_amende',
            'peut_saisir_pesee_jour', 'peut_voir_objectifs_pesage',
            'peut_valider_paiement_amende', 'peut_lister_amendes',
            'peut_saisir_quittance_pesage', 'peut_comptabiliser_quittances_pesage',
            'peut_voir_liste_quittancements_pesage', 'peut_voir_historique_pesees',
            'peut_voir_recettes_pesage', 'peut_voir_stats_pesage',
            # Stock péage
            'peut_charger_stock_peage', 'peut_voir_liste_stocks_peage',
            'peut_voir_stock_date_peage', 'peut_transferer_stock_peage',
            'peut_voir_tracabilite_tickets', 'peut_voir_bordereaux_peage',
            'peut_voir_mon_stock_peage', 'peut_voir_historique_stock_peage',
            'peut_simuler_commandes_peage',
            # Gestion
            'peut_gerer_postes', 'peut_ajouter_poste', 'peut_creer_poste_masse',
            'peut_gerer_utilisateurs', 'peut_creer_utilisateur', 'peut_voir_journal_audit',
            # Rapports
            'peut_voir_rapports_defaillants_peage', 'peut_voir_rapports_defaillants_pesage',
            'peut_voir_rapport_inventaires', 'peut_voir_classement_peage_rendement',
            'peut_voir_classement_station_pesage', 'peut_voir_classement_peage_deperdition',
            'peut_voir_classement_agents_inventaire',
            # Autres
            'peut_parametrage_global', 'peut_voir_compte_emploi',
            'peut_voir_pv_confrontation', 'peut_authentifier_document',
            'peut_voir_tous_postes',
        ]
        
        perms = {}
        for field in PERMISSION_FIELDS:
            perms[field] = getattr(user, field, None)
        return perms
    
    def _list_habilitations(self):
        """Affiche la liste des habilitations reconnues."""
        self.stdout.write(self.style.HTTP_INFO(
            f"\n{'='*70}\n"
            f"  HABILITATIONS RECONNUES (16 au total)\n"
            f"{'='*70}\n"
        ))
        
        self.stdout.write(self.style.SUCCESS("\n  HABILITATIONS PESAGE (station pesage obligatoire):"))
        for hab in self.HABILITATIONS_PESAGE:
            label = self.HABILITATIONS_VALIDES[hab]
            count = UtilisateurSUPPER.objects.filter(habilitation=hab).count()
            self.stdout.write(f"    • {hab}: {label} ({count} utilisateurs)")
        
        self.stdout.write(self.style.SUCCESS("\n  HABILITATIONS PÉAGE (poste péage obligatoire):"))
        for hab in self.HABILITATIONS_PEAGE:
            label = self.HABILITATIONS_VALIDES[hab]
            count = UtilisateurSUPPER.objects.filter(habilitation=hab).count()
            self.stdout.write(f"    • {hab}: {label} ({count} utilisateurs)")
        
        self.stdout.write(self.style.SUCCESS("\n  HABILITATIONS MULTI-POSTES (pas de poste obligatoire):"))
        for hab in self.HABILITATIONS_MULTI_POSTES:
            label = self.HABILITATIONS_VALIDES[hab]
            count = UtilisateurSUPPER.objects.filter(habilitation=hab).count()
            self.stdout.write(f"    • {hab}: {label} ({count} utilisateurs)")
        
        self.stdout.write("")
    
    def _show_matrix(self):
        """Affiche la matrice des permissions par habilitation."""
        self.stdout.write(self.style.HTTP_INFO(
            f"\n{'='*70}\n"
            f"  MATRICE DES PERMISSIONS PAR HABILITATION\n"
            f"{'='*70}\n"
        ))
        
        # Créer un utilisateur temporaire pour chaque habilitation
        for hab_code, hab_label in self.HABILITATIONS_VALIDES.items():
            self.stdout.write(self.style.SUCCESS(f"\n  {hab_label} ({hab_code}):"))
            
            # Créer un utilisateur fictif
            temp_user = UtilisateurSUPPER(habilitation=hab_code)
            
            # Réinitialiser et configurer
            if hasattr(temp_user, '_reinitialiser_toutes_permissions'):
                temp_user._reinitialiser_toutes_permissions()
            if hasattr(temp_user, 'attribuer_permissions_automatiques'):
                temp_user.attribuer_permissions_automatiques()
            
            # Lister les permissions actives
            perms = self._capture_permissions(temp_user)
            active_perms = [p for p, v in perms.items() if v]
            
            if active_perms:
                for perm in sorted(active_perms)[:20]:  # Limiter à 20
                    self.stdout.write(f"    ✓ {perm}")
                if len(active_perms) > 20:
                    self.stdout.write(f"    ... et {len(active_perms) - 20} autres")
            else:
                self.stdout.write("    (aucune permission active)")
    
    def _export_csv(self, filename, data):
        """Exporte les résultats dans un fichier CSV."""
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Matricule', 'Nom', 'Habilitation', 'Status', 'Nb Changements', 'Détails'])
                
                for item in data:
                    changes_str = '; '.join([
                        f"{c['permission']}: {c['old']} → {c['new']}"
                        for c in item.get('changes', [])[:5]
                    ])
                    
                    writer.writerow([
                        item['username'],
                        item['nom'],
                        item['habilitation'],
                        item['status'],
                        len(item.get('changes', [])),
                        changes_str,
                    ])
            
            self.stdout.write(self.style.SUCCESS(f"\n  Export réussi: {filename}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n  Erreur export: {e}"))