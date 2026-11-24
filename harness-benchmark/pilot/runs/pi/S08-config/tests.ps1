. "$PSScriptRoot\src\Read-KeyValue.ps1"
$texto = "# comentario`nnome = app`nurl=http://x.com/a?b=1#frag`n`n  porta=8080  # nao e comentario"
$h = Read-KeyValue -Text $texto
$fail = @()
if ($h['nome'] -ne 'app') { $fail += "nome -> '$($h['nome'])'" }
if ($h['url'] -ne 'http://x.com/a?b=1#frag') { $fail += "url -> '$($h['url'])'" }
if ($h['porta'] -ne '8080  # nao e comentario') { $fail += "porta -> '$($h['porta'])'" }
if ($h.Count -ne 3) { $fail += "numero de chaves: $($h.Count) (esperado 3)" }
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
