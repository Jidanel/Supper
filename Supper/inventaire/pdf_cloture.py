# inventaire/pdf_cloture.py
# Génération des PDF de clôture mensuelle, fidèles aux modèles officiels :
#   - Compte d'emploi du poste de péage   - PV mensuel de confrontation (pesage)
# avec QR code de vérification, fusion de PDF et archive ZIP.

import io  # Tampons mémoire
import zipfile  # Archive ZIP
import qrcode  # QR code (déjà utilisé dans inventaire/utils.py)
from reportlab.lib import colors  # Couleurs
from reportlab.lib.enums import TA_CENTER  # Alignement centré
from reportlab.lib.pagesizes import A4, landscape  # Format paysage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # Styles de texte
from reportlab.lib.units import cm  # Unités
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Image, KeepTogether, Flowable, PageBreak)  # Éléments PDF
from pypdf import PdfWriter, PdfReader  # Fusion de PDF

from inventaire.models_config import ConfigurationGlobale  # En-têtes institutionnels + logo
from inventaire.services.cloture_service import (  # Formats français
    formater_pct, nom_mois, de_mois, date_longue)

# Couleurs des lignes du tableau A (identiques aux modèles)
JAUNE, VERT, SAUMON, BLEU = '#FFE699', '#6AA84F', '#F8CBAD', '#9DC3E6'
GRIS = colors.HexColor('#D9D9D9')  # En-têtes de tableaux B / C

# Libellés bilingues ('fr' par défaut, 'en' disponible)
L = {
    'fr': {
        'ce_titre': "COMPTE D'EMPLOI DU POSTE DE PEAGE DE {poste} POUR LE MOIS {mois}",
        'pv_titre': "PROCÈS VERBAL MENSUEL DE CONFRONTATION DE LA STATION DE PESAGE DE {poste} POUR LE MOIS {mois}",
        'A': 'A- Situation des Stocks et des Abonnements', 'Apv': 'A- Situation des Émissions et des RAR',
        'B': 'B- Situation de la collecte et des reversements',
        'Bpv': 'B- Situation des encaissements et des reversements', 'C': 'C- Conjoncture',
        'qte': 'Quantité/Nombre', 'val': 'Valeur/Montant', 'series': 'Séries',
        'ouv': "Stock d’ouverture du mois (Stock au {veille})", 'app': 'Approv (Imprimerie Nationale)',
        'recu': 'Reapprov Reçu', 'cede': 'Reapprov Cédé', 'vendu': 'Stock vendu',
        'abo': 'Abonnements du mois', 'fin': 'Stock de fin',
        'date': 'Date', 'collecte': '*Montant collecté (5+6)', 'collecte_pv': 'Montant collecté',
        'reverse': 'Montant reversé', 'quittance': 'N° Quittance', 'total': 'Total',
        'date_quitt': 'Date de quittancement', 'acct': 'Historique ACCT', 'ecart_acct': 'Écart (ACCT - Quittances)',
        'pied': "Document édité depuis l'application SUPPER le {date} à {heure}", 'page': 'Page {n}',
        'rend_mois': 'Rendement du Mois de {mois}', 'rend_n1': 'Rendement du Mois {mois}',
        'ecart': 'Ecart', 'indice': "Indice d’Evolution", 'fait': 'Fait à {poste}, le {date}',
        'chef_poste': 'LE CHEF DE POSTE', 'chef_station': 'LE CHEF DE STATION',
        'fait_vierge': 'Fait à ______________________ le ______________________',
        'regisseur': 'Le Régisseur des Recettes', 'verif': 'Scanner pour vérifier ce document',
        'pesees': 'Nombre de Pesées', 'infra': "Nombre d'infractions", 'emis': 'Emissions du Mois',
        'rarp': 'RAR Du mois précédent', 'recouvre': 'Montant Recouvré du Mois', 'rar': 'RAR du Mois',
        'synth': 'SYNTHÈSE', 'mois': 'Mois', 'poste': 'Poste', 'montant': 'Montant',
    },
    'en': {
        'ce_titre': "TICKET USAGE ACCOUNT OF THE TOLL POST OF {poste} FOR {mois}",
        'pv_titre': "MONTHLY CONFRONTATION REPORT OF THE WEIGH STATION OF {poste} FOR {mois}",
        'A': 'A- Stock and Subscription Status', 'Apv': 'A- Fines Issued and Arrears Status',
        'B': 'B- Collection and Payment Status', 'Bpv': 'B- Collection and Payment Status',
        'C': 'C- Business Trend', 'qte': 'Quantity/Number', 'val': 'Value/Amount', 'series': 'Series',
        'ouv': 'Opening stock (Stock at {veille})', 'app': 'Supply (National Printing Office)',
        'recu': 'Restocking received', 'cede': 'Restocking transferred', 'vendu': 'Stock sold',
        'abo': 'Monthly subscriptions', 'fin': 'Closing stock',
        'date': 'Date', 'collecte': '*Amount collected (5+6)', 'collecte_pv': 'Amount collected',
        'reverse': 'Amount paid in', 'quittance': 'Receipt No.', 'total': 'Total',
        'date_quitt': 'Receipt date', 'acct': 'ACCT history', 'ecart_acct': 'Gap (ACCT - Receipts)',
        'pied': 'Document issued from the SUPPER application on {date} at {heure}', 'page': 'Page {n}',
        'rend_mois': 'Yield of {mois}', 'rend_n1': 'Yield of {mois}',
        'ecart': 'Gap', 'indice': 'Evolution index', 'fait': 'Done at {poste}, on {date}',
        'chef_poste': 'THE POST MANAGER', 'chef_station': 'THE STATION MANAGER',
        'fait_vierge': 'Done at ______________________ on ______________________',
        'regisseur': 'The Revenue Collector', 'verif': 'Scan to verify this document',
        'pesees': 'Number of weighings', 'infra': 'Number of offences', 'emis': 'Fines issued',
        'rarp': 'Previous month arrears', 'recouvre': 'Amount recovered', 'rar': 'Arrears of the month',
        'synth': 'SUMMARY', 'mois': 'Month', 'poste': 'Post', 'montant': 'Amount',
    },
}


