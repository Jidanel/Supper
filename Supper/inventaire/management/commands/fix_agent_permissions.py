# ===================================================================
# accounts/management/commands/fix_agent_permissions.py
# Commande Django pour corriger les permissions des agents d'inventaire
# ===================================================================
"""
UTILISATION:
    python manage.py fix_agent_permissions

OPTIONS:
    --dry-run       Affiche ce qui serait fait sans modifier la base
    --username      Corriger un seul agent par son username
    --all           Corriger tous les agents (par défaut)
    --verbose       Afficher les détails complets
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounts.models import UtilisateurSUPPER
from common.permissions import has_permission


class Command(BaseCommand):
    help = 'Corrige les permissions des agents d\'inventaire'
    
    def add_arguments(self, parser):
        """Définir les arguments de la commande"""
        parser.add_argument(
            '--username',
            type=str,
            help='Username de l\'agent à corriger (un seul)',
        )
        
        parser.add_argument(
            '--all',
            action='store_true',
            help='Corriger tous les agents d\'inventaire actifs',
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simuler sans modifier la base de données',
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Afficher les détails complets',
        )
    
    def handle(self, *args, **options):
        """Exécution principale de la commande"""
        
        # Styles de sortie
        self.style.SUCCESS = self.style.SUCCESS
        self.style.ERROR = self.style.ERROR
        self.style.WARNING = self.style.WARNING
        
        # Options
        username = options.get('username')
        all_agents = options.get('all')
        dry_run = options.get('dry_run')
        verbose = options.get('verbose')
        
        # En-tête
        self.stdout.write("="*80)
        self.stdout.write(self.style.SUCCESS("CORRECTION DES PERMISSIONS - AGENTS D'INVENTAIRE"))
        self.stdout.write("="*80)
        
        if dry_run:
            self.stdout.write(self.style.WARNING("\n⚠️  MODE DRY-RUN - Aucune modification ne sera effectuée\n"))
        
        # Déterminer les agents à corriger
        try:
            if username:
                agents = UtilisateurSUPPER.objects.filter(
                    username=username,
                    habilitation='agent_inventaire'
                )
                if not agents.exists():
                    raise CommandError(
                        f"Agent d'inventaire '{username}' non trouvé. "
                        f"Vérifiez le username et l'habilitation."
                    )
            else:
                # Par défaut, tous les agents actifs
                agents = UtilisateurSUPPER.objects.filter(
                    habilitation='agent_inventaire',
                    is_active=True
                )
        except Exception as e:
            raise CommandError(f"Erreur lors de la récupération des agents: {str(e)}")
        
        # Afficher le nombre d'agents
        self.stdout.write(f"\n📊 Agents d'inventaire trouvés: {agents.count()}")
        
        if agents.count() == 0:
            self.stdout.write(self.style.WARNING("\n⚠️  Aucun agent d'inventaire actif trouvé"))
            return
        
        # État AVANT correction
        self.stdout.write("\n" + "="*80)
        self.stdout.write("ÉTAT AVANT CORRECTION")
        self.stdout.write("="*80)
        self.afficher_etat_agents(agents, verbose)
        
        # Correction
        self.stdout.write("\n" + "="*80)
        self.stdout.write("CORRECTION EN COURS...")
        self.stdout.write("="*80)
        
        corriges = 0
        erreurs = 0
        
        for agent in agents:
            try:
                if self.corriger_agent(agent, dry_run, verbose):
                    corriges += 1
            except Exception as e:
                erreurs += 1
                self.stdout.write(
                    self.style.ERROR(f"❌ Erreur pour {agent.username}: {str(e)}")
                )
        
        # État APRÈS correction
        if not dry_run:
            # Recharger depuis la base
            agents = agents.all()  # Force reload
            
            self.stdout.write("\n" + "="*80)
            self.stdout.write("ÉTAT APRÈS CORRECTION")
            self.stdout.write("="*80)
            self.afficher_etat_agents(agents, verbose)
        
        # Résumé
        self.stdout.write("\n" + "="*80)
        self.stdout.write("RÉSUMÉ")
        self.stdout.write("="*80)
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"🔍 Mode dry-run: {corriges} agent(s) seraient corrigé(s)")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"✅ Agents corrigés: {corriges}/{agents.count()}")
            )
            if erreurs > 0:
                self.stdout.write(
                    self.style.ERROR(f"❌ Erreurs: {erreurs}")
                )
        
        # Vérification finale
        if not dry_run and corriges > 0:
            self.verifier_permissions_finales(agents)
    
    def afficher_etat_agents(self, agents, verbose):
        """Affiche l'état des permissions des agents"""
        
        # En-tête du tableau
        if verbose:
            self.stdout.write(
                f"{'Username':<15} {'Nom':<25} {'Saisie':<8} {'Liste':<8} {'Legacy':<8} {'Status'}"
            )
            self.stdout.write("-"*80)
        else:
            self.stdout.write(
                f"{'Username':<15} {'Nom':<30} {'Status'}"
            )
            self.stdout.write("-"*80)
        
        for agent in agents:
            saisie = agent.peut_saisir_inventaire_normal
            liste = agent.peut_voir_liste_inventaires
            legacy = agent.peut_gerer_inventaire
            
            # Déterminer le status
            if saisie and liste and legacy:
                status = self.style.SUCCESS("✅ OK")
            else:
                status = self.style.ERROR("❌ Manque")
            
            if verbose:
                saisie_str = "✅" if saisie else "❌"
                liste_str = "✅" if liste else "❌"
                legacy_str = "✅" if legacy else "❌"
                
                self.stdout.write(
                    f"{agent.username:<15} {agent.nom_complet:<25} "
                    f"{saisie_str:<8} {liste_str:<8} {legacy_str:<8} {status}"
                )
            else:
                self.stdout.write(
                    f"{agent.username:<15} {agent.nom_complet:<30} {status}"
                )
    
    def corriger_agent(self, agent, dry_run, verbose):
        """
        Corrige les permissions d'un agent.
        Retourne True si des modifications ont été faites.
        """
        
        if verbose or dry_run:
            self.stdout.write(f"\n📝 {agent.username} - {agent.nom_complet}")
        
        modifie = False
        changements = []
        
        # ===== PERMISSIONS À ACTIVER =====
        
        permissions_a_activer = [
            ('peut_saisir_inventaire_normal', 'Saisie inventaire normal'),
            ('peut_voir_liste_inventaires', 'Voir liste inventaires'),
            ('peut_voir_jours_impertinents', 'Voir jours impertinents'),
            ('peut_voir_stats_deperdition', 'Voir stats déperdition'),
            ('voir_taux_deperdition', 'Voir taux déperdition'),
            ('peut_gerer_inventaire', 'Gérer inventaire (legacy)'),
        ]
        
        for field, label in permissions_a_activer:
            if not getattr(agent, field):
                if not dry_run:
                    setattr(agent, field, True)
                changements.append(f"✅ Activé: {label}")
                modifie = True
        
        # ===== PERMISSIONS À DÉSACTIVER =====
        
        permissions_a_desactiver = [
            ('peut_saisir_inventaire_admin', 'Saisie inventaire admin'),
            ('peut_voir_liste_inventaires_admin', 'Voir liste inventaires admin'),
        ]
        
        for field, label in permissions_a_desactiver:
            if getattr(agent, field):
                if not dry_run:
                    setattr(agent, field, False)
                changements.append(f"⚠️  Désactivé: {label}")
                modifie = True
        
        # ===== SAUVEGARDER =====
        
        if modifie:
            if not dry_run:
                agent.save()
            
            if verbose or dry_run:
                for c in changements:
                    self.stdout.write(f"   {c}")
                
                if not dry_run:
                    self.stdout.write(
                        self.style.SUCCESS(f"   💾 Sauvegardé en base de données")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"   🔍 Serait sauvegardé (dry-run)")
                    )
        else:
            if verbose:
                self.stdout.write(
                    self.style.SUCCESS(f"   ℹ️  Déjà configuré correctement")
                )
        
        return modifie
    
    def verifier_permissions_finales(self, agents):
        """Vérifie que toutes les permissions sont correctes"""
        
        self.stdout.write("\n" + "="*80)
        self.stdout.write("VÉRIFICATION FINALE avec has_permission()")
        self.stdout.write("="*80)
        
        tous_ok = True
        
        for agent in agents:
            # Tests
            test_saisie = has_permission(agent, 'peut_saisir_inventaire_normal')
            test_legacy = has_permission(agent, 'peut_gerer_inventaire')
            
            if test_saisie and test_legacy:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ {agent.username:<15} Normal: {test_saisie}, Legacy: {test_legacy}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"❌ {agent.username:<15} Normal: {test_saisie}, Legacy: {test_legacy}"
                    )
                )
                tous_ok = False
        
        self.stdout.write("\n" + "="*80)
        
        if tous_ok:
            self.stdout.write(
                self.style.SUCCESS(
                    "🎉 SUCCÈS COMPLET ! Tous les agents ont les bonnes permissions"
                )
            )
            self.stdout.write("\n📋 Permissions activées pour chaque agent:")
            self.stdout.write("   ✅ peut_saisir_inventaire_normal")
            self.stdout.write("   ✅ peut_voir_liste_inventaires")
            self.stdout.write("   ✅ peut_voir_jours_impertinents")
            self.stdout.write("   ✅ peut_voir_stats_deperdition")
            self.stdout.write("   ✅ voir_taux_deperdition")
            self.stdout.write("   ✅ peut_gerer_inventaire (legacy)")
        else:
            self.stdout.write(
                self.style.WARNING(
                    "⚠️  ATTENTION ! Certains agents ont encore des problèmes"
                )
            )
            self.stdout.write("\nRéexécuter avec --verbose pour plus de détails")