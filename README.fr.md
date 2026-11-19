<p align="center">
  <img src="assets/banner-fr.svg" alt="Glowback : lumière d'ambiance pour les LED RGB au dos de votre écran, chaque LED synchronisée à l'image en temps réel" width="100%">
</p>

<p align="center">
  <a href="README.md">English</a> · <b>Français</b> · <a href="README.es.md">Español</a> · <a href="README.de.md">Deutsch</a> · <a href="README.it.md">Italiano</a> · <a href="README.pt.md">Português</a>
</p>

<h1 align="center">Glowback : la lumière d'ambiance pour les écrans avec LED RGB à l'arrière</h1>

<p align="center">
  <b>Synchronisation écran gratuite et open source pour les LED RGB au dos de votre écran.</b><br>
  Chaque LED suit la partie de l'image juste devant elle, en temps réel.<br>
  Compatible avec les appareils <b>Éclairage dynamique de Windows 11</b> et <b>OpenRGB</b>. Sans ruban LED, caméra ni logiciel constructeur.
</p>

<p align="center">
  <a href="https://github.com/Ilyomix/glowback/releases/latest/download/GlowbackSetup.exe"><img alt="Télécharger pour Windows" src="https://img.shields.io/github/v/release/Ilyomix/glowback?label=t%C3%A9l%C3%A9charger%20pour%20Windows&color=7c3aed"></a>
  <img alt="Windows 10/11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows">
  <img alt="Compatible HDR" src="https://img.shields.io/badge/HDR-compatible-ff8a3d">
  <img alt="6 langues" src="https://img.shields.io/badge/langues-6-0ea5e9">
  <a href="LICENSE"><img alt="Licence MIT" src="https://img.shields.io/badge/licence-MIT-blue"></a>
</p>

<p align="center">
  <a href="#-installation">Installation</a> ·
  <a href="#-mon-écran-est-il-compatible-">Compatibilité</a> ·
  <a href="#-menu-de-licône">Menu</a> ·
  <a href="#%EF%B8%8F-désinstaller">Désinstaller</a> ·
  <a href="#-faq">FAQ</a> ·
  <a href="https://ilyomix.github.io/glowback/fr/">Site</a>
</p>

---

De plus en plus d'écrans gaming ont des LED RGB au dos, mais leur logiciel se limite à des effets fixes, respiration ou arc-en-ciel. **Glowback** en fait une **vraie lumière d'ambiance** : il capture l'écran 30 fois par seconde et donne **une couleur propre à chaque LED**, prise sur le bord de l'image juste devant elle. Un coucher de soleil à gauche de l'écran, et le mur de gauche devient orange ; une explosion à droite, et c'est le côté droit qui s'allume.