def _n(v):
    """Nombre avec espace insécable comme séparateur de milliers (13 414 000)."""
    if v is None or v == '':
        return ''  # Valeur absente : cellule laissée vide (modèle vierge)
    return f"{int(v):,}".replace(',', ' ')


def _dec(valeur):
    """Pourcentage JSON (texte) -> Decimal ou None (affiché N/D)."""
    from decimal import Decimal
    return None if valeur is None else Decimal(valeur)


def _pct(valeur):
    """Pourcentage affiché : '' (modèle vierge), 'N/D' (rendement N-1 nul) ou '45,16%'."""
    return '' if valeur == '' else formater_pct(_dec(valeur))


def _somme(lignes, cle):
    """Somme d'une colonne ; None si toutes les valeurs sont vides (modèle vierge)."""
    valeurs = [l[cle] for l in lignes if l.get(cle) not in (None, '')]
    return sum(valeurs) if valeurs else None


def _qr_image(url):
    """QR code (PNG en mémoire) pointant vers la page publique de vérification."""
    buf = io.BytesIO()
    qrcode.make(url).save(buf, format='PNG')
    buf.seek(0)
    return Image(buf, width=1.65 * cm, height=1.65 * cm)


def _styles():
    """Styles de texte communs."""
    base = getSampleStyleSheet()['Normal']
    return {
        'cellule': ParagraphStyle('cell', parent=base, fontName='Helvetica', fontSize=8, leading=9.5),
        'gras': ParagraphStyle('gras', parent=base, fontName='Helvetica-Bold', fontSize=8, leading=9.5),
        'section': ParagraphStyle('sec', parent=base, fontName='Helvetica-Bold', fontSize=10, leading=12, spaceBefore=3, spaceAfter=2),
        'titre': ParagraphStyle('tit', parent=base, fontName='Helvetica-Bold', fontSize=11, leading=14,
                                alignment=TA_CENTER, spaceBefore=2, spaceAfter=3),
        'centre': ParagraphStyle('ctr', parent=base, fontName='Helvetica', fontSize=9, leading=11, alignment=TA_CENTER),
        'centre_gras': ParagraphStyle('ctrg', parent=base, fontName='Helvetica-Bold', fontSize=9, leading=11, alignment=TA_CENTER),
        'petit': ParagraphStyle('pt', parent=base, fontName='Helvetica', fontSize=6, leading=7, alignment=TA_CENTER),
    }


