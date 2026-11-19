<p align="center">
  <img src="assets/banner-it.svg" alt="Glowback: luce ambientale per i LED RGB sul retro del tuo monitor, ogni LED sincronizzato con l'immagine in tempo reale" width="100%">
</p>

<p align="center">
  <a href="README.md">English</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.de.md">Deutsch</a> · <b>Italiano</b> · <a href="README.pt.md">Português</a>
</p>

<h1 align="center">Glowback: luce ambientale per monitor con LED RGB sul retro</h1>

<p align="center">
  <b>Sincronizzazione con lo schermo, gratuita e open source, per i LED RGB sul retro del tuo monitor.</b><br>
  Ogni LED segue la parte dell'immagine davanti a sé, in tempo reale.<br>
  Compatibile con i dispositivi <b>Illuminazione dinamica di Windows 11</b> e <b>OpenRGB</b>. Niente strisce LED, fotocamere o software del produttore.
</p>

<p align="center">
  <a href="https://github.com/Ilyomix/glowback/releases/latest/download/GlowbackSetup.exe"><img alt="Scarica per Windows" src="https://img.shields.io/github/v/release/Ilyomix/glowback?label=scarica%20per%20Windows&color=7c3aed"></a>
  <img alt="Windows 10/11" src="https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows">
  <img alt="HDR" src="https://img.shields.io/badge/HDR-compatibile-ff8a3d">
  <a href="LICENSE"><img alt="Licenza MIT" src="https://img.shields.io/badge/licenza-MIT-blue"></a>
</p>

---

Sempre più monitor da gaming hanno LED RGB sul retro, ma il loro software offre solo effetti fissi, a respiro o arcobaleno. **Glowback** li trasforma in una **vera luce ambientale**: cattura lo schermo 30 volte al secondo e dà **a ogni LED il suo colore**, preso dal bordo dell'immagine proprio davanti a lui. Un tramonto a sinistra dello schermo colora d'arancione la parete di sinistra.

Glowback non è legato a nessuna marca: controlla qualsiasi dispositivo gestibile dall'**Illuminazione dinamica di Windows** (lo standard HID LampArray) o da **[OpenRGB](https://openrgb.org)**: monitor, strisce LED, case per PC, lampade.

## ✨ Funzionalità

- 🎯 **Una zona per LED**, proiettata sul bordo dello schermo più vicino. In alternativa, un solo colore medio.
- 🎬 **Film, giochi, HDR**: cattura tramite GPU (DXGI) a schermo intero, compatibile con l'HDR, **ignora le bande nere**.
- 💡 **Colori luminosi e fedeli**, anche nelle scene scure.
- 🪟 **Una vera app per Windows**: una finestra con un'anteprima in diretta dei tuoi LED, impostazioni rapide dall'icona accanto all'orologio, installer, menu Start, avvio con Windows e disinstallazione pulita da *Impostazioni → App*.
- ⏳ **Sincronizza solo quando vuoi**: mentre un'app è aperta, in primo piano o a schermo intero, sullo schermo che scegli. Il resto del tempo, i LED mantengono il proprio effetto.
- 🔄 **Avviso di aggiornamenti** una volta al giorno (disattivabile).
- 🏠 **Home Assistant, Google Assistant, Alexa e Siri**: Glowback compare come una luce da comandare da dashboard, automazioni o con la voce.
- 🌍 **6 lingue**, in base alla lingua di Windows.
- 🔌 **Plug and play**: rileva automaticamente i dispositivi Illuminazione dinamica e OpenRGB.
- 🪶 **Leggero**: circa 0,5 ms di CPU per immagine.

## 🚀 Installazione

