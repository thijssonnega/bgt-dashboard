# Eenvoudige lokale webserver voor het dashboard (geen Python nodig).
# Gebruik:  powershell -ExecutionPolicy Bypass -File serve.ps1 [-Port 8000]
param([int]$Port = 8000)

$root = (Resolve-Path (Join-Path $PSScriptRoot 'dashboard')).Path
$types = @{
  '.html' = 'text/html; charset=utf-8'; '.js' = 'application/javascript'; '.css' = 'text/css'
  '.json' = 'application/json'; '.geojson' = 'application/geo+json'; '.png' = 'image/png'
  '.svg' = 'image/svg+xml'; '.ico' = 'image/x-icon'; '.txt' = 'text/plain'
}

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
$listener.Start()
Write-Host "Dashboard draait op http://localhost:$Port  (Ctrl+C om te stoppen)"

try {
  while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    $res = $ctx.Response
    try {
      $rel = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath).TrimStart('/')
      if ($rel -eq '') { $rel = 'index.html' }
      $path = [IO.Path]::GetFullPath((Join-Path $root $rel))
      if ($path.StartsWith($root) -and (Test-Path $path -PathType Leaf)) {
        $bytes = [IO.File]::ReadAllBytes($path)
        $ext = [IO.Path]::GetExtension($path).ToLower()
        $res.ContentType = if ($types.ContainsKey($ext)) { $types[$ext] } else { 'application/octet-stream' }
        $res.ContentLength64 = $bytes.Length
        $res.OutputStream.Write($bytes, 0, $bytes.Length)
        $status = 200
      } else {
        $res.StatusCode = 404; $status = 404
      }
      Write-Host "$status $($ctx.Request.Url.AbsolutePath)"
    } catch {
      $res.StatusCode = 500
    } finally {
      $res.Close()
    }
  }
} finally {
  $listener.Stop()
}
