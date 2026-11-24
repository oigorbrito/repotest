function Get-WordCount {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return 0 }
    return ($Text -split '\s+' | Where-Object { $_ -ne '' }).Count
}