Glowback n'est lié à aucune marque. Il pilote tout appareil que l'**Éclairage dynamique de Windows** (le standard HID LampArray) ou **[OpenRGB](https://openrgb.org)** sait contrôler : écrans, rubans LED, boîtiers PC, lampes. Pas de LED compatibles ? [Ajoutez un ruban DIY à 5 $](docs/DIY-LED-strip.md).

## ✨ Fonctionnalités

- 🎯 **Une zone par LED** : chaque LED est projetée sur le bord d'écran le plus proche, pour que la lumière autour de l'écran prolonge l'image. Un mode « couleur moyenne » existe aussi.
- 🎬 **Films, jeux, HDR** : la capture GPU (DXGI) voit la vidéo et les jeux en plein écran, gère le HDR et **ignore les bandes noires des films**.
- 💡 **Couleurs lumineuses et fidèles** : une courbe de luminosité qui conserve la teinte garde la lueur visible dans les scènes sombres.
- 🪟 **Une vraie application Windows** : installateur, menu Démarrer, lancement au démarrage, menu sombre près de l'horloge avec l'état en direct, désinstallation propre depuis *Paramètres → Applications*.
- 🔄 **Mises à jour signalées** : Glowback vérifie GitHub une fois par jour et vous prévient quand une nouvelle version sort. Un interrupteur permet de le désactiver.
- 🏠 **Home Assistant et Google Assistant** : Glowback apparaît comme une lumière à piloter depuis vos tableaux de bord, vos automatisations ou à la voix.
- 🌍 **6 langues** : français, anglais, espagnol, allemand, italien, portugais, selon la langue de Windows.
- 🔌 **Plug and play** : détecte automatiquement les appareils Éclairage dynamique et OpenRGB, et lit la position physique de chaque LED.
- 🖥️ **Multi-écran** : chaque appareil LED suit son propre écran (reconnu par son nom EDID).
- 🎨 **Balance des blancs** par appareil, pour que le mur soit blanc quand l'écran l'est.
- 🪶 **Léger** : environ 0,5 ms de CPU par image. La version Python tient en un seul fichier, sans dépendance.

## 🚀 Installation

1. **Branchez le câble USB montant de l'écran** au PC (USB-B ou USB-C). Les écrans en ont généralement besoin pour que le PC accède à leurs LED.
2. **Désactivez l'Éclairage dynamique de Windows pour cet appareil**, sinon Windows et Glowback se disputent les LED : *Paramètres → Personnalisation → Éclairage dynamique → votre appareil → « Utiliser l'éclairage dynamique sur mes appareils » → Désactivé*.
3. **Installez Glowback :**

| | |
|---|---|
| **Installateur (recommandé)** | Téléchargez [**GlowbackSetup.exe**](https://github.com/Ilyomix/glowback/releases/latest/download/GlowbackSetup.exe) et suivez l'assistant. Pas besoin de droits administrateur. |
| Portable | [GlowbackTray.exe](https://github.com/Ilyomix/glowback/releases/latest/download/GlowbackTray.exe) (application) et [glowback.exe](https://github.com/Ilyomix/glowback/releases/latest/download/glowback.exe) (ligne de commande) |
| Python 3.9+ | `pip install git+https://github.com/Ilyomix/glowback`, puis `glowback --install` |

> Windows SmartScreen peut signaler un éditeur inconnu, car l'application n'est pas encore signée. Cliquez sur *Informations complémentaires → Exécuter quand même*. Le code source et les versions compilées sont publics sur GitHub. [Politique de signature du code](CODE_SIGNING.md) · [Confidentialité](PRIVACY.md)

Glowback s'installe ensuite près de l'horloge. Pour vérifier l'orientation des LED : *menu Démarrer → Outils Glowback → Tester les LED*. La gauche doit être rouge, la droite bleue.

## ✅ Mon écran est-il compatible ?

Glowback fonctionne avec votre écran (ou ruban LED, boîtier, lampe…) si **l'une** de ces conditions est remplie :

1. **Il apparaît dans Windows** sous *Paramètres → Personnalisation → Éclairage dynamique*. Glowback le pilote directement.
2. **Il est pris en charge par [OpenRGB](https://openrgb.org)**. Lancez OpenRGB avec son serveur SDK : Glowback le détecte automatiquement.
3. **Ni l'un ni l'autre ?** Collez un ruban LED derrière l'écran et pilotez-le avec une carte RP2040 à 5 $ : [guide DIY](docs/DIY-LED-strip.md) (en anglais).

`glowback --list` (ou l'état affiché dans le menu de l'icône) montre ce que Glowback a trouvé.

**Appareils testés**

| Appareil | LED | Via | Statut |
|---|---|---|---|
| AOC AGON PRO AG276QZD2 | 47 | Éclairage dynamique | ✅ Testé |
| *Votre écran ?* | | | [Ajoutez-le](https://github.com/Ilyomix/glowback/issues/new?template=device-report.yml) |

Ça marche sur un autre écran ? Ouvrez un [rapport d'appareil](https://github.com/Ilyomix/glowback/issues/new?template=device-report.yml) avec la sortie de `glowback --list` et une courte vidéo : chaque rapport ajoute une ligne à ce tableau.

## 🪟 Menu de l'icône

Clic droit (ou gauche) sur l'icône Glowback près de l'horloge :

- **État** : actif avec le nombre de LED, en pause, ou en recherche de LED
- **Lumière d'ambiance** : pause ou reprise. En pause, les LED reprennent l'effet de l'appareil
- Interrupteurs **Lancer au démarrage** et **Vérifier les mises à jour**
- **Home Assistant** : état de la connexion, cliquez pour le connecter
- **Mode** : chaque LED suit sa zone, ou une seule couleur moyenne
- **Luminosité** : 100 / 75 / 50 / 25 %
- **Créé par Ilyomix**, **Mettre une étoile sur GitHub**, **Ouvrir le journal**, **Quitter**

Les réglages sont mémorisés. Des outils supplémentaires sont dans le menu Démarrer : *Tester les LED* et *Calibrer la balance des blancs*.

## 🏠 Home Assistant et Google Assistant

Glowback peut apparaître dans [Home Assistant](https://www.home-assistant.io) comme une lumière : pilotez la lumière d'ambiance depuis vos tableaux de bord et vos automatisations, ou à la voix avec Google Assistant et Alexa.

1. **Dans Home Assistant** : installez l'application **Mosquitto broker** (*Paramètres → Applications*) et démarrez-la. Home Assistant propose ensuite l'intégration **MQTT** dans *Paramètres → Appareils et services* : ajoutez-la.
2. **Un utilisateur pour Glowback** (conseillé) : *Paramètres → Personnes → Utilisateurs → Ajouter un utilisateur*, par exemple `glowback`. Si *Utilisateurs* n'apparaît pas, activez le *Mode avancé* dans votre profil.
3. **Dans Glowback** : ouvrez le panneau, cliquez sur **Home Assistant**, saisissez l'adresse (`homeassistant.local` marche en général, sinon l'IP de Home Assistant), l'utilisateur et son mot de passe, puis **Connecter**.

Glowback apparaît alors dans *Paramètres → Appareils et services → MQTT* :

| Entité | Rôle |
|---|---|
| `light.glowback` | Allumé/éteint = lumière d'ambiance, luminosité, et le mode en effet (*Zones* ou *Average*) |
| `sensor.glowback_leds` | Nombre de LED pilotées par Glowback |
| `update.glowback` | Signale une nouvelle version, et l'installe |

Elle passe en *indisponible* quand le PC est éteint ou Glowback fermé. Le mot de passe est chiffré pour votre compte Windows et n'est envoyé qu'à votre broker.

**Google Assistant** : avec [Home Assistant Cloud](https://www.nabucasa.com), ouvrez *Paramètres → Assistants vocaux → Exposer* et exposez **Glowback**, puis dites *« Ok Google, éteins Glowback »* ou *« Ok Google, mets Glowback à 50 % »*. Sans abonnement, suivez la [configuration manuelle de Google Assistant](https://www.home-assistant.io/integrations/google_assistant/) de Home Assistant. Alexa fonctionne de la même façon.

Exemple d'automatisation, lumière d'ambiance coupée à minuit :

```yaml
automation:
  - alias: Glowback éteint la nuit
    triggers:
      - trigger: time
        at: "00:00:00"
    actions:
      - action: light.turn_off
        target:
          entity_id: light.glowback
```

En ligne de commande : `glowback --home-assistant mqtt://glowback:MOTDEPASSE@homeassistant.local` (`mqtts://` pour TLS sur le port 8883, `off` pour retirer Glowback de Home Assistant).

## 🗑️ Désinstaller

- **Installé avec GlowbackSetup.exe** : *Paramètres → Applications → Applications installées → Glowback → Désinstaller*. Glowback s'arrête, les LED reprennent l'effet de l'appareil, et son lancement au démarrage, ses réglages et ses journaux sont supprimés.
- **Version Python** : `glowback --uninstall`, puis `pip uninstall glowback`.
- **Portable** : `glowback.exe --uninstall`, puis supprimez les fichiers .exe.

Pour le couper un moment, utilisez l'interrupteur **Lumière d'ambiance** du menu. Pour qu'il ne se lance plus avec Windows, désactivez **Lancer au démarrage**.

## ⚙️ Ligne de commande

| Option | Défaut | Description |
|---|---|---|
| `--mode zones\|average` | `zones` | Chaque LED suit sa zone, ou une seule couleur |
| `--brightness 0-100` | `100` | Luminosité des LED |
| `--boost` | `1.8` | Remonte les couleurs sombres sans changer leur teinte (`1` = désactivé) |
| `--saturation` | `1.25` | Renforcement des couleurs (`1` = couleurs fidèles) |
| `--smoothing` | `0.1` | Durée des transitions en secondes |
| `--radius` | `0.12` | Taille de la zone de chaque LED, en fraction de la hauteur d'écran |
| `--blend 0-1` | `0` | Mélange la moyenne de l'écran dans chaque zone, pour une lueur plus calme |
| `--letterbox on\|off` | `on` | Ignore les bandes noires des films |
| `--capture auto\|dxgi\|gdi` | `auto` | Capture GPU (DXGI) avec repli sur GDI |
| `--fps` | `30` | Mises à jour par seconde (l'appareil peut la plafonner) |
| `--screen` | `auto` | `auto`, `primary`, un numéro de `--list` ou un nom |
| `--device` | appareils d'ambiance | Partie du nom ou `VID:PID`, ou `all` pour inclure claviers et souris |
| `--openrgb [HÔTE:PORT\|off]` | `auto` | Serveur SDK OpenRGB à utiliser (détecté automatiquement sur ce PC) |
| `--home-assistant mqtt://UTILISATEUR:MOTDEPASSE@HÔTE\|off` | | Affiche Glowback dans [Home Assistant](#-home-assistant-et-google-assistant) (mémorisé) |
| `--strip-start` / `--strip-ccw` | `bottom-left` | Début et sens des rubans LED OpenRGB |
| `--mirror` / `--flip` | non | Inverse gauche/droite ou haut/bas |
| `--calibrate` · `--white-balance R,G,B` | | Balance des blancs par appareil (interactive) ou multiplicateurs fixes |
| `--lang en\|fr\|es\|de\|it\|pt` | langue de Windows | Langue de l'interface |
| `--install` / `--uninstall` | | Ajoute à Windows ou retire de Windows (démarrage, menu Démarrer) |
| `--check-updates on\|off` | `on` | Cherche une nouvelle version sur GitHub une fois par jour ([confidentialité](PRIVACY.md)) |
| `--list` · `--test` · `--stop` | | Lister appareils et écrans · motif de test · arrêter Glowback |
| `--diy-layout LxH:G,H,D,B` | | Positions des LED pour le [firmware DIY](docs/DIY-LED-strip.md) |

## 🔬 Fonctionnement

1. **Appareils** : Glowback cherche les interfaces HID de page d'usage `0x59` (*Lighting and Illumination*), usage `LampArray`, et lit la disposition de leurs rapports dans le descripteur HID : aucun code spécifique à une marque. Les appareils OpenRGB sont pilotés via son protocole SDK.
2. **Géométrie** : chaque LED LampArray indique sa position X/Y/Z. Glowback projette chaque LED depuis le centre vers le bord de l'écran. Les rubans LED sont répartis autour de l'écran.
3. **Capture** : DXGI Desktop Duplication fournit chaque image sur le GPU, `GenerateMips` la réduit à environ 80×45, et seule cette mini-image est relue. Les images HDR (FP16 scRGB) sont converties selon votre réglage *Luminosité du contenu SDR*.
4. **Sortie** : couleurs lissées puis envoyées par `LampMultiUpdateReport` après avoir quitté l'`AutonomousMode`, qui est rétabli à la sortie.

Tout le programme tient dans un fichier lisible : [`glowback.py`](glowback.py).

## ❓ FAQ

### Quels écrans sont compatibles ?
Tout écran dont l'éclairage RGB arrière peut être contrôlé par l'Éclairage dynamique de Windows ou par OpenRGB. Lancez `glowback --list`, ou cherchez votre écran dans *Paramètres → Personnalisation → Éclairage dynamique*.

### Comment synchroniser l'éclairage RGB de mon écran avec l'image ?
Installez Glowback, désactivez l'Éclairage dynamique de Windows pour l'écran, et c'est tout : les LED suivent l'image.

### Peut-on avoir une lumière d'ambiance synchronisée sans ruban LED ?
Oui, si votre écran a déjà des LED RGB au dos que l'Éclairage dynamique de Windows ou OpenRGB peut contrôler. Sinon, le [guide DIY](docs/DIY-LED-strip.md) en ajoute pour une dizaine d'euros.

### Ça marche en HDR, dans les jeux et les films en plein écran ?
Oui. La capture DXGI gère les jeux plein écran et sans bordure, les lecteurs vidéo et le bureau HDR, et les bandes noires sont ignorées. Les flux protégés par DRM (par exemple une partie de Netflix dans les navigateurs) sont en général masqués en noir par Windows pour tous les outils de capture.

### Est-ce que ça ralentit mes jeux ?
C'est conçu pour ne pas le faire : la carte graphique fait la réduction d'image, et Glowback utilise environ 0,5 ms de CPU par image à 30 img/s.

### Rien ne s'allume.
Vérifiez que le câble USB montant de l'écran est branché au PC, que l'éclairage RGB est activé dans le menu de l'écran, et que l'Éclairage dynamique de Windows est désactivé pour cet appareil. L'état du menu de l'icône et `glowback --list` montrent ce que voit Glowback.

### Les couleurs sont du mauvais côté.
Utilisez *Tester les LED* dans le menu Démarrer (ou `glowback --test`). Si gauche et droite sont inversés, ajoutez `--mirror` ; si haut et bas sont inversés, ajoutez `--flip`.

## 🗺️ Feuille de route

- [x] Menu de l'icône, installateur, lancement au démarrage, désinstallation, mises à jour signalées
- [x] Capture DXGI, HDR, détection des bandes noires
- [x] Sortie OpenRGB (détectée automatiquement), guide DIY RP2040, balance des blancs
- [x] 6 langues
- [x] Home Assistant, et par lui Google Assistant et Alexa
- [ ] Installateur signé et `winget install Glowback`
- [ ] Écrans en mode portrait dans la capture DXGI
- [ ] Firmware RP2040 précompilé (.uf2)

## ⭐ Soutien

Si Glowback a illuminé votre bureau, **mettez une étoile au dépôt** : ça aide les autres propriétaires d'écrans RGB à le trouver.

---

<sub>Mots-clés : lumière d'ambiance PC, éclairage d'ambiance écran, synchronisation RGB écran, rétroéclairage mural, bias lighting, écran gaming RGB, Éclairage dynamique Windows 11, HID LampArray, OpenRGB synchronisation écran, LED arrière écran, lumière d'ambiance HDR, alternative à Ambilight pour PC, alternative à Hyperion.</sub>

<sub>Ambilight est une marque de Koninklijke Philips N.V. / TP Vision. Les autres noms de produits sont des marques de leurs propriétaires respectifs. Glowback est un projet open source indépendant, sans lien ni approbation de leur part. Inter est sous [licence SIL Open Font](licenses/Inter-OFL.txt).</sub>

MIT © [Ilyomix](https://github.com/Ilyomix) · [Politique de signature du code](CODE_SIGNING.md) · [Confidentialité](PRIVACY.md)