def _avec_logo(entete):
    """Les fonctions d'en-tête du dépôt affichent le texte « DGI » si le logo de la configuration est vide
    ou introuvable. Dans ce cas on le remplace par le logo DGI du dossier media/logos ou static/images."""
    try:
        cellules = entete._cellvalues
        if cellules[0][1] == 'DGI':
            import os
            from django.conf import settings
            candidats = [os.path.join(settings.MEDIA_ROOT, 'logos', 'logo_dgi.png'),
                         os.path.join(settings.MEDIA_ROOT, 'logos_postes', 'logo_dgi.png'),
                         os.path.join(str(getattr(settings, 'BASE_DIR', '')), 'static', 'images', 'logo_dgi.png')]
            for chemin in candidats:
                if os.path.exists(chemin):
                    cellules[0][1] = Image(chemin, width=2.8 * cm, height=2.8 * cm)
                    break
    except Exception:  # Jamais bloquer la génération pour un logo
        pass
    return entete


def _entete_avec_qr(entete, url_verif, st, lb):
    """En-tête institutionnel suivi d'une ligne : QR code centré sous le logo DGI (loin des signatures
    et cachets) et, à sa droite sur le même niveau, « Fait à ______ le ______ » à remplir à la main."""
    petit = ParagraphStyle('verif', parent=st['petit'], alignment=TA_CENTER)
    qr = Table([[_qr_image(url_verif)], [Paragraph(lb['verif'], petit)]], colWidths=[4 * cm])
    qr.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('TOPPADDING', (0, 0), (-1, -1), 0),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    fait = Paragraph(lb['fait_vierge'], ParagraphStyle('fait', parent=st['gras'], fontSize=9, leading=12))
    ligne = Table([['', qr, fait]], colWidths=[11.3 * cm, 4 * cm, 11.3 * cm])  # QR au centre de la page
    ligne.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (2, 0), (2, 0), 0.4 * cm)]))
    return [_avec_logo(entete), ligne]


def _titre(texte, st):
    """Titre principal souligné, en gras, centré (comme les modèles)."""
    return Paragraph(f"<u>{texte}</u>", st['titre'])


def _ligne_signatures(lb, st, colonnes, largeur=26.6 * cm):
    """Ligne horizontale de signatures. `colonnes` = liste de (libellé fonction ou None, nom, « fait à » ou None).
    Chaque colonne : [Fait à…] / fonction soulignée / espace de signature et cachet / nom."""
    cellules = []
    for fonction, nom, fait in colonnes:
        c = []
        if fait:  # Ligne « Fait à … » seulement si elle est demandée (sinon pas de ligne vide)
            c.append(Paragraph(fait, st['centre_gras']))
        c.append(Paragraph(f"<u>{fonction}</u>" if fonction else '&nbsp;', st['centre_gras']))
        c.append(Spacer(1, 0.85 * cm))  # Espace pour signature et cachet
        c.append(Paragraph(nom or '', st['centre']))
        cellules.append(c)
    t = Table([cellules], colWidths=[largeur / len(cellules)] * len(cellules))
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    return t


def _date_fr(iso):
    """'2026-10-08' -> '08/10/2026' ; vide si absente."""
    if not iso:
        return ''
    a, m, j = iso.split('-')
    return f"{j}/{m}/{a}"


