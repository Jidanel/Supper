# inventaire/services/messages_detail.py
# MESSAGES D'ERREUR DÉTAILLÉS pour tout ce qui ne doit pas se dédoubler (quittances, tickets, amendes, recettes...).
# Principe : au lieu de « existe déjà », on dit QUOI (numéro), OÙ (poste/station), QUAND (date et heure de saisie),
# PAR QUI, pour quel montant, et POURQUOI (ticket vendu, gelé, supprimé, transféré...).
# Toutes les fonctions retournent du texte français prêt à afficher ; elles ne lèvent jamais d'exception
# (en cas de champ absent, la partie correspondante est simplement omise).

from django.utils import timezone  # Conversion en heure locale


# ----------------------------------------------------------------------------------------------
# Petits outils de mise en forme
# ----------------------------------------------------------------------------------------------
def fmt_date(d):
    """date -> '12/11/2026' ('date inconnue' si vide)."""
    try:
        return d.strftime('%d/%m/%Y') if d else 'date inconnue'
    except Exception:
        return str(d)


def fmt_dt(dt):
    """datetime -> 'le 12/11/2026 à 14:32' en heure locale (Cameroun)."""
    if not dt:
        return "à une date inconnue"
    try:
        if timezone.is_aware(dt):
            dt = timezone.localtime(dt)
        return f"le {dt:%d/%m/%Y} à {dt:%H:%M}"
    except Exception:
        return str(dt)


def fmt_montant(m):
    """Montant -> '160 000 FCFA'."""
    try:
        return f"{int(round(float(m))):,}".replace(',', ' ') + " FCFA"
    except Exception:
        return f"{m} FCFA"


def qui(user):
    """Utilisateur -> 'Nom (matricule)'."""
    if not user:
        return "un utilisateur inconnu"
    nom = getattr(user, 'nom_complet', '') or getattr(user, 'username', '') or str(user)
    mat = getattr(user, 'username', '')
    return f"{nom} ({mat})" if mat and mat != nom else nom


def _periode_quittance(q):
    """Texte de la période couverte par une quittance (jour ou décade)."""
    if getattr(q, 'type_declaration', '') == 'decade' and getattr(q, 'date_debut_decade', None):
        return f"décade du {fmt_date(q.date_debut_decade)} au {fmt_date(q.date_fin_decade)}"
    return f"recette du {fmt_date(getattr(q, 'date_recette', None))}"


# ----------------------------------------------------------------------------------------------
# Quittances / reçus de versement
# ----------------------------------------------------------------------------------------------
def detail_quittance_peage(q):
    """Description complète d'une quittance péage déjà enregistrée."""
    return (f"Quittance/reçu n° {q.numero_quittance} — poste de péage {q.poste.nom}, {_periode_quittance(q)}, "
            f"montant {fmt_montant(q.montant)}, quittancée le {fmt_date(q.date_quittancement)}, "
            f"enregistrée {fmt_dt(getattr(q, 'date_saisie', None))} par {qui(getattr(q, 'saisi_par', None))}")


def detail_quittance_pesage(q):
    """Description complète d'une quittance pesage déjà enregistrée."""
    return (f"Quittance/reçu n° {q.numero_quittance} — station de pesage {q.station.nom}, {_periode_quittance(q)}, "
            f"montant {fmt_montant(q.montant_quittance)}, quittancée le {fmt_date(q.date_quittancement)}, "
            f"enregistrée {fmt_dt(getattr(q, 'date_saisie', None) or getattr(q, 'date_creation', None))} "
            f"par {qui(getattr(q, 'saisi_par', None))}")


def quittance_existante(numero, exclude_peage_pk=None, exclude_pesage_pk=None):
    """Cherche un numéro de quittance dans le péage ET le pesage. Retourne un message détaillé, ou None."""
    numero = (numero or '').strip()
    if not numero:
        return None
    from inventaire.models import Quittancement
    q = Quittancement.objects.select_related('poste', 'saisi_par').filter(numero_quittance__iexact=numero)
    if exclude_peage_pk:
        q = q.exclude(pk=exclude_peage_pk)
    q = q.first()
    if q:
        return (f"❌ Le numéro de quittance « {numero} » est DÉJÀ ENREGISTRÉ (péage) : {detail_quittance_peage(q)}. "
                f"Un même numéro ne peut pas être saisi deux fois.")
    try:
        from inventaire.models_pesage import QuittancementPesage
        qp = QuittancementPesage.objects.select_related('station', 'saisi_par').filter(numero_quittance__iexact=numero)
        if exclude_pesage_pk:
            qp = qp.exclude(pk=exclude_pesage_pk)
        qp = qp.first()
        if qp:
            return (f"❌ Le numéro de quittance « {numero} » est DÉJÀ ENREGISTRÉ (pesage) : "
                    f"{detail_quittance_pesage(qp)}. Un même numéro ne peut pas être saisi deux fois.")
    except Exception:
        pass
    return None


