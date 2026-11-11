# inventaire/views_cloture.py
# Vues de la clôture mensuelle : saisie des éléments manuels, génération du document,
# téléchargement PDF, vérification publique par QR code, téléchargement en masse.

import datetime  # Dates de la période des défaillants
import json  # Lecture des séries cochées (JSON)
import logging  # Journal technique
from django.contrib import messages  # Messages utilisateur
from django.contrib.auth.decorators import login_required  # Accès authentifié
from django.db import transaction  # Création de version atomique
from django.http import HttpResponse  # Réponses fichier
from django.shortcuts import render, redirect, get_object_or_404  # Raccourcis
from django.urls import reverse  # URL inverses
from django.utils import timezone  # Horodatage

from accounts.models import Poste  # Postes
from common.permissions import (has_permission, check_poste_access,
                                user_has_acces_tous_postes, get_postes_accessibles)  # Sécurité
from common.utils import log_user_action  # Journalisation
from inventaire.models_cloture import ClotureMensuelle, StatutCloture  # Modèles clôture
from inventaire.services import cloture_donnees as cd  # Données des documents
from inventaire.services.cloture_service import fusionner_intervalles, analyser_intervalles  # Séries
from inventaire import pdf_cloture  # Génération PDF

logger = logging.getLogger('supper')

MOIS_COURTS = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc']  # En-têtes compacts
MAX_POSTES_MASSE = 100  # Plafond de postes par téléchargement en masse
TYPES = {'compte_emploi': 'peage', 'pv_confrontation': 'pesage'}  # Type de document -> type de poste
PERMISSIONS = {'compte_emploi': 'peut_voir_compte_emploi',
               'pv_confrontation': 'peut_voir_pv_confrontation'}  # Permission requise par type


def _autorise(user, type_doc, poste):
    """Contrôle double : permission du module + accès au poste."""
    return has_permission(user, PERMISSIONS[type_doc]) and check_poste_access(user, poste)


def _url_verification(request, cloture):
    """URL absolue de la page publique de vérification (contenue dans le QR)."""
    return request.build_absolute_uri(reverse('verifier_cloture', args=[cloture.jeton]))


def _derniere_version(poste, type_doc, mois):
    """Dernière version non remplacée d'un document (ou None)."""
    return ClotureMensuelle.objects.filter(poste=poste, type_document=type_doc, mois=mois
                                           ).exclude(statut=StatutCloture.REMPLACE).order_by('-version').first()


@login_required
def cloture_selection(request):
    """Choix du poste et du mois, avec état « à jour » pour chaque poste accessible."""
    user = request.user
    type_doc = request.GET.get('type', 'compte_emploi')
    if type_doc not in TYPES or not has_permission(user, PERMISSIONS[type_doc]):
        messages.error(request, "Vous n'avez pas la permission d'accéder à ce document.")
        return redirect('common:dashboard')
    mois = request.GET.get('mois') or timezone.localdate().strftime('%Y-%m')
    postes = [p for p in get_postes_accessibles(user, type_poste=TYPES[type_doc])]
    lignes = []
    for p in postes:  # État de chaque poste pour le mois choisi
        statut = cd.statut_complet(TYPES[type_doc], p, mois)  # Jours renseignés + quittances + historique ACCT
        lignes.append({'poste': p, 'statut': statut, 'cloture': _derniere_version(p, type_doc, mois)})
    return render(request, 'inventaire/cloture_selection.html',
                  {'type_doc': type_doc, 'mois': mois, 'lignes': lignes, 'title': 'Clôture mensuelle'})