1. **Collega il cavo USB upstream del monitor** al PC (USB-B o USB-C).
2. **Disattiva l'Illuminazione dinamica di Windows per quel dispositivo**: *Impostazioni → Personalizzazione → Illuminazione dinamica → il tuo dispositivo → «Usa Illuminazione dinamica nei miei dispositivi» → Disattivato*.
3. **Scarica [GlowbackSetup.exe](https://github.com/Ilyomix/glowback/releases/latest/download/GlowbackSetup.exe)** e segui la procedura guidata (non servono diritti di amministratore).

> Windows SmartScreen potrebbe segnalare un autore sconosciuto perché l'app non è ancora firmata: *Ulteriori informazioni → Esegui comunque*. [Politica di firma del codice](CODE_SIGNING.md) · [Privacy](PRIVACY.md)

Per verificare l'orientamento dei LED: *menu Start → Strumenti di Glowback → Prova i LED* (sinistra rossa, destra blu).

## ✅ Il mio monitor è compatibile?

Sì, se vale **una** di queste condizioni:

1. **Compare in Windows** in *Impostazioni → Personalizzazione → Illuminazione dinamica*.
2. **È supportato da [OpenRGB](https://openrgb.org)**: avvia OpenRGB con il suo server SDK e Glowback lo rileva da solo.
3. **Nessuna delle due?** Aggiungi una striscia LED con una scheda RP2040 da 5 $: [guida DIY](docs/DIY-LED-strip.md) (in inglese).

Testato con: AOC AGON PRO AG276QZD2 (47 LED). Funziona sul tuo monitor? [Faccelo sapere](https://github.com/Ilyomix/glowback/issues/new?template=device-report.yml).

## 🪟 L'app

Avviando Glowback dal menu Start si apre la sua finestra: **Luce ambientale** (anteprima in diretta, acceso/spento, modalità, luminosità), **Quando sincronizzare**, **Home Assistant**, **Impostazioni** (avvio con Windows, aggiornamenti, lingua) e **Informazioni**. Chiudendola, Glowback continua in background: fai doppio clic sulla sua icona accanto all'orologio per riaprirla, o un clic per il pannello rapido.

## ⏳ Quando sincronizzare

Di solito Glowback segue lo schermo sempre. Nella pagina **Quando sincronizzare** aggiungi delle condizioni (un'app; quando: aperta, in primo piano o a schermo intero; e su quale schermo): Glowback segue lo schermo solo mentre una è soddisfatta, e il resto del tempo i LED mostrano il proprio effetto. Per esempio: VLC in primo piano, o qualsiasi app a schermo intero sullo schermo dei LED. [Guida completa (in inglese)](README.md#-when-to-sync).

## 🏠 Home Assistant e Google Assistant

Glowback può comparire in Home Assistant come una luce (acceso/spento, luminosità e modalità), da comandare dalle dashboard, dalle automazioni, da Google Assistant, da Alexa e da Siri (app Casa di Apple, con l'integrazione HomeKit Bridge di Home Assistant). Installa l'app **Mosquitto broker** in Home Assistant, poi nel pannello di Glowback fai clic su **Home Assistant** e inserisci indirizzo, utente e password. [Guida completa (in inglese)](README.md#-home-assistant--google-assistant).

## 🗑️ Disinstallare

- **Installer**: *Impostazioni → App → App installate → Glowback → Disinstalla*. I LED tornano all'effetto del dispositivo.
- **Versione Python**: `glowback --uninstall`, poi `pip uninstall glowback`.
- **Portatile**: `glowback.exe --uninstall`, poi elimina i file .exe.

## ❓ Domande frequenti

**Quali monitor sono compatibili?** Qualsiasi monitor la cui illuminazione RGB posteriore sia controllabile tramite l'Illuminazione dinamica di Windows o OpenRGB. Verifica con `glowback --list`.

**Funziona con HDR, giochi e film a schermo intero?** Sì. I contenuti protetti da DRM di solito risultano neri per qualsiasi strumento di cattura.

**Non si accende nulla.** Controlla il cavo USB del monitor, che l'RGB sia attivo nel menu del monitor e che l'Illuminazione dinamica di Windows sia disattivata per quel dispositivo.

**I colori sono dal lato sbagliato.** Usa *Prova i LED*; se sinistra e destra sono invertite, aggiungi `--mirror`.

Opzioni da riga di comando e dettagli tecnici: [README in inglese](README.md#%EF%B8%8F-command-line).

## ⭐ Supporto

Se Glowback illumina la tua scrivania, **metti una stella al repository**: così lo trovano altri possessori di monitor RGB.

---

<sub>Ambilight è un marchio di Koninklijke Philips N.V. / TP Vision. Glowback è un progetto open source indipendente, senza legami con loro.</sub>

MIT © [Ilyomix](https://github.com/Ilyomix) · [Politica di firma del codice](CODE_SIGNING.md) · [Privacy](PRIVACY.md)