def _tableau_b(lb, lignes, cle_collecte, st, colonnes=1, compact=False, avec_total=True, lignes_total=None,
               acct=None, ecart=None, largeur_b=16.2 * cm):
    """Tableau B : Montant collecté | Montant reversé | Date de quittancement | N° Quittance (par bloc),
    puis, une seule fois à droite : Historique ACCT | Écart (ACCT - Quittances).
    L'historique ACCT étant mensuel, il n'apparaît que sur la ligne Total (dernière page).
    Au-delà de quelques quittances, les lignes sont réparties en 2 blocs côte à côte (un seul tableau,
    donc divisible entre pages) pour qu'un poste à 30 quittances reste sur 1-2 pages."""
    n = len(lignes)
    lignes_par_bloc = -(-n // colonnes) if n else 1  # Plafond de n / colonnes
    taille = 6.5 if colonnes >= 3 else (7 if (compact or colonnes > 1) else 7.5)
    th = ParagraphStyle('thB', parent=st['centre_gras'], fontSize=taille, leading=taille + 1.2)
    en_tete = [Paragraph(x, th) for x in (lb[cle_collecte], lb['reverse'], lb['date_quitt'], lb['quittance'])]
    en_tete = en_tete * colonnes + [Paragraph(lb['acct'], th), Paragraph(lb['ecart_acct'], th)]
    data = [en_tete]
    for r in range(lignes_par_bloc):
        ligne = []
        for c in range(colonnes):
            idx = c * lignes_par_bloc + r
            if idx < n:
                l = lignes[idx]
                ligne += [_n(l.get('montant_collecte')), _n(l.get('montant_reverse')),
                          _date_fr(l.get('date')), l.get('numero', '')]
            else:
                ligne += ['', '', '', '']
        data.append(ligne + ['', ''])  # Colonnes ACCT / écart : vides hors ligne Total
    if avec_total:  # Total calculé sur toutes les quittances (même si le tableau est scindé en pages)
        base_total = lignes if lignes_total is None else lignes_total
        total = [_n(_somme(base_total, 'montant_collecte')), _n(_somme(base_total, 'montant_reverse')),
                 lb['total'].upper(), '']
        data.append(total + [''] * 4 * (colonnes - 1) + [_n(acct), _n(ecart)])
    if colonnes == 1 and not compact:  # Bloc à gauche de C (largeur_b), 6 colonnes
        f = largeur_b / (16.2 * cm)
        largeurs = [x * cm * f for x in (2.6, 2.6, 2.7, 3.2, 2.6, 2.5)]
    elif colonnes == 1:  # Pages 1 et 2 (plus de 15 quittances) : pleine largeur utile
        largeurs = [x * cm for x in (3.8, 3.6, 3.8, 4.8, 3.6, 3.6)]
    else:  # Blocs côte à côte : 2 colonnes finales ACCT / écart de 2,4 cm
        bloc = (26.6 * cm - 4.0 * cm) / colonnes
        largeurs = [bloc * 0.22, bloc * 0.21, bloc * 0.26, bloc * 0.31] * colonnes + [2.0 * cm, 2.0 * cm]
    t = Table(data, colWidths=largeurs, repeatRows=1, hAlign='LEFT')  # Aligné à gauche, sous le titre B
    nb_col = 4 * colonnes + 2
    style = [('GRID', (0, 0), (-1, -1), 0.5, colors.black), ('FONTSIZE', (0, 0), (-1, -1), taille),
             ('BACKGROUND', (0, 0), (-1, 0), GRIS), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
             ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
             ('TOPPADDING', (0, 0), (-1, -1), 0.2 if (compact or colonnes > 1) else 1),
             ('BOTTOMPADDING', (0, 0), (-1, -1), 0.2 if (compact or colonnes > 1) else 1)]
    if avec_total:
        style += [('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'), ('BACKGROUND', (0, -1), (-1, -1), GRIS),
                  ('SPAN', (2, -1), (3, -1)), ('ALIGN', (2, -1), (3, -1), 'CENTER')]  # « TOTAL » sur date + N°
    if colonnes > 1:  # Marges latérales réduites pour que les N° de quittance tiennent dans leur cellule
        style += [('LEFTPADDING', (0, 0), (-1, -1), 2), ('RIGHTPADDING', (0, 0), (-1, -1), 2)]
    for c in range(colonnes):  # Montants alignés à droite dans chaque bloc
        style.append(('ALIGN', (4 * c, 1), (4 * c + 1, -1), 'RIGHT'))
        style.append(('ALIGN', (4 * c + 2, 1), (4 * c + 3, -1), 'CENTER'))
    style.append(('ALIGN', (nb_col - 2, 1), (nb_col - 1, -1), 'RIGHT'))
    t.setStyle(TableStyle(style))
    return t


QUITTANCES_PAGE_1 = 15  # Au-delà, 15 quittances en page 1 et le reste en page 2


def _blocs_quittances(lb, d, cle, st, titre, a_grand_tableau):
    """Éléments du tableau B selon le nombre de quittances.
    - peu de quittances : 1 ou 2 blocs côte à côte (retourne aussi le nombre de blocs)
    - plus de 15 : 15 lignes en page 1, saut de page, le reste (avec le total) en page 2."""
    lignes = d['tableau_b']
    if len(lignes) > QUITTANCES_PAGE_1:
        return 'pages', [Paragraph(titre, st['section']),
                         _tableau_b(lb, lignes[:QUITTANCES_PAGE_1], cle, st, compact=True, avec_total=False),
                         PageBreak(), Paragraph(titre + ' (suite)', st['section']),
                         _tableau_b(lb, lignes[QUITTANCES_PAGE_1:], cle, st, compact=True, lignes_total=lignes,
                                    acct=d.get('historique_acct'), ecart=d.get('ecart_acct'))]
    nb = _colonnes_b(len(lignes), a_grand_tableau)
    return nb, [Paragraph(titre, st['section']), _tableau_b(lb, lignes, cle, st, nb, acct=d.get('historique_acct'),
                                                            ecart=d.get('ecart_acct'))]


def _colonnes_b(n, a_grand_tableau):
    """Nombre de blocs côte à côte selon le nombre de quittances (pour que la signature reste sur la page).
    Compte d'emploi (tableau A plus haut) : 1 bloc jusqu'à 7, 2 jusqu'à 10, 3 au-delà ; PV : 1 jusqu'à 11, puis 2."""
    if a_grand_tableau:
        return 1 if n <= 7 else (2 if n <= 10 else 3)
    return 1 if n <= 11 else 2


def _tableau_c(lb, d, mois, st, largeur=15.2 * cm):
    """Tableau C (conjoncture) : rendement du mois, rendement N-1, écart, indice."""
    annee, num = mois.split('-')
    mois_n1 = f"{int(annee) - 1}-{num}"
    centre_gras = ParagraphStyle('c8', parent=st['centre_gras'], fontSize=8, leading=9.5)  # En-têtes qui passent à la ligne
    en_tete = [Paragraph(lb['rend_mois'].format(mois=nom_mois(mois)), centre_gras),
               Paragraph(lb['rend_n1'].format(mois=nom_mois(mois_n1)), centre_gras),
               Paragraph(lb['ecart'], centre_gras), Paragraph(lb['indice'], centre_gras)]
    t = Table([en_tete, [_n(d['total_reverse']), _n(d['rendement_n1']), _n(d['ecart_rendement']),
                         _pct(d['indice_pct'])]],
              colWidths=[largeur * 0.29, largeur * 0.29, largeur * 0.21, largeur * 0.21])
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black), ('BACKGROUND', (0, 0), (-1, 0), GRIS),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTNAME', (2, 1), (3, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    return t


