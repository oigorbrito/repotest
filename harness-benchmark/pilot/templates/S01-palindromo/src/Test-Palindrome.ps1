function Test-Palindrome {
    param([string]$Text)
    $arr = $Text.ToCharArray()
    [array]::Reverse($arr)
    return ((-join $arr) -ceq $Text)
}
