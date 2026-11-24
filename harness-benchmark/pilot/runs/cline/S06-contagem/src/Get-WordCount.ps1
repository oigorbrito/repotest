function Get-WordCount {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return 0 }
    return @([regex]::Matches($Text, '[A-Za-z0-9]+')).Count
}