def _pied_factory(lb):
    """Pied de page de chaque page : signe SUPPER + date et heure d'édition (moment du tirage) + n° de page."""
    from django.utils import timezone
    maintenant = timezone.localtime()
    texte = lb['pied'].format(date=maintenant.strftime('%d/%m/%Y'), heure=maintenant.strftime('%H:%M'))

    def pied(canvas, doc):
        canvas.saveState()
        largeur, _ = doc.pagesize
        canvas.setFillColor(colors.HexColor('#6b7280'))
        canvas.setFont('Helvetica-Bold', 6.5)
        canvas.drawString(doc.leftMargin, 0.22 * cm, '\u25A0 SUPPER')  # Signe : application d'origine
        canvas.setFont('Helvetica', 6.5)
        canvas.drawCentredString(largeur / 2, 0.22 * cm, texte)
        canvas.drawRightString(largeur - doc.rightMargin, 0.22 * cm, lb['page'].format(n=canvas.getPageNumber()))
        canvas.restoreState()
    return pied


def pdf_compte_emploi(cloture, url_verif, langue='fr', buffer=None):
    """PDF du compte d'emploi (paysage), calqué sur le modèle, à partir des données FIGÉES."""
    from inventaire.views_rapports import creer_entete_bilingue  # En-tête + logo DGI du dépôt
    lb, d, st = L[langue], cloture.donnees, _styles()
    buf = buffer or io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            topMargin=0.6 * cm, bottomMargin=0.5 * cm)
    from accounts.models import Poste
    poste = Poste.objects.get(pk=cloture.poste_id)
    mois = d['mois']
    veille = date_longue_courte(mois)

    # --- Tableau A : 7 lignes colorées ---
    def serie(x):
        return Paragraph(x['libelle'], st['cellule']) if x['libelle'] else ''
    lignes = [
        ['', '', lb['qte'], lb['val'], lb['series']],
        ['1', Paragraph(lb['ouv'].format(veille=veille), st['gras']), _n(d['stock_ouverture']['tickets']),
         _n(d['stock_ouverture']['valeur']), serie(d['stock_ouverture'])],
        ['2', Paragraph(lb['app'], st['gras']), _n(d['approv']['tickets']), _n(d['approv']['valeur']), serie(d['approv'])],
        ['3', Paragraph(lb['recu'], st['gras']), _n(d['reappro_recu']['tickets']), _n(d['reappro_recu']['valeur']),
         serie(d['reappro_recu'])],
        ['4', Paragraph(lb['cede'], st['gras']), _n(d['reappro_cede']['tickets']), _n(d['reappro_cede']['valeur']),
         serie(d['reappro_cede'])],
        ['5', Paragraph(lb['vendu'], st['gras']), _n(d['stock_vendu']['tickets']), _n(d['stock_vendu']['valeur']),
         serie(d['stock_vendu'])],
        ['6', Paragraph(lb['abo'], st['gras']), ('0' if d['abonnements'] not in (None, '') else ''), _n(d['abonnements']), ''],
        ['7', Paragraph(lb['fin'], st['gras']), _n(d['stock_fin']['tickets']), _n(d['stock_fin']['valeur']),
         serie(d['stock_fin'])],
    ]
    ta = Table(lignes, colWidths=[0.7 * cm, 9.4 * cm, 3.2 * cm, 3.4 * cm, 9.4 * cm])
    ta.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black), ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'), ('ALIGN', (2, 0), (3, -1), 'CENTER'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (1, 1), (-1, 1), colors.HexColor(JAUNE)), ('BACKGROUND', (1, 2), (-1, 2), colors.HexColor(VERT)),
        ('BACKGROUND', (1, 3), (-1, 4), colors.HexColor(SAUMON)), ('BACKGROUND', (1, 5), (-1, 5), colors.HexColor(BLEU)),
        ('TOPPADDING', (0, 0), (-1, -1), 0.8), ('BOTTOMPADDING', (0, 0), (-1, -1), 0.8)]))

    mode, bloc_b = _blocs_quittances(lb, d, 'collecte', st, lb['B'], True)
    sig_chef = [(None, '', None), (lb['chef_poste'], d['signataire_nom'], None)]
    if mode == 1:  # Peu de quittances : B à gauche, C à droite, puis signature du chef de poste
        milieu = [Table([[bloc_b, [Paragraph(lb['C'], st['section']), _tableau_c(lb, d, mois, st, largeur=10.0 * cm)]]],
                        colWidths=[16.4 * cm, 10.2 * cm], style=[('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                                               ('LEFTPADDING', (0, 0), (-1, -1), 0)]),
                  Spacer(1, 0.4 * cm), _ligne_signatures(lb, st, [(None, '', None), (None, '', None),
                                                                  (lb['chef_poste'], d['signataire_nom'], None)])]
    else:  # B en 2 blocs ou sur 2 pages : C à gauche, puis la signature TOUT EN BAS, sous tous les éléments
        milieu = [*bloc_b, Spacer(1, 0.2 * cm), Paragraph(lb['C'], st['section']),
                  _tableau_c(lb, d, mois, st, largeur=20.0 * cm), Spacer(1, 0.1 * cm),
                  _ligne_signatures(lb, st, [(None, '', None), (None, '', None),
                                             (lb['chef_poste'], d['signataire_nom'], None)])]
    el = [*_entete_avec_qr(creer_entete_bilingue(ConfigurationGlobale.get_config(), poste), url_verif, st, lb),
          _titre(lb['ce_titre'].format(poste=d['poste'].upper(), mois=de_mois(mois)), st),
          Paragraph(lb['A'], st['section']), ta, *milieu]
    pied = _pied_factory(lb)
    doc.build(el, onFirstPage=pied, onLaterPages=pied)
    return buf


def date_longue_courte(mois):
    """Date de la veille du 1er du mois, au format 30/09/2026 (libellé « Stock au … »)."""
    from datetime import timedelta
    from inventaire.services.cloture_donnees import bornes_mois
    v = bornes_mois(mois)[0] - timedelta(days=1)
    return v.strftime('%d/%m/%Y')


def pdf_pv(cloture, url_verif, langue='fr', buffer=None):
    """PDF du PV mensuel de confrontation (paysage), calqué sur le modèle, données FIGÉES."""
    from inventaire.views_pv_confrontation import creer_entete_pv  # En-tête + logo DGI du dépôt
    from accounts.models import Poste
    lb, d, st = L[langue], cloture.donnees, _styles()
    buf = buffer or io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm,
                            topMargin=0.6 * cm, bottomMargin=0.5 * cm)
    station = Poste.objects.get(pk=cloture.poste_id)
    mois = d['mois']

    # --- Tableau A : pesées, infractions, émissions, RAR précédent, recouvré, RAR du mois ---
    ta = Table([[lb['pesees'], lb['infra'], lb['emis'], lb['rarp'], lb['recouvre'], lb['rar']],
                [_n(d['nombre_pesees']), _n(d['nombre_infractions']), _n(d['emissions']),
                 _n(d['rar_precedent']), _n(d['recouvre']), _n(d['rar_mois'])]],
               colWidths=[3.6 * cm, 3.6 * cm, 4 * cm, 4 * cm, 4.6 * cm, 3.6 * cm])
    ta.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black), ('BACKGROUND', (0, 0), (-1, 0), GRIS),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))

    mode, bloc_b = _blocs_quittances(lb, d, 'collecte_pv', st, lb['Bpv'], False)
    signatures = [(lb['regisseur'], d['signataire_nom'], None), (lb['chef_station'], d.get('chef_station_nom', ''), None)]
    if mode == 1:  # Peu de quittances : B à gauche, C à droite, puis régisseur | espace | chef de station
        milieu = [Table([[bloc_b, [Paragraph(lb['C'], st['section']), _tableau_c(lb, d, mois, st, largeur=10.0 * cm)]]],
                        colWidths=[16.4 * cm, 10.2 * cm], style=[('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                                               ('LEFTPADDING', (0, 0), (-1, -1), 0)]),
                  Spacer(1, 0.4 * cm), _ligne_signatures(lb, st, [signatures[0], (None, '', None), signatures[1]])]
    else:  # B en 2 blocs ou sur 2 pages : C à gauche, puis les signatures TOUT EN BAS, sous tous les éléments
        milieu = [*bloc_b, Spacer(1, 0.2 * cm), Paragraph(lb['C'], st['section']),
                  _tableau_c(lb, d, mois, st, largeur=20.0 * cm), Spacer(1, 0.1 * cm),
                  _ligne_signatures(lb, st, [signatures[0], (None, '', None), signatures[1]])]
    el = [*_entete_avec_qr(creer_entete_pv(ConfigurationGlobale.get_config(), station), url_verif, st, lb),
          _titre(lb['pv_titre'].format(poste=d['poste'].upper(), mois=de_mois(mois)), st),
          Paragraph(lb['Apv'], st['section']), ta, *milieu]
    pied = _pied_factory(lb)
    doc.build(el, onFirstPage=pied, onLaterPages=pied)
    return buf


def pdf_synthese(titre, lignes, langue='fr'):
    """Page de synthèse (annuelle/semestrielle) : une ligne par mois."""
    lb = L[langue]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.5 * cm, rightMargin=1.5 * cm)
    st = _styles()
    data = [[lb['mois'], lb['poste'], lb['montant'], lb['indice']]]
    for l in lignes:
        data.append([nom_mois(l['mois']), l['poste'], _n(l['montant']), formater_pct(_dec(l['indice_pct']))])
    data.append(['', lb['total'], _n(sum(l['montant'] for l in lignes)), ''])
    t = Table(data, colWidths=[5 * cm, 8 * cm, 5 * cm, 4 * cm])
    t.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.black), ('BACKGROUND', (0, 0), (-1, 0), GRIS),
                           ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'), ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                           ('FONTSIZE', (0, 0), (-1, -1), 9), ('ALIGN', (2, 1), (3, -1), 'RIGHT')]))
    pied = _pied_factory(lb)
    doc.build([_titre(f"{lb['synth']} - {titre}", st), t], onFirstPage=pied, onLaterPages=pied)
    return buf


def fusionner_pdfs(buffers):
    """Fusionne plusieurs PDF (BytesIO) en un seul."""
    w = PdfWriter()
    for b in buffers:
        b.seek(0)
        for page in PdfReader(b).pages:
            w.add_page(page)
    out = io.BytesIO()
    w.write(out)
    out.seek(0)
    return out


def creer_zip(fichiers):
    """ZIP de {nom_fichier: BytesIO}."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for nom, b in fichiers.items():
            b.seek(0)
            z.writestr(nom, b.read())
    out.seek(0)
    return out
