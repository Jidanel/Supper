from inventaire.models_pesage import PeseesJournalieres
from django.db.models import Q
from django.utils import timezone
from datetime import date
 
print("=" * 70)
print("DIAGNOSTIC: Recherche des PeseesJournalieres avec date NULL")
print("=" * 70)
 
# Rechercher tous les enregistrements avec date=NULL
pesees_sans_date = PeseesJournalieres.objects.filter(date__isnull=True)
count = pesees_sans_date.count()
 
print(f"\n📊 Nombre d'enregistrements avec date=NULL: {count}")
 
if count > 0:
    print("\n📋 Détail des enregistrements problématiques:")
    print("-" * 70)
    
    for pesee in pesees_sans_date:
        print(f"""
    ID: {pesee.pk}
    Station: {pesee.station.nom if pesee.station else 'N/A'}
    Nombre pesées: {pesee.nombre_pesees}
    Date saisie: {pesee.date_saisie}
    Saisi par: {pesee.saisi_par.username if pesee.saisi_par else 'N/A'}
    Observations: {pesee.observations[:50] if pesee.observations else 'Aucune'}...
        """)
    
    print("-" * 70)
    print("\n⚠️  OPTIONS DE CORRECTION:")
    print("""
    OPTION 1 - Corriger avec la date de saisie:
    --------------------------------------------
    for pesee in PeseesJournalieres.objects.filter(date__isnull=True):
        if pesee.date_saisie:
            pesee.date = pesee.date_saisie.date()
            pesee.save(update_fields=['date'])
            print(f"✅ Pesée {pesee.pk} corrigée avec date: {pesee.date}")
    
    OPTION 2 - Supprimer les enregistrements invalides:
    ----------------------------------------------------
    PeseesJournalieres.objects.filter(date__isnull=True).delete()
    print("✅ Enregistrements invalides supprimés")
    
    OPTION 3 - Corriger avec une date spécifique (pour pk=155):
    -----------------------------------------------------------
    pesee = PeseesJournalieres.objects.get(pk=155)
    pesee.date = date(2026, 3, 15)  # Remplacer par la bonne date
    pesee.save(update_fields=['date'])
    print(f"✅ Pesée {pesee.pk} corrigée")
    """)
else:
    print("\n✅ Aucun enregistrement avec date NULL trouvé.")
    print("   Le problème a peut-être déjà été corrigé ou l'ID 155 a une autre anomalie.")
    
    # Vérifier spécifiquement l'ID 155
    print("\n📌 Vérification de l'enregistrement ID 155:")
    try:
        pesee_155 = PeseesJournalieres.objects.get(pk=155)
        print(f"    - Date: {pesee_155.date}")
        print(f"    - Station: {pesee_155.station.nom if pesee_155.station else 'N/A'}")
        print(f"    - Nombre pesées: {pesee_155.nombre_pesees}")
        
        if pesee_155.date is None:
            print("    ⚠️ La date est bien NULL!")
        else:
            print("    ✅ La date est valide")
    except PeseesJournalieres.DoesNotExist:
        print("    ⚠️ L'enregistrement ID 155 n'existe pas")
 
print("\n" + "=" * 70)
print("FIN DU DIAGNOSTIC")
print("=" * 70)