@login_required
def cloture_saisie(request, type_doc, poste_id, mois):
    """Formulaire des éléments manuels (pré-remplis) puis génération d'une nouvelle version."""
    user = request.user
    poste = get_object_or_404(Poste, id=poste_id)
    if type_doc not in TYPES or not _autorise(user, type_doc, poste):
        log_user_action(user=user, action="ACCES_REFUSE", description=f"Clôture {type_doc} - {poste.nom}",
                        details="Permission ou accès au poste manquant", niveau="WARNING")
        messages.error(request, "Accès refusé.")
        return redirect('common:dashboard')

    # Génération possible à tout moment : le statut « complet / en cours » est seulement indicatif.

    existante = _derniere_version(poste, type_doc, mois)
    if existante and existante.statut == StatutCloture.SIGNE:
        messages.error(request, "Ce document est signé et verrouillé.")
        return redirect(f"{reverse('inventaire:cloture_selection')}?type={type_doc}&mois={mois}")

    # Valeurs proposées : dernière version saisie, sinon calcul SUPPER
    if type_doc == 'compte_emploi':
        calcule = cd.preremplir_compte_emploi(poste, mois)
    else:
        calcule = cd.preremplir_pv(poste, mois)
    if existante:
        valeurs = dict(existante.donnees['manuel'])
        if not valeurs.get('rendement_n1'):  # 0 enregistré auparavant : on reprend la valeur calculée
            valeurs['rendement_n1'] = calcule.get('rendement_n1', 0)
    else:
        valeurs = calcule

    if request.method == 'POST':
        try:
            manuel = _lire_formulaire(request.POST, type_doc)
        except ValueError as e:
            messages.error(request, str(e))
        else:
            with transaction.atomic():  # Ancienne version -> remplacée, nouvelle créée
                if existante:
                    existante.statut = StatutCloture.REMPLACE
                    existante.save(update_fields=['statut'])
                donnees = (cd.calculer_compte_emploi(poste, mois, manuel) if type_doc == 'compte_emploi'
                           else cd.calculer_pv(poste, mois, manuel))
                cloture = ClotureMensuelle.objects.create(
                    poste=poste, type_document=type_doc, mois=mois,
                    version=(existante.version + 1) if existante else 1, donnees=donnees,
                    signataire_nom=donnees['signataire_nom'], signataire_fonction=donnees['signataire_fonction'],
                    genere_par=user)
            log_user_action(user=user, action="GENERATION_CLOTURE",
                            description=f"{type_doc} {poste.nom} {mois} v{cloture.version}",
                            details=json.dumps(manuel, default=str)[:1000], niveau="INFO")
            if type_doc == 'compte_emploi' and not donnees['controle_reverse_ok']:
                messages.warning(request, "Attention : le total reversé diffère de (stock vendu + abonnements).")
            if type_doc == 'compte_emploi' and donnees['fin_hors_base']:
                messages.warning(request, "Attention : certaines séries du stock de fin ne figurent ni dans l'ouverture ni dans les approvisionnements du mois.")
            return redirect('inventaire:cloture_pdf', pk=cloture.pk)

    return render(request, 'inventaire/cloture_saisie.html', {
        'type_doc': type_doc, 'poste': poste, 'mois': mois, 'valeurs': valeurs,
        'series_disponibles': cd.series_fin_disponibles(poste, mois) if type_doc == 'compte_emploi' else [],
        'series_cochees': [tuple(s) for s in valeurs.get('series_fin', [])],
        'textes_series': {k: _texte_series(valeurs.get(k, [])) for k in
                          ('series_ouverture', 'series_approv', 'series_recu', 'series_cede')},
        'title': 'Clôture mensuelle'})


def _texte_series(series):
    """Intervalles -> texte éditable, un par ligne (« 11121973-11148800 »)."""
    return "\n".join(f"{d}-{f}" for d, f in series)


def _lire_formulaire(post, type_doc):
    """Convertit le POST en éléments manuels (entiers positifs ; séries en intervalles)."""
    def entier(nom):
        brut = (post.get(nom) or '0').replace(' ', '').replace('\u00a0', '')
        if not brut.isdigit():
            raise ValueError(f"Valeur invalide pour « {nom} ».")
        return int(brut)
    if type_doc == 'compte_emploi':
        manuel = {k: [list(i) for i in analyser_intervalles(post.get(k, ''))]  # Zones de texte de séries
                  for k in ('series_ouverture', 'series_approv', 'series_recu', 'series_cede')}
        cochees = []
        for v in post.getlist('series'):  # Cases cochées : « debut-fin »
            debut, fin = (int(x) for x in v.split('-'))
            cochees.append((debut, fin))
        manuel['series_fin'] = [list(i) for i in fusionner_intervalles(cochees)]
        manuel['abonnements'] = entier('abonnements')
        manuel['rendement_n1'] = entier('rendement_n1')
        return manuel
    return {k: entier(k) for k in ('nombre_pesees', 'nombre_infractions', 'emissions',
                                   'rar_precedent', 'rendement_n1')}


