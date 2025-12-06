#supper/accounts/management/commands/populate_regions.py
from django.core.management.base import BaseCommand
from accounts.models import Region, Departement

class Command(BaseCommand):
    help = 'Peuple les régions et départements du Cameroun'

    def handle(self, *args, **options):
        REGIONS_DEPARTEMENTS = {
            'Adamaoua': ['Djérem', 'Faro-et-Déo', 'Mayo-Banyo', 'Mbéré', 'Vina'],
            'Centre': ['Haute-Sanaga', 'Lekié', 'Mbam-et-Inoubou', 'Mbam-et-Kim',
                      'Méfou-et-Afamba', 'Méfou-et-Akono', 'Mfoundi', 'Nyong-et-Kellé',
                      'Nyong-et-Mfoumou', 'Nyong-et-So\'o'],
            'Est': ['Boumba-et-Ngoko', 'Haut-Nyong', 'Kadey', 'Lom-et-Djérem'],
            'Extrême-Nord': ['Diamaré', 'Logone-et-Chari', 'Mayo-Danay', 'Mayo-Kani',
                            'Mayo-Sava', 'Mayo-Tsanaga'],
            'Littoral': ['Moungo', 'Nkam', 'Sanaga-Maritime', 'Wouri'],
            'Nord': ['Bénoué', 'Faro', 'Mayo-Louti', 'Mayo-Rey'],
            'Nord-Ouest': ['Boyo', 'Bui', 'Donga-Mantung', 'Menchum', 'Mezam',
                          'Momo', 'Ngo-Ketunjia'],
            'Ouest': ['Bamboutos', 'Haut-Nkam', 'Hauts-Plateaux', 'Koung-Khi',
                     'Menoua', 'Mifi', 'Ndé', 'Noun'],
            'Sud': ['Dja-et-Lobo', 'Mvila', 'Océan', 'Vallée-du-Ntem'],
            'Sud-Ouest': ['Fako', 'Koupé-Manengouba', 'Lebialem', 'Manyu', 'Meme', 'Ndian']
        }
        
        for region_nom, departements in REGIONS_DEPARTEMENTS.items():
            region, created = Region.objects.get_or_create(nom=region_nom)
            if created:
                self.stdout.write(f"Région créée: {region_nom}")
            
            for dept_nom in departements:
                dept, created = Departement.objects.get_or_create(
                    nom=dept_nom,
                    region=region
                )
                if created:
                    self.stdout.write(f"  - Département créé: {dept_nom}")
        
        self.stdout.write(self.style.SUCCESS('Régions et départements chargés avec succès!'))