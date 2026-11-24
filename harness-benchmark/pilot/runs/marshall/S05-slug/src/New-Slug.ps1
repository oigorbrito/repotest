function New-Slug {
    param([string]$Text)
    $s = $Text.ToLowerInvariant() -replace '[^a-z0-9]+', '-'
    return $s.Trim('-')
}