@login_required
def cloture_pdf(request, pk):
    """Affiche le PDF d'une version de document."""
    cloture = get_object_or_404(ClotureMensuelle, pk=pk)
    if not _autorise(request.user, cloture.type_document, cloture.poste):
        messages.error(request, "Accès refusé.")
        return redirect('common:dashboard')
    langue = 'en' if request.GET.get('lang') == 'en' else 'fr'
    buf = _pdf(cloture, request, langue)
    log_user_action(user=request.user, action="CONSULTATION_CLOTURE",
                    description=f"{cloture}", details=f"Langue {langue}", niveau="INFO")
    rep = HttpResponse(buf.getvalue(), content_type='application/pdf')
    rep['Content-Disposition'] = f'inline; filename="{cloture.type_document}_{cloture.poste.code}_{cloture.mois}.pdf"'
    return rep


def _pdf(cloture, request, langue='fr'):
    """Choisit le générateur selon le type de document."""
    url = _url_verification(request, cloture)
    if cloture.type_document == 'compte_emploi':
        return pdf_cloture.pdf_compte_emploi(cloture, url, langue)
    return pdf_cloture.pdf_pv(cloture, url, langue)


def verifier_cloture(request, jeton):
    """Page PUBLIQUE (sans connexion) : atteste l'authenticité d'un document via son QR code."""
    cloture = ClotureMensuelle.objects.filter(jeton=jeton).select_related('poste').first()
    return render(request, 'inventaire/verifier_cloture.html', {'cloture': cloture})


# ----------------------------------------------------------------------
# Téléchargement en masse
# ----------------------------------------------------------------------
def mois_de_la_periode(exercice, periode, mois_fin=None):
    """Liste des mois 'YYYY-MM' d'une période : annee, semestre1/2, trimestre1-4, derniers6, derniers12."""
    if periode == 'annee':
        return [f"{exercice}-{m:02d}" for m in range(1, 13)]
    if periode in ('semestre1', 'semestre2'):
        debut = 1 if periode == 'semestre1' else 7
        return [f"{exercice}-{m:02d}" for m in range(debut, debut + 6)]
    if periode.startswith('trimestre'):
        debut = (int(periode[-1]) - 1) * 3 + 1
        return [f"{exercice}-{m:02d}" for m in range(debut, debut + 3)]
    if periode in ('derniers6', 'derniers12'):  # N derniers mois se terminant au mois choisi
        n = 6 if periode == 'derniers6' else 12
        annee, mois = (int(x) for x in (mois_fin or f"{exercice}-12").split('-'))
        resultat = []
        for _ in range(n):
            resultat.append(f"{annee}-{mois:02d}")
            mois -= 1
            if mois == 0:
                annee, mois = annee - 1, 12
        return list(reversed(resultat))
    return [mois_fin] if mois_fin else []