def historique_quittance_existant(h):
    """Description d'un historique ou extrait de compte déjà enregistré."""
    return (f"Historique/extrait n° {h.numero_historique} — poste {h.poste.nom}, mois {getattr(h, 'mois', '')} "
            f"{getattr(h, 'annee', '')}, montant de l'extrait {fmt_montant(getattr(h, 'montant_reel', 0))}, "
            f"enregistré {fmt_dt(getattr(h, 'date_saisie', None))} par {qui(getattr(h, 'saisi_par', None))}")


# ----------------------------------------------------------------------------------------------
# Recettes, inventaires, amendes, pesées
# ----------------------------------------------------------------------------------------------
def detail_recette(r):
    """Description d'une recette journalière péage déjà enregistrée."""
    return (f"Recette du {fmt_date(r.date)} — poste {r.poste.nom}, montant déclaré {fmt_montant(r.montant_declare)}, "
            f"saisie {fmt_dt(getattr(r, 'date_saisie', None))} par {qui(getattr(r, 'chef_poste', None))}")


def detail_inventaire(inv):
    """Description d'un inventaire journalier déjà enregistré."""
    return (f"Inventaire du {fmt_date(inv.date)} — poste {inv.poste.nom}, {getattr(inv, 'total_vehicules', 0)} véhicule(s) "
            f"sur {getattr(inv, 'nombre_periodes_saisies', 0)} période(s), saisi {fmt_dt(getattr(inv, 'date_creation', None))} "
            f"par {qui(getattr(inv, 'agent_saisie', None))}")


def detail_amende(a):
    """Description d'une amende (ticket d'amende) déjà enregistrée."""
    types = [n for n, v in (('surcharge', a.est_surcharge), ('hors gabarit', a.est_hors_gabarit),
                            ('délit de fuite', a.est_delit_fuite)) if v]
    return (f"Ticket d'amende n° {a.numero_ticket} — station {a.station.nom}, véhicule {a.immatriculation}, "
            f"{' + '.join(types) or 'infraction'}, montant {fmt_montant(a.montant_amende)}, "
            f"émis {fmt_dt(a.date_heure_emission)}, enregistré par {qui(getattr(a, 'saisi_par', None))}, "
            f"statut : {a.get_statut_display() if hasattr(a, 'get_statut_display') else ''}")


def amende_existante(numero, exclude_pk=None):
    """Message détaillé si ce numéro de ticket d'amende est déjà enregistré, sinon None."""
    numero = (numero or '').strip()
    if not numero:
        return None
    from inventaire.models_pesage import AmendeEmise
    qs = AmendeEmise.objects.select_related('station', 'saisi_par').filter(numero_ticket__iexact=numero)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    a = qs.first()
    if not a:
        return None
    return (f"❌ Le ticket d'amende n° « {numero} » est DÉJÀ ENREGISTRÉ : {detail_amende(a)}. "
            f"Un même numéro de ticket d'amende ne peut pas être saisi deux fois.")


def detail_pesees(p):
    """Description d'une saisie de pesées journalières déjà enregistrée."""
    return (f"Pesées du {fmt_date(p.date)} — station {p.station.nom}, saisies {fmt_dt(getattr(p, 'date_saisie', None))} "
            f"par {qui(getattr(p, 'saisi_par', None))}")


# ----------------------------------------------------------------------------------------------
# Tickets : pourquoi un ticket n'est pas disponible
# ----------------------------------------------------------------------------------------------
def _plage(s):
    return f"{s.numero_premier}" if s.numero_premier == s.numero_dernier else f"{s.numero_premier}-{s.numero_dernier}"


