function Get-RomanNumeral {
    param([int]$Number)
    if ($Number -lt 1 -or $Number -gt 3999) {
        throw "Number deve estar entre 1 e 3999. Valor recebido: $Number"
    }
    $tabela = @(
        @(1000, 'M'), @(900, 'CM'), @(500, 'D'), @(400, 'CD'),
        @(100, 'C'), @(90, 'XC'), @(50, 'L'), @(40, 'XL'),
        @(10, 'X'), @(9, 'IX'), @(5, 'V'), @(4, 'IV'), @(1, 'I')
    )
    $resultado = ''
    $restante = $Number
    foreach ($par in $tabela) {
        while ($restante -ge $par[0]) {
            $resultado += $par[1]
            $restante -= $par[0]
        }
    }
    return $resultado
}
