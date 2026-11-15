# inventaire/services/authentification.py
# ===================================================================
# SERVICE D'AUTHENTIFICATION DES DOCUMENTS
# Retrouve un document SUPPER à partir de son numéro et renvoie TOUS ses
# éléments (numéro, poste, dates, montants, auteur...) sous une forme unique
# que le gabarit affiche sans connaître le type de document.
# Documents pris en charge :
#   - Quittance ou Reçu de versement (péage et pesage)
#   - Historique ou Extrait de compte (péage)
#   - Bordereau de transfert de stock
#   - Ticket de commande (code de sécurisation du QR)
#   - Compte d'emploi / PV de confrontation (jeton du QR code)
# ===================================================================

from django.urls import reverse  # Pour construire les liens (PDF des clôtures)
from django.utils.translation import gettext as _  # Traduction FR/EN

from inventaire.models import Quittancement, HistoriqueQuittance, HistoriqueStock  # Péage + stocks
from inventaire.models_pesage import QuittancementPesage  # Quittances pesage
from inventaire.models_commandes import DetailCommandePoste  # Tickets commandés (QR)
from inventaire.models_cloture import ClotureMensuelle  # Comptes d'emploi / PV signés

# Types de recherche proposés dans la liste déroulante (valeur, libellé)
TYPES_RECHERCHE = [
    ('auto', _("Automatique (rechercher dans tous)")),  # Essaie tous les types
    ('quittance', _("Quittance ou Reçu de versement")),  # Péage puis pesage
    ('historique', _("Historique ou Extrait de compte")),  # Historiques péage
    ('bordereau', _("Bordereau de transfert")),  # Mouvements de stock
    ('commande', _("Ticket de commande (code QR)")),  # Codes de sécurisation
    ('cloture', _("Compte d'emploi / PV de confrontation")),  # Jeton du QR code
]


# ------------------------------------------------------------------
# OUTILS DE MISE EN FORME
# ------------------------------------------------------------------
def _montant(valeur):
    """Montant lisible : 1 234 567 FCFA (tiret si vide)."""
    if valeur is None:  # Pas de valeur
        return '—'  # Tiret
    return f"{valeur:,.0f}".replace(',', ' ') + ' FCFA'  # Séparateur d'espace


def _date(valeur):
    """Date au format jj/mm/aaaa (tiret si vide)."""
    return valeur.strftime('%d/%m/%Y') if valeur else '—'


def _date_heure(valeur):
    """Date et heure au format jj/mm/aaaa HH:MM (tiret si vide)."""
    return valeur.strftime('%d/%m/%Y %H:%M') if valeur else '—'


def _nom(utilisateur):
    """Nom complet d'un utilisateur (tiret si absent)."""
    return utilisateur.nom_complet if utilisateur else '—'


def _oui_non(valeur):
    """Booléen en Oui/Non."""
    return _("Oui") if valeur else _("Non")


def _url_image(champ_fichier):
    """URL d'un fichier image s'il existe, sinon None."""
    try:
        return champ_fichier.url if champ_fichier else None  # .url peut lever une erreur
    except ValueError:
        return None


def _periode_quittance(q):
    """Texte de la période couverte par une quittance (jour ou décade)."""
    if q.type_declaration == 'journaliere':  # Quittance journalière
        return _("Journée du %(d)s") % {'d': _date(q.date_recette)}
    return _("Décade du %(a)s au %(b)s") % {'a': _date(q.date_debut_decade), 'b': _date(q.date_fin_decade)}


def _resultat(type_, titre, icone, blocs, image=None, statut=None, journal=''):
    """Construit le dictionnaire de résultat commun à tous les types."""
    return {
        'trouve': True,  # Document retrouvé
        'type': type_,  # Code du type (pour le style)
        'titre': titre,  # Titre affiché
        'icone': icone,  # Icône Font Awesome
        'blocs': blocs,  # Liste de blocs {titre, lignes}
        'image_url': image,  # Image jointe éventuelle
        'statut': statut or {'niveau': 'success', 'texte': _("Document authentique et enregistré dans le système SUPPER")},
        'journal': journal,  # Texte pour le journal d'audit
    }


