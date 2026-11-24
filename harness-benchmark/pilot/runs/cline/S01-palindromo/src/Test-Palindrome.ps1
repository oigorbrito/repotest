function Test-Palindrome {
    param([string]$Text)
    $normalized = ($Text -replace '\s', '').ToLowerInvariant()
    $arr = $normalized.ToCharArray()
    [array]::Reverse($arr)
    return ((-join $arr) -ceq $normalized)
}
