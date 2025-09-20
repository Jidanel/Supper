from datetime import date, timedelta
from django.db.models import Avg, Q, Count

def calculer_taux_deperdition_periode(poste, date_debut, date_fin, exclure_impertinents=True):
    """Calcule le taux de déperdition moyen pour une période"""
    from .models import RecetteJournaliere, ConfigurationJour
    
    query = RecetteJournaliere.objects.filter(
        poste=poste,
        date__range=[date_debut, date_fin],
        taux_deperdition__isnull=False
    )
    
    if exclure_impertinents:
        # Exclure les jours impertinents
        jours_impertinents = ConfigurationJour.objects.filter(
            statut='impertinent',
            date__range=[date_debut, date_fin]
        ).values_list('date', flat=True)
        
        query = query.exclude(date__in=jours_impertinents)
    
    return query.aggregate(
        taux_moyen=Avg('taux_deperdition'),
        nombre_jours=Count('id')
    )

def generer_statistiques_taux(poste=None, annee=None):
    """Génère les statistiques de taux pour graphiques"""
    if not annee:
        annee = date.today().year
    
    stats = {
        'journalier': [],
        'hebdomadaire': [],
        'mensuel': [],
        'trimestriel': [],
        'semestriel': [],
        'annuel': None
    }
    
    # Calculer pour chaque mois
    for mois in range(1, 13):
        date_debut = date(annee, mois, 1)
        if mois == 12:
            date_fin = date(annee, 12, 31)
        else:
            date_fin = date(annee, mois + 1, 1) - timedelta(days=1)
        
        result = calculer_taux_deperdition_periode(
            poste, date_debut, date_fin
        )
        
        stats['mensuel'].append({
            'mois': mois,
            'taux': result['taux_moyen'],
            'nombre_jours': result['nombre_jours']
        })
    
    return stats