function Get-RomanNumeral {
    param([int]$Number)
    if ($Number -lt 1 -or $Number -gt 3999) { throw "fora do intervalo 1-3999" }
    $tab = @(
        @(1000,'M'), @(900,'CM'), @(500,'D'), @(400,'CD'), @(100,'C'), @(90,'XC'),
        @(50,'L'), @(40,'XL'), @(10,'X'), @(9,'IX'), @(5,'V'), @(4,'IV'), @(1,'I')
    )
    $out = ''
    foreach ($p in $tab) {
        while ($Number -ge $p[0]) { $out += $p[1]; $Number -= $p[0] }
    }
    return $out
}
