<p align="center">
  <img src="assets/banner-fr.svg" alt="Glowback : lumière d'ambiance pour les LED RGB au dos de votre écran, chaque LED synchronisée à l'image en temps réel" width="100%">
</p>

<h1 align="center">Glowback</h1>

<p align="center">
  <b>La lumière d'ambiance pour les écrans avec LED RGB à l'arrière.</b><br>
  Une app Windows gratuite et open source : chaque LED suit l'image juste devant elle, en temps réel, sur les appareils Éclairage dynamique de Windows 11 et OpenRGB.
</p>

<p align="center">
  <a href="https://github.com/Ilyomix/glowback/releases/latest"><img alt="Dernière version" src="https://img.shields.io/github/v/release/Ilyomix/glowback?label=release&color=8b6cff"></a>
  <a href="https://github.com/Ilyomix/glowback/releases"><img alt="Téléchargements" src="https://img.shields.io/github/downloads/Ilyomix/glowback/total?color=00ccff"></a>
  <a href="https://github.com/Ilyomix/glowback/actions/workflows/ci.yml"><img alt="Tests" src="https://github.com/Ilyomix/glowback/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Windows 10 et 11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078d4">
  <a href="LICENSE"><img alt="Licence MIT" src="https://img.shields.io/badge/license-MIT-3ddc97"></a>
</p>

<p align="center">
  <a href="https://github.com/Ilyomix/glowback/releases/latest/download/GlowbackSetup.exe"><b>⬇ Télécharger pour Windows</b></a>
  &nbsp;·&nbsp; <a href="https://ilyomix.github.io/glowback/fr/"><b>Site web</b></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <b>Français</b> · <a href="README.es.md">Español</a> · <a href="README.de.md">Deutsch</a> · <a href="README.it.md">Italiano</a> · <a href="README.pt.md">Português</a>
</p>

---

De plus en plus d'écrans gaming ont des LED RGB au dos, mais leur logiciel se limite à des effets fixes, respiration ou arc-en-ciel. **Glowback** en fait une **vraie lumière d'ambiance** : il capture l'écran 30 fois par seconde et donne **une couleur propre à chaque LED**, prise sur le bord de l'image juste devant elle. Un coucher de soleil à gauche de l'écran, et le mur de gauche devient orange ; une explosion à droite, et c'est le côté droit qui s'allume.

