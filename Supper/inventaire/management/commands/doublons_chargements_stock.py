# Commande : python manage.py doublons_chargements_stock [--poste NOM] [--appliquer] [--sans-debit]
# Détecte les tickets CHARGÉS DEUX FOIS (Imprimerie Nationale / régularisation) dans une même année :
# une ligne « EN STOCK » dont les numéros ont déjà été chargés par un autre chargement (ligne vendue, transférée,
# ou ligne en stock plus ancienne, même couleur, même année).
# Par défaut : LECTURE SEULE (rapport). Avec --appliquer : retire du stock les numéros en doublon.
#   - seules les lignes EN STOCK sont modifiées (jamais une ligne vendue ou transférée) ;
#   - le débit correspondant est écrit dans l'historique (correction au 1er du mois en cours, mois signés ignorés) ;
#   - une sauvegarde JSON des lignes touchées est écrite avant toute modification.

import json  # Sauvegarde des lignes modifiées
from collections import defaultdict  # Regroupements
from decimal import Decimal  # Montants exacts

from django.core.management.base import BaseCommand  # Base des commandes
from django.db import transaction  # Tout ou rien par ligne
from django.utils import timezone  # Horodatage

from inventaire.models import GestionStock, HistoriqueStock, SerieTicket, StockEvent  # Modèles de stock
from inventaire.services.date_effet import DateEffetError, datetime_effet, debut_du_mois, verifier_date_effet  # Date d'effet
from inventaire.services.permutation_service import _isoler  # Découpe d'une série

PRIX = 500  # Valeur d'un ticket (FCFA)
TYPES_CHARGEMENT = ['imprimerie_nationale', 'regularisation']  # Chargements initiaux (pas les transferts reçus)


def _fusionner(intervalles):
    """Fusionne des intervalles (p, d) qui se touchent ou se chevauchent."""
    res = []
    for p, d in sorted(intervalles):
        if res and p <= res[-1][1] + 1:
            res[-1] = (res[-1][0], max(res[-1][1], d))  # Prolonge l'intervalle précédent
        else:
            res.append((p, d))
    return res


def _chargement_identique(a, b):
    """Deux lignes issues du MÊME chargement (découpes d'une même série) ne sont pas des doublons."""
    return a.date_reception == b.date_reception and a.historique_source_id == b.historique_source_id


def detecter(poste_filtre=None):
    """Retourne la liste des doublons : [{'serie': ligne en stock, 'plages': [(p, d)], 'originaux': [lignes]}]."""
    stock = SerieTicket.objects.filter(statut='stock', type_entree__in=TYPES_CHARGEMENT).select_related('poste', 'couleur')
    if poste_filtre:
        stock = stock.filter(poste__nom__icontains=poste_filtre)
    resultats = []
    for s in stock.order_by('poste__nom', 'couleur_id', 'numero_premier').iterator():
        voisines = SerieTicket.objects.filter(
            couleur=s.couleur, type_entree__in=TYPES_CHARGEMENT, date_reception__year=s.date_reception.year,
            numero_premier__lte=s.numero_dernier, numero_dernier__gte=s.numero_premier,
        ).exclude(pk=s.pk).select_related('poste')
        plages, originaux = [], []
        for o in voisines:
            if _chargement_identique(s, o):
                continue  # Même chargement : pas un doublon
            if o.statut in ('vendu', 'transfere') or (o.statut == 'stock' and (o.date_reception, o.pk) < (s.date_reception, s.pk)):
                plages.append((max(s.numero_premier, o.numero_premier), min(s.numero_dernier, o.numero_dernier)))
                originaux.append(o)  # Chargement antérieur (ou ligne déjà consommée) qui couvre ces numéros
        if plages:
            resultats.append({'serie': s, 'plages': _fusionner(plages), 'originaux': originaux})
    return resultats


