; Instalador de FFmpeg Studio (NSIS 3).
; Compilar con: installer\build-installer.ps1
; Requiere que dist\FFmpegStudio esté generado con build.bat.

Unicode true

!ifndef APP_VERSION
  !define APP_VERSION "1.0.1"
!endif

!define APP_NAME "FFmpeg Studio"
!define APP_EXE "FFmpegStudio.exe"
!define APP_PUBLISHER "FFmpeg Studio"
!define APP_ID "FFmpegStudio"
!define APP_VERSION_4 "1.0.1.0"

!include "MUI2.nsh"

Name "${APP_NAME}"
OutFile "Output\FFmpegStudio-Setup-${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\FFmpeg Studio"
InstallDirRegKey HKCU "Software\${APP_ID}" "InstallDir"
RequestExecutionLevel user
BrandingText "${APP_NAME} ${APP_VERSION}"

SetCompressor /SOLID lzma
SetCompressorDictSize 64

VIProductVersion "${APP_VERSION_4}"
VIAddVersionKey /LANG=1034 "ProductName" "${APP_NAME}"
VIAddVersionKey /LANG=1034 "FileDescription" "Instalador de ${APP_NAME}"
VIAddVersionKey /LANG=1034 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1034 "ProductVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=1034 "LegalCopyright" "FFmpeg incluido bajo GPLv3"

!define MUI_ICON "..\assets\icon.ico"
!define MUI_UNICON "..\assets\icon.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir ${APP_NAME}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\docs\AVISO-FFMPEG.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Spanish"

LangString DESC_Main ${LANG_SPANISH} "Aplicación, FFmpeg y accesos del menú Inicio."
LangString DESC_Desktop ${LANG_SPANISH} "Acceso directo en el escritorio."
LangString SEC_Main ${LANG_SPANISH} "FFmpeg Studio (obligatorio)"
LangString SEC_Desktop ${LANG_SPANISH} "Acceso directo en el escritorio"

Section "$(SEC_Main)" SEC_MAIN
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "..\dist\FFmpegStudio\*.*"
  WriteUninstaller "$INSTDIR\uninstall.exe"

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\Desinstalar ${APP_NAME}.lnk" "$INSTDIR\uninstall.exe" "_?=$INSTDIR"

  WriteRegStr HKCU "Software\${APP_ID}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  ; _?=$INSTDIR evita que el desinstalador se copie a %TEMP% y se lance desde allí:
  ; en equipos donde TEMP permite escribir pero no ejecutar, esa copia falla con
  ; "Error launching installer". Ejecutándolo en su sitio funciona siempre.
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "UninstallString" '"$INSTDIR\uninstall.exe" _?=$INSTDIR'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S _?=$INSTDIR'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "NoRepair" 1
SectionEnd

Section /o "$(SEC_Desktop)" SEC_DESKTOP
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Desinstalar ${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"
  RMDir /r "$INSTDIR"

  ; Con _?= el desinstalador corre desde $INSTDIR y no puede borrarse a sí mismo.
  ; Un cmd oculto espera a que termine y limpia el ejecutable y la carpeta restante.
  Delete /REBOOTOK "$INSTDIR\uninstall.exe"
  RMDir /REBOOTOK "$INSTDIR"
  ExecShell "open" "cmd.exe" '/C ping -n 3 127.0.0.1 >NUL & del /F /Q "$INSTDIR\uninstall.exe" & rmdir "$INSTDIR"' SW_HIDE

  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"
  DeleteRegKey HKCU "Software\${APP_ID}"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_MAIN} $(DESC_Main)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP} $(DESC_Desktop)
!insertmacro MUI_FUNCTION_DESCRIPTION_END
