# ===================================================================
# Créer ce fichier : inventaire/migrations/0008_fix_configurationjour_final.py
# ===================================================================

from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('inventaire', '0007_remove_configurationjour_inventaire__poste_i_c1aa75_idx_and_more'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        # 1. Supprimer l'ancienne contrainte unique qui pose problème
        migrations.RemoveConstraint(
            model_name='configurationjour',
            name='unique_date_configuration',
        ),
        
        # 2. Modifier le champ poste pour permettre NULL (configurations globales)
        migrations.AlterField(
            model_name='configurationjour',
            name='poste',
            field=models.ForeignKey(
                blank=True,
                help_text='Si spécifié, la configuration ne s\'applique qu\'à ce poste. Si vide, s\'applique à tous les postes.',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='configurations_jours',
                to='accounts.poste',
                verbose_name='Poste'
            ),
        ),
        
        # 3. S'assurer que les champs permet_saisie existent (au cas où)
        # Note: Ils existent déjà selon votre migration 0006, mais on s'assure qu'ils ont les bonnes valeurs par défaut
        migrations.RunSQL(
            """
            UPDATE inventaire_configurationjour 
            SET permet_saisie_inventaire = true 
            WHERE permet_saisie_inventaire IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop
        ),
        
        migrations.RunSQL(
            """
            UPDATE inventaire_configurationjour 
            SET permet_saisie_recette = true 
            WHERE permet_saisie_recette IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop
        ),
        
        # 4. Ajouter les nouveaux index optimisés
        migrations.AddIndex(
            model_name='configurationjour',
            index=models.Index(fields=['poste', 'date'], name='inventaire_config_poste_date_idx'),
        ),
        
        migrations.AddIndex(
            model_name='configurationjour',
            index=models.Index(fields=['date', 'statut'], name='inventaire_config_date_statut_idx'),
        ),
        
        # 5. Ajouter la nouvelle contrainte permettant configuration globale + spécifique par poste
        migrations.AddConstraint(
            model_name='configurationjour',
            constraint=models.UniqueConstraint(
                fields=['date', 'poste'], 
                name='unique_date_poste_configuration',
                condition=models.Q(poste__isnull=False)
            ),
        ),
        
        # 6. Contrainte pour s'assurer qu'il n'y a qu'une seule configuration globale par date
        migrations.AddConstraint(
            model_name='configurationjour',
            constraint=models.UniqueConstraint(
                fields=['date'], 
                name='unique_date_global_configuration',
                condition=models.Q(poste__isnull=True)
            ),
        ),
    ]