def expliquer_ticket(poste, couleur, numero):
    """Raconte la vie du ticket `numero` (couleur) vis-à-vis du poste demandé : vendu, en stock ailleurs, gelé,
    supprimé, permuté, transféré, jamais chargé... Retourne une phrase précise."""
    from inventaire.models import SerieTicket
    nom_c = getattr(couleur, 'libelle_affichage', str(couleur))
    base = f"Ticket {nom_c} n° {numero}"
    faits = []

    series = list(SerieTicket.objects.select_related('poste', 'reference_recette', 'poste_destination_transfert')
                  .filter(couleur=couleur, numero_premier__lte=numero, numero_dernier__gte=numero)
                  .order_by('date_reception'))
    for s in series:
        lieu = f"poste {s.poste.nom}"
        charge = f"chargé {fmt_dt(s.date_reception)} ({s.get_type_entree_display()})" if s.type_entree else f"chargé {fmt_dt(s.date_reception)}"
        if s.statut == 'vendu':
            rec = s.reference_recette
            qui_vendu = (f", recette déclarée {fmt_dt(rec.date_saisie)} par {qui(rec.chef_poste)}" if rec else '')
            quand = (f"lors de la recette du {fmt_date(s.date_utilisation)}" if s.date_utilisation
                     else "(date de vente non renseignée)")
            montant = (f" ({fmt_montant(rec.montant_declare)})" if rec else '')
            faits.append(f"VENDU au {lieu} {quand}{montant}{qui_vendu} ; {charge}")
        elif s.statut == 'stock':
            if poste and s.poste_id == poste.pk:
                faits.append(f"EN STOCK au {lieu} (série {_plage(s)}), {charge}")
            else:
                faits.append(f"EN STOCK dans un AUTRE poste : {lieu} (série {_plage(s)}), {charge} — "
                             f"il n'est pas au poste {poste.nom if poste else 'demandé'}")
        elif s.statut == 'transfere':
            dest = s.poste_destination_transfert.nom if s.poste_destination_transfert else 'un autre poste'
            faits.append(f"TRANSFÉRÉ depuis le {lieu} vers {dest} ; {charge}")
        else:
            faits.append(f"statut « {s.statut} » au {lieu} ; {charge}")

    # Banque de gel
    try:
        from inventaire.models_banque_gel import BanqueGel, StatutGel
        for b in BanqueGel.objects.select_related('poste_origine', 'poste_destination', 'gele_par').filter(
                couleur=couleur, numero_premier__lte=numero, numero_dernier__gte=numero):
            if b.statut == StatutGel.GELE:
                faits.append(f"GELÉ (banque de gel) depuis le {fmt_date(b.date_effet_gel)}, ancien poste "
                             f"{b.poste_origine.nom}, par {qui(b.gele_par)} — motif : {b.motif_gel}")
            elif b.statut == StatutGel.DEGELE:
                faits.append(f"GELÉ puis DÉGELÉ vers {b.poste_destination.nom if b.poste_destination else '?'} "
                             f"(effet {fmt_date(b.date_effet_degel)}), ancien poste {b.poste_origine.nom}")
    except Exception:
        pass

    # Suppressions administratives (historique de stock)
    try:
        from inventaire.models import HistoriqueStock
        pattern = f"{couleur.libelle_affichage}"
        for h in HistoriqueStock.objects.select_related('poste', 'effectue_par').filter(
                commentaire__startswith="Suppression administrative", commentaire__contains=pattern)[:50]:
            import re
            m = re.search(r"#(\d+)-(\d+)", h.commentaire or '')
            if m and int(m.group(1)) <= numero <= int(m.group(2)):
                faits.append(f"SUPPRIMÉ du stock du poste {h.poste.nom} par {qui(h.effectue_par)} "
                             f"{fmt_dt(getattr(h, 'date_saisie', None) or h.date_mouvement)} (suppression administrative)")
    except Exception:
        pass

    # Permutations (tuée / réveillée)
    try:
        from inventaire.services.permutation_service import historique_ticket
        for p in historique_ticket(couleur, numero):
            faits.append(f"CONCERNÉ par la permutation n°{p.pk} du poste {p.poste.nom} ({p.get_statut_display()}) "
                         f"{fmt_dt(getattr(p, 'date_operation', None))} par {qui(p.effectue_par)} — motif : {p.motif}")
    except Exception:
        pass

    if not faits:
        return f"{base} : AUCUNE trace — ce numéro n'a jamais été chargé dans SUPPER (ni stock, ni vente, ni transfert)."
    return f"{base} : " + " | ".join(faits)


def expliquer_indisponibilite(poste, couleur, premier, dernier):
    """Explique pourquoi la plage premier..dernier n'est pas entièrement disponible au poste.
    Regroupe les numéros par situation identique pour rester lisible (maximum 6 situations détaillées)."""
    from inventaire.models import SerieTicket
    dispo = list(SerieTicket.objects.filter(poste=poste, couleur=couleur, statut='stock').order_by('numero_premier'))
    manquants, courant = [], None
    for n in range(premier, dernier + 1):
        ok = any(s.numero_premier <= n <= s.numero_dernier for s in dispo)
        if not ok:
            if courant and courant[1] == n - 1:
                courant[1] = n
            else:
                courant = [n, n]
                manquants.append(courant)
        if len(manquants) > 6:
            break
    lignes = []
    for a, b in manquants[:6]:
        # Un seul ticket représentatif par sous-plage : même explication pour toute la sous-plage contiguë
        texte = expliquer_ticket(poste, couleur, a)
        plage = f"{a}" if a == b else f"{a} à {b}"
        lignes.append(f"• Tickets {plage} : {texte.split(' : ', 1)[1] if ' : ' in texte else texte}")
    entete = (f"❌ Les tickets {couleur.libelle_affichage} {premier}-{dernier} ne sont PAS tous disponibles au poste "
              f"{poste.nom}.")
    if dispo:
        entete += " Séries disponibles : " + ", ".join(_plage(s) for s in dispo[:15]) + "."
    else:
        entete += f" Le poste {poste.nom} n'a aucun ticket {couleur.libelle_affichage} en stock."
    return entete + ("\n" + "\n".join(lignes) if lignes else '')


