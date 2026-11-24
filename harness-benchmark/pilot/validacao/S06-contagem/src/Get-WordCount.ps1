function Get-WordCount {
    param([string]$Text)
    return ([regex]::Matches($Text, '[A-Za-z0-9]+')).Count
}
