; Per-user installer. Build with tools/build_windows.py; all payload paths are
; generated from a validated source/runtime allowlist.
Unicode True
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"
!include "x64.nsh"

!define APP_ID "com.heuresis.nomisma.windows"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Nomisma"
Name "Nomisma"
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\Nomisma"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
BrandingText "Nomisma"
Icon "${APP_ICON}"
UninstallIcon "${APP_ICON}"
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName" "Nomisma"
VIAddVersionKey /LANG=1033 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1033 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1033 "FileDescription" "Nomisma installer"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Nomisma contributors"

Var AppMutex
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\Nomisma.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Open Nomisma"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; Holding this mutex also prevents starting the app midway through an upgrade.
!macro AcquireAppMutex
  retry_mutex:
    System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\Nomisma.Desktop") p.r0 ?e'
    Pop $1
    StrCpy $AppMutex $0
    ${If} $0 == 0
      MessageBox MB_ICONSTOP "Nomisma setup could not check whether the application is running." /SD IDOK
      SetErrorLevel 2
      Abort
    ${EndIf}
    ${If} $1 == 183
      System::Call 'kernel32::CloseHandle(p r0)'
      StrCpy $AppMutex 0
      IfSilent mutex_cancel
      MessageBox MB_RETRYCANCEL|MB_ICONINFORMATION "Close Nomisma before continuing. Its monitor will stop when the app closes." IDRETRY retry_mutex
      mutex_cancel:
      SetErrorLevel 2
      Abort
    ${EndIf}
!macroend

Function .onInit
  SetShellVarContext current
  SetRegView 64
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "Nomisma requires Windows 11 on a 64-bit PC." /SD IDOK
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastBuild} 22000
    MessageBox MB_ICONSTOP "Nomisma requires Windows 11 or later." /SD IDOK
    Abort
  ${EndIf}
  ${IfNot} ${IsNativeAMD64}
    MessageBox MB_ICONSTOP "This Nomisma installer is for 64-bit Intel or AMD PCs." /SD IDOK
    Abort
  ${EndIf}
  ; Fixed per-user location; command-line /D overrides are deliberately ignored.
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\Nomisma"
  IfFileExists "$INSTDIR\*" 0 available
    IfFileExists "$INSTDIR\.nomisma-install-id" 0 occupied
    FileOpen $0 "$INSTDIR\.nomisma-install-id" r
    FileRead $0 $1
    FileClose $0
    StrCmp $1 "${APP_ID}" available occupied
    occupied:
      MessageBox MB_ICONSTOP "The Nomisma installation folder contains other files. Move that folder before installing." /SD IDOK
      SetErrorLevel 2
      Abort
  available:
  !insertmacro AcquireAppMutex
FunctionEnd

Function .onGUIEnd
  System::Call 'kernel32::CloseHandle(p $AppMutex)'
FunctionEnd

Function .onInstSuccess
  ; Release before the Finish page's optional app launch.
  System::Call 'kernel32::CloseHandle(p $AppMutex)'
  StrCpy $AppMutex 0
FunctionEnd

Section "Nomisma (required)" Core
  SectionIn RO
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\Nomisma"
  SetOutPath "$INSTDIR"
  SetOverwrite on
  File /r /x ".nomisma-install-id" "${APP_FILES}/*"
  File "${APP_FILES}/.nomisma-install-id"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Nomisma"
  CreateShortcut "$SMPROGRAMS\Nomisma\Nomisma.lnk" "$INSTDIR\Nomisma.exe"
  CreateShortcut "$SMPROGRAMS\Nomisma\Uninstall Nomisma.lnk" "$INSTDIR\Uninstall.exe"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "Nomisma"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "Nomisma contributors"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\Nomisma.exe"
  WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
  WriteRegStr HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1
  System::Call 'kernel32::CloseHandle(p $AppMutex)'
  StrCpy $AppMutex 0
SectionEnd

Section /o "Desktop shortcut" DesktopShortcut
  CreateShortcut "$DESKTOP\Nomisma.lnk" "$INSTDIR\Nomisma.exe"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${Core} "Install Nomisma, its Python and .NET runtimes, and Start menu shortcuts. Research data stays in your user profile."
  !insertmacro MUI_DESCRIPTION_TEXT ${DesktopShortcut} "Add a Nomisma shortcut to your desktop."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function un.onInit
  SetShellVarContext current
  SetRegView 64
  GetFullPathName $0 "$LOCALAPPDATA\Programs\Nomisma"
  GetFullPathName $1 "$INSTDIR"
  StrCmp $0 $1 0 unsafe_uninstall
  FileOpen $0 "$INSTDIR\.nomisma-install-id" r
  IfErrors unsafe_uninstall
  FileRead $0 $1
  FileClose $0
  StrCmp $1 "${APP_ID}" safe_uninstall
  unsafe_uninstall:
    MessageBox MB_ICONSTOP "Nomisma could not verify its installation folder. No files were removed." /SD IDOK
    SetErrorLevel 2
    Abort
  safe_uninstall:
  !insertmacro AcquireAppMutex
FunctionEnd

Function un.onGUIEnd
  System::Call 'kernel32::CloseHandle(p $AppMutex)'
FunctionEnd

Section "Uninstall"
  ; This generated list deletes only files installed by this build. User data,
  ; credentials, browser profile, and unrelated files are never removed.
  !include "${UNINSTALL_FILES}"
  Delete "$INSTDIR\.nomisma-install-id"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\Nomisma\Nomisma.lnk"
  Delete "$SMPROGRAMS\Nomisma\Uninstall Nomisma.lnk"
  RMDir "$SMPROGRAMS\Nomisma"
  Delete "$DESKTOP\Nomisma.lnk"
  DeleteRegKey HKCU "${UNINSTALL_KEY}"
SectionEnd
