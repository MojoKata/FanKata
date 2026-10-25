; Inno Setup script: Fankata-<version>-setup.exe (one download, one UAC prompt).
; Installs the app, the PawnIO driver if missing, and the fankatad service.
; Developer option: /SIMULATE=1 runs the service against simulated hardware (for VMs).

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{4F6C2A1E-8B3D-4E5A-9C7F-2D1B0A9E8F61}
AppName=Fankata
AppVersion={#AppVersion}
AppPublisher=Fankata
AppComments=Fan control with temperature curves
DefaultDirName={autopf}\Fankata
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\..\releases
OutputBaseFilename=Fankata-{#AppVersion}-setup
SetupIconFile=fankata.ico
UninstallDisplayIcon={app}\fankata.exe
UninstallDisplayName=Fankata
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Files]
Source: "..\..\build\windows\dist\Fankata\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "THIRD-PARTY.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\build\windows-deps\PawnIO_setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedPawnIO
; kept for Troubleshoot fans → Repair (requirement 4.7.4)
Source: "..\..\build\windows-deps\PawnIO_setup.exe"; DestDir: "{app}\pawnio"; Flags: ignoreversion

[Registry]
Root: HKLM; Subkey: "Software\Fankata"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Fankata"; ValueType: dword; ValueName: "Simulate"; ValueData: 1; Check: WantSimulate

[Icons]
Name: "{autoprograms}\Fankata"; Filename: "{app}\fankata.exe"; Comment: "Fan control with temperature curves"

[Run]
Filename: "{tmp}\PawnIO_setup.exe"; Parameters: "-install -silent"; StatusMsg: "Installing the PawnIO driver..."; Flags: waituntilterminated; Check: NeedPawnIO
Filename: "{app}\fankatad.exe"; Parameters: "--startup auto install"; StatusMsg: "Registering the Fankata service..."; Flags: runhidden waituntilterminated
Filename: "{app}\fankatad.exe"; Parameters: "--startup auto update"; Flags: runhidden waituntilterminated
Filename: "{sys}\sc.exe"; Parameters: "failure fankatad reset= 60 actions= restart/2000/restart/5000/restart/10000"; Flags: runhidden waituntilterminated
; Signed-in (interactive) users may START this service, so the app can turn Fankata back on
; without elevation. Stopping goes through the service itself (an authorized request), and
; nobody but administrators may reconfigure it.
Filename: "{sys}\sc.exe"; Parameters: "sdset fankatad D:(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCSWRPLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)"; Flags: runhidden waituntilterminated
Filename: "{sys}\sc.exe"; Parameters: "start fankatad"; StatusMsg: "Starting the Fankata service..."; Flags: runhidden waituntilterminated
Filename: "{app}\fankata.exe"; Description: "Open Fankata"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Stopping the service returns every fan to firmware control.
Filename: "{sys}\sc.exe"; Parameters: "stop fankatad"; Flags: runhidden waituntilterminated; RunOnceId: "StopService"
Filename: "{app}\fankatad.exe"; Parameters: "remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveService"

[UninstallDelete]
Type: filesandordirs; Name: "{commonappdata}\Fankata\run"
Type: filesandordirs; Name: "{commonappdata}\Fankata\sim"

[Code]
function NeedPawnIO: Boolean;
begin
  Result := not RegKeyExists(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO');
end;

function WantSimulate: Boolean;
begin
  Result := ExpandConstant('{param:SIMULATE|0}') = '1';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  rc: Integer;
begin
  { upgrading: close any open Fankata window (it keeps no unsaved state) and stop the
    service (fans return to firmware control) before replacing files }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM fankata.exe', '', SW_HIDE, ewWaitUntilTerminated, rc);
  Exec(ExpandConstant('{sys}\sc.exe'), 'stop fankatad', '', SW_HIDE, ewWaitUntilTerminated, rc);
  Sleep(3000);
  Result := '';
end;