Glowback n'est lié à aucune marque. Il pilote tout appareil que l'**Éclairage dynamique de Windows** (le standard HID LampArray) ou **[OpenRGB](https://openrgb.org)** sait contrôler : écrans, rubans LED, boîtiers PC, lampes. Pas de LED compatibles ? [Ajoutez un ruban DIY à 5 $](docs/DIY-LED-strip.md).

## ✨ Fonctionnalités

- 🎯 **Une zone par LED** : chaque LED est projetée sur le bord d'écran le plus proche, pour que la lumière autour de l'écran prolonge l'image. Un mode « couleur moyenne » existe aussi.
- 🎨 **Couleurs, dégradés et musique** : en plus de l'écran, une couleur, un dégradé (fixe ou qui défile), ou des LED qui suivent le son de votre PC : pulsation, spectre ou vagues.
- 🎬 **Films, jeux, HDR** : la capture GPU (DXGI) voit la vidéo et les jeux en plein écran, gère le HDR et **ignore les bandes noires des films**.
- 💡 **Couleurs lumineuses et fidèles** : une courbe de luminosité qui conserve la teinte garde la lueur visible dans les scènes sombres.
- 🪟 **Une vraie application Windows** : une fenêtre avec un aperçu en direct de votre écran et de vos LED, des réglages rapides depuis l'icône près de l'horloge, installateur, menu Démarrer, lancement au démarrage et désinstallation propre depuis *Paramètres → Applications*.
- 🌙 **Profils** : une lumière plus douce la nuit, aux heures de votre choix, et une ambiance par app : la musique quand Spotify joue, l'écran pour les jeux, du bleu dans votre éditeur de code. Ou ne suivre l'écran que quand une app est ouverte.
- 🔄 **Mises à jour signalées** : Glowback vérifie GitHub une fois par jour et vous prévient quand une nouvelle version sort. Un interrupteur permet de le désactiver.
- 📱 **Apple Maison, Google Home et Alexa, sans Home Assistant** : avec Matter, Glowback est une lampe dans l'app Maison de votre téléphone. Allumez-la, réglez sa luminosité et sa couleur à la main, dans des scènes ou à la voix.
- 🏠 **Home Assistant, Google Assistant, Alexa et Siri** : Glowback apparaît comme une lumière à allumer, régler et colorer depuis vos tableaux de bord, vos automatisations ou à la voix.
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

Chaque version est compilée par [GitHub Actions](.github/workflows/release.yml) à partir de ce code source, testée (installation et désinstallation comprises) et publiée avec ses sommes de contrôle SHA-256.

> **Signature du code** : Glowback demande la signature gratuite de [SignPath Foundation](https://signpath.org/) pour les projets open source ; les fichiers Windows seront signés par ce biais dès que le projet sera accepté. D'ici là, Windows SmartScreen peut signaler un éditeur inconnu : cliquez sur *Informations complémentaires → Exécuter quand même*. [Politique de signature du code](CODE_SIGNING.md) · [Confidentialité](PRIVACY.md)

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

## 🪟 L'application

<p align="center"><img src="docs/img/app-fr.webp" width="760" alt="La fenêtre de Glowback : aperçu en direct de l'écran et de la lumière derrière lui, les cinq ambiances et la luminosité"></p>

Lancez Glowback depuis le menu Démarrer et sa fenêtre s'ouvre. Fermez-la et Glowback continue en arrière-plan : double-cliquez sur son icône près de l'horloge pour la rouvrir, ou cliquez une fois pour un panneau rapide.

- **Lumière d'ambiance** : un aperçu en direct de votre écran et de la lumière que vos LED projettent sur le mur, l'interrupteur, l'[ambiance](#-ambiances) (écran, moyenne, couleur, dégradé ou musique) et la luminosité
- **Profils** : un [profil de nuit et une ambiance par app](#-profils)
- **Home Assistant** : état et réglage de la connexion, ce que voit Home Assistant, assistants vocaux
- **Apple et Google** : Glowback comme [lampe Matter](#-apple-maison-google-home-et-alexa) dans Apple Maison, Google Home ou Alexa : son code d'appairage et les apps appairées
- **Paramètres** : lancement au démarrage, mises à jour (tout de suite, ou automatiquement une fois par jour), langue de l'interface, journal
- **À propos** : version, site web, code source, signaler un problème

En pause, les LED reprennent l'effet de l'appareil. Les réglages sont mémorisés. Des outils supplémentaires sont dans le menu Démarrer : *Tester les LED* et *Calibrer la balance des blancs*.

## 🎨 Ambiances

Glowback ne fait pas que suivre l'écran. Sur la page **Lumière d'ambiance**, choisissez ce que montrent les LED :

| Ambiance | Ce que montrent les LED |
|---|---|
| **Écran** | Chaque LED suit la partie de l'image juste à côté d'elle (par défaut) |
| **Moyenne** | Une seule couleur pour toutes les LED : la moyenne de l'écran |
| **Couleur** | Une couleur : 10 pastilles, ou n'importe quelle teinte et saturation |
| **Dégradé** | 2 à 4 couleurs de gauche à droite, fixe ou qui défile doucement, et 6 modèles |
| **Musique** | Les LED suivent le son que joue votre PC : **Pulsation** (elles battent toutes ensemble), **Spectre** (les basses en bas, les aigus en haut) ou **Vagues** (chaque temps fort envoie de la lumière de chaque côté). Leurs couleurs : un arc-en-ciel, les couleurs de l'écran, votre couleur ou votre dégradé |

<p align="center"><img src="docs/img/looks-fr.webp" width="760" alt="L'ambiance Musique : les LED battent avec le son, en arc-en-ciel, avec son style et sa sensibilité"></p>

L'ambiance Musique écoute ce que Windows joue sur sa sortie par défaut (Spotify, YouTube, jeux...), en mémoire : pas de micro, rien n'est enregistré ni envoyé. En ligne de commande : `glowback --mode color --color "#2864FF"`, `glowback --mode gradient --gradient "#FF326E,#FFDC3C"` ou `glowback --mode music`.

## 🌙 Profils

Sur la page **Profils**, l'ambiance change toute seule :

- **Profil de nuit** : de 22:00 à 07:00 (à vos horaires), une luminosité plus basse et, si vous voulez, une autre ambiance, un blanc chaud par exemple.
- **Par app** : une ambiance pour chaque app, quand elle **est ouverte**, **au premier plan**, **en plein écran** (sur l'écran de votre choix) ou **joue du son**. *Auto* garde l'ambiance de la page Lumière d'ambiance.
- **Le reste du temps** : quand aucune de ces apps ne correspond, garder l'ambiance de la page Lumière d'ambiance, rendre aux LED leur propre effet, ou les éteindre.

<p align="center"><img src="docs/img/profiles-fr.webp" width="760" alt="La page Profils : un profil de nuit de 22:30 à 07:00 à 35 %, et une ambiance pour Spotify, les jeux en plein écran et le Bloc-notes"></p>

| App | Quand | Ambiance |
|---|---|---|
| Spotify | Joue du son | Musique · Pulsation |
| N'importe quelle app | Est en plein écran sur l'écran des LED | Écran |
| Visual Studio Code | Est au premier plan | Bleu |

La première app de la liste qui correspond l'emporte, et la luminosité du profil de nuit s'applique à toutes. Glowback vérifie quatre fois par seconde et reconnaît aussi les apps du Store (Netflix, Disney+...).

En ligne de commande, Glowback peut ne suivre l'écran que quand l'une de ces conditions est remplie, les LED affichant leur propre effet le reste du temps (mémorisé ; un Glowback lancé suit en moins de 2 secondes) :

```
glowback --sync-when foreground:vlc.exe --sync-when "fullscreen:*@leds" --sync-when playing:spotify.exe
glowback --sync-when always
```

## 🏠 Home Assistant et Google Assistant

Glowback peut apparaître dans [Home Assistant](https://www.home-assistant.io) comme une lumière : allumez, réglez ou colorez la lumière d'ambiance depuis vos tableaux de bord et vos automatisations, ou à la voix avec Google Assistant, Alexa et Siri.

1. **Dans Home Assistant** : installez l'application **Mosquitto broker** (*Paramètres → Applications*) et démarrez-la. Home Assistant propose ensuite l'intégration **MQTT** dans *Paramètres → Appareils et services* : ajoutez-la.
2. **Un utilisateur pour Glowback** (conseillé) : *Paramètres → Personnes → Utilisateurs → Ajouter un utilisateur*, par exemple `glowback`. Si *Utilisateurs* n'apparaît pas, activez le *Mode avancé* dans votre profil.
3. **Dans Glowback** : ouvrez le panneau, cliquez sur **Home Assistant**, saisissez l'adresse (`homeassistant.local` marche en général, sinon l'IP de Home Assistant), l'utilisateur et son mot de passe, puis **Connecter**.

Glowback apparaît alors dans *Paramètres → Appareils et services → MQTT* :

| Entité | Rôle |
|---|---|
| `light.glowback` | Allumé/éteint = lumière d'ambiance, luminosité, couleur (en choisir une passe à l'ambiance Couleur), et l'ambiance en effet (*Zones*, *Average*, *Color*, *Gradient* ou *Music*) |
| `sensor.glowback_leds` | Nombre de LED pilotées par Glowback |
| `update.glowback` | Signale une nouvelle version, et l'installe |

Elle passe en *indisponible* quand le PC est éteint ou Glowback fermé. Le mot de passe est chiffré pour votre compte Windows et n'est envoyé qu'à votre broker.

**Google Assistant** : avec [Home Assistant Cloud](https://www.nabucasa.com), ouvrez *Paramètres → Assistants vocaux → Exposer* et exposez **Glowback**, puis dites *« Ok Google, éteins Glowback »*, *« Ok Google, mets Glowback à 50 % »* ou *« Ok Google, mets Glowback en bleu »*. Sans abonnement, suivez la [configuration manuelle de Google Assistant](https://www.home-assistant.io/integrations/google_assistant/) de Home Assistant. Alexa fonctionne de la même façon.

**Siri et l'app Maison d'Apple** : ajoutez l'intégration [HomeKit Bridge](https://www.home-assistant.io/integrations/homekit/) de Home Assistant (*Paramètres → Appareils et services → Ajouter une intégration* ; le domaine *Lumière* suffit). Ensuite, dans l'app Maison de l'iPhone, touchez *Ajouter un accessoire* et scannez le code d'appairage que Home Assistant affiche dans ses notifications. Dites *« Dis Siri, éteins Glowback »*, *« Dis Siri, mets Glowback à 50 % »* ou *« Dis Siri, mets Glowback en bleu »*. Maison ne gère pas les effets de lumière : les autres ambiances se règlent dans l'app Glowback ou dans Home Assistant.

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

## 📱 Apple Maison, Google Home et Alexa

Glowback peut aussi être une lampe **Matter**, sans Home Assistant : l'app Maison de votre téléphone l'allume, règle sa luminosité et sa couleur, à la main, dans des scènes et des automatisations, ou à la voix avec Siri, l'Assistant Google ou Alexa.

1. **Dans Glowback** : ouvrez la page **Apple et Google** et activez **Lampe Matter**. Un QR code et un code à 11 chiffres s'affichent pendant 15 minutes. Windows peut demander de laisser passer Glowback dans son pare-feu : autorisez-le (installé pour tous les utilisateurs, Glowback laisse déjà entrer les appareils de votre réseau local).
2. **Sur votre téléphone**, sur le même réseau que le PC :
   - **Apple Maison** : touchez **+** → *Ajouter un accessoire* et scannez le QR code (ou *Plus d'options…* et tapez le code). Glowback n'est pas certifié par la Connectivity Standards Alliance, alors Apple Maison indique *Accessoire non certifié* : touchez *Ajouter quand même*.
   - **Google Home** : Google n'ajoute les appareils non certifiés qu'aux comptes configurés pour les tests. Une fois, dans la [Google Home Developer Console](https://console.home.google.com) : créez un projet, puis une **intégration Matter** avec l'ID fournisseur `0xFFF1` et l'ID produit `0x8000`. Ensuite, dans l'app Google Home connectée au même compte : *Appareils → Ajouter → Appareil compatible Matter*, et scannez le code.
   - **Autres apps Matter** (Alexa, SmartThings, l'intégration Matter de Home Assistant…) : ajoutez un appareil Matter et scannez le code, si l'app accepte les appareils non certifiés.
3. **Une deuxième app** (Google Home après Apple Maison, par exemple) : cliquez sur **Appairer un téléphone** dans Glowback et scannez à nouveau depuis l'autre app. Ou partagez la lampe depuis la première app (Apple Maison : réglages de la lampe → *Activer le mode d'appairage*) et tapez ce code dans l'autre.

| Dans l'app du téléphone | Dans Glowback |
|---|---|
| Allumer / éteindre | Lumière d'ambiance activée / en pause |
| Luminosité | Luminosité |
| Une couleur ou un blanc | L'ambiance Couleur, dans cette couleur |
| Identifier | Les LED clignotent en blanc |

Les autres ambiances (écran, dégradé, musique) et les profils se choisissent dans Glowback ; le téléphone les allume, les éteint et règle leur luminosité. La lampe apparaît comme indisponible quand le PC est en veille ou Glowback fermé.

Tout reste sur votre réseau : Glowback répond sur le port UDP 5540 et s'annonce en mDNS (port 5353). Il garde ses appairages dans `%LOCALAPPDATA%\Glowback\matter.json`, clés chiffrées pour votre compte Windows. Pour désappairer une app, cliquez sur **Retirer** à côté d'elle ; pour cacher la lampe, désactivez Matter.

## 🗑️ Désinstaller

- **Installé avec GlowbackSetup.exe** : *Paramètres → Applications → Applications installées → Glowback → Désinstaller*. Glowback s'arrête, les LED reprennent l'effet de l'appareil, et son lancement au démarrage, ses réglages et ses journaux sont supprimés.
- **Version Python** : `glowback --uninstall`, puis `pip uninstall glowback`.
- **Portable** : `glowback.exe --uninstall`, puis supprimez les fichiers .exe.

Pour le couper un moment, utilisez l'interrupteur **Lumière d'ambiance** du menu. Pour qu'il ne se lance plus avec Windows, désactivez **Lancer au démarrage**.

## ⚙️ Ligne de commande

| Option | Défaut | Description |
|---|---|---|
| `--mode zones\|average\|color\|gradient\|music` | `zones` | L'[ambiance](#-ambiances) : chaque LED sa zone, une couleur moyenne, une couleur, un dégradé, ou le son |
| `--color #RRGGBB` · `--gradient #RRGGBB,#RRGGBB[,...]` | celles de l'app | La couleur de l'ambiance Couleur, les 2 à 4 couleurs de l'ambiance Dégradé |
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
| `--sync-when QUAND:APP[@ÉCRAN]\|always` | | Ne suit l'écran que quand une app est lancée, au premier plan, en plein écran ou joue du son ([profils](#-profils) ; mémorisé, répétable) |
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
5. **Musique** : le loopback WASAPI lit ce que joue la sortie par défaut ; 30 fois par seconde, une FFT de 512 points le découpe en 14 bandes de fréquences, avec un gain automatique et la détection des temps forts, le tout en Python pur.

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

### Les LED peuvent-elles suivre ma musique ?
Oui. Choisissez l'ambiance **Musique** : les LED battent, affichent le spectre ou envoient des vagues avec le son que joue votre PC, quelle que soit l'app. Pour y passer toute seule, ajoutez un profil sur la page Profils : par exemple *Spotify · Joue du son · Musique*.

### Rien ne s'allume.
Vérifiez que le câble USB montant de l'écran est branché au PC, que l'éclairage RGB est activé dans le menu de l'écran, et que l'Éclairage dynamique de Windows est désactivé pour cet appareil. L'état du menu de l'icône et `glowback --list` montrent ce que voit Glowback.

### Les couleurs sont du mauvais côté.
Utilisez *Tester les LED* dans le menu Démarrer (ou `glowback --test`). Si gauche et droite sont inversés, ajoutez `--mirror` ; si haut et bas sont inversés, ajoutez `--flip`.

## 🗺️ Feuille de route

- [x] Une application avec aperçu en direct, panneau rapide, installateur, lancement au démarrage, désinstallation, mises à jour signalées
- [x] Capture DXGI, HDR, détection des bandes noires
- [x] Sortie OpenRGB (détectée automatiquement), guide DIY RP2040, balance des blancs
- [x] 6 langues
- [x] Home Assistant, et par lui Google Assistant, Alexa et Siri
- [x] Conditions de synchro : une app lancée, au premier plan ou en plein écran, sur un écran donné
- [x] Ambiances couleur, dégradé et musique ; profils de nuit et par app
- [ ] Installateur signé et `winget install Glowback`
- [ ] Écrans en mode portrait dans la capture DXGI
- [ ] Firmware RP2040 précompilé (.uf2)

## 🧩 Du même auteur

[**Keyboard Clock**](https://github.com/Ilyomix/keyboard-clock): l'heure en gros chiffres sur votre clavier RGB, pour les claviers Logitech G, Razer, Corsair, ASUS, SteelSeries, HyperX et OpenRGB.

## ⭐ Soutien

Si Glowback a illuminé votre bureau, **mettez une étoile au dépôt** : ça aide les autres propriétaires d'écrans RGB à le trouver.

---

<sub>Mots-clés : lumière d'ambiance PC, éclairage d'ambiance écran, synchronisation RGB écran, rétroéclairage mural, bias lighting, écran gaming RGB, Éclairage dynamique Windows 11, HID LampArray, OpenRGB synchronisation écran, LED arrière écran, lumière d'ambiance HDR, alternative à Ambilight pour PC, alternative à Hyperion, lumière d'ambiance Home Assistant, HomeKit, Siri, LED réactives à la musique, lumière qui suit le son, visualiseur audio LED.</sub>

<sub>Ambilight est une marque de Koninklijke Philips N.V. / TP Vision. Les autres noms de produits sont des marques de leurs propriétaires respectifs. Glowback est un projet open source indépendant, sans lien ni approbation de leur part. Inter est sous [licence SIL Open Font](licenses/Inter-OFL.txt).</sub>

MIT © [Ilyomix](https://github.com/Ilyomix) · [Politique de signature du code](CODE_SIGNING.md) · [Confidentialité](PRIVACY.md)