@login_required
def cloture_masse(request):
    """Téléchargement de plusieurs documents (plusieurs postes, une période) en PDF fusionné ou ZIP."""
    user = request.user
    type_doc = request.GET.get('type') or request.POST.get('type') or 'compte_emploi'
    if (type_doc not in TYPES or not has_permission(user, PERMISSIONS[type_doc])
            or not user_has_acces_tous_postes(user)):  # Réservé aux profils centraux
        messages.error(request, "Vous n'avez pas la permission de télécharger en masse.")
        return redirect('common:dashboard')
    postes = Poste.objects.filter(type=TYPES[type_doc], is_active=True).order_by('nom')

    if request.method == 'POST':
        ids = request.POST.getlist('postes')[:MAX_POSTES_MASSE]  # Plafond de sécurité
        exercice = int(request.POST.get('exercice') or timezone.localdate().year)
        mois_liste = mois_de_la_periode(exercice, request.POST.get('periode', 'annee'), request.POST.get('mois_fin'))
        langue = 'en' if request.POST.get('lang') == 'en' else 'fr'
        sorties, manquants = {}, []
        for poste in postes.filter(id__in=ids):
            morceaux, synth = [], []
            for m in mois_liste:
                c = _derniere_version(poste, type_doc, m)
                if not c:
                    manquants.append(f"{poste.nom} {m}")
                    continue
                morceaux.append(_pdf(c, request, langue))
                d = c.donnees
                synth.append({'mois': m, 'poste': poste.nom, 'indice_pct': d.get('indice_pct'),
                              'montant': d.get('total_reverse', d.get('recouvre', 0))})
            if morceaux:
                if len(mois_liste) > 1:  # Page de synthèse en tête quand plusieurs mois
                    morceaux.insert(0, pdf_cloture.pdf_synthese(poste.nom, synth, langue))
                sorties[f"{type_doc}_{poste.code}.pdf"] = pdf_cloture.fusionner_pdfs(morceaux)
        log_user_action(user=user, action="TELECHARGEMENT_MASSE_CLOTURE",
                        description=f"{type_doc} - {len(sorties)} poste(s)",
                        details=f"Mois: {mois_liste[:1]}…{mois_liste[-1:]}; manquants: {len(manquants)}", niveau="INFO")
        if not sorties:
            messages.warning(request, "Aucun document disponible pour cette sélection.")
        elif request.POST.get('format') == 'pdf':  # Un seul PDF avec tous les postes
            rep = HttpResponse(pdf_cloture.fusionner_pdfs(list(sorties.values())).getvalue(),
                               content_type='application/pdf')
            rep['Content-Disposition'] = f'attachment; filename="{type_doc}_{exercice}.pdf"'
            return rep
        else:  # ZIP : un PDF par poste
            rep = HttpResponse(pdf_cloture.creer_zip(sorties).getvalue(), content_type='application/zip')
            rep['Content-Disposition'] = f'attachment; filename="{type_doc}_{exercice}.zip"'
            return rep

    return render(request, 'inventaire/cloture_masse.html', {
        'type_doc': type_doc, 'postes': postes, 'max_postes': MAX_POSTES_MASSE,
        'annee': timezone.localdate().year, 'title': 'Téléchargement en masse'})


