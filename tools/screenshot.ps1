param(
  [string]$Out = 'D:\test\.probe\ui.png',
  [string]$Title = 'FFmpeg Studio',
  [int]$ProcessId = 0,
  [int]$WaitSeconds = 25
)

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class FfgWin32 {
  [DllImport("user32.dll", SetLastError=true)] public static extern IntPtr FindWindow(string cls, string title);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@

[FfgWin32]::SetProcessDPIAware() | Out-Null

$hwnd = [IntPtr]::Zero
$deadline = (Get-Date).AddSeconds($WaitSeconds)
while ((Get-Date) -lt $deadline -and $hwnd -eq [IntPtr]::Zero) {
  if ($ProcessId -gt 0) {
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($proc) {
      $proc.Refresh()
      if ($proc.MainWindowHandle -ne [IntPtr]::Zero) { $hwnd = $proc.MainWindowHandle }
    }
  } else {
    $hwnd = [FfgWin32]::FindWindow($null, $Title)
  }
  if ($hwnd -eq [IntPtr]::Zero) { Start-Sleep -Milliseconds 400 }
}

if ($hwnd -eq [IntPtr]::Zero) {
  Write-Output 'WINDOW_NOT_FOUND'
  exit 1
}

[FfgWin32]::ShowWindow($hwnd, 9) | Out-Null
[FfgWin32]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 700

$rect = New-Object FfgWin32+RECT
[FfgWin32]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top

function Save-Screen {
  $bmp = New-Object System.Drawing.Bitmap $width, $height
  $graphics = [System.Drawing.Graphics]::FromImage($bmp)
  $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bmp.Size)
  $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
  $graphics.Dispose()
  $bmp.Dispose()
}

# 1) Intento con PrintWindow (captura aunque la ventana esté tapada)
$bmp = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $graphics.GetHdc()
$printed = [FfgWin32]::PrintWindow($hwnd, $hdc, 2)
$graphics.ReleaseHdc($hdc)
$graphics.Dispose()

$dark = $true
if ($printed) {
  $samples = @(
    $bmp.GetPixel([int]($width / 2), [int]($height / 2)),
    $bmp.GetPixel([int]($width / 4), [int]($height / 4)),
    $bmp.GetPixel([int]($width * 0.75), [int]($height * 0.75))
  )
  foreach ($pixel in $samples) {
    if ($pixel.R -gt 12 -or $pixel.G -gt 12 -or $pixel.B -gt 12) { $dark = $false }
  }
}

if ($printed -and -not $dark) {
  $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
  $method = 'printwindow'
} else {
  $bmp.Dispose()
  Save-Screen
  $method = 'screen'
}

Write-Output "CAPTURED $Out ${width}x${height} at $($rect.Left),$($rect.Top) method=$method"