class Command(BaseCommand):
    help = "Détecte (et avec --appliquer retire) les tickets chargés deux fois dans une même année."

    def add_arguments(self, parser):
        parser.add_argument('--poste', help="Limiter à un poste (partie du nom)")
        parser.add_argument('--appliquer', action='store_true', help="Retire réellement les numéros en doublon du stock")
        parser.add_argument('--sans-debit', action='store_true',
                            help="Ne pas écrire de débit dans l'historique (si le doublon n'avait jamais été crédité)")

    def handle(self, *args, **options):
        doublons = detecter(options.get('poste'))
        if not doublons:
            self.stdout.write(self.style.SUCCESS("✅ Aucun ticket chargé deux fois."))
            return
        par_poste, total = defaultdict(int), 0
        for d in doublons:
            s, plages = d['serie'], d['plages']
            nb = sum(y - x + 1 for x, y in plages)
            par_poste[s.poste.nom] += nb
            total += nb
            self.stdout.write(f"\n{s.poste.nom} | {s.couleur.libelle_affichage} | ligne #{s.pk} {s.numero_premier}-{s.numero_dernier} "
                              f"({s.nombre_tickets} tickets) chargée le {s.date_reception:%d/%m/%Y %H:%M} [{s.type_entree}] "
                              f"source historique : {s.historique_source_id or 'AUCUNE'}")
            self.stdout.write(f"   DOUBLON : {', '.join(f'{x}-{y}' for x, y in plages)} = {nb} tickets ({nb * PRIX:,.0f} F)")
            for o in d['originaux'][:4]:
                self.stdout.write(f"   déjà chargé : {o.numero_premier}-{o.numero_dernier} au poste {o.poste.nom}, statut {o.statut}, "
                                  f"chargé le {o.date_reception:%d/%m/%Y %H:%M} [{o.type_entree}]")
        self.stdout.write(self.style.WARNING("\n=== TOTAL PAR POSTE ==="))
        for nom, nb in sorted(par_poste.items(), key=lambda x: -x[1]):
            self.stdout.write(f"{nom:<25} {nb:>8} tickets | {nb * PRIX:>14,.0f} F")
        self.stdout.write(self.style.WARNING(f"Total : {total} tickets = {total * PRIX:,.0f} F dans {len(par_poste)} poste(s)."))
        if not options['appliquer']:
            self.stdout.write("\nLecture seule. Pour retirer ces doublons : relancer avec --appliquer (de préférence poste par poste avec --poste).")
            return
        self.appliquer(doublons, options['sans_debit'])

    def appliquer(self, doublons, sans_debit):
        """Retire les plages en doublon : découpe la ligne, supprime la plage, débite l'historique (1er du mois)."""
        sauvegarde = [{'pk': d['serie'].pk, 'poste': d['serie'].poste.nom, 'couleur': d['serie'].couleur.libelle_affichage,
                       'premier': d['serie'].numero_premier, 'dernier': d['serie'].numero_dernier,
                       'date_reception': d['serie'].date_reception.isoformat(), 'type_entree': d['serie'].type_entree,
                       'historique_source': d['serie'].historique_source_id, 'plages_retirees': d['plages']} for d in doublons]
        fichier = f"doublons_chargements_{timezone.localtime():%Y%m%d_%H%M}.json"
        with open(fichier, 'w', encoding='utf-8') as f:
            json.dump(sauvegarde, f, ensure_ascii=False, indent=2)  # Trace des lignes avant modification
        self.stdout.write(self.style.SUCCESS(f"\nSauvegarde écrite : {fichier}"))
        jour_effet = debut_du_mois(timezone.localdate())
        retires = ignores = 0
        for d in doublons:
            s = d['serie']
            try:
                verifier_date_effet(s.poste, jour_effet)  # Mois signé -> on ne touche pas
            except DateEffetError as exc:
                self.stdout.write(self.style.ERROR(f"IGNORÉ {s.poste.nom} ligne #{s.pk} : {exc}"))
                ignores += 1
                continue
            with transaction.atomic():
                nb_total = 0
                for x, y in d['plages']:
                    # Ligne en stock qui contient encore la plage (les découpes précédentes ont pu la scinder)
                    ligne = SerieTicket.objects.select_for_update().filter(
                        poste=s.poste, couleur=s.couleur, statut='stock', type_entree=s.type_entree,
                        date_reception=s.date_reception, numero_premier__lte=x, numero_dernier__gte=y).first()
                    if ligne is None:
                        continue  # Déjà retirée
                    _isoler(ligne, x, y).delete()  # Isole puis supprime la plage en doublon
                    nb_total += y - x + 1
                if nb_total and not sans_debit and s.historique_source_id:
                    valeur = Decimal(nb_total * PRIX)
                    gs, _c = GestionStock.objects.select_for_update().get_or_create(poste=s.poste, defaults={'valeur_monetaire': Decimal('0')})
                    avant = gs.valeur_monetaire
                    gs.valeur_monetaire = avant - valeur
                    gs.save()
                    effet = datetime_effet(jour_effet)
                    com = (f"Suppression administrative : doublon de chargement {s.couleur.libelle_affichage} "
                           f"{', '.join(f'#{x}-{y}' for x, y in d['plages'])}")[:500]
                    HistoriqueStock.objects.create(
                        poste=s.poste, type_mouvement='DEBIT', type_stock='regularisation', montant=valeur, nombre_tickets=nb_total,
                        stock_avant=avant, stock_apres=gs.valeur_monetaire, commentaire=com, date_mouvement=effet, est_correction=True)
                    StockEvent.objects.create(
                        poste=s.poste, event_type='AJUSTEMENT', event_datetime=effet, montant_variation=-valeur,
                        nombre_tickets_variation=-nb_total, stock_resultant=gs.valeur_monetaire,
                        tickets_resultants=int(gs.valeur_monetaire / 500), commentaire=com)
                elif nb_total:
                    self.stdout.write(f"   (aucun débit écrit pour {s.poste.nom} ligne #{s.pk} : pas de source d'historique ou --sans-debit)")
                retires += nb_total
        self.stdout.write(self.style.SUCCESS(f"\nTerminé : {retires} tickets retirés ({retires * PRIX:,.0f} F), {ignores} ligne(s) ignorée(s) (mois signé)."))
        self.stdout.write("Relancer ensuite la page « Cohérence du stock » pour vérifier les écarts.")