# ------------------------------------------------------------------
# RECHERCHE PAR TYPE DE DOCUMENT
# ------------------------------------------------------------------
def _quittance_peage(numero):
    """Quittance ou reçu de versement d'un poste de péage."""
    q = Quittancement.objects.select_related('poste', 'poste__region', 'saisi_par').filter(
        numero_quittance__iexact=numero).first()  # Recherche insensible à la casse
    if not q:
        return None  # Pas trouvé
    lignes = [
        (_("Numéro de quittance / Numéro de reçu de versement"), q.numero_quittance, 'fort'),
        (_("Module"), _("PÉAGE"), ''),
        (_("Poste"), q.poste.nom, ''),
        (_("Code du poste"), q.poste.code or '—', ''),
        (_("Région"), q.poste.region.nom if getattr(q.poste, 'region', None) else '—', ''),
        (_("Montant"), _montant(q.montant), 'montant'),
        (_("Date de quittancement ou Date de reversement"), _date(q.date_quittancement), ''),
        (_("Type de déclaration"), q.get_type_declaration_display(), ''),
        (_("Période couverte"), _periode_quittance(q), ''),
        (_("Exercice"), q.exercice, ''),
        (_("Mois"), q.mois, ''),
        (_("Verrouillée"), _oui_non(q.verrouille), ''),
        (_("Observations"), q.observations or '—', ''),
    ]
    saisie = [(_("Saisi par"), _nom(q.saisi_par), ''), (_("Date de saisie"), _date_heure(q.date_saisie), '')]
    return _resultat(
        'quittance_peage', _("Quittance ou Reçu de versement (Péage)"), 'fa-receipt',
        [{'titre': _("Document"), 'lignes': lignes}, {'titre': _("Saisie"), 'lignes': saisie}],
        image=_url_image(q.image_quittance),
        journal=f"Quittance péage {q.numero_quittance} | Poste: {q.poste.nom} | Montant: {q.montant} FCFA")


def _quittance_pesage(numero):
    """Quittance ou reçu de versement d'une station de pesage."""
    q = QuittancementPesage.objects.select_related('station', 'station__region', 'saisi_par').filter(
        numero_quittance__iexact=numero).first()
    if not q:
        return None
    lignes = [
        (_("Numéro de quittance / Numéro de reçu de versement"), q.numero_quittance, 'fort'),
        (_("Module"), _("PESAGE"), ''),
        (_("Station"), q.station.nom, ''),
        (_("Code de la station"), q.station.code or '—', ''),
        (_("Région"), q.station.region.nom if getattr(q.station, 'region', None) else '—', ''),
        (_("Montant quittancé"), _montant(q.montant_quittance), 'montant'),
        (_("Montant attendu (amendes payées)"), _montant(q.montant_attendu), ''),
        (_("Écart (quittancé - attendu)"), _montant(q.ecart), ''),
        (_("Date de quittancement ou Date de reversement"), _date(q.date_quittancement), ''),
        (_("Type de déclaration"), q.get_type_declaration_display(), ''),
        (_("Période couverte"), _periode_quittance(q), ''),
        (_("Exercice"), q.exercice, ''),
        (_("Mois"), q.mois, ''),
        (_("Verrouillée"), _oui_non(q.verrouille), ''),
        (_("Observations"), q.observations or '—', ''),
    ]
    saisie = [(_("Saisi par"), _nom(q.saisi_par), ''), (_("Date de saisie"), _date_heure(q.date_saisie), '')]
    return _resultat(
        'quittance_pesage', _("Quittance ou Reçu de versement (Pesage)"), 'fa-receipt',
        [{'titre': _("Document"), 'lignes': lignes}, {'titre': _("Saisie"), 'lignes': saisie}],
        image=_url_image(q.image_quittance),
        journal=f"Quittance pesage {q.numero_quittance} | Station: {q.station.nom} | Montant: {q.montant_quittance} FCFA")


def _historique_peage(numero):
    """Historique ou extrait de compte d'un poste de péage (par son numéro HIST-...)."""
    h = HistoriqueQuittance.objects.select_related('poste', 'poste__region', 'saisi_par').filter(
        numero_historique__iexact=numero).first()
    if not h:
        return None
    lignes = [
        (_("Numéro de l'historique"), h.numero_historique, 'fort'),
        (_("Module"), _("PÉAGE"), ''),
        (_("Poste"), h.poste.nom, ''),
        (_("Code du poste"), h.poste.code or '—', ''),
        (_("Région"), h.poste.region.nom if getattr(h.poste, 'region', None) else '—', ''),
        (_("Mois concerné"), h.get_mois_display(), ''),
        (_("Montant de l'extrait de compte"), _montant(h.montant_reel), 'montant'),
        (_("Observations"), h.observations or '—', ''),
    ]
    saisie = [(_("Saisi par"), _nom(h.saisi_par), ''), (_("Date de saisie"), _date_heure(h.date_saisie), ''),
              (_("Dernière modification"), _date_heure(h.date_modification), '')]
    return _resultat(
        'historique_peage', _("Historique ou Extrait de compte (Péage)"), 'fa-landmark',
        [{'titre': _("Document"), 'lignes': lignes}, {'titre': _("Saisie"), 'lignes': saisie}],
        image=_url_image(h.image_historique),
        journal=f"Historique péage {h.numero_historique} | Poste: {h.poste.nom} | Montant: {h.montant_reel} FCFA")


