Unicode true
!include "MUI2.nsh"
!define APP "Reel Maker"
!ifndef VER
  !define VER "0.0.0"
!endif
Name "${APP}"
OutFile "ReelMakerSetup.exe"
InstallDir "$LOCALAPPDATA\Programs\ReelMaker"
InstallDirRegKey HKCU "Software\ReelMaker" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
BrandingText "${APP} ${VER}"
VIProductVersion "${VER}.0"
VIAddVersionKey "ProductName" "${APP}"
VIAddVersionKey "FileDescription" "${APP} installer"
VIAddVersionKey "FileVersion" "${VER}"
VIAddVersionKey "ProductVersion" "${VER}"
VIAddVersionKey "LegalCopyright" "Reel Maker"

!define MUI_ICON "ReelMaker\icon.ico"
!define MUI_UNICON "ReelMaker\icon.ico"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "This will install Reel Maker: turn 16:9 videos into 9:16 Instagram Reels with backgrounds, safe zones, trimming, text, logos and covers.$\r$\n$\r$\nAn internet connection is used once during setup to download the video encoder (about 30 MB).$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Open Reel Maker now"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApp

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInstSuccess
  IfSilent 0 +2
    Exec '"$INSTDIR\python\pythonw.exe" -I "$INSTDIR\app\launch.pyw"'
FunctionEnd

Function LaunchApp
  Exec '"$INSTDIR\python\pythonw.exe" -I "$INSTDIR\app\launch.pyw"'
FunctionEnd

Section "Install"
  ; When updating from inside the app, wait until Reel Maker has closed
  ; (its files can't be replaced while it's running).
  StrCpy $1 0
  waitloop:
    IfFileExists "$INSTDIR\python\python312.dll" 0 waitdone
    ClearErrors
    Delete "$INSTDIR\python\python312.dll"
    IfFileExists "$INSTDIR\python\python312.dll" 0 waitdone
    IntOp $1 $1 + 1
    IntCmp $1 40 waitfail
    Sleep 500
    Goto waitloop
  waitfail:
    IfSilent 0 +2
      Abort
    MessageBox MB_OK|MB_ICONEXCLAMATION "Please close Reel Maker, then click OK to continue."
    StrCpy $1 0
    Goto waitloop
  waitdone:
  SetOutPath "$INSTDIR"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app"
  File /r "ReelMaker\*.*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  IfFileExists "$LOCALAPPDATA\ReelMaker\ffmpeg\ffmpeg.exe" ffdone
  DetailPrint "Downloading the video encoder (about 30 MB)..."
  nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\get-ffmpeg.ps1" -Dest "$LOCALAPPDATA\ReelMaker\ffmpeg\ffmpeg.exe"'
  Pop $0
  StrCmp $0 "0" ffdone
  DetailPrint "The encoder couldn't be downloaded right now. Reel Maker will get it the first time you export."
  ffdone:

  CreateDirectory "$SMPROGRAMS\${APP}"
  CreateShortCut "$SMPROGRAMS\${APP}\${APP}.lnk" "$INSTDIR\python\pythonw.exe" '-I "$INSTDIR\app\launch.pyw"' "$INSTDIR\icon.ico" 0
  CreateShortCut "$SMPROGRAMS\${APP}\Uninstall ${APP}.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortCut "$DESKTOP\${APP}.lnk" "$INSTDIR\python\pythonw.exe" '-I "$INSTDIR\app\launch.pyw"' "$INSTDIR\icon.ico" 0

  WriteRegStr HKCU "Software\ReelMaker" "InstallDir" "$INSTDIR"
  !define UNKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\ReelMaker"
  WriteRegStr HKCU "${UNKEY}" "DisplayName" "${APP}"
  WriteRegStr HKCU "${UNKEY}" "DisplayVersion" "${VER}"
  WriteRegStr HKCU "${UNKEY}" "DisplayIcon" "$INSTDIR\icon.ico"
  WriteRegStr HKCU "${UNKEY}" "Publisher" "Reel Maker"
  WriteRegStr HKCU "${UNKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNKEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "${UNKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNKEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\${APP}.lnk"
  RMDir /r "$SMPROGRAMS\${APP}"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\icon.ico"
  Delete "$INSTDIR\get-ffmpeg.ps1"
  RMDir /r "$LOCALAPPDATA\ReelMaker\ffmpeg"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ReelMaker"
  DeleteRegKey HKCU "Software\ReelMaker"
SectionEnd
