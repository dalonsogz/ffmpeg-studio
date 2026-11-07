# AGENTS.md (plantilla genérica)

Plantilla para aplicaciones de escritorio en Windows (front-end de una herramienta de línea de
comandos, visor, editor, etc.). Copia este archivo a la raíz de otro proyecto como `AGENTS.md` y
elimina lo que no aplique. Son reglas cortas, basadas en fallos reales.

## Reglas de oro

- Nada se da por terminado sin ejecutarlo y comprobarlo: archivo generado, salida esperada, captura.
- Un comando que "funciona" pero no produce el efecto esperado es un fallo, no un éxito.
- Antes de repetir un intento fallido, cambia de estrategia o busca la causa.

## Entorno Windows

- **`%TEMP%` puede permitir escribir pero no ejecutar** (ACLs de sandbox o seguridad). No dependas de
  lanzar binarios copiados a Temp; en instaladores usa `_?=` o ejecuta en su sitio.
- **Si el proyecto vive fuera de `C:`**, .NET puede tratar la ruta como remota: revisa
  `loadFromRemoteSources` o la configuración del runtime y prueba el `.exe` empaquetado desde ahí.
- **Carpetas del perfil** (`Videos`, `Temp`, `Documentos`) pueden estar restringidas: prueba escritura
  real y usa una cascada de destinos (elegido → perfil → temporal propia).
- **PowerShell 5.1 corrompe UTF-8** con `Set-Content`/`Out-File`: edita textos con Python
  (`encoding="utf-8"`) o con la herramienta de edición. El CWD de .NET no sigue a `Set-Location`.
- **Lanzar GUIs o instaladores desde un agente bloquea la espera**: segundo plano y captura por PID.

## Stack

- Prueba el shell de escritorio antes de construir: WebView2/pywebview/Tauri suelen ser estables;
  Electron puede fallar por drivers o entorno (`ACCESS_VIOLATION`). Un fallo temprano ahorra días.
- No expongas objetos de ventana al puente JS (provoca cuelgues): guárdalos en un global del módulo.
- UI simple (HTML/CSS/JS) y sondeo periódico; menos dependencias, menos fallos de integración.
- Instancia única con mutex con nombre: la segunda instancia enfoca la primera y sale con 0.

## Empaquetado

- PyInstaller **onedir plano** (`--contents-directory "."`), sin UPX, con runtime hooks para DLLs
  nativas. La configuración del runtime (`.exe.config`, manifiestos) viaja junto al ejecutable.
- **Nunca ejecutes el `.exe` intermedio de `build\`**; solo el de `dist\`.
- Si `dist\` está bloqueada, compila a otra carpeta y copia con `robocopy`; no insistas en borrar o
  renombrar un directorio bloqueado.
- Instalador: **NSIS** es fiable; asegúrate de crear la carpeta de salida en el script. Desinstalador
  con `_?=` para ejecutarse en su sitio; limpia el ejecutable restante.
- Firma al final: primero la app y luego el instalador, siempre con timestamp; token/HSM o servicio
  en la nube (no hay `.pfx`).

## Procesos externos (herramientas CLI)

- Salida **atómica**: escribir en un temporal único y `os.replace` al terminar; borrar en error o
  cancelación.
- Comprobar espacio y requisitos antes de lanzar; estimar duración o tamaño.
- Progreso por stdout, cancelación por stdin/señal y **una cola secuencial**; no lances N procesos a
  la vez.
- Validar las opciones antes de construir el comando (códec/contenedor, pistas, filtros que obligan a
  recodificar).
- Detección de capacidades con una **prueba real**, no solo comprobando que el binario existe; reintento
  en modo seguro si falla.

## Pruebas

- **No fijes valores del fixture** (duración, tamaño, texto): derívalos del propio material o de la
  salida. Cambiar la muestra no debe romper las pruebas.
- Si faltan binarios o muestras: **skip**, no fallo.
- Integración real de extremo a extremo y comprobación del artefacto, no solo que el proceso termine.
- UI: capturas por ventana/PID; no hay DOM programable.

## CI

- Cachea dependencias grandes; clave versionada a mano para forzar actualización.
- Evita espejos con límite de descargas; usa releases de GitHub o CDN estable y reintentos.
- Crea las carpetas de salida en los scripts; instala herramientas con Chocolatey o winget.
- Usa actions actuales (Node 24) y publica artifacts; los binarios no se versionan.

## Flujo del agente

0. Comprueba el entorno con un script (TEMP, unidad, herramientas).
1. Lee antes de editar; cambios pequeños.
2. Tras cada bloque: pruebas y ejecución real.
3. Verifica con evidencia (archivo, captura, salida), nunca con suposiciones.
4. GUI e instaladores en segundo plano; comprueba procesos huérfanos.
5. Si algo se bloquea: busca la causa, cambia de ruta, no repitas el mismo intento.
6. Documenta comandos reproducibles y capturas.

## Anti-patrones

- Editar UTF-8 con PowerShell.
- Confiar en `%TEMP%` para ejecutables.
- Ejecutar el `.exe` de `build\`.
- Pruebas con valores absolutos del fixture.
- Descargar dependencias grandes sin caché.
- Esperar de forma síncrona a GUIs o instaladores.
- Declarar terminado sin ejecutar.

## Checklist antes de entregar

- [ ] Pruebas en verde y app lanzada desde el artefacto final.
- [ ] Instalador compilado y desinstalación probada (si aplica).
- [ ] README con requisitos, uso y limitaciones.
- [ ] Sin restos: `.tmp`, `build\`, `__pycache__`, `.spec`.
- [ ] Versión y artefactos claros.
