# AGENTS.md

Reglas para agentes que trabajen en este proyecto (front-end de escritorio para FFmpeg en Windows)
o en aplicaciones similares. Cada punto evita un fallo real que ya costó tiempo; no es teoría.
Para reutilizarlo en otro proyecto, cópialo en su raíz y borra las secciones que no apliquen.

## Regla de oro

- No declares nada terminado sin ejecutarlo: compila, lanza y verifica con `ffprobe`, archivo o captura.
- Un comando que "funciona" pero no genera salida es un fallo, no un éxito.

## Entorno Windows de este equipo

- **`D:` no es de fiar para .NET.** Cargar `Python.Runtime.dll` desde ahí falla con
  `Failed to resolve Python.Runtime.Loader.Initialize`. Solución: `<exe>.exe.config` con
  `<loadFromRemoteSources enabled="true"/>` junto al ejecutable (debe viajar siempre con él).
- **`%TEMP%` permite escribir pero no ejecutar** (ACL heredado `Todos:(R,W,DC)`). Nunca dependas de
  ejecutar binarios copiados a Temp. NSIS: `_?=$INSTDIR` para que el desinstalador no se copie.
- **Carpetas del perfil restringidas**: `Videos` o `Temp` pueden dar "Acceso denegado". Elige destino
  probando escritura con un archivo temporal y cae en cascada a la carpeta de salida, el perfil o una
  temp propia.
- **PowerShell 5.1 reescribe UTF-8 como Windows-1252** con `Set-Content`/`Out-File`. Nunca edites
  HTML/JS/MD con PowerShell; usa Python con `encoding="utf-8"` o la herramienta de edición.
- El CWD de .NET no sigue a `Set-Location`: usa rutas absolutas en `[System.IO.File]`.
- Los procesos GUI lanzados desde el agente bloquean la espera: lánzalos en segundo plano y captura
  con PrintWindow (`tools/screenshot.ps1`).

## Stack

- Electron dio `ACCESS_VIOLATION` al arrancar: descartado. **pywebview + WebView2** funciona.
- No expongas la ventana en `js_api` (cuelga el puente): guárdala en un global del módulo.
- UI en HTML/CSS/JS vanilla con sondeo cada ~700 ms. Menos dependencias, menos fallos.
- Instancia única con mutex con nombre: la segunda instancia enfoca la primera y sale con 0.

## Empaquetado

- PyInstaller **onedir plano** (`--contents-directory "."`), `--noupx`, runtime hook para
  pythonnet/WebView2 y `.exe.config` copiado al lado.
- Nunca ejecutes el `.exe` de `build\`: es intermedio y falla con `Failed to load Python DLL`.
- Si `dist\` está bloqueada (proceso o Explorador), compila a otra carpeta (`FFGUI_DISTPATH`) y copia
  con `robocopy`; no insistas en borrar o renombrar el directorio bloqueado.
- Instalador: **NSIS** funciona de forma fiable. Inno Setup extraído no arranca su motor en este
  entorno; si se usa, comprobar que el setup se ejecuta de verdad.
- NSIS **no crea** `installer\Output`: créala en el script antes de compilar.
- Desinstalador: `UninstallString = '"$INSTDIR\uninstall.exe" _?=$INSTDIR'` para ejecutarlo en su
  sitio; limpia el ejecutable restante con un `cmd` oculto o `/REBOOTOK`.
- Firma: `signtool` primero sobre la app y luego sobre el instalador, siempre con timestamp; hoy la
  clave va en token/HSM o Azure Trusted Signing (no hay `.pfx`).

## FFmpeg

- Salida **atómica**: escribir en `.<uuid>.ext` y `os.replace` al terminar; borrar en error o
  cancelación. Nunca escribir directamente el destino.
- Comprobar espacio antes de empezar (`shutil.disk_usage`) y estimar por bitrate/duración.
- Progreso con `-progress pipe:1`; cancelar enviando `q` por stdin; `-y` siempre.
- Dos pasadas: **mismas pistas en ambas**; si la primera omite audio, la segunda falla con -5.
- Cambiar velocidad, fps, encuadre, resolución, pistas o filtros exige recodificar: valídalo antes de
  construir el comando.
- GPU: que el códec exista no basta; haz una codificación de prueba y reintenta en CPU si falla.
- El filtro `subtitles` resuelve rutas contra el CWD: usa ruta absoluta y escapada.
- Una cola secuencial; no lances varios `ffmpeg` a la vez.

## Pruebas

- **No fijes valores del fixture** (duración, resolución, texto): derívalos con `ffprobe` o leyendo el
  archivo. Un CI con muestra de 4 s rompió pruebas que asumían 6 s.
- Si faltan binarios o muestra, **skip**, no fallo.
- Pruebas de integración reales: recorte, dos pasadas, unión, subtítulos, captura.
- Para UI, capturas con PrintWindow; no hay DOM programable.

## CI (GitHub Actions)

- Cachea binarios grandes con `actions/cache` y clave versionada a mano; sube el sufijo (`v1`→`v2`)
  para forzar actualización.
- Evita gyan.dev (503/504 por límite): usa el espejo de GitHub (BtbN) y `curl --retry`.
- NSIS vía Chocolatey; crea `installer\Output` antes de compilar.
- Usa actions recientes (v7, Node 24) para no arrastrar avisos de deprecación.
- Publica artifacts de portable e instalador; los `.exe` no se versionan.

## Flujo del agente

0. Ejecuta `tools\check-env.ps1` al empezar: detecta TEMP sin ejecución, unidad remota, FFmpeg/NSIS.
1. Lee el archivo antes de editarlo; cambios pequeños y verificables.
2. Tras cada bloque: pruebas y ejecución real de la app.
3. Verifica con evidencia (ffprobe, archivo, captura), nunca con "debería funcionar".
4. Antes de lanzar instaladores o GUIs, usa segundo plano y comprueba procesos.
5. Si algo se bloquea: busca procesos huérfanos, usa rutas alternativas y no repitas el mismo intento.
6. Documenta en README con secciones y capturas; deja los comandos reproducibles.

## Anti-patrones

- Editar UTF-8 con PowerShell.
- Confiar en `%TEMP%` para ejecutables.
- Ejecutar el `.exe` de `build\`.
- Pruebas con valores absolutos del fixture.
- Descargar dependencias grandes sin caché ni espejo.
- Esperar de forma síncrona a instaladores o ventanas.
- Declarar terminado sin ejecutar.
