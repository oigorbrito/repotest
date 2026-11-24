. "$PSScriptRoot\src\Test-Palindrome.ps1"
$casos = @(
  @('ana', $true), @('Ana', $true), @('arara', $true),
  @('A man a plan a canal Panama', $true), @('abc', $false), @('ab', $false)
)
$fail = @()
foreach ($c in $casos) {
  $r = [bool](Test-Palindrome -Text $c[0])
  if ($r -ne $c[1]) { $fail += "'$($c[0])' -> $r" }
}
if ($fail.Count -eq 0) { "PASS"; exit 0 }
"FAIL: " + ($fail -join "; "); exit 1
