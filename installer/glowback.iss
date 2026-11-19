; Glowback Windows installer (Inno Setup 6.3+). Built by .github/workflows/release.yml:
;   ISCC /DMyAppVersion=1.2.3 installer\glowback.iss
; Expects dist\Glowback\ (PyInstaller --onedir, no console) and dist\glowback.exe (command line).
; Code-signed releases add /DSignedUninstaller (see CODE_SIGNING.md).

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{8E1F5C2A-6B7D-4E7A-9C51-3F2B7A9D0C41}
AppName=Glowback
AppVersion={#MyAppVersion}
AppVerName=Glowback {#MyAppVersion}
AppPublisher=Ilyomix
AppPublisherURL=https://github.com/Ilyomix/glowback
AppSupportURL=https://github.com/Ilyomix/glowback/issues
AppUpdatesURL=https://github.com/Ilyomix/glowback/releases
AppComments=Ambient light for the RGB LEDs on the back of your monitor
DefaultDirName={autopf}\Glowback
DisableDirPage=auto
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=GlowbackSetup
SetupIconFile=..\assets\glowback.ico
UninstallDisplayIcon={app}\Glowback.exe
UninstallDisplayName=Glowback
ShowLanguageDialog=auto
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
; Code signing (SignPath Foundation) requires the product name and version on every signed file
VersionInfoVersion={#MyAppVersion}
VersionInfoTextVersion={#MyAppVersion}
VersionInfoProductName=Glowback
VersionInfoProductVersion={#MyAppVersion}
VersionInfoProductTextVersion={#MyAppVersion}
VersionInfoCompany=Ilyomix
VersionInfoCopyright=Copyright (c) 2026 Ilyomix. MIT License.
VersionInfoDescription=Glowback installer
#ifdef SignedUninstaller
; A first compile writes the uninstaller to build\uninstaller and stops. Once that file is signed (together with the
; apps), the second compile embeds its signature, so the installed unins000.exe is signed too.
SignedUninstaller=yes
SignedUninstallerDir=..\build\uninstaller
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[CustomMessages]
; English is the default for every language; the lines below override it
Tools=Glowback tools
TestLeds=Test the LEDs (orientation)
Calibrate=Calibrate the white balance
Comment=Ambient light for the RGB LEDs on the back of your monitor
DynamicLighting=Tip: turn off Windows Dynamic Lighting for your monitor (Settings > Personalization > Dynamic Lighting), otherwise Windows and Glowback fight over the LEDs.
UpdatesGroup=Updates:
CheckUpdates=Check for a new version once a day (asks GitHub; only the Glowback version is sent)
french.Tools=Outils Glowback
french.TestLeds=Tester les LED (orientation)
french.Calibrate=Calibrer la balance des blancs
french.Comment=Lumière d'ambiance pour les LED RGB au dos de votre écran
french.DynamicLighting=Astuce : désactivez l'Éclairage dynamique de Windows pour votre écran (Paramètres > Personnalisation > Éclairage dynamique), sinon Windows et Glowback se disputent les LED.
french.UpdatesGroup=Mises à jour :
french.CheckUpdates=Rechercher une nouvelle version une fois par jour (sur GitHub ; seule la version de Glowback est envoyée)
spanish.Tools=Herramientas de Glowback
spanish.TestLeds=Probar los LED (orientación)
spanish.Calibrate=Calibrar el balance de blancos
spanish.Comment=Luz ambiental para los LED RGB de la parte trasera de tu monitor
spanish.DynamicLighting=Consejo: desactiva la Iluminación dinámica de Windows para tu monitor (Configuración > Personalización > Iluminación dinámica); si no, Windows y Glowback se disputarán los LED.
spanish.UpdatesGroup=Actualizaciones:
spanish.CheckUpdates=Buscar una nueva versión una vez al día (en GitHub; solo se envía la versión de Glowback)
german.Tools=Glowback-Werkzeuge
german.TestLeds=LEDs testen (Ausrichtung)
german.Calibrate=Weißabgleich kalibrieren
german.Comment=Umgebungslicht für die RGB-LEDs auf der Rückseite deines Monitors
german.DynamicLighting=Tipp: Schalte die dynamische Beleuchtung von Windows für deinen Monitor aus (Einstellungen > Personalisierung > Dynamische Beleuchtung), sonst streiten sich Windows und Glowback um die LEDs.
german.UpdatesGroup=Updates:
german.CheckUpdates=Einmal täglich nach einer neuen Version suchen (auf GitHub; nur die Glowback-Version wird gesendet)
italian.Tools=Strumenti di Glowback
italian.TestLeds=Prova i LED (orientamento)
italian.Calibrate=Calibra il bilanciamento del bianco
italian.Comment=Luce ambientale per i LED RGB sul retro del tuo monitor
italian.DynamicLighting=Suggerimento: disattiva l'Illuminazione dinamica di Windows per il tuo monitor (Impostazioni > Personalizzazione > Illuminazione dinamica), altrimenti Windows e Glowback si contendono i LED.
italian.UpdatesGroup=Aggiornamenti:
italian.CheckUpdates=Cercare una nuova versione una volta al giorno (su GitHub; viene inviata solo la versione di Glowback)
brazilianportuguese.Tools=Ferramentas do Glowback
brazilianportuguese.TestLeds=Testar os LEDs (orientação)
brazilianportuguese.Calibrate=Calibrar o balanço de branco
brazilianportuguese.Comment=Luz ambiente para os LEDs RGB na traseira do seu monitor
brazilianportuguese.DynamicLighting=Dica: desative a Iluminação dinâmica do Windows para o seu monitor (Configurações > Personalização > Iluminação dinâmica), senão o Windows e o Glowback disputam os LEDs.
brazilianportuguese.UpdatesGroup=Atualizações:
brazilianportuguese.CheckUpdates=Procurar uma nova versão uma vez por dia (no GitHub; só a versão do Glowback é enviada)
portuguese.Tools=Ferramentas do Glowback
portuguese.TestLeds=Testar os LEDs (orientação)
portuguese.Calibrate=Calibrar o equilíbrio de brancos
portuguese.Comment=Luz ambiente para os LEDs RGB na traseira do seu monitor
portuguese.DynamicLighting=Dica: desative a Iluminação dinâmica do Windows para o seu monitor (Definições > Personalização > Iluminação dinâmica), caso contrário o Windows e o Glowback disputam os LEDs.
portuguese.UpdatesGroup=Atualizações:
portuguese.CheckUpdates=Procurar uma nova versão uma vez por dia (no GitHub; apenas é enviada a versão do Glowback)

[Tasks]
Name: "autostart"; Description: "{cm:AutoStartProgram,Glowback}"; GroupDescription: "{cm:AutoStartProgramGroupDescription}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
; Shown during installation as SignPath Foundation's terms ask for anything that contacts a server (PRIVACY.md)
Name: "checkupdates"; Description: "{cm:CheckUpdates}"; GroupDescription: "{cm:UpdatesGroup}"

[Files]
Source: "..\dist\Glowback\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\glowback.exe"; DestDir: "{app}"; DestName: "glowback-cli.exe"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Glowback"; Filename: "{app}\Glowback.exe"; Comment: "{cm:Comment}"
Name: "{autoprograms}\{cm:Tools}\{cm:TestLeds}"; Filename: "{app}\glowback-cli.exe"; Parameters: "--test --pause-at-end"; IconFilename: "{app}\Glowback.exe"
Name: "{autoprograms}\{cm:Tools}\{cm:Calibrate}"; Filename: "{app}\glowback-cli.exe"; Parameters: "--calibrate --pause-at-end"; IconFilename: "{app}\Glowback.exe"
Name: "{autodesktop}\Glowback"; Filename: "{app}\Glowback.exe"; Comment: "{cm:Comment}"; Tasks: desktopicon

[Registry]
; Same value the tray menu's "Start with Windows" toggles
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Glowback"; ValueData: """{app}\Glowback.exe"" --background --from-autostart"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
; Saves the "check for updates" box. Silent installs (in-app updates) keep the setting as it is.
Filename: "{app}\glowback-cli.exe"; Parameters: "--check-updates {code:UpdateChecksSwitch}"; Flags: runhidden runasoriginaluser waituntilterminated; Check: InteractiveInstall
Filename: "{app}\Glowback.exe"; Description: "{cm:LaunchProgram,Glowback}"; Flags: nowait postinstall skipifsilent
; In-app updates run this installer silently with /RELAUNCH=1: start the new version afterwards
Filename: "{app}\Glowback.exe"; Parameters: "--after-update"; Flags: nowait; Check: ShouldRelaunch

[UninstallRun]
; Stops Glowback (LEDs go back to the monitor's own effect) and removes startup entry, settings and logs
Filename: "{app}\Glowback.exe"; Parameters: "--uninstall"; RunOnceId: "GlowbackCleanup"; Flags: runhidden waituntilterminated

[Code]
var
  UpdateTaskShown: Boolean;

function ShouldRelaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

function InteractiveInstall: Boolean;
begin
  Result := not WizardSilent;
end;

{ Glowback writes settings.json with Python's json module: "key": value }
function UpdateChecksOff: Boolean;
var
  Settings: AnsiString;
begin
  Result := LoadStringFromFile(ExpandConstant('{localappdata}\Glowback\settings.json'), Settings) and
    (Pos('"check_updates": false', String(Settings)) > 0);
end;

function UpdateChecksSwitch(Param: String): String;
begin
  if WizardIsTaskSelected('checkupdates') then
    Result := 'on'
  else
    Result := 'off';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  { An older Glowback may be running: ask it to hand the LEDs back and quit before files are replaced }
  if FileExists(ExpandConstant('{app}\Glowback.exe')) then
  begin
    Exec(ExpandConstant('{app}\Glowback.exe'), '--stop', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1500);
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { The box shows the current setting the first time the page appears: it may have been turned off in Glowback }
  if (CurPageID = wpSelectTasks) and not UpdateTaskShown then
  begin
    UpdateTaskShown := True;
    if UpdateChecksOff then
      WizardSelectTasks('!checkupdates');
  end;
  if CurPageID = wpFinished then
    WizardForm.FinishedLabel.Caption := WizardForm.FinishedLabel.Caption + #13#10#13#10 + CustomMessage('DynamicLighting');
end;
