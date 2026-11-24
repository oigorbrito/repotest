function Test-Palindrome {
    param([string]$Text)
    $norm = ($Text -replace '\s', '').ToLowerInvariant()
    $arr = $norm.ToCharArray()
    [array]::Reverse($arr)
    return ((-join $arr) -ceq $norm)
}
