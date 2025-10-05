# ===================================================================
# accounts/admin.py - VERSION CORRIGÉE ET SIMPLIFIÉE
# ===================================================================

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponse
import csv
import logging

from .models import UtilisateurSUPPER, Poste, JournalAudit, NotificationUtilisateur

logger = logging.getLogger('supper')

# ===================================================================
# CONFIGURATION DU MODÈLE UTILISATEUR
# ===================================================================

@admin.register(UtilisateurSUPPER)
class UtilisateurSUPPERAdmin(UserAdmin):
    """Administration des utilisateurs SUPPER"""
    
    model = UtilisateurSUPPER
    
    # Liste d'affichage
    list_display = (
        'username', 
        'nom_complet', 
        'habilitation_badge', 
        'poste_affectation', 
        'is_active_badge',
        'date_creation'
    )
    
    list_filter = (
        'habilitation', 
        'is_active', 
        'is_staff',
        'is_superuser',
        'poste_affectation__region',
        'date_creation'
    )
    
    search_fields = ('username', 'nom_complet', 'telephone', 'email')
    ordering = ('-date_creation',)
    
    # Configuration des fieldsets pour le formulaire de modification
    fieldsets = (
        (None, {
            'fields': ('username', 'password')
        }),
        (_('Informations personnelles'), {
            'fields': ('nom_complet', 'telephone', 'email')
        }),
        (_('Affectation'), {
            'fields': ('poste_affectation', 'habilitation', 'acces_tous_postes')
        }),
        (_('Permissions système'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
        (_('Permissions métier'), {
            'fields': (
                'peut_saisir_peage', 'peut_saisir_pesage',
                'peut_gerer_peage', 'peut_gerer_pesage',
                'peut_gerer_personnel', 'peut_gerer_budget',
                'peut_gerer_inventaire', 'peut_gerer_archives',
                'peut_gerer_stocks_psrr', 'peut_gerer_stock_info'
            ),
            'classes': ('collapse',)
        }),
        (_('Dates importantes'), {
            'fields': ('last_login', 'date_joined', 'date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
        (_('Informations système'), {
            'fields': ('cree_par',),
            'classes': ('collapse',)
        }),
    )
    
    # Configuration pour l'ajout d'utilisateur
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'nom_complet', 'telephone', 
                'password1', 'password2',
                'habilitation', 'poste_affectation'
            ),
        }),
    )
    
    readonly_fields = ('date_creation', 'date_modification', 'last_login', 'date_joined')
    
    def habilitation_badge(self, obj):
        """Badge coloré pour l'habilitation"""
        colors = {
            'admin_principal': 'danger',
            'chef_peage': 'primary',
            'chef_pesage': 'primary',
            'focal_regional': 'info',
            'caissier': 'success',
            'agent_inventaire': 'secondary',
            'chef_service': 'warning',
            'coord_psrr': 'danger',
            'serv_info': 'info',
            'serv_emission': 'warning',
        }
        color = colors.get(obj.habilitation, 'secondary')
        
        # Obtenir le libellé depuis les choix du modèle
        display = obj.get_habilitation_display() if hasattr(obj, 'get_habilitation_display') else obj.habilitation
        
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, display
        )
    habilitation_badge.short_description = 'Habilitation'
    
    def is_active_badge(self, obj):
        """Badge pour le statut actif"""
        if obj.is_active:
            return format_html('<span class="badge bg-success">✓ Actif</span>')
        return format_html('<span class="badge bg-danger">✗ Inactif</span>')
    is_active_badge.short_description = 'Statut'
    
    def save_model(self, request, obj, form, change):
        """Logique personnalisée de sauvegarde"""
        if not change:  # Nouvelle création
            obj.cree_par = request.user
        super().save_model(request, obj, form, change)
        
        # Log de l'action
        action = "Modification utilisateur" if change else "Création utilisateur"
        JournalAudit.objects.create(
            utilisateur=request.user,
            action=action,
            details=f"Utilisateur: {obj.username} - {obj.nom_complet}",
            adresse_ip=request.META.get('REMOTE_ADDR'),
            succes=True
        )
    
    # Actions personnalisées
    actions = ['reset_password', 'activate_users', 'deactivate_users', 'export_users']
    
    def reset_password(self, request, queryset):
        """Réinitialiser les mots de passe"""
        count = 0
        for user in queryset:
            user.set_password('supper2025')
            user.save()
            count += 1
        
        self.message_user(request, f'✓ {count} mot(s) de passe réinitialisé(s) à "supper2025".')
        
        # Log de l'action
        JournalAudit.objects.create(
            utilisateur=request.user,
            action="Réinitialisation mots de passe",
            details=f"{count} utilisateur(s) concerné(s)",
            adresse_ip=request.META.get('REMOTE_ADDR'),
            succes=True
        )
    reset_password.short_description = '🔑 Réinitialiser les mots de passe'
    
    def activate_users(self, request, queryset):
        """Activer les utilisateurs"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'✓ {count} utilisateur(s) activé(s).')
    activate_users.short_description = '✓ Activer les utilisateurs'
    
    def deactivate_users(self, request, queryset):
        """Désactiver les utilisateurs"""
        count = queryset.update(is_active=False)
        self.message_user(request, f'✓ {count} utilisateur(s) désactivé(s).')
    deactivate_users.short_description = '✗ Désactiver les utilisateurs'
    
    def export_users(self, request, queryset):
        """Exporter en CSV"""
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="utilisateurs_supper.csv"'
        
        # BOM UTF-8 pour Excel
        response.write('\ufeff')
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Matricule', 'Nom complet', 'Téléphone', 'Email', 
            'Habilitation', 'Poste', 'Région', 'Actif', 'Date création'
        ])
        
        for user in queryset:
            writer.writerow([
                user.username,
                user.nom_complet,
                user.telephone,
                user.email or '',
                user.get_habilitation_display() if hasattr(user, 'get_habilitation_display') else user.habilitation,
                user.poste_affectation.nom if user.poste_affectation else '',
                user.poste_affectation.region if user.poste_affectation else '',
                'Oui' if user.is_active else 'Non',
                user.date_creation.strftime('%d/%m/%Y') if user.date_creation else ''
            ])
        
        return response
    export_users.short_description = '📥 Exporter en CSV'

# ===================================================================
# CONFIGURATION DU MODÈLE POSTE
# ===================================================================

@admin.register(Poste)
class PosteAdmin(admin.ModelAdmin):
    """Administration des postes"""
    
    list_display = (
        'nom', 'code', 'type_badge', 
        'region_display', 'departement', 
        'actif_badge', 
    )
    
    list_filter = ('type', 'region', 'is_active')
    search_fields = ('nom', 'code', 'region', 'departement')
    ordering = ('region', 'nom')
    
    fieldsets = (
        ('Informations générales', {
            'fields': ('nom', 'code', 'type', 'is_active')
        }),
        ('Localisation', {
            'fields': ('region', 'departement', 'axe_routier')
        }),
        ('Coordonnées GPS', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',)
        }),
        ('Informations complémentaires', {
            'fields': ('description',),
            'classes': ('collapse',)
        }),
        ('Métadonnées', {
            'fields': ('date_creation', 'date_modification'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('date_creation', 'date_modification')
    class Media:
        js = ('admin/js/region_departement.js',)
        
    def type_badge(self, obj):
        """Badge pour le type de poste"""
        colors = {
            'peage': 'success',
            'pesage': 'info'
        }
        color = colors.get(obj.type, 'secondary')
        display = obj.get_type_display() if hasattr(obj, 'get_type_display') else obj.type_poste
        
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, display
        )
    type_badge.short_description = 'Type'
    
    def region_display(self, obj):
        """Affichage de la région"""
        return obj.get_region_display() if hasattr(obj, 'get_region_display') else obj.region
    region_display.short_description = 'Région'
    
    def actif_badge(self, obj):
        """Badge pour le statut actif"""
        if obj.is_active:
            return format_html('<span class="badge bg-success">✓ Actif</span>')
        return format_html('<span class="badge bg-danger">✗ Inactif</span>')
    actif_badge.short_description = 'Statut'
    
    # Actions
    actions = ['activate_postes', 'deactivate_postes', 'export_postes']
    
    def activate_postes(self, request, queryset):
        """Activer les postes"""
        count = queryset.update(is_active=True)
        self.message_user(request, f'✓ {count} poste(s) activé(s).')
    activate_postes.short_description = '✓ Activer les postes'
    
    def deactivate_postes(self, request, queryset):
        """Désactiver les postes"""
        count = queryset.update(actif=False)
        self.message_user(request, f'✓ {count} poste(s) désactivé(s).')
    deactivate_postes.short_description = '✗ Désactiver les postes'
    
    def export_postes(self, request, queryset):
        """Exporter en CSV"""
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="postes_supper.csv"'
        
        # BOM UTF-8
        response.write('\ufeff')
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Code', 'Nom', 'Type', 'Région', 'Département', 
            'axe_routier', 'Localisation', 'Actif'
        ])
        
        for poste in queryset:
            writer.writerow([
                poste.code,
                poste.nom,
                poste.get_type_poste_display() if hasattr(poste, 'get_type_poste_display') else poste.type_poste,
                poste.get_region_display() if hasattr(poste, 'get_region_display') else poste.region,
                poste.departement,
                poste.axe_routier or '',
                poste.localisation,
                'Oui' if poste.actif else 'Non'
            ])
        
        return response
    export_postes.short_description = '📥 Exporter en CSV'

# ===================================================================
# CONFIGURATION DU JOURNAL D'AUDIT
# ===================================================================

@admin.register(JournalAudit)
class JournalAuditAdmin(admin.ModelAdmin):
    """Administration du journal d'audit"""
    
    list_display = (
        'timestamp', 'utilisateur', 'action', 
        'succes_badge', 'adresse_ip'
    )
    
    list_filter = ('succes', 'timestamp', 'action')
    search_fields = ('utilisateur__username', 'utilisateur__nom_complet', 'action', 'details')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    
    # Lecture seule pour tout
    readonly_fields = (
        'timestamp', 'utilisateur', 'action', 'details',
        'adresse_ip', 'user_agent', 'session_key',
        'url_acces', 'methode_http', 'duree_execution',
        'statut_reponse', 'succes'
    )
    
    def has_add_permission(self, request):
        """Interdire l'ajout manuel"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Interdire la modification"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Seuls les superusers peuvent supprimer"""
        return request.user.is_superuser
    
    def succes_badge(self, obj):
        """Badge pour le succès"""
        if obj.succes:
            return format_html('<span class="badge bg-success">✓ Succès</span>')
        return format_html('<span class="badge bg-danger">✗ Échec</span>')
    succes_badge.short_description = 'Résultat'
    
    # Actions
    actions = ['export_logs']
    
    def export_logs(self, request, queryset):
        """Exporter les logs"""
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="journal_audit_supper.csv"'
        
        # BOM UTF-8
        response.write('\ufeff')
        
        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Date/Heure', 'Utilisateur', 'Action', 'Détails',
            'IP', 'URL', 'Méthode', 'Succès'
        ])
        
        for log in queryset:
            writer.writerow([
                log.timestamp.strftime('%d/%m/%Y %H:%M:%S'),
                log.utilisateur.username if log.utilisateur else '',
                log.action,
                log.details[:100] if log.details else '',
                log.adresse_ip or '',
                log.url_acces or '',
                log.methode_http or '',
                'Oui' if log.succes else 'Non'
            ])
        
        return response
    export_logs.short_description = '📥 Exporter les logs'

