<p align="center">
  <img src="assets/banner.svg" alt="Glowback : Ambilight pour écran PC avec LED RGB à l'arrière, chaque LED synchronisée à l'image en temps réel" width="100%">
</p>

<h1 align="center">Glowback : l'Ambilight pour les LED RGB au dos de votre écran PC</h1>

<p align="center">
  <b>Synchronisation écran gratuite et open source pour les LED RGB à l'arrière de votre moniteur.</b><br>
  Chaque LED suit la partie de l'image juste devant elle, en temps réel, comme une TV Philips Ambilight.<br>
  Sans ruban LED, sans caméra, sans logiciel constructeur. Compatible avec tout appareil <b>Éclairage dynamique de Windows 11</b>.
</p>

<p align="center">
  <a href="https://github.com/Ilyomix/glowback/releases/latest"><img alt="Télécharger pour Windows" src="https://img.shields.io/github/v/release/Ilyomix/glowback?label=t%C3%A9l%C3%A9charger%20pour%20Windows&color=7c3aed"></a>
  <img alt="Windows 10/11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows">
  <img alt="Compatible HDR" src="https://img.shields.io/badge/HDR-compatible-ff8a3d">
  <img alt="Zéro dépendance" src="https://img.shields.io/badge/d%C3%A9pendances-0-success">
  <a href="LICENSE"><img alt="Licence MIT" src="https://img.shields.io/badge/licence-MIT-blue"></a>
</p>

<p align="center">
  <a href="#-démarrage-rapide">Démarrage rapide</a> ·
  <a href="#-écrans-et-appareils-compatibles">Appareils compatibles</a> ·
  <a href="#-icône-de-notification-et-intégration-windows">Intégration Windows</a> ·
  <a href="#%EF%B8%8F-désinstaller">Désinstaller</a> ·
  <a href="#-faq">FAQ</a> ·
  <a href="https://ilyomix.github.io/glowback/">Site</a> ·
  <a href="README.md">🇬🇧 English</a>
</p>

---

Les écrans gaming comme l'**AOC AGON PRO** (Light FX) ont des LED RGB adressables au dos, mais le logiciel fourni se limite à des effets fixes, respiration ou arc-en-ciel. **Glowback** en fait un véritable **éclairage d'ambiance façon Ambilight** : il capture l'écran 30 fois par seconde et donne **une couleur propre à chaque LED**, prise sur le bord de l'image juste devant elle. Un coucher de soleil à gauche de l'écran, et le mur de gauche devient orange ; une explosion à droite, et c'est le côté droit qui s'allume.

Glowback pilote les appareils **HID LampArray**, le standard ouvert derrière l'**Éclairage dynamique de Windows 11** : écrans avec RGB à l'arrière, mais aussi rubans LED, boîtiers PC et lampes compatibles.

## ✨ Fonctionnalités

- 🎯 **Une zone par LED** : chaque LED est projetée sur le bord d'écran le plus proche, comme une TV Ambilight. Un mode « couleur moyenne » unique existe aussi.
- 🎬 **Vidéo et jeux en plein écran** : la capture GPU (DXGI Desktop Duplication) voit les lecteurs et les jeux en plein écran, **HDR compris**. **Les bandes noires sont ignorées** sur les films (détection letterbox et pillarbox).
- 💡 **Couleurs lumineuses et fidèles** : une courbe de luminosité qui conserve la teinte garde la lueur visible dans les scènes sombres ; la saturation est réglable.
- 🪟 **Intégration Windows native** : une icône dans la zone de notification pour mettre en pause, changer de mode ou de luminosité. Lancement au démarrage en option, entrée dans le menu Démarrer, désinstallation en une commande.
- 🔌 **Plug and play** : détecte tous les appareils Éclairage dynamique et lit la position physique de chaque LED dans l'appareil.
- 🖥️ **Multi-écran** : associe chaque appareil LED à son propre écran grâce au nom de modèle de l'EDID.
- 🪶 **Léger** : environ 0,5 ms de CPU par image, un seul fichier Python, **zéro dépendance**.
- 🔁 **Robuste** : survit à l'extinction de l'écran, à la veille, aux reconnexions USB et aux changements de résolution ou de HDR.
- 🌈 **Au-delà des écrans** : appareils [OpenRGB](https://openrgb.org) (`--openrgb`), [ruban LED DIY avec une RP2040 à 5 $](docs/DIY-LED-strip.md), balance des blancs par appareil (`--calibrate`).

## 🚀 Démarrage rapide

1. **Branchez le câble USB montant de l'écran** (USB-B ou USB-C de l'écran vers le PC) : le contrôleur des LED est un périphérique USB.
2. **Désactivez l'Éclairage dynamique de Windows pour cet appareil**, sinon Windows et Glowback se disputent les LED :
   *Paramètres → Personnalisation → Éclairage dynamique → votre écran → « Utiliser l'éclairage dynamique sur mes appareils » → Désactivé*.