def _bordereau(numero):
    """Bordereau de transfert : une ligne de détail par opération (débit/crédit)."""
    operations = list(HistoriqueStock.objects.filter(numero_bordereau__iexact=numero).select_related(
        'poste', 'poste__region', 'poste_origine', 'poste_destination', 'effectue_par').order_by('date_mouvement'))
    if not operations:
        return None
    blocs = []  # Un bloc par opération
    for op in operations:
        lignes = [
            (_("Numéro de bordereau"), op.numero_bordereau, 'fort'),
            (_("Poste"), op.poste.nom, ''),
            (_("Type de mouvement"), op.get_type_mouvement_display(), ''),
            (_("Montant"), _montant(op.montant), 'montant'),
            (_("Nombre de tickets"), op.nombre_tickets, ''),
            (_("Date du mouvement"), _date_heure(op.date_mouvement), ''),
            (_("Poste d'origine"), op.poste_origine.nom if op.poste_origine else '—', ''),
            (_("Poste de destination"), op.poste_destination.nom if op.poste_destination else '—', ''),
            (_("Stock avant"), _montant(op.stock_avant), ''),
            (_("Stock après"), _montant(op.stock_apres), ''),
            (_("Effectué par"), _nom(op.effectue_par), ''),
            (_("Commentaire"), op.commentaire or '—', ''),
        ]
        blocs.append({'titre': _("Opération sur %(p)s") % {'p': op.poste.nom}, 'lignes': lignes})
    return _resultat('bordereau', _("Bordereau de transfert"), 'fa-file-invoice', blocs,
                     journal=f"Bordereau {numero} | Opérations: {len(operations)}")


def _commande(code):
    """Ticket de commande identifié par le code de sécurisation de son QR code."""
    d = DetailCommandePoste.objects.select_related('poste', 'poste__region', 'commande').filter(
        code_securisation__iexact=code).first()
    if not d:
        return None
    lignes = [
        (_("Code de sécurisation"), d.code_securisation, 'fort'),
        (_("Commande n°"), d.commande.numero_commande, ''),
        (_("Exercice"), d.commande.exercice, ''),
        (_("Période"), d.commande.get_periode_display_complet(), ''),
        (_("Poste"), d.poste.nom, ''),
        (_("Région"), d.poste.region.nom if getattr(d.poste, 'region', None) else '—', ''),
        (_("Montant de la commande"), _montant(d.montant_commande), 'montant'),
        (_("Nombre de tickets"), d.nombre_tickets, ''),
        (_("Nombre de carnets"), d.nombre_carnets, ''),
    ]
    return _resultat('commande', _("Ticket de commande (code QR)"), 'fa-ticket-alt',
                     [{'titre': _("Commande"), 'lignes': lignes}],
                     journal=f"Commande {d.commande.numero_commande} | Poste: {d.poste.nom} | Code: {d.code_securisation}")


def _cloture(jeton):
    """Compte d'emploi (péage) ou PV de confrontation (pesage) identifié par le jeton de son QR code."""
    jeton = jeton.rstrip('/').split('/')[-1]  # Accepte aussi l'URL complète lue dans le QR
    c = ClotureMensuelle.objects.select_related('poste', 'poste__region', 'genere_par').filter(jeton=jeton).first()
    if not c:
        return None
    lignes = [
        (_("Type de document"), c.get_type_document_display(), 'fort'),
        (_("Poste / Station"), c.poste.nom, ''),
        (_("Code du poste"), c.poste.code or '—', ''),
        (_("Région"), c.poste.region.nom if getattr(c.poste, 'region', None) else '—', ''),
        (_("Mois"), c.mois, ''),
        (_("Version"), c.version, ''),
        (_("Statut"), c.get_statut_display(), ''),
        (_("Titulaire (signataire)"), f"{c.signataire_nom or '—'} ({c.signataire_fonction or '—'})", ''),
    ]
    edition = [(_("Généré par"), _nom(c.genere_par), ''), (_("Date de génération"), _date_heure(c.date_generation), '')]
    # Une version remplacée reste authentique mais l'utilisateur doit en être averti
    statut = None
    if c.statut == 'remplace':
        statut = {'niveau': 'warning', 'texte': _("Ce document est authentique mais a été remplacé par une version plus récente.")}
    res = _resultat('cloture', c.get_type_document_display(), 'fa-file-signature',
                    [{'titre': _("Document"), 'lignes': lignes}, {'titre': _("Édition"), 'lignes': edition}],
                    statut=statut, journal=f"{c} | jeton {c.jeton[:6]}…")
    res['lien_pdf'] = reverse('inventaire:cloture_pdf', args=[c.pk])  # Pour ouvrir le PDF
    return res


# ------------------------------------------------------------------
# POINT D'ENTRÉE
# ------------------------------------------------------------------
# Ordre de recherche pour chaque type demandé
_ORDRE = {
    'auto': [_quittance_peage, _quittance_pesage, _historique_peage, _bordereau, _commande, _cloture],
    'quittance': [_quittance_peage, _quittance_pesage],
    'historique': [_historique_peage],
    'bordereau': [_bordereau],
    'commande': [_commande],
    'cloture': [_cloture],
}


def rechercher_document(numero, type_recherche='auto'):
    """Cherche le document ; renvoie le résultat détaillé ou {'trouve': False, ...}."""
    numero = (numero or '').strip()  # Nettoyage de la saisie
    for fonction in _ORDRE.get(type_recherche, _ORDRE['auto']):  # Types demandés, dans l'ordre
        resultat = fonction(numero)  # Tentative de recherche
        if resultat:  # Trouvé : on s'arrête
            return resultat
    return {'trouve': False, 'message': _("Aucun document trouvé avec le numéro : %(n)s") % {'n': numero}}
