function New-Slug {
    param([string]$Text)
    $slug = $Text.ToLowerInvariant() -creplace '[^a-z0-9]+', '-'
    return $slug.Trim('-')
}
