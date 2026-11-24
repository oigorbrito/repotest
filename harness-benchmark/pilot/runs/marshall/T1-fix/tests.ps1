. "$PSScriptRoot\src\Get-Average.ps1"
$fail = @()
if ((Get-Average -Values @(1,2,3)) -ne 2) { $fail += "media [1,2,3] esperada 2" }
if ((Get-Average -Values @()) -ne 0) { $fail += "lista vazia esperada 0" }
if ((Get-Average -Values @(5)) -ne 5) { $fail += "media [5] esperada 5" }
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