3. **Installez Glowback** avec l'une de ces options :

**Option A : application Windows, sans Python**
Téléchargez [`GlowbackTray.exe`](https://github.com/Ilyomix/glowback/releases/latest/download/GlowbackTray.exe) et double-cliquez dessus : l'icône apparaît près de l'horloge. Pour la version en ligne de commande, prenez [`glowback.exe`](https://github.com/Ilyomix/glowback/releases/latest/download/glowback.exe) et tapez `.\glowback.exe` au lieu de `glowback` dans les commandes ci-dessous.

**Option B : avec Python 3.9+** (installe la commande `glowback`)
```bash
pip install git+https://github.com/Ilyomix/glowback
```
```bash
glowback --install
```

**Option C : fichier unique**
```bash
curl -LO https://raw.githubusercontent.com/Ilyomix/glowback/main/glowback.py
```
```bash
python glowback.py
```
(tapez ensuite `python glowback.py` au lieu de `glowback` dans les commandes ci-dessous)

`glowback --install` lance Glowback au démarrage de Windows, en arrière-plan, et l'ajoute au menu Démarrer. Vérifiez ensuite l'orientation une fois :

```bash
glowback --test
```

La gauche doit être rouge et la droite bleue. Si c'est inversé, ajoutez `--mirror`.

## 🪟 Icône de notification et intégration Windows

Glowback vit dans la zone de notification, à côté de l'horloge. Clic droit (ou gauche) sur son icône :

| Élément du menu | Effet |
|---|---|
| **Ambilight enabled** | Pause ou reprise. En pause, les LED reprennent l'effet réglé dans le menu de l'écran |
| **Each LED follows its zone / One average color** | Change de mode instantanément |
| **Brightness** | 100 / 75 / 50 / 25 % |
| **Start with Windows** | Active ou désactive le lancement au démarrage |
| **Open log / Help and updates** | Dépannage et cette page |
| **Quit** | Arrête Glowback et rend les LED à l'écran |

Les réglages faits depuis l'icône sont mémorisés. Lancez `glowback --no-tray` si vous ne voulez pas d'icône.

## ✅ Écrans et appareils compatibles

Glowback fonctionne avec les appareils **HID LampArray**. Si votre appareil apparaît dans *Paramètres → Personnalisation → Éclairage dynamique*, il devrait fonctionner. Vérifiez avec `glowback --list`.

| Appareil | LED | Statut |
|---|---|---|
| **AOC AGON PRO AG276QZD2** (Light FX, `05F6:AC37`) | 47 | ✅ Testé |
| Autres écrans AOC AGON avec Light FX compatible Éclairage dynamique | n/a | 🟡 Devrait marcher. [Signalez-le](https://github.com/Ilyomix/glowback/issues/new?template=device-report.yml) |
| Tout écran, ruban LED, boîtier ou lampe listé dans l'*Éclairage dynamique* de Windows | n/a | 🟡 Devrait marcher. [Signalez-le](https://github.com/Ilyomix/glowback/issues/new?template=device-report.yml) |
| Claviers et souris compatibles Éclairage dynamique | n/a | 🟡 Sur demande avec `--device all` |
| **Tout appareil RGB pris en charge par [OpenRGB](https://openrgb.org)** (rubans ARGB, cartes mères, boîtiers, WLED…) | n/a | 🟡 Avec `--openrgb` (voir plus bas) |
| **N'importe quel écran + une carte RP2040 à 5 $ et un ruban LED** | n/a | 🛠️ [Guide DIY](docs/DIY-LED-strip.md) |

**Ça marche sur un autre écran ?** Ouvrez un [rapport d'appareil](https://github.com/Ilyomix/glowback/issues/new?template=device-report.yml) avec la sortie de `glowback --list` et une courte vidéo : chaque rapport ajoute une ligne à ce tableau.

## 🌈 OpenRGB, rubans LED et DIY

- **OpenRGB** : démarrez le serveur SDK d'[OpenRGB](https://openrgb.org), puis lancez `glowback --openrgb`. Les rubans LED sont supposés faire le tour de l'écran à partir de `--strip-start` (par défaut `bottom-left`, sens horaire ; `--strip-ccw` pour l'inverse). Les appareils matriciels utilisent leur propre disposition. Glowback les passe en mode direct, puis remet votre effet OpenRGB à la sortie.
- **Pas de RGB sur votre écran ?** Fabriquez-le : [guide DIY avec une carte RP2040 à 5 $](docs/DIY-LED-strip.md) (en anglais). `glowback --diy-layout` génère les positions des LED pour le firmware.
- **Balance des blancs** : LED et peinture murale sont rarement neutres. Lancez `glowback --calibrate` et ajustez au clavier jusqu'à ce que le mur paraisse blanc. Le réglage est mémorisé par appareil.

## 🆚 Glowback face aux autres solutions d'éclairage d'ambiance

| | Glowback | TV Ambilight | Kits ruban LED + boîtier ou caméra | DIY (Hyperion, Prismatik + Arduino) |
|---|---|---|---|---|
| Utilise les LED déjà présentes sur l'écran | ✅ | n/a | ❌ | ❌ |
| Matériel à acheter | Aucun | Une TV | Ruban, boîtier ou caméra | Ruban et microcontrôleur |
| Synchronisation par LED | ✅ | ✅ | ✅ | ✅ |
| Open source | ✅ MIT | ❌ | ❌ | ✅ |
| Temps d'installation | 1 minute | n/a | 30 min et plus | Plusieurs heures |

## ⚙️ Options

| Option | Défaut | Description |
|---|---|---|
| `--mode zones\|average` | `zones` | `zones` : chaque LED suit sa partie de l'image. `average` : une seule couleur |
| `--brightness 0-100` | `100` | Luminosité des LED |
| `--boost` | `1.8` | Remonte les couleurs sombres sans changer leur teinte (`1` = désactivé). Augmentez-le si la lueur est trop faible |
| `--saturation` | `1.25` | Renforcement des couleurs (`1` = couleurs fidèles) |
| `--gamma` | `1.0` | Gamma par canal. Au-dessus de 1, les sombres sont plus profonds |
| `--smoothing` | `0.1` | Durée des transitions en secondes. Plus haut = plus calme, `0` = instantané |
| `--radius` | `0.12` | Taille de la zone de chaque LED, en fraction de la hauteur d'écran |
| `--blend 0-1` | `0` | Mélange la moyenne de tout l'écran dans chaque zone, pour une lueur plus calme |
| `--letterbox on\|off` | `on` | Ignore les bandes noires des films |
| `--capture auto\|dxgi\|gdi` | `auto` | Capture GPU (DXGI) avec repli sur GDI |
| `--fps` | `30` | Mises à jour par seconde (plafonné par l'appareil, ex. 50 Hz pour l'AOC Light FX) |
| `--screen` | `auto` | `auto` (EDID, sinon écran principal), `primary`, un numéro de `--list` ou un nom |
| `--device` | appareils d'ambiance | Partie du nom ou `VID:PID`, ou `all` pour inclure claviers et souris |
| `--mirror` / `--flip` | non | Inverse gauche/droite ou haut/bas si `--test` les montre à l'envers |
| `--openrgb [HÔTE:PORT]` | non | Pilote aussi les appareils OpenRGB (par défaut `127.0.0.1:6742`) |
| `--strip-start` / `--strip-ccw` | `bottom-left` | Début et sens des rubans LED OpenRGB |
| `--calibrate` · `--white-balance R,G,B` | | Balance des blancs par appareil (interactive) · ou multiplicateurs fixes |
| `--diy-layout LxH:G,H,D,B` | | Positions des LED pour le [firmware DIY RP2040](docs/DIY-LED-strip.md) |
| `--install` / `--uninstall` | | Ajoute à Windows ou retire de Windows (démarrage et menu Démarrer) |
| `--autostart on\|off` | | Active ou désactive seulement le lancement au démarrage |
| `--list` · `--test` · `--stop` | | Lister appareils et écrans · motif de test · arrêter l'instance en cours |
| `--no-tray` · `-v` | | Pas d'icône de notification · affiche les images par seconde |

Exemple, lueur plus douce pour les films :

```bash
glowback --install --brightness 70 --smoothing 0.35 --blend 0.2
```

## 🗑️ Désinstaller

**1. Retirer Glowback de Windows** (l'arrête, le retire du démarrage et du menu Démarrer, supprime ses réglages et ses journaux) :

```bash
glowback --uninstall
```

Avec le `.exe` : `.\glowback.exe --uninstall` depuis son dossier.

**2. Supprimer le programme :**
- installé avec pip : `pip uninstall glowback`
- `.exe` : supprimez `glowback.exe` / `GlowbackTray.exe`
- fichier unique : supprimez `glowback.py`

Les LED reprennent automatiquement l'effet réglé dans le menu de l'écran.

**Juste le couper un moment ?** Clic droit sur l'icône, puis décochez *Ambilight enabled*. Pour qu'il ne se lance plus avec Windows, décochez *Start with Windows*, ou désactivez « Glowback » dans *Gestionnaire des tâches → Applications de démarrage*.

## 🔬 Fonctionnement

1. **Détection** : Glowback cherche les interfaces HID de page d'usage `0x59` (*Lighting and Illumination*), usage `LampArray`. Les ID de rapport et la disposition des octets sont **lus dans le descripteur HID** via `HidP_*` : aucun code spécifique à un appareil.
2. **Géométrie** : chaque LED indique sa position X/Y/Z en micromètres. Glowback les normalise et projette chaque LED depuis le centre vers le bord de l'écran, comme une TV Ambilight associe ses LED à l'image.
3. **Capture** : DXGI Desktop Duplication fournit chaque nouvelle image sur le GPU. `GenerateMips` la réduit à environ 80×45 pixels, et seule cette mini-image est relue. Les images HDR (FP16 scRGB) sont converties selon votre réglage *Luminosité du contenu SDR*. GDI sert de repli.
4. **Sortie** : couleurs lissées dans le temps puis envoyées par `LampMultiUpdateReport` (8 LED par rapport, le dernier marqué `LampUpdateComplete`) après avoir quitté l'`AutonomousMode`, qui est rétabli à la sortie.

Tout le programme tient dans un fichier lisible : [`glowback.py`](glowback.py).

## ❓ FAQ

### Comment synchroniser l'éclairage RGB de mon écran avec l'image ?
Installez Glowback, désactivez l'Éclairage dynamique de Windows pour l'écran et lancez `glowback --install`. Les LED arrière suivent ensuite l'image automatiquement.

### L'AOC AGON Light FX peut-il se synchroniser avec l'écran, façon Ambilight ?
Pas avec le logiciel d'AOC, limité à des effets préréglés. Le contrôleur Light FX de l'AG276QZD2 (et probablement d'autres AGON récents) est compatible avec le standard Éclairage dynamique de Windows, que Glowback utilise pour synchroniser chaque LED avec l'image.

### Peut-on avoir un Ambilight sur un écran PC sans ruban LED ?
Oui, si l'écran a des LED RGB au dos compatibles avec l'Éclairage dynamique de Windows : Glowback les utilise directement.

### Ça marche en HDR, dans les jeux et les films en plein écran ?
Oui. La capture DXGI gère les jeux en plein écran et en fenêtré sans bordure, les lecteurs vidéo et le bureau HDR, et les bandes noires sont ignorées. Les flux protégés par DRM (par exemple une partie de Netflix dans les navigateurs) sont en général masqués en noir par Windows pour tous les outils de capture : les LED restent alors sombres.

### Est-ce que ça ralentit mes jeux ?
C'est conçu pour ne pas le faire : la carte graphique fait la réduction d'image, et Glowback utilise environ 0,5 ms de CPU par image à 30 img/s (mesuré sur le PC de l'auteur).

### La lueur est trop faible.
Augmentez `--boost` (par exemple `2.5`), vérifiez la luminosité Light FX dans le menu de l'écran et assurez-vous que l'Éclairage dynamique de Windows est désactivé pour l'appareil.

### Rien ne s'allume.
Vérifiez que le câble USB montant de l'écran est branché au PC, que Light FX / RGB est activé dans le menu de l'écran, et que l'Éclairage dynamique de Windows est désactivé pour cet appareil. `glowback --list` montre ce que voit Glowback ; le journal se trouve dans `%LOCALAPPDATA%\Glowback`.

### Les couleurs sont du mauvais côté.
Lancez `glowback --test`. Si gauche et droite sont inversés, ajoutez `--mirror` ; si haut et bas sont inversés, ajoutez `--flip`.

### Quel lien avec Philips Ambilight, Hyperion ou Prismatik ?
Aucun. Glowback est un projet indépendant inspiré de la même idée. Il n'a besoin ni de ruban LED ni de microcontrôleur si votre écran a déjà des LED au dos.

## 🗺️ Feuille de route

- [x] Icône de notification avec réglages rapides, démarrage avec Windows, menu Démarrer, désinstallation
- [x] Capture DXGI Desktop Duplication (moins de CPU, jeux et vidéo plein écran, HDR)
- [x] Détection des bandes noires (letterbox) pour les films
- [x] Sortie OpenRGB SDK, pour les écrans et rubans LED non LampArray
- [x] [Guide DIY](docs/DIY-LED-strip.md) : transformer n'importe quel ruban LED en LampArray avec une carte RP2040 à 5 $
- [x] Calibration de la balance des blancs par appareil
- [ ] Écrans en mode portrait dans la capture DXGI (repli GDI aujourd'hui)
- [ ] Firmware RP2040 précompilé (.uf2) pour les longueurs de ruban courantes

## ⭐ Soutien

Si Glowback a illuminé votre bureau, **mettez une étoile au dépôt** : ça aide les autres propriétaires d'écrans RGB à le trouver.

---

<sub>Mots-clés : ambilight PC, ambilight écran PC, ambilight Windows 11, synchronisation RGB écran, éclairage d'ambiance écran, rétroéclairage mural PC, bias lighting, AOC AGON Light FX synchronisation écran, AGON PRO AG276QZD2 RGB, Éclairage dynamique Windows 11, HID LampArray, LED arrière écran gaming, ambilight HDR, alternative gratuite à Hyperion, alternative à Prismatik.</sub>

<sub>Ambilight est une marque de Koninklijke Philips N.V. / TP Vision. AOC et AGON sont des marques de leurs propriétaires respectifs. Glowback est un projet open source indépendant, sans lien ni approbation de leur part.</sub>

MIT © Ilyomix
