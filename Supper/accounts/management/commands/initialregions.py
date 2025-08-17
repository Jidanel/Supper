from django.core.management.base import BaseCommand
from accounts.models import Region, Departement

class Command(BaseCommand):
    help = 'Initialise les régions et départements du Cameroun'

    def handle(self, *args, **options):
        data = {
            "Adamawa": [
                "Djérem", "Faro-et-Déo", "Mayo-Banyo", "Mbéré", "Vina"
            ],
            "Centre": [
                "Haute-Sanaga", "Lekié", "Mbam-et-Inoubou", "Mbam-et-Kim",
                "Méfou-et-Afamba", "Méfou-et-Akono", "Mfoundi",
                "Nyong-et-Kéllé", "Nyong-et-Mfoumou", "Nyong-et-So'o",
            ],
            "Est": [
                "Boumba-et-Ngoko", "Haut-Nyong", "Kadey", "Lom-et-Djérem"
            ],
            "Extrême-Nord": [
                "Diamaré", "Logone-et-Chari", "Mayo-Danay",
                "Mayo-Kani", "Mayo-Sava", "Mayo-Tsanaga"
            ],
            "Littoral": [
                "Moungo", "Nkam", "Sanaga-Maritime", "Wouri"
            ],
            "Nord": [
                "Bénoué", "Faro", "Mayo-Louti", "Mayo-Rey",
                "Faro-et-Déo", "Diamaré"
            ],
            "Nord-Ouest": [
                "Bui", "Donga-Mantung", "Momo", "Mezam", "Menchum"
            ],
            "Ouest": [
                "Bamboutos", "Bamoun", "Haut-Nkam", "Menoua",
                "Mifi", "Ndé"
            ],
            "Sud": [
                "Ocean", "Vallee-du-Ntem", "Dja-et-Lobo"
            ],
            "Sud-Ouest": [
                "Fako", "Kupe-Manengouba", "Lebialem", "Manyu",
                "Meme"
            ],
        }

        self.stdout.write('Initialisation des régions et départements...')
        for region_name, departements in data.items():
            region, created = Region.objects.get_or_create(nom=region_name)
            for dep_name in departements:
                Departement.objects.get_or_create(region=region, nom=dep_name)
        self.stdout.write(self.style.SUCCESS('Initialisation terminée.'))
