function Assert-NonEmpty {
    param(
        [string]$Value,
        [string]$Name
    )
    if ([string]::IsNullOrWhiteSpace($Value)) { throw "campo $Name vazio" }
}
function Set-UserName {
    param([string]$Value)
    Assert-NonEmpty -Value $Value -Name 'Nome'
    return $Value.Trim()
}
function Set-UserEmail {
    param([string]$Value)
    Assert-NonEmpty -Value $Value -Name 'Email'
    return $Value.Trim()
}
function Set-UserCity {
    param([string]$Value)
    Assert-NonEmpty -Value $Value -Name 'Cidade'
    return $Value.Trim()
}
