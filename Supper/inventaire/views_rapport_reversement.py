# inventaire/views_rapport_reversement.py
# Page « Rapport de reversement » : par poste et par période de jours de recette, compare déclarations et quittances
# (péage) ou liste les quittances (pesage). Accès : administrateurs, Service Émissions et Recouvrement, et les
# utilisateurs autorisés à consulter les quittances.
import csv  # Export CSV
import datetime  # Dates

from django.contrib import messages  # Messages utilisateur
from django.contrib.auth.decorators import login_required  # Connexion obligatoire
from django.http import HttpResponse  # Réponse CSV
from django.shortcuts import render, redirect  # Rendu et redirection
from django.utils import timezone  # Date du jour

from accounts.models import Poste, Region  # Postes et régions
from common.permissions import is_admin_user, log_acces_refuse  # Droits
from inventaire.services.rapport_reversement import rapport_par_reversement, rapport_peage, rapport_pesage  # Calculs


def peut_voir_rapport_reversement(user):
    """Administrateurs, Service Émissions/Recouvrement, ou droit de consulter les quittances péage/pesage."""
    if not user or not user.is_authenticated:
        return False
    return (is_admin_user(user) or getattr(user, 'habilitation', None) == 'serv_emission'
            or getattr(user, 'peut_voir_liste_quittances_peage', False)
            or getattr(user, 'peut_voir_liste_quittancements_pesage', False))


def _date(texte, defaut):
    """Lit AAAA-MM-JJ ; retourne `defaut` si le texte est vide ou invalide."""
    try:
        return datetime.date.fromisoformat(texte)
    except (TypeError, ValueError):
        return defaut


@login_required
def rapport_reversement(request):
    """Tableau de reversement. Filtres GET : debut, fin (jours de RECETTE), type=peage|pesage, poste, region, ecarts=1."""
    if not peut_voir_rapport_reversement(request.user):
        log_acces_refuse(request.user, "rapport_reversement", "Droit de consulter les quittances requis")
        messages.error(request, "Accès non autorisé.")
        return redirect('/')
    aujourdhui = timezone.localdate()
    debut = _date(request.GET.get('debut'), aujourdhui.replace(day=1))  # Par défaut : 1er du mois
    fin = _date(request.GET.get('fin'), aujourdhui)  # Par défaut : aujourd'hui
    if fin < debut:
        messages.error(request, "La date de fin est antérieure à la date de début : les dates ont été inversées.")
        debut, fin = fin, debut
    if (fin - debut).days > 92:
        messages.warning(request, "Période limitée à 93 jours : la fin a été ramenée à 93 jours après le début.")
        fin = debut + datetime.timedelta(days=92)
    type_poste = request.GET.get('type') if request.GET.get('type') in ('peage', 'pesage') else 'peage'
    poste_id = request.GET.get('poste') or None
    region_id = request.GET.get('region') or None
    seulement_ecarts = request.GET.get('ecarts') == '1'
    base = request.GET.get('base') if request.GET.get('base') in ('reversement', 'recette') else 'reversement'  # Par défaut : dates de reversement
    if base == 'reversement':  # La période porte sur la date de quittancement (comme la liste des quittances)
        jours, lignes, totaux, avertissement = rapport_par_reversement(type_poste, debut, fin, poste_id, region_id, seulement_ecarts)
        if avertissement:
            messages.warning(request, avertissement)
    elif type_poste == 'peage':  # La période porte sur les jours de recette
        jours, lignes, totaux = rapport_peage(debut, fin, poste_id, region_id, seulement_ecarts)
    else:
        jours, lignes, totaux = rapport_pesage(debut, fin, poste_id, region_id, seulement_ecarts)
    if request.GET.get('export') == 'csv':  # Export du tableau de synthèse
        return _export_csv(type_poste, debut, fin, lignes)
    contexte = {
        'base': base, 'debut': debut, 'fin': fin, 'jours': jours, 'lignes': lignes, 'totaux': totaux, 'type_poste': type_poste,
        'poste_id': poste_id, 'region_id': region_id, 'seulement_ecarts': seulement_ecarts,
        'postes': Poste.objects.filter(type=type_poste, is_active=True).order_by('nom'),
        'regions': Region.objects.order_by('nom'),
    }
    return render(request, 'inventaire/rapport_reversement.html', contexte)


def _export_csv(type_poste, debut, fin, lignes):
    """CSV de synthèse (séparateur « ; », encodage Excel)."""
    reponse = HttpResponse(content_type='text/csv; charset=utf-8')
    reponse.write('\ufeff')  # BOM unique : Excel lit correctement les accents
    reponse['Content-Disposition'] = f'attachment; filename="reversement_{type_poste}_{debut}_{fin}.csv"'
    w = csv.writer(reponse, delimiter=';')
    if type_poste == 'peage':
        w.writerow(['Poste', 'Déclaré', 'Quittancé', 'Écart', 'Jours déclarés non quittancés', 'Montant non quittancé', 'Quittances'])
        for l in lignes:
            w.writerow([l['poste'].nom, l['total_declare'], l['total_quittance'], l['ecart'],
                        ' '.join(j.strftime('%d/%m') for j in l['jours_manquants']), l['montant_manquant'],
                        ' | '.join(f"{b['numero']} (reversée le {b['reversement']:%d/%m}, recette {b['p']:%d/%m}→{b['d']:%d/%m}) {b['montant']}" for b in l['blocs'])])
    else:
        w.writerow(['Station', 'Quittancé', 'Jours sans quittance', 'Quittances'])
        for l in lignes:
            w.writerow([l['poste'].nom, l['total_quittance'], ' '.join(j.strftime('%d/%m') for j in l['jours_manquants']),
                        ' | '.join(f"{b['numero']} (reversée le {b['reversement']:%d/%m}, recette {b['p']:%d/%m}→{b['d']:%d/%m}) {b['montant']}" for b in l['blocs'])])
    return reponse