# ===================================================================
# CONFIGURATION DES NOTIFICATIONS
# ===================================================================

@admin.register(NotificationUtilisateur)
class NotificationUtilisateurAdmin(admin.ModelAdmin):
    """Administration des notifications"""
    
    list_display = (
        'titre', 'destinataire', 'type_badge', 
        'lue_badge', 'date_creation'
    )
    
    list_filter = ('type_notification', 'lu', 'date_creation')
    search_fields = ('titre', 'message', 'destinataire__username')
    date_hierarchy = 'date_creation'
    ordering = ('-date_creation',)
    
    fieldsets = (
        ('Notification', {
            'fields': ('titre', 'message', 'type_notification')
        }),
        ('Destinataires', {
            'fields': ('destinataire', 'expediteur')
        }),
        ('Statut', {
            'fields': ('lue', 'date_lecture')
        }),
        ('Métadonnées', {
            'fields': ('date_creation',),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ('date_creation', 'date_lecture')
    
    def type_badge(self, obj):
        """Badge pour le type"""
        colors = {
            'info': 'info',
            'warning': 'warning',
            'error': 'danger',
            'success': 'success',
            'system': 'secondary'
        }
        color = colors.get(obj.type_notification, 'secondary')
        display = obj.get_type_notification_display() if hasattr(obj, 'get_type_notification_display') else obj.type_notification
        
        return format_html(
            '<span class="badge bg-{}">{}</span>',
            color, display
        )
    type_badge.short_description = 'Type'
    
    def lue_badge(self, obj):
        """Badge pour le statut de lecture"""
        if obj.lue:
            return format_html('<span class="badge bg-success">✓ Lue</span>')
        return format_html('<span class="badge bg-warning">⚠ Non lue</span>')
    lue_badge.short_description = 'Statut'
    
    def save_model(self, request, obj, form, change):
        """Définir l'expéditeur automatiquement"""
        if not change:  # Nouvelle notification
            obj.expediteur = request.user
        super().save_model(request, obj, form, change)
    
    # Actions
    actions = ['mark_as_read', 'mark_as_unread']
    
    def mark_as_read(self, request, queryset):
        """Marquer comme lues"""
        count = queryset.update(lue=True)
        self.message_user(request, f'✓ {count} notification(s) marquée(s) comme lue(s).')
    mark_as_read.short_description = '✓ Marquer comme lues'
    
    def mark_as_unread(self, request, queryset):
        """Marquer comme non lues"""
        count = queryset.update(lue=False)
        self.message_user(request, f'✓ {count} notification(s) marquée(s) comme non lue(s).')
    mark_as_unread.short_description = '⚠ Marquer comme non lues'

# ===================================================================
# CONFIGURATION DU SITE ADMIN
# ===================================================================

# Personnalisation du site admin
admin.site.site_header = 'SUPPER - Administration'
admin.site.site_title = 'SUPPER Admin'
admin.site.index_title = 'Tableau de bord'

# Essayer de retirer Group s'il est enregistré
try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass