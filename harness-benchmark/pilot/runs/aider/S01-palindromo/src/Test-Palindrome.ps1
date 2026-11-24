function Test-Palindrome {
    param([string]$Text)
    $clean = ($Text -replace '\s', '').ToLowerInvariant()
    $arr = $clean.ToCharArray()
    [array]::Reverse($arr)
    return ((-join $arr) -ceq $clean)
}