# ----------------------------------------------------------------------
# Postes / stations défaillants (non à jour sur une période)
# ----------------------------------------------------------------------
@login_required
def cloture_defaillants(request):
    """Liste des postes (péage) ou stations (pesage) non à jour sur la période choisie ; export Excel."""
    user = request.user
    type_doc = request.GET.get('type', 'compte_emploi')
    if type_doc not in TYPES or not has_permission(user, PERMISSIONS[type_doc]):
        messages.error(request, "Vous n'avez pas la permission d'accéder à cette liste.")
        return redirect('common:dashboard')
    aujourdhui = timezone.localdate()
    # Critères cochés : recettes (péage), quittances, historique ACCT. Par défaut tous.
    valides = ('recettes', 'quittances', 'acct') if type_doc == 'compte_emploi' else ('quittances', 'acct')
    if request.GET.get('afficher') or request.GET.get('export'):
        criteres = [c for c in request.GET.getlist('critere') if c in valides]
    else:
        criteres = list(valides)  # Premier affichage du formulaire : tout est coché

    def _date(nom, defaut):  # Lecture d'une date AAAA-MM-JJ, valeur par défaut si absente/invalide
        try:
            return datetime.date.fromisoformat(request.GET.get(nom, ''))
        except ValueError:
            return defaut
    date_debut = _date('date_debut', aujourdhui.replace(month=1, day=1))
    date_fin = _date('date_fin', aujourdhui)
    resultat, erreur = [], None
    if request.GET.get('afficher') or request.GET.get('export'):  # Calcul seulement sur demande
        if date_debut > date_fin:
            erreur = "La date de départ doit être antérieure ou égale à la date d'arrivée."
        elif not criteres:
            erreur = "Cochez au moins un critère (recettes, quittances, historique ACCT)."
        else:
            postes = get_postes_accessibles(user, type_poste=TYPES[type_doc]).select_related('region').order_by('region__nom', 'nom')
            resultat = cd.liste_defaillants(TYPES[type_doc], postes, date_debut, date_fin, criteres)
            log_user_action(user=user, action="LISTE_DEFAILLANTS",
                            description=f"{type_doc} - {len(resultat)} défaillant(s)",
                            details=f"{date_debut} → {date_fin}; critères {','.join(criteres)}", niveau="INFO")
    if erreur:
        messages.error(request, erreur)
    if request.GET.get('export') and resultat:
        return _export_defaillants_xlsx(resultat, type_doc, str(date_debut), str(date_fin))
    # Mise en forme : une colonne par mois, une cellule par poste/mois (nombre de jours en défaut)
    fin_effective = min(date_fin, aujourdhui)
    mois_cols = []
    if resultat or request.GET.get('afficher'):
        for m in cd._mois_de_intervalle(date_debut, fin_effective) if date_debut <= fin_effective else []:
            d, f = cd.bornes_mois(m)
            nb = (min(f, fin_effective) - max(d, date_debut)).days + 1  # Jours du mois dans la période
            mois_cols.append({'code': m, 'libelle': f"{MOIS_COURTS[int(m[5:])-1]} {m[2:4]}", 'jours': nb})
    resultat.sort(key=lambda r: (getattr(r['poste'].region, 'nom', '') or '', -r['total_jours'], r['poste'].nom))
    for r in resultat:  # Cellules alignées sur les colonnes + niveau de gravité (couleur)
        par_mois = {x['mois']: x for x in r['mois']}
        r['cellules'] = []
        for col in mois_cols:
            x = par_mois.get(col['code'])
            if x:
                part = x['nb_jours'] / col['jours'] if col['jours'] else 0
                # Niveau de couleur : 0 = seulement ACCT manquant ; 1 < 25 % ; 2 de 25 à 75 % ; 3 >= 75 %
                x['niveau'] = 0 if not x['nb_jours'] else (3 if part >= 0.75 else (2 if part >= 0.25 else 1))
            r['cellules'].append(x)
    return render(request, 'inventaire/cloture_defaillants.html', {
        'type_doc': type_doc, 'resultat': resultat, 'date_debut': date_debut, 'date_fin': date_fin,
        'criteres': criteres, 'afficher': bool(request.GET.get('afficher')) and not erreur,
        'mois_cols': mois_cols, 'avec_detail': request.GET.get('detail') == '1',
        'total_jours': sum(r['total_jours'] for r in resultat),
        'nb_regions': len({getattr(r['poste'].region, 'nom', '') for r in resultat}),
        'maintenant': timezone.localtime(), 'title': 'Postes défaillants'})


def _export_defaillants_xlsx(resultat, type_doc, debut_txt, fin_txt):
    """Export Excel de la liste des défaillants (une ligne par poste et par mois en défaut)."""
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = 'Défaillants'
    ws.append(['Région', 'Poste', 'Mois', 'Jours en défaut', 'Jours sans quittance', 'Jours sans recette',
               'Historique ACCT manquant', 'Premier jour', 'Dernier jour'])
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in resultat:
        for m in r['mois']:
            ws.append([getattr(r['poste'].region, 'nom', ''), r['poste'].nom, m['mois'], m['nb_jours'],
                       m['nb_sans_quittance'], m['nb_sans_recette'], 'Oui' if m['sans_acct'] else '',
                       m['premier'].strftime('%d/%m/%Y') if m['premier'] else '',
                       m['dernier'].strftime('%d/%m/%Y') if m['dernier'] else ''])
    for col in 'ABCDEFGHI':
        ws.column_dimensions[col].width = 26
    out = io.BytesIO()
    wb.save(out)
    rep = HttpResponse(out.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    rep['Content-Disposition'] = f'attachment; filename="defaillants_{type_doc}_{debut_txt}_{fin_txt}.xlsx"'
    return rep
