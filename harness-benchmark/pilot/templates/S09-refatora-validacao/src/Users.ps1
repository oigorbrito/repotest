function Set-UserName {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { throw "campo Nome vazio" }
    return $Value.Trim()
}
function Set-UserEmail {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { throw "campo Email vazio" }
    return $Value.Trim()
}
function Set-UserCity {
    param([string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { throw "campo Cidade vazio" }
    return $Value.Trim()
}
