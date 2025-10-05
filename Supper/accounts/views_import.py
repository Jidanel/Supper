# accounts/views_import.py
import pandas as pd
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
import openpyxl
from io import BytesIO

from accounts.models import Poste, Region
from common.utils import log_user_action

def is_admin(user):
    return user.is_authenticated and user.is_admin

@login_required
@user_passes_test(is_admin)
def import_postes_excel(request):
    """Vue pour importer des postes depuis un fichier Excel"""
    
    if request.method == 'POST':
        fichier = request.FILES.get('fichier_excel')
        action_doublon = request.POST.get('action_doublon', 'sauter')
        
        if not fichier:
            messages.error(request, "Veuillez sélectionner un fichier Excel")
            return redirect('accounts:import_postes')
        
        if not fichier.name.endswith(('.xlsx', '.xls')):
            messages.error(request, "Le fichier doit être au format Excel (.xlsx ou .xls)")
            return redirect('accounts:import_postes')
        
        try:
            # Lire le fichier Excel
            df = pd.read_excel(fichier)
            
            # Traiter l'import
            resultats = traiter_import_postes(df, action_doublon, request.user)
            
            # Afficher les résultats
            if resultats['success']:
                messages.success(
                    request,
                    f"Import terminé ! {resultats['nb_crees']} postes créés, "
                    f"{resultats['nb_modifies']} modifiés, {resultats['nb_sautes']} sautés, "
                    f"{resultats['nb_erreurs']} erreurs"
                )
                
                log_user_action(
                    request.user,
                    "Import postes Excel groupé",
                    f"Créés: {resultats['nb_crees']}, Modifiés: {resultats['nb_modifies']}",
                    request
                )
            else:
                messages.error(request, f"Erreur lors de l'import: {resultats['erreur']}")
            
            context = {'resultats': resultats}
            return render(request, 'accounts/import_postes_resultats.html', context)
            
        except Exception as e:
            messages.error(request, f"Erreur lors de la lecture du fichier: {str(e)}")
            return redirect('accounts:import_postes')
    
    # GET request - afficher le formulaire
    return render(request, 'accounts/import_postes_form.html')


def traiter_import_postes(df, action_doublon, user):
    """Traite l'import des postes depuis Excel avec type de poste"""

    # CORRECTION : Normaliser les noms de colonnes (insensible à la casse)
    df.columns = df.columns.str.strip().str.lower()
    nb_crees = 0
    nb_modifies = 0
    nb_sautes = 0
    nb_erreurs = 0
    erreurs_detail = []
    regions_non_trouvees = set()
    types_invalides = set()
    
    # Vérifier les colonnes requises
    colonnes_requises = ['nom', 'region', 'code', 'type']
    colonnes_manquantes = [col for col in colonnes_requises if col not in df.columns]
    
    if colonnes_manquantes:
        return {
            'success': False,
            'erreur': f"Colonnes manquantes dans le fichier: {', '.join(colonnes_manquantes)}"
        }
    
    # Mapping des régions
    regions_db = {}
    for region in Region.objects.all():
        nom_normalise = region.nom.upper().strip()
        regions_db[nom_normalise] = region
    
    # Mapping des types de postes (normalisation)
    types_valides = {
        'PEAGE': 'peage',
        'PÉAGE': 'peage',
        'peage': 'peage',
        'péage': 'peage',
        'PG': 'peage',
        'PESAGE': 'pesage',
        'pesage': 'pesage',
        'PS': 'pesage',
    }
    
    try:
        with transaction.atomic():
            for index, row in df.iterrows():
                try:
                    # Extraire les données
                    nom_poste = str(row['nom']).strip()
                    code_poste = str(row['code']).strip().upper()
                    nom_region = str(row['region']).strip().upper()
                    type_poste_raw = str(row['type']).strip()
                    
                    # Vérifier données non vides
                    if not nom_poste or nom_poste == 'nan':
                        continue
                    
                    if not code_poste or code_poste == 'nan':
                        erreurs_detail.append(f"Ligne {index + 2}: Code manquant pour {nom_poste}")
                        nb_erreurs += 1
                        continue
                    
                    if not nom_region or nom_region == 'nan':
                        erreurs_detail.append(f"Ligne {index + 2}: Région manquante pour {nom_poste}")
                        nb_erreurs += 1
                        continue
                    
                    if not type_poste_raw or type_poste_raw == 'nan':
                        erreurs_detail.append(f"Ligne {index + 2}: Type manquant pour {nom_poste}")
                        nb_erreurs += 1
                        continue
                    
                    # Normaliser le type de poste
                    type_poste = types_valides.get(type_poste_raw.upper())
                    
                    if not type_poste:
                        types_invalides.add(type_poste_raw)
                        erreurs_detail.append(
                            f"Ligne {index + 2}: Type '{type_poste_raw}' invalide pour {nom_poste}. "
                            f"Types acceptés: peage, péage, pesage"
                        )
                        nb_erreurs += 1
                        continue
                    
                    # Chercher la région
                    region = regions_db.get(nom_region)
                    
                    if not region:
                        regions_non_trouvees.add(nom_region)
                        erreurs_detail.append(f"Ligne {index + 2}: Région '{nom_region}' introuvable")
                        nb_erreurs += 1
                        continue
                    
                    # Vérifier si le poste existe déjà
                    poste_existant = Poste.objects.filter(code=code_poste).first()
                    
                    if poste_existant:
                        if action_doublon == 'ecraser':
                            # Mise à jour
                            poste_existant.nom = nom_poste
                            poste_existant.region = region
                            poste_existant.type = type_poste
                            poste_existant.save()
                            nb_modifies += 1
                        else:
                            # Sauter
                            nb_sautes += 1
                    else:
                        # Créer nouveau poste
                        Poste.objects.create(
                            code=code_poste,
                            nom=nom_poste,
                            region=region,
                            type=type_poste,
                            is_active=True
                        )
                        nb_crees += 1
                        
                except Exception as e:
                    erreurs_detail.append(f"Ligne {index + 2}: {str(e)}")
                    nb_erreurs += 1
        
        return {
            'success': True,
            'nb_crees': nb_crees,
            'nb_modifies': nb_modifies,
            'nb_sautes': nb_sautes,
            'nb_erreurs': nb_erreurs,
            'erreurs_detail': erreurs_detail[:50],
            'regions_non_trouvees': list(regions_non_trouvees),
            'types_invalides': list(types_invalides)
        }
        
    except Exception as e:
        return {
            'success': False,
            'erreur': str(e),
            'nb_crees': 0,
            'nb_modifies': 0,
            'nb_sautes': 0,
            'nb_erreurs': 0
        }

@login_required
@user_passes_test(is_admin)
def telecharger_modele_postes_excel(request):
    """Génère et télécharge un modèle Excel pour l'import de postes avec type"""
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Postes à importer"
    
    from openpyxl.styles import Font, PatternFill, Alignment
    
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    
    # En-têtes avec colonne type
    headers = ['nom', 'region', 'code', 'type']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col)
        cell.value = header.upper()
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    
    # Exemples
    exemples = [
        ['Péage de Yaoundé-Nord', 'Centre', 'PG001', 'peage'],
        ['Péage de Douala-Bonabéri', 'Littoral', 'PG002', 'peage'],
        ['Pesage de Bafoussam', 'Ouest', 'PS001', 'pesage'],
        ['Pesage de Ngaoundéré', 'Adamaoua', 'PS002', 'pesage'],
    ]
    
    for row_num, exemple in enumerate(exemples, 2):
        for col, value in enumerate(exemple, 1):
            ws.cell(row=row_num, column=col).value = value
    
    # Ajuster largeurs
    ws.column_dimensions['A'].width = 40
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 15
    ws.column_dimensions['D'].width = 15
    
    # Instructions
    ws_instructions = wb.create_sheet("Instructions")
    instructions = [
        ["INSTRUCTIONS POUR L'IMPORT DE POSTES"],
        [""],
        ["Format du fichier :"],
        ["- Colonne A : Nom complet du poste"],
        ["- Colonne B : Nom de la région (doit correspondre exactement)"],
        ["- Colonne C : Code unique du poste (ex: PG001, PS001)"],
        ["- Colonne D : Type de poste (peage ou pesage)"],
        [""],
        ["Types de poste acceptés :"],
        ["  - peage, péage, PEAGE, PÉAGE, PG"],
        ["  - pesage, PESAGE, PS"],
        [""],
        ["Régions valides :"],
    ]
    
    for region in Region.objects.all().order_by('nom'):
        instructions.append([f"  - {region.nom}"])
    
    instructions.extend([
        [""],
        ["Important :"],
        ["- Le département et l'axe routier peuvent être ajoutés manuellement après"],
        ["- Les codes doivent être uniques"],
        ["- Les noms de régions doivent correspondre exactement"],
        ["- Le type doit être soit 'peage' soit 'pesage'"],
    ])
    
    for row_num, instruction in enumerate(instructions, 1):
        ws_instructions.cell(row=row_num, column=1).value = instruction[0]
    
    ws_instructions.column_dimensions['A'].width = 70
    
    # Sauvegarder
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=modele_import_postes.xlsx'
    
    return response