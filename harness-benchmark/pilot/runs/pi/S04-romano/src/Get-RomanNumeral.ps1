function Get-RomanNumeral {
    param([int]$Number)

    if ($Number -lt 1 -or $Number -gt 3999) {
        throw "Number deve estar entre 1 e 3999. Valor recebido: $Number"
    }

    $valores = @(1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1)
    $simbolos = @('M', 'CM', 'D', 'CD', 'C', 'XC', 'L', 'XL', 'X', 'IX', 'V', 'IV', 'I')

    $resultado = New-Object System.Text.StringBuilder
    $restante = $Number
    for ($i = 0; $i -lt $valores.Count; $i++) {
        while ($restante -ge $valores[$i]) {
            [void]$resultado.Append($simbolos[$i])
            $restante -= $valores[$i]
        }
    }

    return $resultado.ToString()
}
