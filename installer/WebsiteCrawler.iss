; Inno Setup 6 script: packages dist\WebsiteCrawler\ (build_exe.bat) into dist\WebsiteCrawler-Setup.exe.
; Build: ISCC /DAppVersion=<server.py VERSION> installer\WebsiteCrawler.iss (build_exe.bat does this).
;
; Per user, without an admin prompt: the in-app updater rewrites the install folder, so it must be
; writable by the user (never Program Files). The app keeps its crawl results in jobs\ and its logs
; beside WebsiteCrawler.exe (server.BASE_DIR), so the uninstaller asks before deleting crawl results.

#ifndef AppVersion
  #error Pass the version: ISCC /DAppVersion=1.2.2 installer\WebsiteCrawler.iss
#endif

[Setup]
; Fixed for good: the same AppId makes a newer installer upgrade the existing install in place.
AppId={{629E9CBC-620B-40FC-84FC-6AE323925583}
AppName=Website Crawler
AppVersion={#AppVersion}
AppVerName=Website Crawler {#AppVersion}
AppPublisher=addico786
AppPublisherURL=https://github.com/addico786/website_crawler
AppUpdatesURL=https://github.com/addico786/website_crawler/releases/latest
VersionInfoVersion={#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\WebsiteCrawler
DisableDirPage=auto
DisableProgramGroupPage=yes
UninstallDisplayName=Website Crawler
UninstallDisplayIcon={app}\WebsiteCrawler.exe
; Close a running app (and its crawl worker) before replacing its files.
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
OutputDir=..\dist
OutputBaseFilename=WebsiteCrawler-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; An upgrade replaces the program as a whole, as the in-app updater does (robocopy /MIR).
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\WebsiteCrawler\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Website Crawler"; Filename: "{app}\WebsiteCrawler.exe"
Name: "{autodesktop}\Website Crawler"; Filename: "{app}\WebsiteCrawler.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WebsiteCrawler.exe"; Description: "Launch Website Crawler"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Files the app writes itself: in-app updates may have added program files, plus its logs.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\_update"
Type: files; Name: "{app}\app.log"
Type: files; Name: "{app}\browser_install.log"

[Code]
function IsEmptyDir(Dir: String): Boolean;
var
  FindRec: TFindRec;
begin
  Result := True;
  if FindFirst(Dir + '\*', FindRec) then
  try
    repeat
      if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
        Result := False;
    until (not Result) or (not FindNext(FindRec));
  finally
    FindClose(FindRec);
  end;
end;

// Crawl results live in {app}\jobs. Ask before deleting them; a silent uninstall keeps them.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Jobs: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  Jobs := ExpandConstant('{app}\jobs');
  if DirExists(Jobs) then
  begin
    if IsEmptyDir(Jobs) then
      RemoveDir(Jobs)
    else if (not UninstallSilent) and (MsgBox('Also delete your crawl results?' + #13#10#13#10 +
        'They are in ' + Jobs + '. Choose No to keep them.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
      DelTree(Jobs, True, True, True);
  end;
  RemoveDir(ExpandConstant('{app}'));
end;