# ----------------------------------------------------------------------------------------------
# Description générique d'un objet quelconque (utilisée par le gestionnaire central de doublons)
# ----------------------------------------------------------------------------------------------
def decrire_objet(obj):
    """Description générique : 'Nom du modèle — champ : valeur, ...' avec les libellés lisibles des champs."""
    try:
        morceaux = []
        for f in obj._meta.concrete_fields:
            if f.name == 'id' or f.primary_key:
                continue
            val = getattr(obj, f.name, None)
            if val in (None, ''):
                continue
            if hasattr(f, 'choices') and f.choices:
                val = getattr(obj, f'get_{f.name}_display', lambda: val)()
            elif getattr(f, 'remote_field', None):
                val = str(val)
            elif hasattr(val, 'strftime'):
                val = fmt_dt(val)[3:] if hasattr(val, 'hour') else fmt_date(val)
            morceaux.append(f"{getattr(f, 'verbose_name', f.name)} : {val}")
            if len(morceaux) >= 10:
                break
        return f"{obj._meta.verbose_name} (#{obj.pk}) — " + ", ".join(morceaux)
    except Exception:
        return str(obj)


# ----------------------------------------------------------------------------------------------
# Utilisateurs et postes : doublons de matricule / de code
# ----------------------------------------------------------------------------------------------
def utilisateur_existant(matricule, exclude_pk=None):
    """Message détaillé si ce matricule est déjà attribué, sinon None."""
    from accounts.models import UtilisateurSUPPER  # Import local : évite les imports circulaires
    qs = UtilisateurSUPPER.objects.filter(username__iexact=(matricule or '').strip())
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    u = qs.select_related('poste_affectation').first()
    if not u:
        return None
    poste = getattr(u, 'poste_affectation', None)
    return (f"❌ Le matricule « {matricule} » est DÉJÀ ATTRIBUÉ à {u.nom_complet} "
            f"(rôle : {u.get_habilitation_display()}, poste : {poste.nom if poste else 'aucun'}, "
            f"compte {'actif' if u.is_active else 'DÉSACTIVÉ'}, créé {fmt_dt(getattr(u, 'date_creation', None))}).")


def poste_existant(code, exclude_pk=None):
    """Message détaillé si ce code de poste est déjà utilisé, sinon None."""
    from accounts.models import Poste  # Import local
    qs = Poste.objects.filter(code__iexact=(code or '').strip())
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    p = qs.first()
    if not p:
        return None
    return (f"❌ Le code « {code} » est DÉJÀ UTILISÉ par le poste « {p.nom} » "
            f"(type : {p.get_type_display()}, région : {getattr(p.region, 'nom', 'non définie')}, "
            f"{'actif' if getattr(p, 'is_active', True) else 'DÉSACTIVÉ'}).")


# ----------------------------------------------------------------------------------------------
# Montant d'une quittance de péage : multiple de 500 (prix d'un ticket)
# ----------------------------------------------------------------------------------------------
def montant_non_multiple_500(montant):
    """Message explicatif si `montant` n'est pas un multiple de 500 FCFA, sinon None."""
    try:
        valeur = int(round(float(montant)))  # Montant entier en FCFA
    except (TypeError, ValueError):
        return None  # Les autres contrôles gèrent les montants invalides
    if valeur % 500 == 0:
        return None
    bas = (valeur // 500) * 500  # Multiple de 500 inférieur
    haut = bas + 500  # Multiple de 500 supérieur
    return (f"❌ Montant refusé : {fmt_montant(valeur)} n'est pas un multiple de 500. "
            f"Un ticket de péage coûte 500 FCFA : le montant d'une quittance doit donc être un multiple de 500 "
            f"(500, 1 000, 1 500, 2 000…). Montants les plus proches : {fmt_montant(bas)} ou {fmt_montant(haut)}. "
            f"Vérifiez le montant écrit sur la quittance.")
