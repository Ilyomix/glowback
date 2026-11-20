# Glowback on the Microsoft Store

What to enter in [Partner Center](https://partner.microsoft.com/dashboard/apps-and-games/overview) for Glowback's Store listing, in its six languages. The package is built by the release workflow (`installer/msix/make_msix.py`, build artifact `Glowback-<version>`); the screenshots by `python installer/msix/store_screenshots.py` (in `build/store/<language>/`).

Every field below stays within Partner Center's limits: description 10,000 characters, short description 1,000, what's new 1,500, up to 20 features of 200 characters, up to 7 search terms of 30 characters (21 words in all), captions and system requirements 200.

## Submission options

| Field | Value |
|---|---|
| Pricing | Free, all markets |
| Category | Utilities & tools |
| Privacy policy URL | https://github.com/Ilyomix/glowback/blob/main/PRIVACY.md |
| Website | https://ilyomix.github.io/glowback/ (or the page in each language: `https://ilyomix.github.io/glowback/fr/`, `es/`, `de/`, `it/`, `pt/`) |
| Support contact info | https://github.com/Ilyomix/glowback/issues |
| Age ratings | IARC questionnaire: a utility; no violence, sex, gambling or purchases; users don't chat or share content with each other; no location sharing; no web browser. Expected rating: 3+ / Everyone |
| Display mode | Not a game: no Xbox or gaming options |

### Restricted capabilities: why runFullTrust

```text
Glowback is a Win32 desktop app (Python, packaged with PyInstaller). It needs runFullTrust to capture the screen (DXGI Desktop Duplication), drive LED devices through HID LampArray (Windows Dynamic Lighting) or the OpenRGB SDK on 127.0.0.1, show an icon in the notification area and start at sign-in.
```

### Notes for certification

```text
Glowback is a Win32 desktop app (Python, packaged with PyInstaller) that lights the RGB LEDs on the back of a monitor, and other LED devices, with the colors at the edges of the screen.

Why runFullTrust: it captures the screen with DXGI Desktop Duplication, drives LED devices through HID LampArray (Windows Dynamic Lighting) or the OpenRGB SDK server on 127.0.0.1:6742, shows an icon in the notification area, and starts at sign-in through its StartupTask (the user can turn it off in Settings > Apps > Startup). While the "Music" look is on, it reads the default audio output through WASAPI loopback (never a microphone) and records nothing.

Testing without RGB hardware: the app starts and its window opens; the "Ambient light" page shows a live preview of the screen even when no LED device is connected.

Network: only if the user turns on "Matter light" (the "Apple & Google" page), Glowback answers on UDP port 5540 and announces itself with mDNS (UDP 5353) on the local network, so phones' Home apps can pair with it; the package declares inbound firewall rules for these two ports. Only if the user connects Home Assistant, it talks to the MQTT broker the user enters.

No account or sign-in, no in-app purchases, no ads, no telemetry. In the Store version the app's own update checker is off: the Store updates it.
```

## English (en-us)

Product name: **Glowback**. Website for this language: https://ilyomix.github.io/glowback/

### Description

```text
Glowback turns the RGB LEDs on the back of your monitor into real ambient light. Gaming monitors' own software only offers static, breathing or rainbow effects: Glowback captures your screen 30 times a second and gives each LED its own color, taken from the edge of the picture right in front of it. A sunset on the left of the screen turns the wall on the left orange.

Glowback is not tied to one brand. It drives any device that Windows Dynamic Lighting (the HID LampArray standard) or OpenRGB can control: monitors, LED strips, PC cases, lamps.

Besides the screen, the LEDs can show one color, a gradient (still or flowing), or follow the sound your PC plays: pulse, spectrum or waves, without a microphone and without recording anything. Profiles change the look on their own: a softer light at night, the music while Spotify plays, the screen for games.

Control it from your phone too: with Matter, Glowback is a light in Apple Home, Google Home or Alexa, on your local network. Glowback is an uncertified Matter light: Apple Home asks you to confirm (Add Anyway), and Google Home needs a free test setup first. It also works with Home Assistant: switch it, dim it and color it from dashboards, automations or by voice.

What you need
• A monitor or another device with RGB LEDs that Windows Dynamic Lighting or OpenRGB can control. For a monitor, connect its USB upstream cable to the PC.
• Turn Windows Dynamic Lighting off for that device (Settings > Personalization > Dynamic Lighting), so Windows and Glowback don't both drive the LEDs.

Glowback is free and open source (MIT license): no account, no ads, no telemetry. Source code, guides and the list of tested devices: https://github.com/Ilyomix/glowback
```

### What's new in this version

```text
First version on the Microsoft Store. The Store keeps Glowback up to date, and Windows starts it when you sign in (you can turn that off in Settings > Apps > Startup). Used Glowback before? Your settings and the phones paired with Matter carry over.
```

### Product features

```text
Each LED takes the color of the screen edge closest to it, or one average color for all
Movies, games and HDR: GPU capture in full screen, movie black bars ignored
Bright, true colors, even in dark scenes
Looks: the screen, one color, a still or flowing gradient, or the music your PC plays
Profiles: a night light at the hours you choose, and a look for each app
Matter: a light in Apple Home, Google Home or Alexa, on your local network
Home Assistant: dashboards, automations, Google Assistant, Alexa and Siri
A window with a live preview of your screen and your LEDs
Quick settings from the icon next to the clock
Finds Windows Dynamic Lighting and OpenRGB devices on its own
Multi-monitor: each LED device follows its own screen
White balance per device
About 0.5 ms of CPU per frame
6 languages: English, French, Spanish, German, Italian and Portuguese
Free and open source: no account, no ads, no telemetry
```

### Screenshots

| File | Caption |
|---|---|
| `build/store/en/1-light.png` | Ambient light: a live preview of your screen and your LEDs |
| `build/store/en/2-music.png` | The Music look: the LEDs follow the sound your PC plays |
| `build/store/en/3-profiles.png` | Profiles: a night light and a look for each app |
| `build/store/en/4-matter.png` | Apple & Google: add Glowback to your phone's Home app with Matter |
| `build/store/en/5-home.png` | Home Assistant: Glowback as a light in your dashboards |

### Short description

```text
Ambient light for monitors with RGB LEDs on the back. Glowback captures your screen 30 times a second and gives each LED the color of the picture right in front of it.
```

### Search terms (one per box)

```text
ambient light
bias lighting
RGB monitor
screen sync
Dynamic Lighting
OpenRGB
Matter light
```

### Copyright and trademark info

```text
© 2026 Ilyomix. Free and open source, MIT license.
```

### Additional system requirements (minimum hardware)

```text
A monitor or device with RGB LEDs that Windows Dynamic Lighting or OpenRGB can control
Windows Dynamic Lighting needs Windows 11; OpenRGB also works on Windows 10
```

## Français (fr-fr)

Product name: **Glowback**. Website for this language: https://ilyomix.github.io/glowback/fr/

### Description

```text
Glowback transforme les LED RGB à l'arrière de votre écran en vraie lumière d'ambiance. Le logiciel des écrans gaming ne propose que des effets fixes, respiration ou arc-en-ciel : Glowback capture l'écran 30 fois par seconde et donne à chaque LED sa propre couleur, prise sur le bord de l'image juste devant elle. Un coucher de soleil à gauche de l'écran teinte le mur de gauche en orange.

Glowback n'est lié à aucune marque. Il pilote tout appareil que l'Éclairage dynamique de Windows (le standard HID LampArray) ou OpenRGB savent contrôler : écrans, rubans LED, boîtiers de PC, lampes.

En plus de l'écran, les LED peuvent afficher une couleur, un dégradé (fixe ou en mouvement), ou suivre le son de votre PC : pulsation, spectre ou vagues, sans micro et sans rien enregistrer. Les profils changent l'ambiance tout seuls : une lumière plus douce la nuit, la musique pendant que Spotify joue, l'écran pour les jeux.

Pilotez-le aussi depuis votre téléphone : avec Matter, Glowback est une lampe dans Apple Maison, Google Home ou Alexa, sur votre réseau local. Glowback est une lampe Matter non certifiée : Apple Maison vous demande de confirmer (Ajouter quand même), et Google Home demande d'abord une configuration de test gratuite. Il fonctionne aussi avec Home Assistant : allumez-le, réglez sa luminosité et sa couleur depuis les tableaux de bord, les automatisations ou à la voix.

Ce qu'il faut
• Un écran ou un autre appareil avec des LED RGB que l'Éclairage dynamique de Windows ou OpenRGB savent contrôler. Pour un écran, branchez son câble USB montant (upstream) au PC.
• Désactivez l'Éclairage dynamique de Windows pour cet appareil (Paramètres > Personnalisation > Éclairage dynamique), pour que Windows et Glowback ne pilotent pas les LED en même temps.

Glowback est gratuit et open source (licence MIT) : pas de compte, pas de pub, pas de télémétrie. Code source, guides et liste des appareils testés : https://github.com/Ilyomix/glowback
```

### What's new in this version

```text
Première version sur le Microsoft Store. Le Store tient Glowback à jour, et Windows le lance à l'ouverture de session (désactivable dans Paramètres > Applications > Démarrage). Vous utilisiez déjà Glowback ? Vos réglages et les téléphones associés avec Matter sont conservés.
```

### Product features

```text
Chaque LED prend la couleur du bord de l'écran le plus proche, ou une couleur moyenne pour toutes
Films, jeux et HDR : capture par le GPU en plein écran, bandes noires ignorées
Des couleurs vives et fidèles, même dans les scènes sombres
Ambiances : l'écran, une couleur, un dégradé fixe ou en mouvement, ou la musique de votre PC
Profils : une lumière de nuit aux heures de votre choix, et une ambiance par application
Matter : une lampe dans Apple Maison, Google Home ou Alexa, sur votre réseau local
Home Assistant : tableaux de bord, automatisations, Google Assistant, Alexa et Siri
Une fenêtre avec un aperçu en direct de votre écran et de vos LED
Les réglages rapides depuis l'icône près de l'horloge
Trouve tout seul les appareils Éclairage dynamique de Windows et OpenRGB
Multi-écran : chaque appareil LED suit son propre écran
Balance des blancs par appareil
Environ 0,5 ms de processeur par image
6 langues : français, anglais, espagnol, allemand, italien et portugais
Gratuit et open source : pas de compte, pas de pub, pas de télémétrie
```

### Screenshots

| File | Caption |
|---|---|
| `build/store/fr/1-light.png` | Lumière d'ambiance : un aperçu en direct de votre écran et de vos LED |
| `build/store/fr/2-music.png` | L'ambiance Musique : les LED suivent le son de votre PC |
| `build/store/fr/3-profiles.png` | Profils : une lumière de nuit et une ambiance par application |
| `build/store/fr/4-matter.png` | Apple et Google : ajoutez Glowback à Apple Maison, Google Home ou Alexa avec Matter |
| `build/store/fr/5-home.png` | Home Assistant : Glowback devient une lampe dans vos tableaux de bord |

### Short description

```text
La lumière d'ambiance pour les écrans avec LED RGB à l'arrière. Glowback capture l'écran 30 fois par seconde et donne à chaque LED la couleur de l'image juste devant elle.
```

### Search terms (one per box)

```text
lumière d'ambiance
rétroéclairage écran
écran RGB
Éclairage dynamique
OpenRGB
synchro écran
lampe Matter
```

### Copyright and trademark info

```text
© 2026 Ilyomix. Gratuit et open source, licence MIT.
```

### Additional system requirements (minimum hardware)

```text
Un écran ou un appareil avec des LED RGB que l'Éclairage dynamique de Windows ou OpenRGB savent contrôler
L'Éclairage dynamique demande Windows 11 ; OpenRGB fonctionne aussi sous Windows 10
```

## Español (es-es)

Product name: **Glowback**. Website for this language: https://ilyomix.github.io/glowback/es/

### Description

```text
Glowback convierte los LED RGB de la parte trasera de tu monitor en una auténtica luz ambiental. El software de los monitores gaming solo ofrece efectos fijos, de respiración o arcoíris: Glowback captura la pantalla 30 veces por segundo y da a cada LED su propio color, tomado del borde de la imagen que tiene delante. Un atardecer a la izquierda de la pantalla tiñe de naranja la pared izquierda.

Glowback no depende de ninguna marca: controla cualquier dispositivo que la Iluminación dinámica de Windows (el estándar HID LampArray) u OpenRGB puedan manejar: monitores, tiras LED, cajas de PC, lámparas.

Además de la pantalla, los LED pueden mostrar un color, un degradado (fijo o en movimiento) o seguir el sonido de tu PC: pulso, espectro u ondas, sin micrófono y sin grabar nada. Los perfiles cambian el ambiente solos: una luz más suave de noche, la música mientras suena Spotify, la pantalla para los juegos.

Contrólalo también desde el teléfono: con Matter, Glowback es una luz en Apple Casa, Google Home o Alexa, en tu red local. Glowback es una luz Matter no certificada: Apple Casa te pide confirmar (Añadir de todos modos) y Google Home necesita antes una configuración de prueba gratuita. También funciona con Home Assistant: enciéndelo y ajusta el brillo y el color desde paneles, automatizaciones o por voz.

Qué necesitas
• Un monitor u otro dispositivo con LED RGB que la Iluminación dinámica de Windows u OpenRGB puedan controlar. Si es un monitor, conecta su cable USB de subida al PC.
• Desactiva la Iluminación dinámica de Windows para ese dispositivo (Configuración > Personalización > Iluminación dinámica), para que Windows y Glowback no controlen los LED a la vez.

Glowback es gratuito y de código abierto (licencia MIT): sin cuenta, sin anuncios, sin telemetría. Código fuente, guías y lista de dispositivos probados: https://github.com/Ilyomix/glowback
```

### What's new in this version

```text
Primera versión en Microsoft Store. La Store mantiene Glowback actualizado y Windows lo inicia al iniciar sesión (puedes desactivarlo en Configuración > Aplicaciones > Inicio). ¿Ya usabas Glowback? Se conservan tus ajustes y los teléfonos vinculados con Matter.
```

### Product features

```text
Cada LED toma el color del borde de pantalla más cercano, o un color promedio para todos
Películas, juegos y HDR: captura por GPU en pantalla completa, ignora las bandas negras
Colores luminosos y fieles, incluso en escenas oscuras
Ambientes: la pantalla, un color, un degradado fijo o en movimiento, o la música de tu PC
Perfiles: una luz nocturna a las horas que elijas y un ambiente para cada app
Matter: una luz en Apple Casa, Google Home o Alexa, en tu red local
Home Assistant: paneles, automatizaciones, Google Assistant, Alexa y Siri
Una ventana con vista previa en directo de tu pantalla y tus LED
Ajustes rápidos desde el icono junto al reloj
Detecta solo los dispositivos de Iluminación dinámica de Windows y OpenRGB
Varios monitores: cada dispositivo LED sigue su propia pantalla
Balance de blancos por dispositivo
Unos 0,5 ms de CPU por imagen
6 idiomas: español, inglés, francés, alemán, italiano y portugués
Gratuito y de código abierto: sin cuenta, sin anuncios, sin telemetría
```

### Screenshots

| File | Caption |
|---|---|
| `build/store/es/1-light.png` | Luz ambiental: vista previa en directo de tu pantalla y tus LED |
| `build/store/es/2-music.png` | El ambiente Música: los LED siguen el sonido de tu PC |
| `build/store/es/3-profiles.png` | Perfiles: una luz nocturna y un ambiente para cada app |
| `build/store/es/4-matter.png` | Apple y Google: añade Glowback a la app Casa de tu teléfono con Matter |
| `build/store/es/5-home.png` | Home Assistant: Glowback como una luz en tus paneles |

### Short description

```text
Luz ambiental para monitores con LED RGB traseros. Glowback captura la pantalla 30 veces por segundo y da a cada LED el color de la imagen que tiene delante.
```

### Search terms (one per box)

```text
luz ambiental
retroiluminación
monitor RGB
Iluminación dinámica
OpenRGB
sincronizar pantalla
luz Matter
```

### Copyright and trademark info

```text
© 2026 Ilyomix. Gratuito y de código abierto, licencia MIT.
```

### Additional system requirements (minimum hardware)

```text
Un monitor o dispositivo con LED RGB que la Iluminación dinámica de Windows u OpenRGB puedan controlar
La Iluminación dinámica requiere Windows 11; OpenRGB también funciona en Windows 10
```

## Deutsch (de-de)

Product name: **Glowback**. Website for this language: https://ilyomix.github.io/glowback/de/

### Description

```text
Glowback macht die RGB-LEDs auf der Rückseite deines Monitors zu echtem Umgebungslicht. Die Software von Gaming-Monitoren bietet nur statische, pulsierende oder Regenbogen-Effekte: Glowback erfasst den Bildschirm 30-mal pro Sekunde und gibt jeder LED ihre eigene Farbe, genommen vom Bildrand direkt vor ihr. Ein Sonnenuntergang links im Bild färbt die linke Wand orange.

Glowback ist an keine Marke gebunden: Es steuert jedes Gerät, das die dynamische Beleuchtung von Windows (der HID-LampArray-Standard) oder OpenRGB ansprechen kann: Monitore, LED-Streifen, PC-Gehäuse, Lampen.

Neben dem Bildschirm können die LEDs eine Farbe zeigen, einen Verlauf (still oder in Bewegung) oder dem Ton deines PCs folgen: Puls, Spektrum oder Wellen, ohne Mikrofon und ohne Aufnahme. Profile wechseln das Licht von selbst: nachts ein sanfteres Licht, Musik, während Spotify spielt, der Bildschirm für Spiele.

Steuere es auch vom Handy aus: Mit Matter ist Glowback eine Lampe in Apple Home, Google Home oder Alexa, in deinem lokalen Netzwerk. Glowback ist eine nicht zertifizierte Matter-Lampe: Apple Home bittet um Bestätigung (Trotzdem hinzufügen), Google Home braucht vorher eine kostenlose Test-Einrichtung. Es funktioniert auch mit Home Assistant: ein- und ausschalten, Helligkeit und Farbe über Dashboards, Automationen oder per Sprache.

Was du brauchst
• Einen Monitor oder ein anderes Gerät mit RGB-LEDs, das die dynamische Beleuchtung von Windows oder OpenRGB steuern kann. Bei einem Monitor das USB-Upstream-Kabel mit dem PC verbinden.
• Die dynamische Beleuchtung von Windows für dieses Gerät ausschalten (Einstellungen > Personalisierung > Dynamische Beleuchtung), damit Windows und Glowback nicht gleichzeitig die LEDs steuern.

Glowback ist kostenlos und Open Source (MIT-Lizenz): kein Konto, keine Werbung, keine Telemetrie. Quellcode, Anleitungen und Liste der getesteten Geräte: https://github.com/Ilyomix/glowback
```

### What's new in this version

```text
Erste Version im Microsoft Store. Der Store hält Glowback aktuell, und Windows startet es bei der Anmeldung (abschaltbar unter Einstellungen > Apps > Autostart). Du hast Glowback schon benutzt? Deine Einstellungen und die per Matter gekoppelten Handys bleiben erhalten.
```

### Product features

```text
Jede LED bekommt die Farbe des nächstgelegenen Bildrands, oder alle eine Durchschnittsfarbe
Filme, Spiele und HDR: GPU-Erfassung im Vollbild, schwarze Balken werden ignoriert
Helle, natürliche Farben, auch in dunklen Szenen
Licht: der Bildschirm, eine Farbe, ein stiller oder bewegter Verlauf oder die Musik deines PCs
Profile: ein Nachtlicht zu den Uhrzeiten deiner Wahl und ein Licht für jede App
Matter: eine Lampe in Apple Home, Google Home oder Alexa, im lokalen Netzwerk
Home Assistant: Dashboards, Automationen, Google Assistant, Alexa und Siri
Ein Fenster mit Live-Vorschau deines Bildschirms und deiner LEDs
Schnelleinstellungen über das Symbol neben der Uhr
Findet Geräte für die dynamische Beleuchtung von Windows und OpenRGB automatisch
Mehrere Monitore: Jedes LED-Gerät folgt seinem eigenen Bildschirm
Weißabgleich pro Gerät
Etwa 0,5 ms CPU pro Bild
6 Sprachen: Deutsch, Englisch, Französisch, Spanisch, Italienisch und Portugiesisch
Kostenlos und Open Source: kein Konto, keine Werbung, keine Telemetrie
```

### Screenshots

| File | Caption |
|---|---|
| `build/store/de/1-light.png` | Umgebungslicht: Live-Vorschau deines Bildschirms und deiner LEDs |
| `build/store/de/2-music.png` | Das Licht Musik: Die LEDs folgen dem Ton deines PCs |
| `build/store/de/3-profiles.png` | Profile: ein Nachtlicht und ein Licht für jede App |
| `build/store/de/4-matter.png` | Apple & Google: Glowback mit Matter zur Home-App deines Handys hinzufügen |
| `build/store/de/5-home.png` | Home Assistant: Glowback als Lampe in deinen Dashboards |

### Short description

```text
Umgebungslicht für Monitore mit RGB-LEDs auf der Rückseite. Glowback erfasst den Bildschirm 30-mal pro Sekunde und gibt jeder LED die Farbe des Bildes direkt vor ihr.
```

### Search terms (one per box)

```text
Umgebungslicht
Bias Lighting
RGB Monitor
Dynamische Beleuchtung
OpenRGB
Bildschirm Sync
Matter Lampe
```

### Copyright and trademark info

```text
© 2026 Ilyomix. Kostenlos und Open Source, MIT-Lizenz.
```

### Additional system requirements (minimum hardware)

```text
Ein Monitor oder Gerät mit RGB-LEDs, das die dynamische Beleuchtung von Windows oder OpenRGB steuern kann
Die dynamische Beleuchtung braucht Windows 11; OpenRGB läuft auch unter Windows 10
```

## Italiano (it-it)

Product name: **Glowback**. Website for this language: https://ilyomix.github.io/glowback/it/

### Description

```text
Glowback trasforma i LED RGB sul retro del tuo monitor in una vera luce ambientale. Il software dei monitor da gaming offre solo effetti fissi, a respiro o arcobaleno: Glowback cattura lo schermo 30 volte al secondo e dà a ogni LED il suo colore, preso dal bordo dell'immagine proprio davanti a lui. Un tramonto a sinistra dello schermo colora d'arancione la parete di sinistra.

Glowback non è legato a nessuna marca: controlla qualsiasi dispositivo gestibile dall'Illuminazione dinamica di Windows (lo standard HID LampArray) o da OpenRGB: monitor, strisce LED, case per PC, lampade.

Oltre allo schermo, i LED possono mostrare un colore, una sfumatura (ferma o in movimento) o seguire il suono del PC: pulsazione, spettro o onde, senza microfono e senza registrare nulla. I profili cambiano l'atmosfera da soli: una luce più morbida di notte, la musica mentre suona Spotify, lo schermo per i giochi.

Comandalo anche dal telefono: con Matter, Glowback è una luce in Apple Casa, Google Home o Alexa, sulla tua rete locale. Glowback è una luce Matter non certificata: Apple Casa chiede di confermare (Aggiungi comunque), Google Home richiede prima una configurazione di prova gratuita. Funziona anche con Home Assistant: accendilo, regola luminosità e colore da dashboard, automazioni o con la voce.

Cosa serve
• Un monitor o un altro dispositivo con LED RGB controllabile dall'Illuminazione dinamica di Windows o da OpenRGB. Per un monitor, collega al PC il suo cavo USB upstream.
• Disattiva l'Illuminazione dinamica di Windows per quel dispositivo (Impostazioni > Personalizzazione > Illuminazione dinamica), così Windows e Glowback non comandano i LED insieme.

Glowback è gratuito e open source (licenza MIT): nessun account, nessuna pubblicità, nessuna telemetria. Codice sorgente, guide ed elenco dei dispositivi testati: https://github.com/Ilyomix/glowback
```

### What's new in this version

```text
Prima versione su Microsoft Store. Lo Store tiene aggiornato Glowback e Windows lo avvia all'accesso (puoi disattivarlo in Impostazioni > App > Avvio). Usavi già Glowback? Le tue impostazioni e i telefoni associati con Matter restano.
```

### Product features

```text
Ogni LED prende il colore del bordo dello schermo più vicino, o un solo colore medio per tutti
Film, giochi e HDR: cattura tramite GPU a schermo intero, bande nere ignorate
Colori luminosi e fedeli, anche nelle scene scure
Atmosfere: lo schermo, un colore, una sfumatura ferma o in movimento, o la musica del PC
Profili: una luce notturna agli orari che scegli e un'atmosfera per ogni app
Matter: una luce in Apple Casa, Google Home o Alexa, sulla rete locale
Home Assistant: dashboard, automazioni, Google Assistant, Alexa e Siri
Una finestra con l'anteprima in diretta dello schermo e dei LED
Impostazioni rapide dall'icona accanto all'orologio
Rileva da solo i dispositivi Illuminazione dinamica di Windows e OpenRGB
Più monitor: ogni dispositivo LED segue il proprio schermo
Bilanciamento del bianco per dispositivo
Circa 0,5 ms di CPU per immagine
6 lingue: italiano, inglese, francese, spagnolo, tedesco e portoghese
Gratuito e open source: nessun account, nessuna pubblicità, nessuna telemetria
```

### Screenshots

| File | Caption |
|---|---|
| `build/store/it/1-light.png` | Luce ambientale: anteprima in diretta dello schermo e dei LED |
| `build/store/it/2-music.png` | L'atmosfera Musica: i LED seguono il suono del PC |
| `build/store/it/3-profiles.png` | Profili: una luce notturna e un'atmosfera per ogni app |
| `build/store/it/4-matter.png` | Apple e Google: aggiungi Glowback all'app Casa del telefono con Matter |
| `build/store/it/5-home.png` | Home Assistant: Glowback come luce nelle tue dashboard |

### Short description

```text
Luce ambientale per monitor con LED RGB sul retro. Glowback cattura lo schermo 30 volte al secondo e dà a ogni LED il colore dell'immagine proprio davanti a lui.
```

### Search terms (one per box)

```text
luce ambientale
retroilluminazione
monitor RGB
Illuminazione dinamica
OpenRGB
sincronizza schermo
luce Matter
```

### Copyright and trademark info

```text
© 2026 Ilyomix. Gratuito e open source, licenza MIT.
```

### Additional system requirements (minimum hardware)

```text
Un monitor o dispositivo con LED RGB controllabile dall'Illuminazione dinamica di Windows o da OpenRGB
L'Illuminazione dinamica richiede Windows 11; OpenRGB funziona anche su Windows 10
```

## Português (Brasil) (pt-br)

Product name: **Glowback**. Website for this language: https://ilyomix.github.io/glowback/pt/

### Description

```text
O Glowback transforma os LEDs RGB na traseira do seu monitor em uma verdadeira luz ambiente. O software dos monitores gamer só oferece efeitos fixos, de respiração ou arco-íris: o Glowback captura a tela 30 vezes por segundo e dá a cada LED sua própria cor, tirada da borda da imagem bem à sua frente. Um pôr do sol à esquerda da tela deixa a parede da esquerda laranja.

O Glowback não depende de nenhuma marca: ele controla qualquer dispositivo que a Iluminação dinâmica do Windows (o padrão HID LampArray) ou o OpenRGB consigam controlar: monitores, fitas LED, gabinetes, luminárias.

Além da tela, os LEDs podem mostrar uma cor, um degradê (parado ou em movimento) ou acompanhar o som do seu PC: pulso, espectro ou ondas, sem microfone e sem gravar nada. Os perfis mudam o clima sozinhos: uma luz mais suave à noite, a música enquanto o Spotify toca, a tela para os jogos.

Controle também pelo celular: com Matter, o Glowback é uma luz no app Casa da Apple, no Google Home ou na Alexa, na sua rede local. O Glowback é uma luz Matter não certificada: o app Casa pede para confirmar (Adicionar Mesmo Assim) e o Google Home precisa antes de uma configuração de teste gratuita. Ele também funciona com o Home Assistant: ligue, ajuste o brilho e a cor pelos painéis, automações ou por voz.

O que você precisa
• Um monitor ou outro dispositivo com LEDs RGB que a Iluminação dinâmica do Windows ou o OpenRGB consigam controlar. No caso de um monitor, conecte o cabo USB upstream dele ao PC.
• Desative a Iluminação dinâmica do Windows para esse dispositivo (Configurações > Personalização > Iluminação dinâmica), para que o Windows e o Glowback não controlem os LEDs ao mesmo tempo.

O Glowback é gratuito e de código aberto (licença MIT): sem conta, sem anúncios, sem telemetria. Código-fonte, guias e lista de dispositivos testados: https://github.com/Ilyomix/glowback
```

### What's new in this version

```text
Primeira versão na Microsoft Store. A Store mantém o Glowback atualizado, e o Windows o inicia quando você entra (dá para desativar em Configurações > Aplicativos > Inicialização). Já usava o Glowback? Suas configurações e os celulares pareados com Matter são mantidos.
```

### Product features

```text
Cada LED pega a cor da borda da tela mais próxima, ou uma cor média para todos
Filmes, jogos e HDR: captura pela GPU em tela cheia, ignora as barras pretas
Cores brilhantes e fiéis, mesmo em cenas escuras
Climas: a tela, uma cor, um degradê parado ou em movimento, ou a música do seu PC
Perfis: uma luz noturna nos horários que você escolher e um clima para cada app
Matter: uma luz no app Casa da Apple, no Google Home ou na Alexa, na sua rede local
Home Assistant: painéis, automações, Google Assistente, Alexa e Siri
Uma janela com prévia ao vivo da sua tela e dos seus LEDs
Ajustes rápidos pelo ícone ao lado do relógio
Detecta sozinho os dispositivos de Iluminação dinâmica do Windows e o OpenRGB
Vários monitores: cada dispositivo LED segue a sua própria tela
Balanço de branco por dispositivo
Cerca de 0,5 ms de CPU por quadro
6 idiomas: português, inglês, francês, espanhol, alemão e italiano
Gratuito e de código aberto: sem conta, sem anúncios, sem telemetria
```

### Screenshots

| File | Caption |
|---|---|
| `build/store/pt/1-light.png` | Luz ambiente: prévia ao vivo da sua tela e dos seus LEDs |
| `build/store/pt/2-music.png` | O clima Música: os LEDs acompanham o som do seu PC |
| `build/store/pt/3-profiles.png` | Perfis: uma luz noturna e um clima para cada app |
| `build/store/pt/4-matter.png` | Apple e Google: adicione o Glowback ao app Casa do celular com Matter |
| `build/store/pt/5-home.png` | Home Assistant: o Glowback como uma luz nos seus painéis |

### Short description

```text
Luz ambiente para monitores com LEDs RGB na traseira. O Glowback captura a tela 30 vezes por segundo e dá a cada LED a cor da imagem bem à sua frente.
```

### Search terms (one per box)

```text
luz ambiente
retroiluminação
monitor RGB
Iluminação dinâmica
OpenRGB
sincronizar tela
luz Matter
```

### Copyright and trademark info

```text
© 2026 Ilyomix. Gratuito e de código aberto, licença MIT.
```

### Additional system requirements (minimum hardware)

```text
Um monitor ou dispositivo com LEDs RGB que a Iluminação dinâmica do Windows ou o OpenRGB consigam controlar
A Iluminação dinâmica exige o Windows 11; o OpenRGB também funciona no Windows 10
```
