function Test-Palindrome {
    param([string]$Text)
    $s = ($Text -replace '\s', '').ToLowerInvariant()
    $arr = $s.ToCharArray()
    [array]::Reverse($arr)
    return ((-join $arr) -eq $s)
}
